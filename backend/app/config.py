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
