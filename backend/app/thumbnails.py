"""Derived thumbnails for the library grid (spec §9, Chunk C).

Thumbnails are generated on demand and cached on LOCAL disk (fast, safe), even when the
original media lives on the NAS. Generation is deliberately light for the Pi 4: a single
downscale to THUMB_MAX_PX, saved as WebP. Pillow is imported lazily; if it isn't
installed the caller falls back to serving the original image.
"""
from __future__ import annotations

from pathlib import Path

from . import config


def _safe_source(rel_path: str) -> Path | None:
    """Resolve a DB-relative media path under MEDIA_ROOT, rejecting traversal."""
    root = config.media_root().resolve()
    candidate = (root / rel_path).resolve()
    if not str(candidate).startswith(str(root)):
        return None
    return candidate if candidate.is_file() else None


def thumb_dest(rel_path: str) -> Path:
    # Mirror the media layout under the thumbs dir, always ending in .webp.
    return config.thumbs_dir() / (rel_path + ".webp")


def get_or_create(rel_path: str) -> Path | None:
    """Return the cached thumbnail path, generating it if needed. None if unavailable."""
    src = _safe_source(rel_path)
    if src is None:
        return None
    dest = thumb_dest(rel_path)
    # Regenerate if missing or older than the source.
    if dest.is_file() and dest.stat().st_mtime >= src.stat().st_mtime:
        return dest

    try:
        from PIL import Image  # lazy
    except ImportError:
        return None

    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(src) as im:
            im = im.convert("RGB")
            im.thumbnail((config.THUMB_MAX_PX, config.THUMB_MAX_PX))
            im.save(dest, "WEBP", quality=80, method=4)
        return dest
    except Exception:
        return None
