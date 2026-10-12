"""Backup settings (set in the admin console, stored in the DB) and the weekly schedule math.

Pure and dependency-free so the "is a backup due?" rules can be unit-tested without a clock.
"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_PREFIX = "backup."
DEFAULT_DRIVE_FOLDER_NAME = "Recipe App Backups"


class SettingsError(ValueError):
    """A setting the admin typed is not usable; the message is shown to them as-is."""


@dataclass
class BackupSettings:
    enabled: bool = False             # weekly automatic backups on/off (manual always works)
    local_enabled: bool = True        # save to a folder on the Pi / a NAS / a USB drive
    local_dir: str = ""
    drive_enabled: bool = False       # save to Google Drive
    drive_folder_name: str = DEFAULT_DRIVE_FOLDER_NAME
    drive_folder_id: str = ""         # resolved by the app; not user-editable
    include_media: bool = True        # photos too — needed to rebuild the library on a new Pi
    day: int = 6                      # 0=Monday … 6=Sunday
    hour: int = 3                     # local time, 0-23


_BOOLS = {"enabled", "local_enabled", "drive_enabled", "include_media"}
_INTS = {"day", "hour"}
USER_EDITABLE = {f.name for f in fields(BackupSettings)} - {"drive_folder_id"}


def _defaults() -> BackupSettings:
    s = BackupSettings(local_dir=str(config.BACKUP_LOCAL_DIR))
    return s


def load(conn: sqlite3.Connection) -> BackupSettings:
    """Stored values over defaults. A legacy DRIVE_BACKUP_FOLDER_ID in .env is honoured until
    the admin names a folder in the console."""
    s = _defaults()
    stored = {
        r["key"][len(_PREFIX):]: r["value"]
        for r in conn.execute("SELECT key, value FROM app_setting WHERE key LIKE 'backup.%'")
    }
    for f in fields(BackupSettings):
        if f.name not in stored:
            continue
        raw = stored[f.name]
        if f.name in _BOOLS:
            setattr(s, f.name, raw == "1")
        elif f.name in _INTS:
            try:
                setattr(s, f.name, int(raw))
            except (TypeError, ValueError):
                pass
        else:
            setattr(s, f.name, raw or "")
    if "drive_folder_name" not in stored and not s.drive_folder_id and config.DRIVE_BACKUP_FOLDER_ID:
        s.drive_folder_id = config.DRIVE_BACKUP_FOLDER_ID
    return s


def _store(conn: sqlite3.Connection, name: str, value) -> None:
    v = "1" if value is True else "0" if value is False else str(value)
    conn.execute(
        "INSERT INTO app_setting(key, value, updated_at) VALUES (?, ?, datetime('now')) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
        (_PREFIX + name, v),
    )


def save_internal(conn: sqlite3.Connection, **values) -> None:
    """Persist values the app itself resolves (e.g. the Drive folder id)."""
    for k, v in values.items():
        _store(conn, k, v)
    conn.commit()


def check_local_dir(path_str: str) -> Path:
    """The chosen folder must be absolute, creatable and writable — proven by writing to it,
    so a typo or a missing NAS mount is caught when saving, not at 3 AM on Sunday."""
    raw = (path_str or "").strip()
    if not raw:
        raise SettingsError("Enter the folder to save the backup in.")
    p = Path(raw).expanduser()
    if not p.is_absolute():
        raise SettingsError("Use a full folder path that starts with / (for example /mnt/nas/recipes-backup).")
    try:
        p.mkdir(parents=True, exist_ok=True)
        probe = p / f".write-test-{os.getpid()}"
        probe.write_bytes(b"ok")
        probe.unlink()
    except OSError as e:
        raise SettingsError(
            f"Can't write to {p} ({e.strerror or e}). Check the path, and that a NAS or USB drive is mounted."
        ) from e
    return p


def same_disk_as_db(path_str: str) -> bool:
    """True when the backup folder is on the same filesystem as the database — i.e. it would
    die with the Pi's SD card, which defeats the point of a hardware-failure backup."""
    try:
        p = Path(path_str).expanduser()
        while not p.exists() and p != p.parent:
            p = p.parent
        db_dir = config.DB_PATH.parent
        return os.stat(p).st_dev == os.stat(db_dir).st_dev
    except OSError:
        return False


