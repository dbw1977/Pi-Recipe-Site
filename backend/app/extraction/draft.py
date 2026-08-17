"""The normalized draft contract + conversion into a storable recipe draft.

Claude (and the URL scraper) produce an `ExtractedRecipe`; `to_recipe_input` turns it into
a `schemas.RecipeIn` with status='draft', resolving suggested tag names against the
controlled vocabulary (unknown tags are dropped — CLAUDE.md rule 7)."""
from __future__ import annotations

import json
import re
from typing import Optional

from pydantic import BaseModel, Field, ValidationError

from ..schemas import EquipmentIn, GroupIn, IngredientIn, RecipeIn, StepIn
from . import autotag


# --------------------------------------------------------------------------- #
# The JSON contract we ask Claude to return (spec §10) and that the scraper maps into.
# --------------------------------------------------------------------------- #
class ExtractedIngredient(BaseModel):
    quantity: Optional[float] = None
    unit: Optional[str] = None
    name: str
    note: Optional[str] = None
    scalable: int = 1


class ExtractedGroup(BaseModel):
    name: Optional[str] = None
    ingredients: list[ExtractedIngredient] = Field(default_factory=list)


class ExtractedEquipment(BaseModel):
    name: str
    inferred: int = 1


class ExtractedRecipe(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    source_name: Optional[str] = None
    source_handle: Optional[str] = None
    servings_base: Optional[int] = None
    servings_unit: Optional[str] = None
    total_time: Optional[int] = None
    groups: list[ExtractedGroup] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    equipment: list[ExtractedEquipment] = Field(default_factory=list)
    # Tags as {dimension: [names]} — resolved against the controlled vocabulary later.
    tags: dict[str, list[str]] = Field(default_factory=dict)


_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def parse_extracted_json(raw: str) -> ExtractedRecipe:
    """Parse Claude's response into an ExtractedRecipe.

    Tolerates accidental markdown fences and leading/trailing prose by extracting the first
    balanced JSON object. Raises ValueError if nothing parseable is found (caller retries
    once, then drops whatever parsed into the review screen — spec §10)."""
    text = _FENCE_RE.sub("", raw.strip())
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Last resort: grab the outermost {...} block.
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("No JSON object found in model output")
        data = json.loads(text[start : end + 1])
    try:
        return ExtractedRecipe.model_validate(data)
    except ValidationError as e:  # pragma: no cover - defensive
        raise ValueError(f"Extracted JSON did not match the draft schema: {e}") from e


# --------------------------------------------------------------------------- #
# Tag resolution against the controlled vocabulary
# --------------------------------------------------------------------------- #
class TagIndex:
    """Maps tag names to ids, constrained to the seeded vocabulary (CLAUDE.md rule 7)."""

    def __init__(self, rows: list[dict]):
        # rows: {id, name, category}
        self._by_cat_name: dict[tuple[str, str], int] = {}
        self._by_name: dict[str, int] = {}
        self.allowed_by_category: dict[str, list[str]] = {}
        for r in rows:
            cat, name = r["category"], r["name"]
            self._by_cat_name[(cat.lower(), name.lower())] = r["id"]
            # First occurrence wins for bare-name lookups (dimensions rarely collide).
            self._by_name.setdefault(name.lower(), r["id"])
            self.allowed_by_category.setdefault(cat, []).append(name)

    def resolve(self, suggested: dict[str, list[str]]) -> list[int]:
        ids: list[int] = []
        for category, names in (suggested or {}).items():
            for name in names or []:
                tid = self._by_cat_name.get((category.lower(), str(name).lower()))
                if tid is None:
                    tid = self._by_name.get(str(name).lower())  # tolerate wrong dimension
                if tid is not None and tid not in ids:
                    ids.append(tid)
        return ids


def to_recipe_input(
    extracted: ExtractedRecipe,
    *,
    source_type: str,
    tag_index: TagIndex,
    source_url: str | None = None,
    hero_image: str | None = None,
    status: str = "draft",
) -> RecipeIn:
    """Convert an ExtractedRecipe into a storable draft RecipeIn."""
    groups = [
        GroupIn(
            name=g.name,
            sort_order=gi,
            ingredients=[
                IngredientIn(
                    quantity=ing.quantity,
                    unit=ing.unit,
                    name=ing.name,
                    note=ing.note,
                    scalable=1 if ing.scalable else 0,
                    sort_order=ii,
                )
                for ii, ing in enumerate(g.ingredients)
                if ing.name and ing.name.strip()
            ],
        )
        for gi, g in enumerate(extracted.groups)
    ]
    steps = [StepIn(text=s.strip(), sort_order=i) for i, s in enumerate(extracted.steps) if s and s.strip()]
    equipment = [
        EquipmentIn(name=e.name.strip(), inferred=1 if e.inferred else 0, sort_order=i)
        for i, e in enumerate(extracted.equipment)
        if e.name and e.name.strip()
    ]

    # Auto-select tags from the recipe's own words so drafts arrive tagged for approval,
    # not blank. Merged with (never overriding) whatever the AI already suggested; both
    # are constrained to the controlled vocabulary by TagIndex.resolve (rule 7).
    auto_tags = autotag.suggest_tags(
        title=extracted.title,
        description=extracted.description,
        ingredient_names=[ing.name for g in extracted.groups for ing in g.ingredients if ing.name],
        steps=list(extracted.steps),
        total_time=extracted.total_time,
        allowed_by_category=tag_index.allowed_by_category,
    )
    tag_ids = tag_index.resolve(autotag.merge_tag_names(extracted.tags, auto_tags))

    return RecipeIn(
        title=(extracted.title or "Untitled import").strip(),
        description=extracted.description,
        source_type=source_type,
        source_name=extracted.source_name,
        source_url=source_url,
        source_handle=extracted.source_handle,
        hero_image=hero_image,
        servings_base=extracted.servings_base,
        servings_unit=extracted.servings_unit,
        total_time=extracted.total_time,
        status=status,
        groups=groups,
        steps=steps,
        equipment=equipment,
        tag_ids=tag_ids,
    )
