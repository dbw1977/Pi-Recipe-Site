"""URL import (spec §5a).

1. `recipe-scrapers` attempts structured extraction (works offline for supported sites —
   no API key needed).
2. If Claude is configured, the scraped fields are handed to Claude for full structuring
   (structured ingredients + tags + equipment inference). Otherwise a dependency-free
   parser structures the ingredient strings and the user fills tags/equipment in review.
3. Unsupported site + no Claude key → a clear FeatureUnavailable (never a crash).
Remote hero images are downloaded into the local media store (never hot-linked).
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field

from ..schemas import GroupIn, IngredientIn, RecipeIn, StepIn
from . import claude, media
from .draft import ExtractedRecipe, to_recipe_input
from .errors import FeatureUnavailable
from .ingredients import parse_ingredient_lines
from .tags import load_tag_index


@dataclass
class ImportResult:
    recipe: RecipeIn
    media: list[dict] = field(default_factory=list)  # {kind, path, caption}
    duplicate: dict | None = None


def _try_scraper(url: str) -> dict | None:
    try:
        from recipe_scrapers import scrape_me  # lazy
    except ImportError:
        return None
    try:
        s = scrape_me(url, wild_mode=True)
    except Exception:
        return None

    def safe(fn):
        try:
            return fn()
        except Exception:
            return None

    data = {
        "title": safe(s.title),
        "ingredients": safe(s.ingredients) or [],
        "instructions_list": safe(s.instructions_list) or (
            (safe(s.instructions) or "").split("\n") if safe(s.instructions) else []
        ),
        "image": safe(s.image),
        "host": safe(s.host),
        "author": safe(s.author),
        "total_time": safe(s.total_time),
        "yields": safe(s.yields),
    }
    if not data["title"] and not data["ingredients"]:
        return None
    return data


def _scraped_to_text(d: dict) -> str:
    parts = [f"Title: {d.get('title') or ''}"]
    if d.get("author"):
        parts.append(f"Author/source: {d['author']}")
    if d.get("host"):
        parts.append(f"Site: {d['host']}")
    if d.get("yields"):
        parts.append(f"Yield: {d['yields']}")
    if d.get("total_time"):
        parts.append(f"Total time (min): {d['total_time']}")
    parts.append("Ingredients:\n" + "\n".join(d.get("ingredients") or []))
    parts.append("Instructions:\n" + "\n".join(d.get("instructions_list") or []))
    return "\n\n".join(parts)


def _yield_to_servings(yields: str | None) -> tuple[int | None, str | None]:
    if not yields:
        return None, None
    m = re.search(r"(\d+)", yields)
    base = int(m.group(1)) if m else None
    unit = re.sub(r"[\d\s]+", " ", yields).strip() or "servings"
    return base, unit


def _scraped_to_extracted(d: dict) -> ExtractedRecipe:
    """Offline path: structure the scraper output without any AI (no tags/equipment)."""
    parsed = parse_ingredient_lines(d.get("ingredients") or [])
    base, unit = _yield_to_servings(d.get("yields"))
    return ExtractedRecipe(
        title=d.get("title"),
        source_name=d.get("author") or d.get("host"),
        servings_base=base,
        servings_unit=unit,
        total_time=d.get("total_time"),
        groups=[
            {
                "name": None,
                "ingredients": [
                    {
                        "quantity": p.quantity, "unit": p.unit, "name": p.name,
                        "note": p.note, "scalable": p.scalable,
                    }
                    for p in parsed
                ],
            }
        ],
        steps=d.get("instructions_list") or [],
        equipment=[],
        tags={},
    )


def import_url(conn: sqlite3.Connection, url: str) -> ImportResult:
    url = url.strip()
    if not re.match(r"^https?://", url):
        raise FeatureUnavailable("That doesn't look like a web address (must start with http).")

    tag_index = load_tag_index(conn)
    scraped = _try_scraper(url)

    if scraped:
        hero = media.download_image(scraped.get("image"))
        if claude.available():
            extracted = claude.structure_text(
                _scraped_to_text(scraped), tag_index.allowed_by_category, kind="recipe"
            )
            extracted.source_name = extracted.source_name or scraped.get("author") or scraped.get("host")
        else:
            extracted = _scraped_to_extracted(scraped)
        recipe = to_recipe_input(
            extracted, source_type="url", tag_index=tag_index, source_url=url, hero_image=hero
        )
        return ImportResult(recipe=recipe)

    # Scraper couldn't handle the site → Claude fallback on the readable page text.
    if not claude.available():
        raise FeatureUnavailable(
            "This site isn't supported by the offline scraper, and no Anthropic key is set "
            "for the AI fallback. Add ANTHROPIC_API_KEY, or add the recipe by hand.",
            needs="ANTHROPIC_API_KEY",
        )
    text = _fetch_readable_text(url)
    extracted = claude.structure_text(text, tag_index.allowed_by_category, kind="page text")
    recipe = to_recipe_input(
        extracted, source_type="url", tag_index=tag_index, source_url=url, hero_image=None
    )
    return ImportResult(recipe=recipe)


def _fetch_readable_text(url: str) -> str:
    import requests

    resp = requests.get(url, timeout=25, headers={"User-Agent": "PiRecipeSite/0.2"})
    resp.raise_for_status()
    html = resp.text
    # Crude tag strip — Claude tolerates messy text; we just remove scripts/styles/markup.
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return text[:16000]
