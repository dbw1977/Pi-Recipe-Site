"""Screenshot / image import via Claude vision (spec §5b).

The uploaded screenshot is always the extraction source; optional video/extra photos are
attached as media. Instagram is never scraped programmatically — the user supplies any
video file manually (spec §5b).
"""
from __future__ import annotations

import sqlite3

from . import claude, media
from .draft import to_recipe_input
from .errors import FeatureUnavailable
from .tags import load_tag_index
from .url_import import ImportResult

# Anthropic vision accepts these media types.
_VISION_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


def _vision_media_type(content_type: str | None) -> str:
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct in _VISION_TYPES:
        return ct
    if ct in ("image/jpg", "image/pjpeg"):
        return "image/jpeg"
    return "image/jpeg"  # best-effort default


def import_screenshot(
    conn: sqlite3.Connection,
    image_bytes: bytes,
    content_type: str | None,
    *,
    extra_media: list[tuple[bytes, str | None, str]] | None = None,
) -> ImportResult:
    """extra_media: list of (bytes, content_type, kind) for optional video/photos."""
    if not claude.available():
        raise FeatureUnavailable(
            "Screenshot import needs the Anthropic API (Claude vision). "
            "Add ANTHROPIC_API_KEY to your .env to enable it.",
            needs="ANTHROPIC_API_KEY",
        )
    tag_index = load_tag_index(conn)
    extracted = claude.extract_from_image(
        image_bytes, _vision_media_type(content_type), tag_index.allowed_by_category
    )

    # Store the screenshot as media; it becomes the hero unless a cover photo is supplied.
    screenshot_rel = media.save_bytes(image_bytes, content_type=content_type, filename="screenshot")
    media_rows = [{"kind": "image", "path": screenshot_rel, "caption": "source screenshot"}]
    hero = screenshot_rel
    cover_set = False

    for data, ctype, kind in extra_media or []:
        rel = media.save_bytes(data, content_type=ctype)
        media_rows.append({"kind": kind, "path": rel, "caption": None})
        # The first supplied photo becomes the cover (hero), preferred over the screenshot.
        if kind == "image" and not cover_set:
            hero = rel
            cover_set = True

    recipe = to_recipe_input(
        extracted, source_type="instagram", tag_index=tag_index, hero_image=hero
    )
    return ImportResult(recipe=recipe, media=media_rows)
