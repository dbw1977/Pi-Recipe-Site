"""Recipe of the Week endpoints (spec §9)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import featured
from ..db import get_connection, transaction

router = APIRouter(prefix="/api/featured", tags=["featured"])


def _current() -> dict:
    conn = get_connection()
    try:
        return featured.get_featured(conn)
    finally:
        conn.close()


@router.get("")
def get_featured_endpoint():
    return _current()


@router.post("/{recipe_id}/pin")
def pin_endpoint(recipe_id: int):
    with transaction() as conn:
        if not conn.execute("SELECT 1 FROM recipe WHERE id = ?", (recipe_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Recipe not found")
        featured.pin(conn, recipe_id)
    return _current()


@router.delete("/pin")
def unpin_endpoint():
    with transaction() as conn:
        featured.unpin(conn)
    return _current()
