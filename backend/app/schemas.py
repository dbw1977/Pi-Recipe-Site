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
    # AI-variation lineage (Chunk F). Set at creation; preserved on edit.
    generated: int = 0
    derived_from_recipe_id: Optional[int] = None
    generation_prompt: Optional[str] = None


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
    # AI-variation lineage (Chunk F)
    generated: int = 0
    derived_from_recipe_id: Optional[int] = None
    derived_from_title: Optional[str] = None
    generation_prompt: Optional[str] = None


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
    generated: int = 0


class TagCategoryOut(BaseModel):
    id: int
    name: str
    tags: list[TagOut]


# --------------------------------------------------------------------------- #
# Places (Chunk D, spec §14) — a second collection: where to eat + what to order.
# --------------------------------------------------------------------------- #
class DishIn(BaseModel):
    name: str
    note: Optional[str] = None
    must_order: int = 0
    sort_order: int = 0


class PlaceIn(BaseModel):
    name: str
    place_type: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    maps_url: Optional[str] = None
    maps_place_id: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    price_level: Optional[int] = None      # 1–4
    our_rating: Optional[int] = None       # 1–5
    our_notes: Optional[str] = None
    source_name: Optional[str] = None
    source_url: Optional[str] = None
    hero_image: Optional[str] = None
    visited: int = 1                       # 1 = been there; 0 = want to try
    status: str = "published"
    dishes: list[DishIn] = Field(default_factory=list)
    tag_ids: list[int] = Field(default_factory=list)  # Cuisine etc. (city/type/price mirror in)


class DishOut(DishIn):
    id: int


class PlaceOut(BaseModel):
    id: int
    name: str
    place_type: Optional[str]
    city: Optional[str]
    address: Optional[str]
    maps_url: Optional[str]
    maps_place_id: Optional[str]
    phone: Optional[str]
    website: Optional[str]
    price_level: Optional[int]
    our_rating: Optional[int]
    our_notes: Optional[str]
    source_name: Optional[str]
    source_url: Optional[str]
    hero_image: Optional[str]
    visited: int
    status: str
    created_at: Optional[str]
    updated_at: Optional[str]
    dishes: list[DishOut]
    tags: list[TagOut]


class PlaceCard(BaseModel):
    """Compact shape for the Eat Out grid."""
    id: int
    name: str
    place_type: Optional[str]
    city: Optional[str]
    price_level: Optional[int]
    our_rating: Optional[int]
    hero_image: Optional[str]
    visited: int
    status: str
    tags: list[TagOut]


# --------------------------------------------------------------------------- #
# Meal planner + grocery list (Chunk E)
# --------------------------------------------------------------------------- #
class EntryIn(BaseModel):
    day_index: int = 0
    meal_slot: Optional[str] = None
    recipe_id: Optional[int] = None
    place_id: Optional[int] = None
    scale: float = 1.0
    sort_order: int = 0


class EntryPatch(BaseModel):
    day_index: Optional[int] = None
    meal_slot: Optional[str] = None
    scale: Optional[float] = None
    sort_order: Optional[int] = None


class EntryOut(BaseModel):
    id: int
    day_index: int
    meal_slot: Optional[str]
    scale: float
    sort_order: Optional[int]
    kind: str                       # 'recipe' | 'place'
    recipe_id: Optional[int]
    place_id: Optional[int]
    title: str                      # resolved recipe title or place name
    hero_image: Optional[str]


class MealPlanIn(BaseModel):
    start_date: str                 # ISO date (YYYY-MM-DD)
    title: Optional[str] = None


class MealPlanCard(BaseModel):
    id: int
    start_date: str
    title: Optional[str]
    entry_count: int


class MealPlanOut(BaseModel):
    id: int
    start_date: str
    title: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]
    entries: list[EntryOut]


class GroceryLineIn(BaseModel):
    """A computed line from the client-side aggregator (deterministic core)."""
    name: str
    unit: Optional[str] = None
    display: Optional[str] = None
    base: Optional[float] = None
    family: str = "none"
    aisle: str = "Other"
    recipes: list[str] = Field(default_factory=list)


class GroceryGenerateIn(BaseModel):
    items: list[GroceryLineIn] = Field(default_factory=list)


class ManualItemIn(BaseModel):
    name: str
    unit: Optional[str] = None
    display: Optional[str] = None
    aisle: str = "Other"


class ItemPatch(BaseModel):
    checked: Optional[bool] = None


class GroceryItemOut(BaseModel):
    id: int
    name: str
    unit: Optional[str]
    display: Optional[str]
    base: Optional[float]
    family: str
    aisle: str
    checked: int
    manual: int
    recipes: list[str]
    sort_order: Optional[int]
