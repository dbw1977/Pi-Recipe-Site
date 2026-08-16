"""Numbered-SQL migration runner, applied idempotently at startup (CLAUDE.md / spec §16).

Each file in app/migrations/NNN_*.sql is applied once, in numeric order, inside a
transaction. Applied filenames are recorded in `schema_migrations` so re-running is a
no-op. Migrations must stay non-destructive so the schema can evolve across chunks.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .db import get_connection
from .seed import seed_taxonomy

_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename   TEXT PRIMARY KEY,
            applied_at TEXT DEFAULT (datetime('now'))
        )
        """
    )


def _applied(conn: sqlite3.Connection) -> set[str]:
    _ensure_migrations_table(conn)
    return {row["filename"] for row in conn.execute("SELECT filename FROM schema_migrations")}


def run_migrations() -> None:
    """Apply any pending migrations, then (idempotently) seed the tag taxonomy."""
    conn = get_connection()
    try:
        applied = _applied(conn)
        files = sorted(p for p in _MIGRATIONS_DIR.glob("*.sql"))
        for path in files:
            if path.name in applied:
                continue
            sql = path.read_text()
            conn.executescript(sql)
            conn.execute("INSERT INTO schema_migrations(filename) VALUES (?)", (path.name,))
            conn.commit()
        # Seeding is idempotent (INSERT OR IGNORE) so it is safe to run on every startup.
        seed_taxonomy(conn)
        conn.commit()
    finally:
        conn.close()
