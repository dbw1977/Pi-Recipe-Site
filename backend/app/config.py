"""Configuration via environment / .env (never hardcoded — CLAUDE.md rule 4)."""
from __future__ import annotations

import os
from pathlib import Path

# Load .env if present (optional dependency-free loader).
def _load_dotenv() -> None:
    # Look for .env at the repo root (two levels up from this file: backend/app/ -> repo/).
    for candidate in (Path.cwd() / ".env", Path(__file__).resolve().parents[2] / ".env"):
        if candidate.is_file():
            for raw in candidate.read_text().splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                os.environ.setdefault(key, value)
            return


_load_dotenv()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]

# GOLDEN RULE #1: the SQLite DB lives on LOCAL DISK ONLY — never on a NAS/NFS/SMB mount.
# Default to a local ./data/recipes.db relative to the backend package.
DB_PATH = Path(
    os.environ.get("RECIPE_DB_PATH", str(_REPO_ROOT / "backend" / "data" / "recipes.db"))
).expanduser()

# Media root: originals may live on the NAS (spec §2). Only used from Chunk C onward,
# but wired here so the path is configurable from day one. Store RELATIVE paths in the DB.
MEDIA_ROOT = Path(
    os.environ.get("MEDIA_ROOT", str(_REPO_ROOT / "backend" / "media"))
).expanduser()

# Where the built React app lives (Vite build output). Served as static files by FastAPI.
FRONTEND_DIST = Path(
    os.environ.get("FRONTEND_DIST", str(_REPO_ROOT / "frontend" / "dist"))
).expanduser()

# Home city default for Places (Chunk D). Harmless to define now.
HOME_CITY = os.environ.get("HOME_CITY", "")

# Server bind (LAN-only, plain HTTP — CLAUDE.md rule 9).
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))

# ---------------------------------------------------------------------------
# Chunk B — imports. Every credential is optional: a missing one disables ONLY
# its feature, with a clear message (CLAUDE.md rule 8; chunk-B prompt). Nothing
# here is required for the manual app to run.
# ---------------------------------------------------------------------------
# Anthropic (Claude) — screenshot/vision, text structuring, tagging, equipment inference.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
# Default workhorse + fallback for messy/low-confidence extractions (spec §10).
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001").strip()
ANTHROPIC_FALLBACK_MODEL = os.environ.get("ANTHROPIC_FALLBACK_MODEL", "claude-sonnet-5").strip()

# whisper.cpp (local voice transcription) — configurable binary + model path (spec §5d).
WHISPER_BIN = os.environ.get("WHISPER_BIN", "").strip()
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "").strip()

# Google Drive import (spec §5c) — OAuth client secret + stored token + target folder.
GOOGLE_CLIENT_SECRETS = os.environ.get("GOOGLE_CLIENT_SECRETS", "").strip()
GOOGLE_TOKEN_PATH = os.environ.get(
    "GOOGLE_TOKEN_PATH", str(_REPO_ROOT / "backend" / "data" / "google_token.json")
).strip()
DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID", "").strip()


def media_root() -> Path:
    """Media root, created on demand. Originals may live on the NAS in production."""
    MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
    return MEDIA_ROOT


# ---------------------------------------------------------------------------
# Chunk C — polish + backups
# ---------------------------------------------------------------------------
# Derived thumbnails live on LOCAL disk (fast, safe) even when originals are on the NAS.
# Default alongside the DB so they land on local disk wherever RECIPE_DB_PATH points.
THUMBS_DIR = Path(
    os.environ.get("THUMBS_DIR", str(DB_PATH.parent / "thumbs"))
).expanduser()
THUMB_MAX_PX = int(os.environ.get("THUMB_MAX_PX", "480"))


def thumbs_dir() -> Path:
    THUMBS_DIR.mkdir(parents=True, exist_ok=True)
    return THUMBS_DIR


# Backups (spec §11). Local nightly snapshots go here (often the NAS mount); the DB
# itself never lives here. Keep the last N. Weekly Drive backup overwrites one file in
# a DEDICATED folder — separate from the import folder so the scanner never touches it.
BACKUP_LOCAL_DIR = Path(
    os.environ.get("BACKUP_LOCAL_DIR", str(MEDIA_ROOT / "backups"))
).expanduser()
BACKUP_KEEP = int(os.environ.get("BACKUP_KEEP", "7"))
DRIVE_BACKUP_FOLDER_ID = os.environ.get("DRIVE_BACKUP_FOLDER_ID", "").strip()
DRIVE_BACKUP_FILENAME = os.environ.get("DRIVE_BACKUP_FILENAME", "recipes-backup.db").strip()
