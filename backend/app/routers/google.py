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
        "drive_backup_folder": True,                       # the app makes its own folder by name
        "drive_import_ready": drive.available() and authorized,
        "drive_backup_ready": drive.client_configured() and authorized,
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
    # Accept either a bare code or the full localhost redirect URL the browser landed on. The URL
    # also carries `state`, which tells us which sign-in link the code belongs to.
    code, state = raw, None
    if "code=" in raw:
        parsed = urlparse.urlparse(raw)
        query = urlparse.parse_qs(parsed.query or raw.split("?", 1)[-1])
        code = query.get("code", [raw])[0]
        state = query.get("state", [None])[0]
    try:
        drive.finish_auth(code, config.GOOGLE_OAUTH_REDIRECT, state)
    except FeatureUnavailable as e:
        raise HTTPException(status_code=503, detail=e.message)
    except drive.AuthError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Couldn't connect to Google: {str(e)[:200]}")
    return {"authorized": True}


@router.post("/disconnect")
def disconnect() -> dict:
    return {"authorized": False, "removed": drive.disconnect()}
