"""Meal planner + grocery list endpoints (Chunk E).

Plans and entries are persisted here; the grocery list is aggregated client-side (reusing
the scaling engine) and posted to /grocery/generate, which merges it with stored state.
The AI aisle categorizer is optional and degrades to a no-op without a key (rule 8).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import crud_meals
from ..db import get_connection, transaction
from ..extraction import claude
from ..schemas import (
    EntryIn, EntryOut, EntryPatch, GroceryGenerateIn, GroceryItemOut, ManualItemIn,
    ItemPatch, MealPlanCard, MealPlanIn, MealPlanOut,
)

router = APIRouter(prefix="/api/meal-plans", tags=["meal-plans"])


@router.get("", response_model=list[MealPlanCard])
def list_plans():
    conn = get_connection()
    try:
        return crud_meals.list_plans(conn)
    finally:
        conn.close()


@router.post("", response_model=MealPlanOut, status_code=201)
def create_plan(data: MealPlanIn):
    with transaction() as conn:
        pid = crud_meals.create_plan(conn, data.start_date, data.title)
        plan = crud_meals.get_plan(conn, pid)
    return plan


@router.get("/{plan_id}", response_model=MealPlanOut)
def get_plan(plan_id: int):
    conn = get_connection()
    try:
        plan = crud_meals.get_plan(conn, plan_id)
    finally:
        conn.close()
    if plan is None:
        raise HTTPException(status_code=404, detail="Meal plan not found")
    return plan


@router.delete("/{plan_id}", status_code=204)
def delete_plan(plan_id: int):
    with transaction() as conn:
        if not crud_meals.delete_plan(conn, plan_id):
            raise HTTPException(status_code=404, detail="Meal plan not found")
    return None


# --- Entries ---------------------------------------------------------------- #
@router.post("/{plan_id}/entries", response_model=EntryOut, status_code=201)
def add_entry(plan_id: int, data: EntryIn):
    if (data.recipe_id is None) == (data.place_id is None):
        raise HTTPException(status_code=400, detail="Provide exactly one of recipe_id or place_id")
    with transaction() as conn:
        if crud_meals.get_plan(conn, plan_id) is None:
            raise HTTPException(status_code=404, detail="Meal plan not found")
        eid = crud_meals.add_entry(conn, plan_id, data)
        entry = next(e for e in crud_meals.get_plan(conn, plan_id).entries if e.id == eid)
    return entry


@router.patch("/{plan_id}/entries/{entry_id}", status_code=204)
def update_entry(plan_id: int, entry_id: int, patch: EntryPatch):
    with transaction() as conn:
        if not crud_meals.update_entry(conn, entry_id, patch):
            raise HTTPException(status_code=404, detail="Entry not found")
    return None


@router.delete("/{plan_id}/entries/{entry_id}", status_code=204)
def delete_entry(plan_id: int, entry_id: int):
    with transaction() as conn:
        if not crud_meals.delete_entry(conn, entry_id):
            raise HTTPException(status_code=404, detail="Entry not found")
    return None


# --- Grocery list ----------------------------------------------------------- #
@router.get("/{plan_id}/grocery", response_model=list[GroceryItemOut])
def get_grocery(plan_id: int):
    conn = get_connection()
    try:
        return crud_meals.list_grocery(conn, plan_id)
    finally:
        conn.close()


@router.post("/{plan_id}/grocery/generate", response_model=list[GroceryItemOut])
def generate_grocery(plan_id: int, data: GroceryGenerateIn):
    with transaction() as conn:
        if crud_meals.get_plan(conn, plan_id) is None:
            raise HTTPException(status_code=404, detail="Meal plan not found")
        return crud_meals.generate_grocery(conn, plan_id, data.items)


@router.post("/{plan_id}/grocery/items", response_model=GroceryItemOut, status_code=201)
def add_manual(plan_id: int, data: ManualItemIn):
    if not data.name.strip():
        raise HTTPException(status_code=400, detail="Item name required")
    with transaction() as conn:
        return crud_meals.add_manual_item(conn, plan_id, data)


@router.patch("/{plan_id}/grocery/items/{item_id}", status_code=204)
def patch_item(plan_id: int, item_id: int, patch: ItemPatch):
    with transaction() as conn:
        if patch.checked is not None and not crud_meals.set_checked(conn, item_id, patch.checked):
            raise HTTPException(status_code=404, detail="Item not found")
    return None


@router.delete("/{plan_id}/grocery/items/{item_id}", status_code=204)
def delete_item(plan_id: int, item_id: int):
    with transaction() as conn:
        if not crud_meals.delete_item(conn, item_id):
            raise HTTPException(status_code=404, detail="Item not found")
    return None


# --- Optional AI aisle categorization (no key -> empty map, never an error) --- #
class CategorizeIn(BaseModel):
    names: list[str]


@router.post("/grocery/categorize")
def categorize(payload: CategorizeIn) -> dict:
    """Best-effort {name: aisle} for items the built-in lookup left as 'Other'."""
    return {"available": claude.available(), "aisles": claude.categorize_aisles(payload.names)}
