"""Place CRUD + Eat Out library/search/filter + place drafts (Chunk D, spec §14).

Parallels the recipe router and reuses the same review/Drafts pattern: places land as a
draft on import and are approved to publish. Existing recipe endpoints are untouched.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from .. import config, crud_places
from ..db import get_connection, transaction
from ..extraction.duplicates import find_duplicate
from ..schemas import PlaceCard, PlaceIn, PlaceOut

router = APIRouter(prefix="/api/places", tags=["places"])


@router.get("", response_model=list[PlaceCard])
def list_places(
    q: str | None = Query(default=None),
    tags: str | None = Query(default=None, description="Comma-separated tag ids; place must have ALL"),
    city: str | None = Query(default=None, description="Exact city match"),
    status: str = Query(default="published"),
):
    tag_ids = [int(t) for t in tags.split(",") if t.strip().isdigit()] if tags else []
    conn = get_connection()
    try:
        return crud_places.list_places(conn, query=q, tag_ids=tag_ids, status=status, city=city)
    finally:
        conn.close()


@router.get("/meta")
def places_meta():
    """Home city (for defaulting new entries) + the cities you've saved so far."""
    conn = get_connection()
    try:
        return {"home_city": config.HOME_CITY or None, "cities": crud_places.list_cities(conn)}
    finally:
        conn.close()


@router.get("/cities", response_model=list[str])
def list_cities():
    """Distinct cities among published places — for the city filter and export picker."""
    conn = get_connection()
    try:
        return crud_places.list_cities(conn)
    finally:
        conn.close()


# --- Drafts (reuses the review flow; kept under /places so the queue can be per-collection) #
@router.get("/drafts", response_model=list[PlaceCard])
def list_place_drafts():
    conn = get_connection()
    try:
        return crud_places.list_places(conn, status="draft")
    finally:
        conn.close()


@router.get("/{place_id}", response_model=PlaceOut)
def get_place(place_id: int):
    conn = get_connection()
    try:
        place = crud_places.get_place(conn, place_id)
    finally:
        conn.close()
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")
    return place


@router.post("", response_model=PlaceOut, status_code=201)
def create_place(data: PlaceIn):
    with transaction() as conn:
        place_id = crud_places.create_place(conn, data)
        place = crud_places.get_place(conn, place_id)
    return place


@router.put("/{place_id}", response_model=PlaceOut)
def update_place(place_id: int, data: PlaceIn):
    with transaction() as conn:
        if not crud_places.update_place(conn, place_id, data):
            raise HTTPException(status_code=404, detail="Place not found")
        place = crud_places.get_place(conn, place_id)
    return place


@router.post("/{place_id}/approve", response_model=PlaceOut)
def approve_place(place_id: int):
    with transaction() as conn:
        if not crud_places.set_status(conn, place_id, "published"):
            raise HTTPException(status_code=404, detail="Place not found")
        place = crud_places.get_place(conn, place_id)
    return place


@router.delete("/{place_id}", status_code=204)
def delete_place(place_id: int):
    with transaction() as conn:
        if not crud_places.delete_place(conn, place_id):
            raise HTTPException(status_code=404, detail="Place not found")
    return None
