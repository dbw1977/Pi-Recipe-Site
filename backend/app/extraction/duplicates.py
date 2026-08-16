"""Light duplicate detection at import (spec §15): match on source URL or fuzzy title."""
from __future__ import annotations

import re
import sqlite3
from difflib import SequenceMatcher


def _normalize(title: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", title.lower()).strip()


def find_duplicate(
    conn: sqlite3.Connection,
    *,
    title: str,
    source_url: str | None,
    exclude_id: int | None = None,
    statuses: tuple[str, ...] = ("published", "draft"),
) -> dict | None:
    """Return {id, title, reason} of a likely duplicate, or None.

    Exact source_url match wins; otherwise a fuzzy title match (≥ 0.86 ratio). Compares
    against the given statuses (published + other drafts by default, so a bulk load doesn't
    create dupes of itself), excluding `exclude_id` so a draft never matches itself."""
    placeholders = ",".join("?" for _ in statuses)
    params: list = list(statuses)
    exclude_clause = ""
    if exclude_id is not None:
        exclude_clause = " AND id != ?"
        params_excl = params + [exclude_id]
    else:
        params_excl = params

    if source_url:
        row = conn.execute(
            f"SELECT id, title FROM recipe WHERE source_url = ? AND status IN ({placeholders})"
            f"{exclude_clause} LIMIT 1",
            [source_url, *params_excl],
        ).fetchone()
        if row:
            return {"id": row["id"], "title": row["title"], "reason": "same source URL"}

    target = _normalize(title)
    if not target:
        return None
    rows = conn.execute(
        f"SELECT id, title FROM recipe WHERE status IN ({placeholders}){exclude_clause}",
        params_excl,
    ).fetchall()
    for row in rows:
        ratio = SequenceMatcher(None, target, _normalize(row["title"] or "")).ratio()
        if ratio >= 0.86:
            return {"id": row["id"], "title": row["title"], "reason": "similar title"}
    return None
