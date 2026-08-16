"""Load the controlled tag vocabulary as a TagIndex."""
from __future__ import annotations

import sqlite3

from .draft import TagIndex


def load_tag_index(conn: sqlite3.Connection) -> TagIndex:
    rows = conn.execute(
        """
        SELECT t.id, t.name, c.name AS category
        FROM tag t JOIN tag_category c ON t.category_id = c.id
        ORDER BY c.id, t.name
        """
    ).fetchall()
    return TagIndex([dict(r) for r in rows])
