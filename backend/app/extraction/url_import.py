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


# A real browser User-Agent. recipe-scrapers' own fetch sends a bot UA that many
# sites (Cloudflare-fronted WordPress like Plays Well With Butter) answer with 403 —
# which otherwise looks like "site not supported". We fetch the HTML ourselves with
# this UA, then hand it to scrape_html.
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
)

# A User-Agent alone isn't enough for bot-protected sites (Dotdash Meredith — Food & Wine,
# Allrecipes, Serious Eats — and Cloudflare-fronted sites) which 403 requests that don't look
# like a real browser navigation. Send the headers Chrome sends. (Accept-Encoding is limited to
# gzip/deflate — br needs a brotli decoder requests may not have, which would garble the body.)
_BROWSER_HEADERS = {
    "User-Agent": _BROWSER_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}


def _try_scraper(url: str) -> dict | None:
    try:
        import requests  # lazy
        from recipe_scrapers import scrape_html
    except ImportError:
        return None
    # Fetch with full browser headers so sites that block bots still return their HTML.
    try:
        resp = requests.get(url, timeout=25, headers=_BROWSER_HEADERS)
        resp.raise_for_status()
        html = resp.text
    except Exception:
        return None
    # wild_mode falls back to schema.org / JSON-LD extraction for sites without a
    # dedicated recipe-scrapers plugin (most WordPress recipe sites emit it).
    try:
        s = scrape_html(html, org_url=url, wild_mode=True)
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


# --------------------------------------------------------------------------- #
# Reddit — no structured recipe data, so read the post's JSON and let Claude
# structure the free text (post body, or the top comment when the body is thin).
# --------------------------------------------------------------------------- #
_REDDIT_UA = "PiRecipeSite/0.3 (personal recipe importer)"


def _is_reddit(url: str) -> bool:
    host = re.sub(r"^https?://", "", url).split("/", 1)[0].lower()
    return host.endswith("reddit.com") or host == "redd.it" or host.endswith(".redd.it")


def _reddit_json_url(url: str) -> str:
    u = url.split("?")[0].split("#")[0].rstrip("/")
    if not u.endswith(".json"):
        u += ".json"
    return u + "?raw_json=1"


def _reddit_post_text(url: str) -> dict:
    """Fetch a Reddit post as JSON and return {title, text, subreddit, author, image}."""
    import requests

    try:
        resp = requests.get(
            _reddit_json_url(url), timeout=25, headers={"User-Agent": _REDDIT_UA}
        )
        resp.raise_for_status()
        data = resp.json()
        post = data[0]["data"]["children"][0]["data"]
    except Exception as e:
        raise FeatureUnavailable(
            "Couldn't read that Reddit post right now (Reddit may be rate-limiting, or "
            "the link isn't a direct post URL). Try again shortly, or paste the full post link.",
        ) from e

    title = post.get("title", "") or ""
    body = (post.get("selftext") or "").strip()
    subreddit = post.get("subreddit_name_prefixed") or (
        f"r/{post.get('subreddit', '')}" if post.get("subreddit") else None
    )
    author = f"u/{post['author']}" if post.get("author") else None

    # Hero image: a direct image post, else the generated preview.
    image = None
    dest = (post.get("url_overridden_by_dest") or "").lower()
    if post.get("post_hint") == "image" or dest.endswith((".jpg", ".jpeg", ".png", ".webp")):
        image = post.get("url_overridden_by_dest")
    if not image:
        try:
            image = post["preview"]["images"][0]["source"]["url"].replace("&amp;", "&")
        except (KeyError, IndexError, TypeError):
            pass

    # Many recipe posts (esp. r/GifRecipes) keep the recipe in the top comment, not the body.
    comments_text = ""
    if len(body) < 60:
        try:
            bodies = [
                ch["data"]["body"]
                for ch in data[1]["data"]["children"]
                if ch.get("kind") == "t1"
                and ch["data"].get("body")
                and ch["data"].get("author") not in (None, "AutoModerator")
            ]
            bodies.sort(key=len, reverse=True)  # the recipe is usually the meatiest comment
            comments_text = "\n\n".join(bodies[:2])
        except (KeyError, IndexError, TypeError):
            pass

    text = "\n\n".join(p for p in (f"Title: {title}", body, comments_text) if p.strip())
    return {"title": title, "text": text, "subreddit": subreddit, "author": author, "image": image}


