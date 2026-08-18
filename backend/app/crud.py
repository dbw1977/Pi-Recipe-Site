"""Data-access layer for recipes (plain sqlite3).

Handles the nested recipe aggregate (groups → ingredients, steps, equipment, tags)
and keeps the FTS index in sync on every write.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from .schemas import RecipeCard, RecipeIn, RecipeOut


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# FTS sync
# --------------------------------------------------------------------------- #
def _rebuild_fts(conn: sqlite3.Connection, recipe_id: int) -> None:
    """Rebuild a single recipe's FTS row from its current data.

    Called after every create/update. We DELETE the old row by rowid and INSERT a fresh
    one, concatenating ingredient names + tag names + source into the search columns
    (spec §4 / §9). Because the FTS table is self-contained (see 001_initial.sql), the
    delete needs only the rowid — no replay of previous values.
    """
    r = conn.execute(
        "SELECT title, description, source_name, source_handle, source_url "
        "FROM recipe WHERE id = ?",
        (recipe_id,),
    ).fetchone()
    if r is None:
        return

    ingredient_names = [
        row["name"]
        for row in conn.execute(
            """
            SELECT i.name FROM ingredient i
            JOIN ingredient_group g ON i.group_id = g.id
            WHERE g.recipe_id = ?
            """,
            (recipe_id,),
        )
    ]
    tag_names = [
        row["name"]
        for row in conn.execute(
            """
            SELECT t.name FROM tag t
            JOIN recipe_tag rt ON rt.tag_id = t.id
            WHERE rt.recipe_id = ?
            """,
            (recipe_id,),
        )
    ]
    source = " ".join(
        s for s in (r["source_name"], r["source_handle"], r["source_url"]) if s
    )

    conn.execute("DELETE FROM recipe_fts WHERE rowid = ?", (recipe_id,))
    conn.execute(
        """
        INSERT INTO recipe_fts(rowid, title, description, source, ingredients, tags)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            recipe_id,
            r["title"] or "",
            r["description"] or "",
            source,
            " ".join(ingredient_names),
            " ".join(tag_names),
        ),
    )


# --------------------------------------------------------------------------- #
# Write helpers
# --------------------------------------------------------------------------- #
def _insert_children(conn: sqlite3.Connection, recipe_id: int, data: RecipeIn) -> None:
    for gi, group in enumerate(data.groups):
        cur = conn.execute(
            "INSERT INTO ingredient_group(recipe_id, name, sort_order) VALUES (?, ?, ?)",
            (recipe_id, group.name, group.sort_order or gi),
        )
        group_id = cur.lastrowid
        for ii, ing in enumerate(group.ingredients):
            conn.execute(
                """
                INSERT INTO ingredient(group_id, quantity, unit, name, note, scalable, sort_order)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    group_id, ing.quantity, ing.unit, ing.name, ing.note,
                    ing.scalable, ing.sort_order or ii,
                ),
            )
    for si, step in enumerate(data.steps):
        conn.execute(
            "INSERT INTO step(recipe_id, text, sort_order) VALUES (?, ?, ?)",
            (recipe_id, step.text, step.sort_order or si),
        )
    for ei, eq in enumerate(data.equipment):
        conn.execute(
            "INSERT INTO equipment(recipe_id, name, inferred, sort_order) VALUES (?, ?, ?, ?)",
            (recipe_id, eq.name, eq.inferred, eq.sort_order or ei),
        )
    for tag_id in data.tag_ids:
        conn.execute(
            "INSERT OR IGNORE INTO recipe_tag(recipe_id, tag_id) VALUES (?, ?)",
            (recipe_id, tag_id),
        )


def _delete_children(conn: sqlite3.Connection, recipe_id: int) -> None:
    # ingredient rows cascade from their group; delete groups + the rest explicitly.
    conn.execute("DELETE FROM ingredient_group WHERE recipe_id = ?", (recipe_id,))
    conn.execute("DELETE FROM step WHERE recipe_id = ?", (recipe_id,))
    conn.execute("DELETE FROM equipment WHERE recipe_id = ?", (recipe_id,))
    conn.execute("DELETE FROM recipe_tag WHERE recipe_id = ?", (recipe_id,))


def create_recipe(conn: sqlite3.Connection, data: RecipeIn) -> int:
    now = _now()
    cur = conn.execute(
        """
        INSERT INTO recipe(
            title, description, source_type, source_name, source_url, source_handle,
            hero_image, servings_base, servings_unit, total_time, created_at, updated_at, status,
            generated, derived_from_recipe_id, generation_prompt
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data.title, data.description, data.source_type, data.source_name,
            data.source_url, data.source_handle, data.hero_image, data.servings_base,
            data.servings_unit, data.total_time, now, now, data.status,
            data.generated, data.derived_from_recipe_id, data.generation_prompt,
        ),
    )
    recipe_id = cur.lastrowid
    _insert_children(conn, recipe_id, data)
    _rebuild_fts(conn, recipe_id)
    return recipe_id


