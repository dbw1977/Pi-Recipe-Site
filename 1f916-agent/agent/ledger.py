"""Local SQLite ledger of everything the agent observes and does.

Two jobs: (1) enforce daily budgets by counting successful write actions in the
current UTC day, and (2) provide the raw material for the daily report. The DB
lives on local disk with WAL enabled — the same rules the recipe app follows
(never on a network filesystem; WAL for concurrent access).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

WRITE_KINDS = {"post", "comment", "vote"}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _day_bounds_utc(day: datetime | None = None) -> tuple[str, str]:
    day = (day or datetime.now(timezone.utc)).astimezone(timezone.utc)
    start = day.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(hour=23, minute=59, second=59, microsecond=999999)
    return start.isoformat(), end.isoformat()


class Ledger:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL;")   # two writers safe
        self.conn.execute("PRAGMA foreign_keys=ON;")
        self._migrate()

    def _migrate(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at  TEXT NOT NULL,
                finished_at TEXT,
                status      TEXT NOT NULL DEFAULT 'running',
                notes       TEXT
            );
            CREATE TABLE IF NOT EXISTS actions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id      INTEGER REFERENCES runs(id),
                ts          TEXT NOT NULL,
                kind        TEXT NOT NULL,      -- post|comment|vote|register|tag|...
                target_type TEXT,               -- post|comment
                target_id   INTEGER,
                summary     TEXT,               -- short human description
                payload     TEXT,               -- JSON of what we sent
                result      TEXT,               -- JSON of what we got back
                success     INTEGER NOT NULL DEFAULT 0,
                error       TEXT
            );
            CREATE TABLE IF NOT EXISTS observations (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id  INTEGER REFERENCES runs(id),
                ts      TEXT NOT NULL,
                kind    TEXT NOT NULL,           -- feed|inbox|stats|identity|error
                data    TEXT                     -- JSON
            );
            CREATE INDEX IF NOT EXISTS idx_actions_ts ON actions(ts);
            CREATE INDEX IF NOT EXISTS idx_actions_kind ON actions(kind);
            CREATE INDEX IF NOT EXISTS idx_obs_ts ON observations(ts);
            """
        )
        self.conn.commit()

    # -- runs --------------------------------------------------------------
    def start_run(self) -> int:
        cur = self.conn.execute(
            "INSERT INTO runs (started_at, status) VALUES (?, 'running')", (_utcnow(),)
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def finish_run(self, run_id: int, status: str = "ok", notes: str | None = None) -> None:
        self.conn.execute(
            "UPDATE runs SET finished_at=?, status=?, notes=? WHERE id=?",
            (_utcnow(), status, notes, run_id),
        )
        self.conn.commit()

    # -- actions -----------------------------------------------------------
    def record_action(
        self,
        run_id: int,
        kind: str,
        *,
        target_type: str | None = None,
        target_id: int | None = None,
        summary: str | None = None,
        payload: Any = None,
        result: Any = None,
        success: bool = True,
        error: str | None = None,
    ) -> int:
        cur = self.conn.execute(
            """INSERT INTO actions
               (run_id, ts, kind, target_type, target_id, summary, payload, result, success, error)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                run_id,
                _utcnow(),
                kind,
                target_type,
                target_id,
                summary,
                json.dumps(payload, default=str) if payload is not None else None,
                json.dumps(result, default=str) if result is not None else None,
                1 if success else 0,
                error,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def record_observation(self, run_id: int, kind: str, data: Any) -> None:
        self.conn.execute(
            "INSERT INTO observations (run_id, ts, kind, data) VALUES (?,?,?,?)",
            (run_id, _utcnow(), kind, json.dumps(data, default=str)),
        )
        self.conn.commit()

    # -- budgets & reporting ----------------------------------------------
    def count_today(self, kind: str, day: datetime | None = None) -> int:
        """Successful actions of `kind` in the given UTC day."""
        start, end = _day_bounds_utc(day)
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM actions WHERE kind=? AND success=1 AND ts BETWEEN ? AND ?",
            (kind, start, end),
        ).fetchone()
        return int(row["n"])

    def already_acted(self, kind: str, target_type: str, target_id: int) -> bool:
        """True if we already did this exact write (e.g. voted this post)."""
        row = self.conn.execute(
            """SELECT 1 FROM actions
               WHERE kind=? AND target_type=? AND target_id=? AND success=1 LIMIT 1""",
            (kind, target_type, target_id),
        ).fetchone()
        return row is not None

    def recent_post_titles(self, limit: int = 20) -> list[str]:
        rows = self.conn.execute(
            "SELECT summary FROM actions WHERE kind='post' AND success=1 ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [r["summary"] for r in rows if r["summary"]]

    def actions_since(self, since_iso: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM actions WHERE ts >= ? ORDER BY id ASC", (since_iso,)
        ).fetchall()
        return [dict(r) for r in rows]

    def observations_since(self, since_iso: str, kinds: Iterable[str] | None = None) -> list[dict[str, Any]]:
        if kinds:
            placeholders = ",".join("?" for _ in kinds)
            rows = self.conn.execute(
                f"SELECT * FROM observations WHERE ts >= ? AND kind IN ({placeholders}) ORDER BY id ASC",
                (since_iso, *kinds),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM observations WHERE ts >= ? ORDER BY id ASC", (since_iso,)
            ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        try:
            self.conn.close()
        except sqlite3.Error:
            pass
