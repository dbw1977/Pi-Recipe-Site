"""Recipe of the Week (spec §9).

Deterministic weekly pick keyed to the ISO week — stable all week, identical for both
users, and computed on load (no cron). `featured_history` records past picks so recent
ones aren't repeated until the library cycles. A manual "Feature this" pin overrides the
automatic pick for the current week.
"""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import date

from . import crud
from .schemas import RecipeCard


def current_iso_week(today: date | None = None) -> str:
    y, w, _ = (today or date.today()).isocalendar()
    return f"{y}-W{w:02d}"


def _published_ids(conn: sqlite3.Connection) -> list[int]:
    return [
        r["id"]
        for r in conn.execute(
            "SELECT id FROM recipe WHERE status = 'published' ORDER BY id"
        )
    ]


def _recent_auto_ids(conn: sqlite3.Connection, limit: int) -> list[int]:
    """Distinct recipe ids featured most recently (any pick), newest first."""
    seen: list[int] = []
    for r in conn.execute(
        "SELECT recipe_id FROM featured_history ORDER BY id DESC LIMIT ?", (limit * 3,)
    ):
        rid = r["recipe_id"]
        if rid not in seen:
            seen.append(rid)
        if len(seen) >= limit:
            break
    return seen


def _stable_index(iso_week: str, n: int) -> int:
    """A stable index in [0, n) derived from the week string (PYTHONHASHSEED-independent)."""
    digest = hashlib.md5(iso_week.encode()).hexdigest()
    return int(digest, 16) % n


def get_featured(conn: sqlite3.Connection, today: date | None = None) -> dict:
    """Return {"recipe": RecipeCard|None, "iso_week": str, "pinned": bool}."""
    week = current_iso_week(today)

    def card_if_published(recipe_id: int) -> RecipeCard | None:
        c = crud.get_card(conn, recipe_id)
        return c if c and c.status == "published" else None

    # 1) A manual pin for this week always wins.
    row = conn.execute(
        "SELECT recipe_id FROM featured_history WHERE iso_week = ? AND pinned = 1 "
        "ORDER BY id DESC LIMIT 1",
        (week,),
    ).fetchone()
    if row:
        card = card_if_published(row["recipe_id"])
        if card:
            return {"recipe": card.model_dump(), "iso_week": week, "pinned": True}

    # 2) Already auto-picked earlier this week? Keep it stable.
    row = conn.execute(
        "SELECT recipe_id FROM featured_history WHERE iso_week = ? AND pinned = 0 "
        "ORDER BY id DESC LIMIT 1",
        (week,),
    ).fetchone()
    if row:
        card = card_if_published(row["recipe_id"])
        if card:
            return {"recipe": card.model_dump(), "iso_week": week, "pinned": False}

    # 3) Compute a fresh deterministic pick, excluding recently featured recipes so the
    #    library cycles before anything repeats.
    published = _published_ids(conn)
    if not published:
        return {"recipe": None, "iso_week": week, "pinned": False}

    exclude = set(_recent_auto_ids(conn, max(0, len(published) - 1)))
    eligible = [i for i in published if i not in exclude] or published
    pick = eligible[_stable_index(week, len(eligible))]

    conn.execute(
        "INSERT INTO featured_history(recipe_id, iso_week, pinned) VALUES (?, ?, 0)",
        (pick, week),
    )
    conn.commit()
    card = crud.get_card(conn, pick)
    return {"recipe": card.model_dump() if card else None, "iso_week": week, "pinned": False}


def pin(conn: sqlite3.Connection, recipe_id: int, today: date | None = None) -> None:
    """Pin a recipe as this week's featured pick (manual override)."""
    week = current_iso_week(today)
    conn.execute("DELETE FROM featured_history WHERE iso_week = ? AND pinned = 1", (week,))
    conn.execute(
        "INSERT INTO featured_history(recipe_id, iso_week, pinned) VALUES (?, ?, 1)",
        (recipe_id, week),
    )


def unpin(conn: sqlite3.Connection, today: date | None = None) -> None:
    """Remove this week's manual pin, reverting to the automatic pick."""
    week = current_iso_week(today)
    conn.execute("DELETE FROM featured_history WHERE iso_week = ? AND pinned = 1", (week,))
