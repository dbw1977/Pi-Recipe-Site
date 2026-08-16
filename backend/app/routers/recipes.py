"""Recipe CRUD + library/search endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from .. import crud
from ..db import get_connection, transaction
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
