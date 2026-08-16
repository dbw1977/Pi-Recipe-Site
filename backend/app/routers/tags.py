"""Tag taxonomy endpoints (controlled vocabulary, spec §8)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db import get_connection, transaction
from ..schemas import TagCategoryOut, TagOut

router = APIRouter(prefix="/api/tags", tags=["tags"])


@router.get("", response_model=list[TagCategoryOut])
def list_tags():
    """All tags grouped by dimension, for filters and the recipe editor."""
    conn = get_connection()
    try:
        categories = conn.execute(
            "SELECT id, name FROM tag_category ORDER BY id"
        ).fetchall()
        out: list[TagCategoryOut] = []
        for c in categories:
            tags = conn.execute(
                "SELECT id, name FROM tag WHERE category_id = ? ORDER BY name",
                (c["id"],),
            ).fetchall()
            out.append(
                TagCategoryOut(
                    id=c["id"],
                    name=c["name"],
                    tags=[TagOut(id=t["id"], name=t["name"], category=c["name"]) for t in tags],
                )
            )
        return out
    finally:
        conn.close()


class NewTag(BaseModel):
    category_id: int
    name: str


@router.post("", response_model=TagOut, status_code=201)
def create_tag(payload: NewTag):
    """Add a new tag to an existing dimension by hand (spec §4: added in UI, not per-import)."""
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Tag name required")
    with transaction() as conn:
        cat = conn.execute(
            "SELECT name FROM tag_category WHERE id = ?", (payload.category_id,)
        ).fetchone()
        if cat is None:
            raise HTTPException(status_code=404, detail="Tag category not found")
        conn.execute(
            "INSERT OR IGNORE INTO tag(category_id, name) VALUES (?, ?)",
            (payload.category_id, name),
        )
        row = conn.execute(
            "SELECT id FROM tag WHERE category_id = ? AND name = ?",
            (payload.category_id, name),
        ).fetchone()
        return TagOut(id=row["id"], name=name, category=cat["name"])
