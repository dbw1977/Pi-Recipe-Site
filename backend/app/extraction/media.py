"""Save import media into the local media store; download remote images locally.

CLAUDE.md rule 3 / spec §15: on import, download remote images into the media store —
never hot-link (source pages rot). Store only the relative path in the DB.
Originals may live on the NAS in production (MEDIA_ROOT); Chunk C wires the mount.
"""
from __future__ import annotations

import mimetypes
import secrets
from datetime import datetime, timezone
from pathlib import Path

from .. import config

_EXT_BY_MIME = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif",
    "audio/mpeg": ".mp3", "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/webm": ".webm",
    "audio/ogg": ".ogg", "audio/mp4": ".m4a", "video/mp4": ".mp4", "video/quicktime": ".mov",
}


def _dated_relpath(ext: str) -> str:
    day = datetime.now(timezone.utc).strftime("%Y/%m")
    return f"{day}/{secrets.token_hex(8)}{ext}"


def save_bytes(data: bytes, *, content_type: str | None = None, filename: str | None = None) -> str:
    """Write bytes into the media store, returning the DB-relative path."""
    ext = ""
    if filename:
        ext = Path(filename).suffix.lower()
    if not ext and content_type:
        ext = _EXT_BY_MIME.get(content_type.split(";")[0].strip(), "")
    if not ext and content_type:
        ext = mimetypes.guess_extension(content_type.split(";")[0].strip()) or ""
    rel = _dated_relpath(ext or ".bin")
    dest = config.media_root() / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return rel


def download_image(url: str) -> str | None:
    """Download a remote image into the media store. Returns the relative path, or None
    on any failure (import proceeds without a hero image rather than crashing)."""
    if not url:
        return None
    try:
        import requests  # lazy

        resp = requests.get(url, timeout=20, headers={"User-Agent": "PiRecipeSite/0.2"})
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "image/jpeg")
        if "image" not in content_type:
            return None
        return save_bytes(resp.content, content_type=content_type)
    except Exception:
        return None
