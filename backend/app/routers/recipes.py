"""Recipe CRUD + library/search + AI variations (Chunk F)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from .. import crud
from ..db import get_connection, transaction
from ..extraction import claude
from ..extraction.draft import to_recipe_input
from ..extraction.errors import ExtractionError, FeatureUnavailable
from ..extraction.tags import load_tag_index
from ..schemas import RecipeCard, RecipeIn, RecipeOut

router = APIRouter(prefix="/api/recipes", tags=["recipes"])


@router.get("", response_model=list[RecipeCard])
def list_recipes(
    q: str | None = Query(default=None, description="Full-text search (title, ingredients, tags, source, notes)"),
    tags: str | None = Query(default=None, description="Comma-separated tag ids; recipe must have ALL of them"),
    status: str = Query(default="published"),
):
    tag_ids = [int(t) for t in tags.split(",") if t.strip().isdigit()] if tags else []
    conn = get_connection()
    try:
        return crud.list_recipes(conn, query=q, tag_ids=tag_ids, status=status)
    finally:
        conn.close()


@router.get("/{recipe_id}", response_model=RecipeOut)
def get_recipe(recipe_id: int):
    conn = get_connection()
    try:
        recipe = crud.get_recipe(conn, recipe_id)
    finally:
        conn.close()
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe


@router.post("", response_model=RecipeOut, status_code=201)
def create_recipe(data: RecipeIn):
    with transaction() as conn:
        recipe_id = crud.create_recipe(conn, data)
        recipe = crud.get_recipe(conn, recipe_id)
    return recipe


@router.put("/{recipe_id}", response_model=RecipeOut)
def update_recipe(recipe_id: int, data: RecipeIn):
    with transaction() as conn:
        ok = crud.update_recipe(conn, recipe_id, data)
        if not ok:
            raise HTTPException(status_code=404, detail="Recipe not found")
        recipe = crud.get_recipe(conn, recipe_id)
    return recipe


@router.delete("/{recipe_id}", status_code=204)
def delete_recipe(recipe_id: int):
    with transaction() as conn:
        ok = crud.delete_recipe(conn, recipe_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return None


# --------------------------------------------------------------------------- #
# AI variations (Chunk F, spec §18) — generate a draft variation of a saved recipe.
# --------------------------------------------------------------------------- #
def _source_dict(r: RecipeOut) -> dict:
    tags: dict[str, list[str]] = {}
    for t in r.tags:
        tags.setdefault(t.category, []).append(t.name)
    return {
        "title": r.title,
        "description": r.description,
        "servings_base": r.servings_base,
        "servings_unit": r.servings_unit,
        "total_time": r.total_time,
        "groups": [
            {
                "name": g.name,
                "ingredients": [
                    {"quantity": i.quantity, "unit": i.unit, "name": i.name,
                     "note": i.note, "scalable": i.scalable}
                    for i in g.ingredients
                ],
            }
            for g in r.groups
        ],
        "steps": [s.text for s in r.steps],
        "equipment": [{"name": e.name, "inferred": e.inferred} for e in r.equipment],
        "tags": tags,
    }


class VariationIn(BaseModel):
    instruction: str


@router.post("/{recipe_id}/variations")
def create_variation(recipe_id: int, payload: VariationIn):
    """Generate a realistic variation of a saved recipe as a DRAFT (never auto-published)."""
    if not claude.available():
        raise HTTPException(
            status_code=503,
            detail="AI variations need the Anthropic key. Add ANTHROPIC_API_KEY to your .env.",
        )
    instruction = payload.instruction.strip()
    if not instruction:
        raise HTTPException(status_code=400, detail="Describe the change you want.")

    with transaction() as conn:
        source = crud.get_recipe(conn, recipe_id)
        if source is None:
            raise HTTPException(status_code=404, detail="Recipe not found")
        tag_index = load_tag_index(conn)
        try:
            extracted = claude.generate_variation(
                _source_dict(source), instruction, tag_index.allowed_by_category
            )
        except FeatureUnavailable as e:
            raise HTTPException(status_code=503, detail=e.message)
        except ExtractionError as e:
            raise HTTPException(
                status_code=502,
                detail="The AI didn't return a usable recipe — try rephrasing. " + e.message,
            )
        recipe_in = to_recipe_input(extracted, source_type="ai", tag_index=tag_index)
        # Keep base servings if the model dropped them.
        recipe_in.servings_base = recipe_in.servings_base or source.servings_base
        recipe_in.servings_unit = recipe_in.servings_unit or source.servings_unit
        recipe_in.generated = 1
        recipe_in.derived_from_recipe_id = recipe_id
        recipe_in.generation_prompt = instruction
        rid = crud.create_draft(conn, recipe_in, [])
        draft = crud.get_recipe(conn, rid)
    return {"draft": draft.model_dump(), "duplicate": None}


class HeroIn(BaseModel):
    hero_image: str


@router.post("/{recipe_id}/hero", response_model=RecipeOut)
def set_hero(recipe_id: int, payload: HeroIn):
    """Set the hero image (used by the device photo uploader, Chunk F)."""
    with transaction() as conn:
        if not crud.set_hero(conn, recipe_id, payload.hero_image):
            raise HTTPException(status_code=404, detail="Recipe not found")
        return crud.get_recipe(conn, recipe_id)
