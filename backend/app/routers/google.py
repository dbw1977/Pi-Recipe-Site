"""Google account connection (OAuth) — powers Drive import AND the weekly Drive backup.

The Pi is a headless LAN device, and Google only allows https or http://localhost OAuth
redirects — never http://recipes.local — so this uses the copy-paste code flow: the user
opens the consent URL, approves, and pastes back the code (or the whole redirected
localhost URL) from their browser's address bar. One consent covers import + backup.
"""
from __future__ import annotations

import urllib.parse as urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import config
from ..extraction import drive
from ..extraction.errors import FeatureUnavailable

router = APIRouter(prefix="/api/google", tags=["google"])


@router.get("/status")
def status() -> dict:
    authorized = drive.authorized()
    return {
        "configured": drive.client_configured(),          # client_secret.json present
        "authorized": authorized,                          # a Google account is connected
        "drive_import_folder": bool(config.DRIVE_FOLDER_ID),
        "drive_backup_folder": bool(config.DRIVE_BACKUP_FOLDER_ID),
        "drive_import_ready": drive.available() and authorized,
        "drive_backup_ready": bool(config.DRIVE_BACKUP_FOLDER_ID) and authorized,
    }


@router.get("/auth-url")
def auth_url() -> dict:
    try:
        return {
            "url": drive.auth_url(config.GOOGLE_OAUTH_REDIRECT),
            "redirect_uri": config.GOOGLE_OAUTH_REDIRECT,
        }
    except FeatureUnavailable as e:
        raise HTTPException(status_code=503, detail=e.message)


class ConnectIn(BaseModel):
    code: str


@router.post("/connect")
def connect(payload: ConnectIn) -> dict:
    raw = payload.code.strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Paste the code (or the whole redirected URL).")
    # Accept either a bare code or the full localhost redirect URL the browser landed on.
    code = raw
    if "code=" in raw:
        parsed = urlparse.urlparse(raw)
        query = parsed.query or raw.split("?", 1)[-1]
        code = urlparse.parse_qs(query).get("code", [raw])[0]
    try:
        drive.finish_auth(code, config.GOOGLE_OAUTH_REDIRECT)
    except FeatureUnavailable as e:
        raise HTTPException(status_code=503, detail=e.message)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail="Couldn't connect with that code (it may be expired — try again). " + str(e)[:200],
        )
    return {"authorized": True}


@router.post("/disconnect")
def disconnect() -> dict:
    return {"authorized": False, "removed": drive.disconnect()}
