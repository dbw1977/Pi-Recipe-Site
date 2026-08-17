"""Screenshot / image import via Claude vision (spec §5b).

One or more screenshots of the SAME recipe are read together (a caption split across
images, or ingredients and steps on separate screens) and combined into one recipe.
An optional cover photo becomes the hero. Instagram is never scraped programmatically —
the user supplies the images manually (spec §5b).
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

_SCREENSHOT_INSTRUCTION = (
    "These are one or more screenshots of the SAME recipe (for example an Instagram caption "
    "split across images, or the ingredients and the steps on separate screens). Read all of "
    "them and combine everything into a single recipe as JSON per the schema. Do not treat "
    "them as separate recipes."
)


def _vision_media_type(content_type: str | None) -> str:
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct in _VISION_TYPES:
        return ct
    if ct in ("image/jpg", "image/pjpeg"):
        return "image/jpeg"
    return "image/jpeg"  # best-effort default


def import_screenshots(
    conn: sqlite3.Connection,
    images: list[tuple[bytes, str | None]],
    *,
    cover: tuple[bytes, str | None] | None = None,
) -> ImportResult:
    """images: list of (bytes, content_type), all read together as one recipe.
    cover: optional (bytes, content_type) hero photo, preferred over the screenshots."""
    if not claude.available():
        raise FeatureUnavailable(
            "Screenshot import needs the Anthropic API (Claude vision). "
            "Add ANTHROPIC_API_KEY to your .env to enable it.",
            needs="ANTHROPIC_API_KEY",
        )
    if not images:
        raise FeatureUnavailable("Pick at least one screenshot to import.")

    tag_index = load_tag_index(conn)
    extracted = claude.extract_from_images(
        [(b, _vision_media_type(ct)) for b, ct in images],
        tag_index.allowed_by_category,
        instruction=_SCREENSHOT_INSTRUCTION,
    )

    media_rows: list[dict] = []
    hero: str | None = None

    # A supplied cover photo wins as the hero; otherwise the first screenshot.
    if cover is not None:
        cb, cct = cover
        rel = media.save_bytes(cb, content_type=cct)
        media_rows.append({"kind": "image", "path": rel, "caption": "cover photo"})
        hero = rel

    for b, ct in images:
        rel = media.save_bytes(b, content_type=ct, filename="screenshot")
        media_rows.append({"kind": "image", "path": rel, "caption": "source screenshot"})
        if hero is None:
            hero = rel

    recipe = to_recipe_input(
        extracted, source_type="instagram", tag_index=tag_index, hero_image=hero
    )
    return ImportResult(recipe=recipe, media=media_rows)
