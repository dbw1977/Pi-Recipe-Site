"""Google Drive import (spec §5c).

One-time OAuth; a manual "Scan" button (no background polling). Scans ONLY the configured
recipes folder — never a backup folder — and tracks processed file ids so re-scans skip
them. Each file becomes a draft. All Google libraries are imported lazily and the whole
path is optional: with nothing configured, `available()` is False and callers get a clear
message instead of a crash.
"""
from __future__ import annotations

import io
import json
import sqlite3
from pathlib import Path

from .. import config
from . import claude, media
from .draft import to_recipe_input
from .errors import ExtractionError, FeatureUnavailable
from .tags import load_tag_index

# readonly → scan the user's Recipes folder (import, §5c);
# drive.file → create/overwrite the app's own backup file (§11). One consent covers both.
SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.file",
]


def available() -> bool:
    """Configured enough to attempt Drive (client secrets + a target folder)."""
    return bool(config.GOOGLE_CLIENT_SECRETS and config.DRIVE_FOLDER_ID)


def _require_configured() -> None:
    if not config.GOOGLE_CLIENT_SECRETS:
        raise FeatureUnavailable(
            "Google Drive import needs OAuth client secrets. Set GOOGLE_CLIENT_SECRETS to "
            "the path of your downloaded client_secret.json.",
            needs="GOOGLE_CLIENT_SECRETS",
        )
    if not config.DRIVE_FOLDER_ID:
        raise FeatureUnavailable(
            "Set DRIVE_FOLDER_ID to the id of your Drive 'Recipes' folder.",
            needs="DRIVE_FOLDER_ID",
        )


def _lazy_imports():
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import Flow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseDownload
    except ImportError as e:  # pragma: no cover
        raise FeatureUnavailable(
            "Google libraries aren't installed. Run: pip install -r requirements.txt",
            needs="google-api-python-client",
        ) from e
    return Credentials, Flow, Request, build, MediaIoBaseDownload


def _token_path() -> Path:
    return Path(config.GOOGLE_TOKEN_PATH)


def authorized() -> bool:
    return _token_path().exists()


def _load_credentials():
    _require_configured()
    Credentials, _, Request, _, _ = _lazy_imports()
    if not _token_path().exists():
        raise FeatureUnavailable(
            "Google Drive isn't authorized yet. Open the Drive setup in the app to connect "
            "your Google account (one time).",
            needs="Drive authorization",
        )
    creds = Credentials.from_authorized_user_file(str(_token_path()), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _token_path().write_text(creds.to_json())
    return creds


# --------------------------------------------------------------------------- #
# OAuth (manual code exchange — works for a headless LAN device)
# --------------------------------------------------------------------------- #
def _make_flow(redirect_uri: str):
    _, Flow, _, _, _ = _lazy_imports()
    return Flow.from_client_secrets_file(
        config.GOOGLE_CLIENT_SECRETS, scopes=SCOPES, redirect_uri=redirect_uri
    )


def auth_url(redirect_uri: str) -> str:
    _require_configured()
    flow = _make_flow(redirect_uri)
    url, _ = flow.authorization_url(access_type="offline", prompt="consent", include_granted_scopes="true")
    return url


def finish_auth(code: str, redirect_uri: str) -> None:
    _require_configured()
    flow = _make_flow(redirect_uri)
    flow.fetch_token(code=code)
    _token_path().parent.mkdir(parents=True, exist_ok=True)
    _token_path().write_text(flow.credentials.to_json())


# --------------------------------------------------------------------------- #
# Scan
# --------------------------------------------------------------------------- #
def _download_bytes(service, file_id: str, MediaIoBaseDownload) -> bytes:
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, service.files().get_media(fileId=file_id))
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()


def _export_doc_text(service, file_id: str) -> str:
    data = service.files().export(fileId=file_id, mimeType="text/plain").execute()
    return data.decode("utf-8", errors="replace") if isinstance(data, bytes) else str(data)


def scan(conn: sqlite3.Connection, persist) -> dict:
    """Scan the configured folder; create a draft per new file. `persist(recipe, media)`
    stores a draft and returns its id. Returns a summary dict for the UI."""
    creds = _load_credentials()
    _, _, _, build, MediaIoBaseDownload = _lazy_imports()
    service = build("drive", "v3", credentials=creds, cache_discovery=False)

    processed = {r["file_id"] for r in conn.execute("SELECT file_id FROM drive_processed")}
    tag_index = load_tag_index(conn)

    q = f"'{config.DRIVE_FOLDER_ID}' in parents and trashed = false"
    resp = service.files().list(
        q=q, fields="files(id, name, mimeType)", pageSize=200
    ).execute()
    files = resp.get("files", [])

    created, skipped, errors = [], [], []
    for f in files:
        fid, name, mime = f["id"], f.get("name", "file"), f.get("mimeType", "")
        if fid in processed:
            continue
        try:
            if mime.startswith("image/"):
                if not claude.available():
                    raise FeatureUnavailable("image files need Claude vision (ANTHROPIC_API_KEY)")
                raw = _download_bytes(service, fid, MediaIoBaseDownload)
                extracted = claude.extract_from_image(raw, _vision_type(mime), tag_index.allowed_by_category)
                rel = media.save_bytes(raw, content_type=mime, filename=name)
                recipe = to_recipe_input(extracted, source_type="drive", tag_index=tag_index, hero_image=rel)
                media_rows = [{"kind": "image", "path": rel, "caption": name}]
            elif mime == "application/vnd.google-apps.document":
                if not claude.available():
                    raise FeatureUnavailable("document files need Claude (ANTHROPIC_API_KEY)")
                text = _export_doc_text(service, fid)
                extracted = claude.structure_text(text, tag_index.allowed_by_category, kind="document")
                recipe = to_recipe_input(extracted, source_type="drive", tag_index=tag_index)
                media_rows = []
            elif mime.startswith("text/"):
                if not claude.available():
                    raise FeatureUnavailable("text files need Claude (ANTHROPIC_API_KEY)")
                text = _download_bytes(service, fid, MediaIoBaseDownload).decode("utf-8", "replace")
                extracted = claude.structure_text(text, tag_index.allowed_by_category, kind="text file")
                recipe = to_recipe_input(extracted, source_type="drive", tag_index=tag_index)
                media_rows = []
            else:
                skipped.append({"name": name, "reason": f"unsupported type {mime}"})
                continue

            recipe.source_name = recipe.source_name or "Google Drive"
            recipe_id = persist(recipe, media_rows)
            conn.execute(
                "INSERT OR REPLACE INTO drive_processed(file_id, recipe_id, name, processed_at) "
                "VALUES (?, ?, ?, datetime('now'))",
                (fid, recipe_id, name),
            )
            created.append({"name": name, "recipe_id": recipe_id})
        except (ExtractionError, FeatureUnavailable) as e:
            errors.append({"name": name, "error": getattr(e, "message", str(e))})
        except Exception as e:  # keep scanning the rest of the batch
            errors.append({"name": name, "error": str(e)[:200]})

    conn.commit()
    return {"created": created, "skipped": skipped, "errors": errors, "total_seen": len(files)}


def _vision_type(mime: str) -> str:
    return mime if mime in {"image/jpeg", "image/png", "image/gif", "image/webp"} else "image/jpeg"
