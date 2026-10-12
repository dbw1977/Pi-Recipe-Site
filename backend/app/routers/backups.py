"""Backups admin: settings, status (with live progress), and Back up now (spec §11).

The weekly schedule runs inside the app (backup_scheduler); "Back up now" and the schedule
share one background runner, so the page just polls /status while a run is in flight."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import backup, backup_settings, config
from ..db import get_connection
from ..extraction import drive

router = APIRouter(prefix="/api/backups", tags=["backups"])

_estimate_cache: dict = {"at": 0.0, "key": None, "value": None}


def _last(conn, kind: str) -> dict | None:
    r = conn.execute(
        "SELECT kind, target, ok, message, size_bytes, created_at "
        "FROM backup_log WHERE kind = ? ORDER BY id DESC LIMIT 1",
        (kind,),
    ).fetchone()
    return dict(r) if r else None


def _media_estimate(settings: backup_settings.BackupSettings) -> dict:
    """Photo count/size for the "include photos (≈ N MB)" hint. Cached a minute — walking a NAS
    on every status poll would be wasteful."""
    import time

    key = settings.local_dir
    if _estimate_cache["key"] == key and time.time() - _estimate_cache["at"] < 60:
        return _estimate_cache["value"]
    value = backup.media_estimate(backup._exclude_dirs(settings))
    _estimate_cache.update(at=time.time(), key=key, value=value)
    return value


def _status() -> dict:
    conn = get_connection()
    try:
        s = backup_settings.load(conn)
        local, drive_last = _last(conn, "local"), _last(conn, "drive")
    finally:
        conn.close()
    running = backup.current()
    return {
        "settings": {
            "enabled": s.enabled,
            "local_enabled": s.local_enabled,
            "local_dir": s.local_dir,
            "drive_enabled": s.drive_enabled,
            "drive_folder_name": s.drive_folder_name,
            "include_media": s.include_media,
            "day": s.day,
            "hour": s.hour,
        },
        "day_names": backup_settings.DAY_NAMES,
        "local": local,
        "drive": drive_last,
        "running": running["running"],
        "step": running["step"],
        "next_run": (
            backup_settings.next_scheduled(datetime.now(), s.day, s.hour).isoformat(timespec="minutes")
            if s.enabled and (s.local_enabled or s.drive_enabled) else None
        ),
        "media": None if running["running"] else _media_estimate(s),
        "local_same_disk": s.local_enabled and backup_settings.same_disk_as_db(s.local_dir),
        "google": {"configured": drive.client_configured(), "authorized": drive.authorized()},
        # Kept for older clients:
        "drive_configured": s.drive_enabled,
    }


@router.get("/status")
def status():
    return _status()


class SettingsIn(BaseModel):
    enabled: Optional[bool] = None
    local_enabled: Optional[bool] = None
    local_dir: Optional[str] = None
    drive_enabled: Optional[bool] = None
    drive_folder_name: Optional[str] = None
    include_media: Optional[bool] = None
    day: Optional[int] = None
    hour: Optional[int] = None


@router.put("/settings")
def save_settings(payload: SettingsIn):
    conn = get_connection()
    try:
        try:
            backup_settings.update(conn, payload.model_dump(exclude_none=True))
        except backup_settings.SettingsError as e:
            raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()
    _estimate_cache["key"] = None
    return _status()


class RunIn(BaseModel):
    kind: str = "enabled"  # 'enabled' (what's switched on in settings) | 'local' | 'drive' | 'both'


@router.post("/run")
def run(payload: RunIn):
    """Start a backup now. Returns straight away; poll /status for progress."""
    conn = get_connection()
    try:
        s = backup_settings.load(conn)
    finally:
        conn.close()

    if payload.kind == "enabled":
        targets = {t for t, on in (("local", s.local_enabled), ("drive", s.drive_enabled)) if on}
    elif payload.kind == "both":
        targets = {"local", "drive"}
    elif payload.kind in ("local", "drive"):
        targets = {payload.kind}
    else:
        raise HTTPException(status_code=400, detail="kind must be enabled|local|drive|both")
    if not targets:
        raise HTTPException(status_code=400, detail="Choose where to save the backup first (this Pi / NAS, or Google Drive).")
    if "drive" in targets and not drive.authorized():
        raise HTTPException(status_code=400, detail="Connect Google first (card above), then back up to Drive.")

    if not backup.start_background(targets):
        raise HTTPException(status_code=409, detail="A backup is already running.")
    return _status()
