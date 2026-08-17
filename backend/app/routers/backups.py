"""Backup status + on-demand trigger (spec §11). Scheduled runs use the CLI/systemd."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import config
from ..db import get_connection

router = APIRouter(prefix="/api/backups", tags=["backups"])


def _last(conn, kind: str) -> dict | None:
    r = conn.execute(
        "SELECT kind, target, ok, message, size_bytes, created_at "
        "FROM backup_log WHERE kind = ? ORDER BY id DESC LIMIT 1",
        (kind,),
    ).fetchone()
    return dict(r) if r else None


@router.get("/status")
def status():
    conn = get_connection()
    try:
        return {
            "local": _last(conn, "local"),
            "drive": _last(conn, "drive"),
            "drive_configured": bool(config.DRIVE_BACKUP_FOLDER_ID),
        }
    finally:
        conn.close()


class RunIn(BaseModel):
    kind: str = "local"  # 'local' | 'drive' | 'both'


@router.post("/run")
def run(payload: RunIn):
    from .. import backup  # imported lazily; pulls Google libs only for drive

    try:
        if payload.kind == "local":
            backup.run_local()
        elif payload.kind == "drive":
            backup.run_drive()
        elif payload.kind == "both":
            backup.run_local()
            backup.run_drive()
        else:
            raise HTTPException(status_code=400, detail="kind must be local|drive|both")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:300])
    return status()
