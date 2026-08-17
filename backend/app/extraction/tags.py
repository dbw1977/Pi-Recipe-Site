"""Load the controlled tag vocabulary as a TagIndex."""
from __future__ import annotations

import sqlite3

from .draft import TagIndex


def load_tag_index(conn: sqlite3.Connection, collection: str = "recipe") -> TagIndex:
    """Load the controlled vocabulary as a TagIndex.

    `collection` scopes which dimensions are visible so recipe and place tagging stay
    separate while Cuisine ('both') is shared:
      - 'recipe' -> recipe + both   (default; preserves existing recipe behavior)
      - 'place'  -> place + both
      - 'all'    -> everything
    Tolerates an older DB where tag_category has no `collection` column yet.
    """
    if collection == "all":
        where = ""
    elif collection == "place":
        where = "WHERE c.collection IN ('place', 'both')"
    else:
        where = "WHERE c.collection IN ('recipe', 'both')"
    try:
        rows = conn.execute(
            f"""
            SELECT t.id, t.name, c.name AS category
            FROM tag t JOIN tag_category c ON t.category_id = c.id
            {where}
            ORDER BY c.id, t.name
            """
        ).fetchall()
    except sqlite3.OperationalError:
        # No `collection` column (pre-Chunk-D DB) — fall back to all tags.
        rows = conn.execute(
            """
            SELECT t.id, t.name, c.name AS category
            FROM tag t JOIN tag_category c ON t.category_id = c.id
            ORDER BY c.id, t.name
            """
        ).fetchall()
    return TagIndex([dict(r) for r in rows])
