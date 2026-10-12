"""Backups admin: settings, status (with live progress), and Back up now (spec §11).

The weekly schedule runs inside the app (backup_scheduler); "Back up now" and the schedule
share one background runner, so the page just polls /status while a run is in flight."""
from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
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


def _local_backup(s: backup_settings.BackupSettings) -> dict | None:
    """The backup file sitting in the saved folder, if any — offered as a restore source."""
    if not s.local_dir:
        return None
    f = Path(s.local_dir).expanduser() / backup.ARCHIVE_NAME
    try:
        st = f.stat()
    except OSError:
        return None
    return {
        "modified": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(timespec="seconds"),
        "size_bytes": st.st_size,
        "dir": s.local_dir,
    }


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
        "kind": running["kind"],  # "backup" | "restore" while running
        "step": running["step"],
        "restore_result": running["restore_result"],
        "local_backup": _local_backup(s),
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


# --------------------------------------------------------------------------- #
# Restore from inside the app: stage -> check/preview -> (confirm) -> apply
# --------------------------------------------------------------------------- #
_staged_source = {"label": "file"}


def _preview(label: str | None = None) -> dict:
    """What's in the staged backup, next to what the library holds right now."""
    if label:
        _staged_source["label"] = label
    return {**backup.inspect_backup(backup.staged_file()), "source": _staged_source["label"],
            "current": backup.current_counts()}


def _refuse_if_busy() -> None:
    if backup.current()["running"]:
        raise HTTPException(status_code=409, detail="A backup or restore is running — wait for it to finish.")


@router.post("/restore/upload")
async def restore_upload(request: Request):
    """Receive a backup file as the raw request body (not multipart: a backup with photos can be
    hundreds of MB, and this streams it straight to disk). Checked before anything is replaced."""
    _refuse_if_busy()
    staging = backup.staging_dir()
    declared = int(request.headers.get("content-length") or 0)
    if declared and shutil.disk_usage(staging).free < declared * 1.1 + 50_000_000:
        raise HTTPException(status_code=507, detail=(
            f"Not enough free space on the Pi for a {declared // 1_000_000} MB upload "
            f"({shutil.disk_usage(staging).free // 1_000_000} MB free)."))
    backup.clear_staged()
    part = staging / "incoming.part"
    try:
        with open(part, "wb") as f:
            async for chunk in request.stream():
                f.write(chunk)
        os.replace(part, backup.staged_file())
        preview = await run_in_threadpool(_preview, "uploaded file")
    except backup.BackupError as e:
        backup.clear_staged()
        raise HTTPException(status_code=400, detail=str(e))
    except OSError as e:
        backup.clear_staged()
        raise HTTPException(status_code=507, detail=f"Couldn't save the upload: {e.strerror or e}")
    except Exception:
        backup.clear_staged()  # e.g. the phone dropped off wifi mid-upload
        raise
    return preview


class StageIn(BaseModel):
    source: str  # 'folder' | 'drive'


@router.post("/restore/stage")
def restore_stage(payload: StageIn):
    """Fetch the backup already saved in the chosen folder, or from Google Drive, for review."""
    _refuse_if_busy()
    conn = get_connection()
    try:
        s = backup_settings.load(conn)
    finally:
        conn.close()
    try:
        if payload.source == "folder":
            src = Path(s.local_dir).expanduser() / backup.ARCHIVE_NAME
            if not src.is_file():
                raise HTTPException(status_code=404, detail=f"No {backup.ARCHIVE_NAME} found in {s.local_dir}.")
            backup.clear_staged()
            shutil.copyfile(src, backup.staged_file())
            return _preview("saved folder")
        if payload.source == "drive":
            if not drive.authorized():
                raise HTTPException(status_code=400, detail="Connect Google first (card above), then restore from Drive.")
            backup.clear_staged()
            downloaded = backup.fetch_from_drive(backup.staging_dir())
            os.replace(downloaded, backup.staged_file())
            return _preview("Google Drive")
    except backup.BackupError as e:
        backup.clear_staged()
        raise HTTPException(status_code=400, detail=str(e))
    except OSError as e:
        backup.clear_staged()
        raise HTTPException(status_code=507, detail=f"Couldn't copy the backup: {e.strerror or e}")
    raise HTTPException(status_code=400, detail="source must be folder|drive")


@router.get("/restore/staged")
def restore_staged():
    """The backup waiting for confirmation, if any (so a page reload doesn't lose it)."""
    if not backup.staged_file().is_file():
        return None
    try:
        return _preview()
    except backup.BackupError:
        backup.clear_staged()
        return None


@router.delete("/restore/staged", status_code=204)
def restore_discard():
    _refuse_if_busy()
    backup.clear_staged()
    return None


class ApplyIn(BaseModel):
    include_media: bool = True


@router.post("/restore/apply")
def restore_apply(payload: ApplyIn):
    """Replace the library with the staged backup. Runs in the background; poll /status."""
    if not backup.staged_file().is_file():
        raise HTTPException(status_code=400, detail="Choose a backup to restore first.")
    if not backup.start_restore(backup.staged_file(), payload.include_media):
        raise HTTPException(status_code=409, detail="A backup or restore is running — wait for it to finish.")
    return _status()
