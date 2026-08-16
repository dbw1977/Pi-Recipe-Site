"""SQLite connection helpers.

- WAL mode (CLAUDE.md rule 2): two users may write concurrently.
- Foreign keys ON so ON DELETE CASCADE actually cascades.
- Row factory returns dict-like rows.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from . import config


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    # WAL allows a reader and a writer at the same time without blocking — important for
    # two people on phones hitting the same Pi. NORMAL sync is safe under WAL.
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def get_connection() -> sqlite3.Connection:
    """A fresh connection to the configured DB. Caller is responsible for closing."""
    return _connect(config.DB_PATH)


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """Context manager that commits on success and rolls back on error."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
