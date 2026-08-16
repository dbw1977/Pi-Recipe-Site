"""Drafts queue (spec §6): review, per-row Approve / Edit / Discard, and Approve-all.

Editing a draft reuses the normal recipe editor (PUT /api/recipes/{id}); approving flips
status draft → published. Nothing here auto-publishes without an explicit call."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import crud
from ..db import get_connection, transaction
from ..extraction.duplicates import find_duplicate
from ..schemas import RecipeCard

router = APIRouter(prefix="/api/drafts", tags=["drafts"])


class DraftCard(RecipeCard):
    duplicate: dict | None = None


@router.get("", response_model=list[DraftCard])
def list_drafts():
    conn = get_connection()
    try:
        cards = crud.list_recipes(conn, status="draft")
        out: list[DraftCard] = []
        for c in cards:
            dup = find_duplicate(
                conn, title=c.title, source_url=None, exclude_id=c.id, statuses=("published",)
            )
            out.append(DraftCard(**c.model_dump(), duplicate=dup))
        return out
    finally:
        conn.close()


@router.post("/{recipe_id}/approve")
def approve_draft(recipe_id: int):
    with transaction() as conn:
        if not crud.set_status(conn, recipe_id, "published"):
            raise HTTPException(status_code=404, detail="Draft not found")
        recipe = crud.get_recipe(conn, recipe_id)
    return recipe


class ApproveAllIn(BaseModel):
    ids: list[int] | None = None  # omit = approve every draft


@router.post("/approve-all")
def approve_all(payload: ApproveAllIn):
    with transaction() as conn:
        if payload.ids:
            ids = payload.ids
        else:
            ids = [r["id"] for r in conn.execute("SELECT id FROM recipe WHERE status = 'draft'")]
        for rid in ids:
            crud.set_status(conn, rid, "published")
    return {"approved": ids, "count": len(ids)}


@router.delete("/{recipe_id}", status_code=204)
def discard_draft(recipe_id: int):
    with transaction() as conn:
        if not crud.delete_recipe(conn, recipe_id):
            raise HTTPException(status_code=404, detail="Draft not found")
    return None