def update(conn: sqlite3.Connection, patch: dict) -> BackupSettings:
    """Validate and save the fields the admin changed; returns the new settings."""
    current = load(conn)
    new = BackupSettings(**asdict(current))
    for k, v in patch.items():
        if k not in USER_EDITABLE or v is None:
            continue
        if k in _BOOLS:
            if not isinstance(v, bool):
                raise SettingsError(f"{k} must be true or false.")
            setattr(new, k, v)
        elif k in _INTS:
            if isinstance(v, bool) or not isinstance(v, int):
                raise SettingsError(f"{k} must be a whole number.")
            setattr(new, k, v)
        else:
            setattr(new, k, str(v).strip())

    if not 0 <= new.day <= 6:
        raise SettingsError("Pick a day of the week.")
    if not 0 <= new.hour <= 23:
        raise SettingsError("Pick an hour between 0 and 23.")
    if new.local_enabled:
        new.local_dir = str(check_local_dir(new.local_dir))
    if new.drive_enabled:
        if not new.drive_folder_name or len(new.drive_folder_name) > 100:
            raise SettingsError("Give the Drive folder a name (up to 100 characters).")
        if any(c in new.drive_folder_name for c in "/\\"):
            raise SettingsError("The Drive folder name can't contain / or \\.")
    if new.enabled and not (new.local_enabled or new.drive_enabled):
        raise SettingsError("Turn on at least one place to save the backup (this Pi / NAS, or Google Drive).")

    # A different folder name means "make/find that folder" — forget the old resolved id.
    if new.drive_folder_name != current.drive_folder_name:
        new.drive_folder_id = ""
        _store(conn, "drive_folder_id", "")
    for f in fields(BackupSettings):
        if f.name == "drive_folder_id":
            continue
        _store(conn, f.name, getattr(new, f.name))
    conn.commit()
    return new


# --------------------------------------------------------------------------- #
# Schedule (naive local time — the Pi's own clock)
# --------------------------------------------------------------------------- #
def last_scheduled(now: datetime, day: int, hour: int) -> datetime:
    """The most recent moment at or before `now` that falls on `day` at `hour`:00."""
    cand = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    cand -= timedelta(days=(now.weekday() - day) % 7)
    if cand > now:
        cand -= timedelta(days=7)
    return cand


def next_scheduled(now: datetime, day: int, hour: int) -> datetime:
    return last_scheduled(now, day, hour) + timedelta(days=7)


def parse_log_time(value: str | None) -> datetime | None:
    """backup_log stores UTC (`datetime('now')`); compare in the Pi's local time."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "")).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return dt.astimezone().replace(tzinfo=None)


def due_targets(
    settings: BackupSettings,
    now: datetime,
    last_ok: dict[str, datetime | None],
    last_attempt: dict[str, datetime | None],
    retry_after: timedelta = timedelta(hours=1),
) -> list[str]:
    """Which destinations should run now. A destination is due when weekly backups are on, the
    latest scheduled slot has passed, it has no success since that slot, and it wasn't tried in
    the last hour (so a broken Drive link retries hourly, not every tick). Being late is fine:
    a Pi that was off at 3 AM Sunday simply backs up when it next wakes."""
    if not settings.enabled:
        return []
    slot = last_scheduled(now, settings.day, settings.hour)
    wanted = [t for t, on in (("local", settings.local_enabled), ("drive", settings.drive_enabled)) if on]
    due = []
    for t in wanted:
        ok = last_ok.get(t)
        if ok is not None and ok >= slot:
            continue
        tried = last_attempt.get(t)
        if tried is not None and now - tried < retry_after:
            continue
        due.append(t)
    return due
