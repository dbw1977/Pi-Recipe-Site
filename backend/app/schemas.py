"""Request/response models. Ingredients are always structured (CLAUDE.md rule 5)."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Input models (create / update)
# --------------------------------------------------------------------------- #
class IngredientIn(BaseModel):
    quantity: Optional[float] = None
    unit: Optional[str] = None
    name: str
    note: Optional[str] = None
    scalable: int = 1
    sort_order: int = 0


class GroupIn(BaseModel):
    name: Optional[str] = None
    sort_order: int = 0
    ingredients: list[IngredientIn] = Field(default_factory=list)


class StepIn(BaseModel):
    text: str
    sort_order: int = 0


class EquipmentIn(BaseModel):
    name: str
    inferred: int = 0
    sort_order: int = 0


class RecipeIn(BaseModel):
    title: str
    description: Optional[str] = None
    source_type: Optional[str] = "manual"
    source_name: Optional[str] = None
    source_url: Optional[str] = None
    source_handle: Optional[str] = None
    hero_image: Optional[str] = None
    servings_base: Optional[int] = None
    servings_unit: Optional[str] = None
    total_time: Optional[int] = None
    status: str = "published"
    groups: list[GroupIn] = Field(default_factory=list)
    steps: list[StepIn] = Field(default_factory=list)
    equipment: list[EquipmentIn] = Field(default_factory=list)
    tag_ids: list[int] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Output models
# --------------------------------------------------------------------------- #
class IngredientOut(IngredientIn):
    id: int


class GroupOut(BaseModel):
    id: int
    name: Optional[str]
    sort_order: int
    ingredients: list[IngredientOut]


class StepOut(StepIn):
    id: int


class EquipmentOut(EquipmentIn):
    id: int


class TagOut(BaseModel):
    id: int
    name: str
    category: str


class RecipeOut(BaseModel):
    id: int
    title: str
    description: Optional[str]
    source_type: Optional[str]
    source_name: Optional[str]
    source_url: Optional[str]
    source_handle: Optional[str]
    hero_image: Optional[str]
    servings_base: Optional[int]
    servings_unit: Optional[str]
    total_time: Optional[int]
    status: str
    created_at: Optional[str]
    updated_at: Optional[str]
    groups: list[GroupOut]
    steps: list[StepOut]
    equipment: list[EquipmentOut]
    tags: list[TagOut]


class RecipeCard(BaseModel):
    """Compact shape for the library grid."""
    id: int
    title: str
    source_name: Optional[str]
    source_handle: Optional[str]
    hero_image: Optional[str]
    servings_base: Optional[int]
    servings_unit: Optional[str]
    total_time: Optional[int]
    status: str
    tags: list[TagOut]


class TagCategoryOut(BaseModel):
    id: int
    name: str
    tags: list[TagOut]