def update_recipe(conn: sqlite3.Connection, recipe_id: int, data: RecipeIn) -> bool:
    exists = conn.execute("SELECT 1 FROM recipe WHERE id = ?", (recipe_id,)).fetchone()
    if not exists:
        return False
    conn.execute(
        """
        UPDATE recipe SET
            title=?, description=?, source_type=?, source_name=?, source_url=?,
            source_handle=?, hero_image=?, servings_base=?, servings_unit=?,
            total_time=?, status=?, updated_at=?
        WHERE id=?
        """,
        (
            data.title, data.description, data.source_type, data.source_name,
            data.source_url, data.source_handle, data.hero_image, data.servings_base,
            data.servings_unit, data.total_time, data.status, _now(), recipe_id,
        ),
    )
    _delete_children(conn, recipe_id)
    _insert_children(conn, recipe_id, data)
    _rebuild_fts(conn, recipe_id)
    return True


def delete_recipe(conn: sqlite3.Connection, recipe_id: int) -> bool:
    cur = conn.execute("DELETE FROM recipe WHERE id = ?", (recipe_id,))
    conn.execute("DELETE FROM recipe_fts WHERE rowid = ?", (recipe_id,))
    return cur.rowcount > 0


def add_media(conn: sqlite3.Connection, recipe_id: int, rows: list[dict]) -> None:
    """Attach media rows {kind, path, caption} to a recipe (used by imports, Chunk B)."""
    for m in rows or []:
        conn.execute(
            "INSERT INTO media(recipe_id, kind, path, caption) VALUES (?, ?, ?, ?)",
            (recipe_id, m.get("kind"), m.get("path"), m.get("caption")),
        )


def create_draft(conn: sqlite3.Connection, data: RecipeIn, media_rows: list[dict] | None = None) -> int:
    """Persist an imported recipe as a draft (status forced to 'draft') plus its media.
    Nothing auto-publishes — the Drafts queue requires an explicit approval (rule 10)."""
    data.status = "draft"
    recipe_id = create_recipe(conn, data)
    add_media(conn, recipe_id, media_rows or [])
    return recipe_id


def set_status(conn: sqlite3.Connection, recipe_id: int, status: str) -> bool:
    cur = conn.execute(
        "UPDATE recipe SET status = ?, updated_at = ? WHERE id = ?",
        (status, _now(), recipe_id),
    )
    return cur.rowcount > 0


def set_hero(conn: sqlite3.Connection, recipe_id: int, hero_image: str) -> bool:
    cur = conn.execute(
        "UPDATE recipe SET hero_image = ?, updated_at = ? WHERE id = ?",
        (hero_image, _now(), recipe_id),
    )
    return cur.rowcount > 0