def _import_reddit(conn: sqlite3.Connection, url: str) -> ImportResult:
    tag_index = load_tag_index(conn)
    post = _reddit_post_text(url)
    if not claude.available():
        raise FeatureUnavailable(
            "Reddit posts are free text with no recipe data, so importing them needs the "
            "Anthropic key to pull out the ingredients and steps. Add ANTHROPIC_API_KEY, "
            "or copy it in by hand.",
            needs="ANTHROPIC_API_KEY",
        )
    extracted = claude.structure_text(post["text"], tag_index.allowed_by_category, kind="Reddit recipe post")
    extracted.source_name = extracted.source_name or post["subreddit"]
    extracted.source_handle = extracted.source_handle or post["author"]
    hero = media.download_image(post["image"]) if post["image"] else None
    recipe = to_recipe_input(
        extracted, source_type="reddit", tag_index=tag_index, source_url=url, hero_image=hero
    )
    return ImportResult(recipe=recipe)


def import_url(conn: sqlite3.Connection, url: str) -> ImportResult:
    url = url.strip()
    if not re.match(r"^https?://", url):
        raise FeatureUnavailable("That doesn't look like a web address (must start with http).")

    if _is_reddit(url):
        return _import_reddit(conn, url)

    tag_index = load_tag_index(conn)
    scraped = _try_scraper(url)

    # Use the scraper's result when it actually found ingredients — or when there's no AI key
    # to do better. If it returned a page but NO ingredients (common on article-style pages
    # the plugin half-parses), fall through to the richer JSON-LD + Claude path below.
    if scraped and (scraped.get("ingredients") or not claude.available()):
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

    # Scraper couldn't handle the site (or found no ingredients) → Claude fallback, fed the
    # page's schema.org JSON-LD recipe data when present (far better than raw page text).
    if not claude.available():
        raise FeatureUnavailable(
            "This site isn't supported by the offline scraper, and no Anthropic key is set "
            "for the AI fallback. Add ANTHROPIC_API_KEY, or add the recipe by hand.",
            needs="ANTHROPIC_API_KEY",
        )
    text = _fetch_readable_text(url)
    extracted = claude.structure_text(text, tag_index.allowed_by_category, kind="recipe web page")
    extracted.source_name = extracted.source_name or (scraped or {}).get("host")
    hero = media.download_image((scraped or {}).get("image"))
    recipe = to_recipe_input(
        extracted, source_type="url", tag_index=tag_index, source_url=url, hero_image=hero
    )
    return ImportResult(recipe=recipe)


def _fetch_readable_text(url: str) -> str:
    """Fetch a page and return recipe-focused text for Claude: any schema.org JSON-LD recipe
    blocks first (most modern sites embed the full recipe there), then the stripped page text.
    A blocked/failed fetch becomes a clean FeatureUnavailable, never an unhandled 500."""
    import requests

    try:
        resp = requests.get(url, timeout=25, headers=_BROWSER_HEADERS)
    except Exception as e:
        raise FeatureUnavailable(
            "Couldn't reach that page — check the link and the Pi's internet, or add it by hand."
        ) from e
    # A 403/401/429 here means bot protection (Food & Wine, Allrecipes, etc.) refused us — no
    # header trick beats that from a script, so point straight at the screenshot import.
    if resp.status_code in (401, 403, 429):
        raise FeatureUnavailable(
            "This site blocks automated imports — it only serves a real browser. Open it on your "
            "phone, screenshot the recipe, and use “From a screenshot” instead (that always works)."
        )
    if resp.status_code >= 400:
        raise FeatureUnavailable(
            f"Couldn't read that page (HTTP {resp.status_code}). Try a screenshot of the recipe "
            "instead, or add it by hand."
        )
    return _readable_from_html(resp.text)


def _readable_from_html(html: str) -> str:
    # 1) schema.org JSON-LD recipe blocks — the structured gold most sites embed.
    blocks = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, flags=re.S | re.I,
    )
    jsonld = "\n\n".join(b.strip() for b in blocks if "recipe" in b.lower())[:12000]

    # 2) The visible page text, scripts/styles stripped, as a backstop.
    stripped = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", stripped))[:12000]

    parts = []
    if jsonld:
        parts.append("STRUCTURED RECIPE DATA (schema.org JSON-LD):\n" + jsonld)
    parts.append("PAGE TEXT:\n" + text)
    return "\n\n".join(parts)
