"""Runs the weekly backup from inside the app: wake up every ~10 minutes, ask "is a backup
due?" (see backup_settings.due_targets), and start one in the background if so. Late is fine —
a Pi that was off at the scheduled hour backs up as soon as it's running again."""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime

from . import backup, backup_settings
from .db import get_connection

CHECK_EVERY_SECONDS = 600
FIRST_CHECK_DELAY_SECONDS = 60  # let the app finish starting before doing any heavy work


def _log_times(conn, kind: str) -> tuple[datetime | None, datetime | None]:
    """(latest success, latest attempt) for a destination, in local time."""
    ok = conn.execute("SELECT MAX(created_at) FROM backup_log WHERE kind = ? AND ok = 1", (kind,)).fetchone()[0]
    any_ = conn.execute("SELECT MAX(created_at) FROM backup_log WHERE kind = ?", (kind,)).fetchone()[0]
    return backup_settings.parse_log_time(ok), backup_settings.parse_log_time(any_)


def tick(now: datetime | None = None) -> list[str]:
    """One check. Returns the destinations a backup was started for ([] if nothing was due)."""
    now = now or datetime.now()
    conn = get_connection()
    try:
        settings = backup_settings.load(conn)
        last_ok, last_try = {}, {}
        for kind in ("local", "drive"):
            last_ok[kind], last_try[kind] = _log_times(conn, kind)
    finally:
        conn.close()
    targets = backup_settings.due_targets(settings, now, last_ok, last_try)
    if targets and backup.start_background(set(targets)):
        return targets
    return []


async def scheduler_loop() -> None:
    await asyncio.sleep(FIRST_CHECK_DELAY_SECONDS)
    while True:
        try:
            await asyncio.to_thread(tick)
        except Exception as e:  # never let the loop die — try again next time
            print(f"(warning) backup schedule check failed: {e}", file=sys.stderr)
        await asyncio.sleep(CHECK_EVERY_SECONDS)