# --------------------------------------------------------------------------- #
# Read helpers
# --------------------------------------------------------------------------- #
def _tags_for(conn: sqlite3.Connection, recipe_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT t.id, t.name, c.name AS category
        FROM tag t
        JOIN recipe_tag rt ON rt.tag_id = t.id
        JOIN tag_category c ON t.category_id = c.id
        WHERE rt.recipe_id = ?
        ORDER BY c.id, t.name
        """,
        (recipe_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_recipe(conn: sqlite3.Connection, recipe_id: int) -> RecipeOut | None:
    r = conn.execute("SELECT * FROM recipe WHERE id = ?", (recipe_id,)).fetchone()
    if r is None:
        return None

    groups = []
    for g in conn.execute(
        "SELECT * FROM ingredient_group WHERE recipe_id = ? ORDER BY sort_order, id",
        (recipe_id,),
    ):
        ings = conn.execute(
            "SELECT * FROM ingredient WHERE group_id = ? ORDER BY sort_order, id",
            (g["id"],),
        ).fetchall()
        groups.append(
            {
                "id": g["id"],
                "name": g["name"],
                "sort_order": g["sort_order"] or 0,
                "ingredients": [dict(i) for i in ings],
            }
        )

    steps = [
        dict(s)
        for s in conn.execute(
            "SELECT * FROM step WHERE recipe_id = ? ORDER BY sort_order, id", (recipe_id,)
        )
    ]
    equipment = [
        dict(e)
        for e in conn.execute(
            "SELECT * FROM equipment WHERE recipe_id = ? ORDER BY sort_order, id",
            (recipe_id,),
        )
    ]
    derived_from_title = None
    if r["derived_from_recipe_id"] is not None:
        src = conn.execute(
            "SELECT title FROM recipe WHERE id = ?", (r["derived_from_recipe_id"],)
        ).fetchone()
        derived_from_title = src["title"] if src else None

    return RecipeOut(
        **dict(r),
        groups=groups,
        steps=steps,
        equipment=equipment,
        tags=_tags_for(conn, recipe_id),
        derived_from_title=derived_from_title,
    )


def _card_from_row(conn: sqlite3.Connection, row: sqlite3.Row) -> RecipeCard:
    return RecipeCard(**dict(row), tags=_tags_for(conn, row["id"]))


def get_card(conn: sqlite3.Connection, recipe_id: int) -> RecipeCard | None:
    row = conn.execute("SELECT * FROM recipe WHERE id = ?", (recipe_id,)).fetchone()
    return _card_from_row(conn, row) if row else None


def list_recipes(
    conn: sqlite3.Connection,
    query: str | None = None,
    tag_ids: list[int] | None = None,
    status: str = "published",
) -> list[RecipeCard]:
    """List recipe cards, optionally filtered by FTS search and/or tag ids (AND across tags).

    Empty query = full grid (spec §9). Search and tag filters combine.
    """
    tag_ids = tag_ids or []
    # Params are collected in the exact left-to-right order the placeholders appear in the
    # final SQL string: JOIN, then WHERE.
    join_params: list = []
    where_params: list = []
    joins = ""
    where = ["r.status = ?"]
    where_params.append(status)
    order = "r.updated_at DESC, r.id DESC"

    if query and query.strip():
        # Prefix match on each term; rank title/ingredients above notes via bm25 weights.
        fts_query = _build_fts_query(query)
        joins += " JOIN recipe_fts f ON f.rowid = r.id"
        where.append("recipe_fts MATCH ?")
        where_params.append(fts_query)
        # bm25 returns lower (more negative) = better; column order:
        # title, description, source, ingredients, tags. (Kept out of any GROUP BY —
        # tag AND-filtering below is a subquery, so bm25 stays usable in ORDER BY.)
        order = "bm25(recipe_fts, 10.0, 1.0, 3.0, 8.0, 5.0)"

    if tag_ids:
        # AND semantics: the recipe must carry *all* selected tags. Done as a subquery so
        # the outer query has no GROUP BY (SQLite forbids bm25() alongside GROUP BY).
        placeholders = ",".join("?" for _ in tag_ids)
        where.append(
            "r.id IN (SELECT recipe_id FROM recipe_tag WHERE tag_id IN "
            f"({placeholders}) GROUP BY recipe_id HAVING COUNT(DISTINCT tag_id) = ?)"
        )
        where_params.extend(tag_ids)
        where_params.append(len(tag_ids))

    sql = (
        f"SELECT r.* FROM recipe r{joins} "
        f"WHERE {' AND '.join(where)} ORDER BY {order}"
    )
    params = join_params + where_params
    rows = conn.execute(sql, params).fetchall()
    return [_card_from_row(conn, row) for row in rows]


def _build_fts_query(query: str) -> str:
    """Turn a raw search string into a safe FTS5 prefix query.

    Each whitespace-separated term becomes a quoted prefix token ("avo"* -> avocado).
    Quoting protects against FTS5 syntax characters in user input.
    """
    terms = [t for t in query.replace('"', " ").split() if t]
    return " ".join(f'"{t}"*' for t in terms)
