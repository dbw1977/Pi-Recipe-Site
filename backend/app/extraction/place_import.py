"""Place import from screenshot(s) via Claude vision (Chunk D, spec §14).

Reuses the screenshot pipeline: read one or more images of a recommendation (a friend's
text, an IG post) and pull out the place name, city, dishes, and cuisine. Lands as a place
draft for review — nothing auto-publishes (rule 10).
"""
from __future__ import annotations

import sqlite3

from .. import config
from ..schemas import DishIn, PlaceIn
from . import claude, media
from .screenshot import _vision_media_type
from .tags import load_tag_index
from .errors import FeatureUnavailable


class PlaceImportResult:
    def __init__(self, place: PlaceIn, media_rows: list[dict]):
        self.place = place
        self.media = media_rows


def import_place_screenshots(
    conn: sqlite3.Connection,
    images: list[tuple[bytes, str | None]],
    *,
    cover: tuple[bytes, str | None] | None = None,
) -> PlaceImportResult:
    if not claude.available():
        raise FeatureUnavailable(
            "Importing a place from a screenshot needs the Anthropic API (Claude vision). "
            "Add ANTHROPIC_API_KEY to your .env to enable it.",
            needs="ANTHROPIC_API_KEY",
        )
    if not images:
        raise FeatureUnavailable("Pick at least one screenshot to import.")

    tag_index = load_tag_index(conn, collection="place")
    allowed_cuisines = tag_index.allowed_by_category.get("Cuisine", [])
    extracted = claude.extract_place_from_images(
        [(b, _vision_media_type(ct)) for b, ct in images],
        allowed_cuisines,
        home_city=config.HOME_CITY,
    )

    media_rows: list[dict] = []
    hero: str | None = None
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

    cuisine_ids = tag_index.resolve({"Cuisine": extracted.cuisine})
    place = PlaceIn(
        name=(extracted.name or "Imported place").strip(),
        place_type=extracted.place_type,
        city=(extracted.city or config.HOME_CITY or None),
        address=extracted.address,
        our_notes=extracted.our_notes,
        source_name=extracted.source_name,
        hero_image=hero,
        status="draft",
        dishes=[
            DishIn(name=d.name.strip(), note=d.note, must_order=1 if d.must_order else 0, sort_order=i)
            for i, d in enumerate(extracted.dishes)
            if d.name and d.name.strip()
        ],
        tag_ids=cuisine_ids,
    )
    return PlaceImportResult(place=place, media_rows=media_rows)
