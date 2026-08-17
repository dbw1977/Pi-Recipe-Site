"""Data-access layer for places (Chunk D, spec §14).

Parallels crud.py: a place aggregate (dishes + tags + media) with its own FTS index.
The city, place type, and price level are stored as columns AND mirrored into shared tags
so the Eat Out grid filters through the same tag mechanism recipes use — and Cuisine tags
are shared outright. City tags are created on demand (the vocabulary grows as you travel).
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from .schemas import PlaceCard, PlaceIn, PlaceOut

_PRICE_TAGS = {1: "$", 2: "$$", 3: "$$$", 4: "$$$$"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# Tag mirroring — city / type / price become tags (find-or-create), so filtering
# is uniform. Cuisine (and anything else) comes through explicitly in tag_ids.
# --------------------------------------------------------------------------- #
def _ensure_tag(conn: sqlite3.Connection, category: str, name: str) -> int | None:
    name = (name or "").strip()
    if not name:
        return None
    cat = conn.execute("SELECT id FROM tag_category WHERE name = ?", (category,)).fetchone()
    if cat is None:
        return None
    conn.execute(
        "INSERT OR IGNORE INTO tag(category_id, name) VALUES (?, ?)", (cat["id"], name)
    )
    row = conn.execute(
        "SELECT id FROM tag WHERE category_id = ? AND name = ?", (cat["id"], name)
    ).fetchone()
    return row["id"] if row else None


def _effective_tag_ids(conn: sqlite3.Connection, data: PlaceIn) -> list[int]:
    ids: list[int] = list(data.tag_ids or [])
    mirrors = [
        ("City/Area", (data.city or "").strip()),
        ("Place Type", (data.place_type or "").strip().title() if data.place_type else ""),
        ("Price", _PRICE_TAGS.get(data.price_level or 0, "")),
    ]
    for category, value in mirrors:
        if value:
            tid = _ensure_tag(conn, category, value)
            if tid is not None and tid not in ids:
                ids.append(tid)
    return ids


# --------------------------------------------------------------------------- #
# FTS sync
# --------------------------------------------------------------------------- #
def _rebuild_fts(conn: sqlite3.Connection, place_id: int) -> None:
    p = conn.execute(
        "SELECT name, city, our_notes FROM place WHERE id = ?", (place_id,)
    ).fetchone()
    if p is None:
        return
    cuisine = [
        row["name"]
        for row in conn.execute(
            """
            SELECT t.name FROM tag t
            JOIN place_tag pt ON pt.tag_id = t.id
            JOIN tag_category c ON t.category_id = c.id
            WHERE pt.place_id = ? AND c.name = 'Cuisine'
            """,
            (place_id,),
        )
    ]
    dishes = [
        " ".join(x for x in (row["name"], row["note"]) if x)
        for row in conn.execute(
            "SELECT name, note FROM place_dish WHERE place_id = ?", (place_id,)
        )
    ]
    conn.execute("DELETE FROM place_fts WHERE rowid = ?", (place_id,))
    conn.execute(
        "INSERT INTO place_fts(rowid, name, city, cuisine, dishes, notes) VALUES (?, ?, ?, ?, ?, ?)",
        (
            place_id,
            p["name"] or "",
            p["city"] or "",
            " ".join(cuisine),
            " ".join(dishes),
            p["our_notes"] or "",
        ),
    )


# --------------------------------------------------------------------------- #
# Write
# --------------------------------------------------------------------------- #
def _insert_children(conn: sqlite3.Connection, place_id: int, data: PlaceIn) -> None:
    for di, dish in enumerate(data.dishes):
        if not (dish.name and dish.name.strip()):
            continue
        conn.execute(
            "INSERT INTO place_dish(place_id, name, note, must_order, sort_order) "
            "VALUES (?, ?, ?, ?, ?)",
            (place_id, dish.name.strip(), dish.note, dish.must_order, dish.sort_order or di),
        )
    for tag_id in _effective_tag_ids(conn, data):
        conn.execute(
            "INSERT OR IGNORE INTO place_tag(place_id, tag_id) VALUES (?, ?)", (place_id, tag_id)
        )


def _delete_children(conn: sqlite3.Connection, place_id: int) -> None:
    conn.execute("DELETE FROM place_dish WHERE place_id = ?", (place_id,))
    conn.execute("DELETE FROM place_tag WHERE place_id = ?", (place_id,))


_COLS = (
    "name, place_type, city, address, maps_url, maps_place_id, phone, website, "
    "price_level, our_rating, our_notes, source_name, source_url, hero_image, visited, status"
)


def _values(data: PlaceIn) -> tuple:
    return (
        data.name, data.place_type, data.city, data.address, data.maps_url, data.maps_place_id,
        data.phone, data.website, data.price_level, data.our_rating, data.our_notes,
        data.source_name, data.source_url, data.hero_image, data.visited, data.status,
    )


def create_place(conn: sqlite3.Connection, data: PlaceIn) -> int:
    now = _now()
    placeholders = ", ".join("?" for _ in range(16))
    cur = conn.execute(
        f"INSERT INTO place({_COLS}, created_at, updated_at) VALUES ({placeholders}, ?, ?)",
        (*_values(data), now, now),
    )
    place_id = cur.lastrowid
    _insert_children(conn, place_id, data)
    _rebuild_fts(conn, place_id)
    return place_id


def update_place(conn: sqlite3.Connection, place_id: int, data: PlaceIn) -> bool:
    if not conn.execute("SELECT 1 FROM place WHERE id = ?", (place_id,)).fetchone():
        return False
    assignments = ", ".join(f"{c.strip()}=?" for c in _COLS.split(","))
    conn.execute(
        f"UPDATE place SET {assignments}, updated_at=? WHERE id=?",
        (*_values(data), _now(), place_id),
    )
    _delete_children(conn, place_id)
    _insert_children(conn, place_id, data)
    _rebuild_fts(conn, place_id)
    return True


def delete_place(conn: sqlite3.Connection, place_id: int) -> bool:
    # place_dish / place_tag / media cascade via FK; FTS + place row removed explicitly.
    conn.execute("DELETE FROM place_dish WHERE place_id = ?", (place_id,))
    conn.execute("DELETE FROM place_tag WHERE place_id = ?", (place_id,))
    conn.execute("DELETE FROM media WHERE place_id = ?", (place_id,))
    cur = conn.execute("DELETE FROM place WHERE id = ?", (place_id,))
    conn.execute("DELETE FROM place_fts WHERE rowid = ?", (place_id,))
    return cur.rowcount > 0


def add_media(conn: sqlite3.Connection, place_id: int, rows: list[dict]) -> None:
    for m in rows or []:
        conn.execute(
            "INSERT INTO media(place_id, kind, path, caption) VALUES (?, ?, ?, ?)",
            (place_id, m.get("kind"), m.get("path"), m.get("caption")),
        )


def create_draft(conn: sqlite3.Connection, data: PlaceIn, media_rows: list[dict] | None = None) -> int:
    data.status = "draft"
    place_id = create_place(conn, data)
    add_media(conn, place_id, media_rows or [])
    return place_id


def set_status(conn: sqlite3.Connection, place_id: int, status: str) -> bool:
    cur = conn.execute(
        "UPDATE place SET status = ?, updated_at = ? WHERE id = ?", (status, _now(), place_id)
    )
    return cur.rowcount > 0


# --------------------------------------------------------------------------- #
# Read
# --------------------------------------------------------------------------- #
def _tags_for(conn: sqlite3.Connection, place_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT t.id, t.name, c.name AS category
        FROM tag t
        JOIN place_tag pt ON pt.tag_id = t.id
        JOIN tag_category c ON t.category_id = c.id
        WHERE pt.place_id = ?
        ORDER BY c.id, t.name
        """,
        (place_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_place(conn: sqlite3.Connection, place_id: int) -> PlaceOut | None:
    p = conn.execute("SELECT * FROM place WHERE id = ?", (place_id,)).fetchone()
    if p is None:
        return None
    dishes = [
        dict(d)
        for d in conn.execute(
            "SELECT * FROM place_dish WHERE place_id = ? ORDER BY must_order DESC, sort_order, id",
            (place_id,),
        )
    ]
    return PlaceOut(**dict(p), dishes=dishes, tags=_tags_for(conn, place_id))


def _card_from_row(conn: sqlite3.Connection, row: sqlite3.Row) -> PlaceCard:
    return PlaceCard(**dict(row), tags=_tags_for(conn, row["id"]))


def get_card(conn: sqlite3.Connection, place_id: int) -> PlaceCard | None:
    row = conn.execute(
        "SELECT id, name, place_type, city, price_level, our_rating, hero_image, visited, status "
        "FROM place WHERE id = ?",
        (place_id,),
    ).fetchone()
    return _card_from_row(conn, row) if row else None


def list_cities(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT city FROM place WHERE city IS NOT NULL AND city != '' "
        "AND status = 'published' ORDER BY city"
    ).fetchall()
    return [r["city"] for r in rows]


def list_places(
    conn: sqlite3.Connection,
    query: str | None = None,
    tag_ids: list[int] | None = None,
    status: str = "published",
    city: str | None = None,
) -> list[PlaceCard]:
    """List place cards, filtered by FTS search, tag ids (AND), and/or an exact city."""
    tag_ids = tag_ids or []
    where = ["p.status = ?"]
    params: list = [status]
    joins = ""
    order = "p.updated_at DESC, p.id DESC"

    if query and query.strip():
        joins += " JOIN place_fts f ON f.rowid = p.id"
        where.append("place_fts MATCH ?")
        params.append(_build_fts_query(query))
        order = "bm25(place_fts, 10.0, 6.0, 4.0, 6.0, 2.0)"

    if city:
        where.append("p.city = ?")
        params.append(city)

    if tag_ids:
        placeholders = ",".join("?" for _ in tag_ids)
        where.append(
            "p.id IN (SELECT place_id FROM place_tag WHERE tag_id IN "
            f"({placeholders}) GROUP BY place_id HAVING COUNT(DISTINCT tag_id) = ?)"
        )
        params.extend(tag_ids)
        params.append(len(tag_ids))

    sql = f"SELECT p.* FROM place p{joins} WHERE {' AND '.join(where)} ORDER BY {order}"
    rows = conn.execute(sql, params).fetchall()
    return [_card_from_row(conn, row) for row in rows]


def _build_fts_query(query: str) -> str:
    terms = [t for t in query.replace('"', " ").split() if t]
    return " ".join(f'"{t}"*' for t in terms)
