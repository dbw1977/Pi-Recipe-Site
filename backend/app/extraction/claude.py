"""Anthropic (Claude) wrapper for extraction, structuring, tagging, equipment inference.

Every entry point degrades gracefully: with no ANTHROPIC_API_KEY set, `available()` is
False and callers raise FeatureUnavailable with a clear message (CLAUDE.md rule 8). The
`anthropic` SDK is imported lazily so the app runs even if the package isn't installed.
"""
from __future__ import annotations

import base64

from .. import config
from .draft import ExtractedRecipe, parse_extracted_json
from .errors import ExtractionError, FeatureUnavailable

_SYSTEM = """You extract structured recipe data from messy sources (screenshots, pasted \
page text, voice transcripts). Return ONLY a single JSON object — no prose, no markdown \
fences. Match this schema exactly:

{
  "title": string,
  "description": string | null,        // one short line, NOT the blog story
  "source_name": string | null,        // site or account, e.g. "chacekitchen"
  "source_handle": string | null,      // e.g. "@chacekitchen" if visible
  "servings_base": integer | null,
  "servings_unit": string | null,      // "servings", "salads", "cups", ...
  "total_time": integer | null,        // minutes
  "groups": [
    { "name": string | null,           // e.g. "For the dressing"; null if ungrouped
      "ingredients": [
        { "quantity": number | null,   // null for "to taste" / assembly items
          "unit": string | null,       // canonical: tsp, tbsp, cup, g, oz, clove, slice, whole...
          "name": string,
          "note": string | null,       // "minced", "to taste", brand notes
          "scalable": 0 | 1 }          // 0 = never scale (salt to taste, garnishes, assembly)
      ] }
  ],
  "steps": [ string ],                 // may be empty (e.g. Instagram captions)
  "equipment": [ { "name": string, "inferred": 0 | 1 } ],  // see rules below
  "tags": { "Dimension": [ "TagName", ... ] }              // ONLY from the allowed list
}

Rules:
- Structured ingredients only. Split combined amounts; keep prep words ("minced") in note.
- Assembly items with no measurement get quantity=null, unit=null, scalable=0.
- "to taste"/garnish items: scalable=0, keep the phrase in note.
- Equipment: list tools explicitly named, AND infer the obvious ones from the steps
  (grill the steak -> grill; whisk the dressing -> whisk + mixing bowl). Mark every
  inferred tool inferred=1; tools named in the source inferred=0. Do not over-invent.
- Tags: choose ONLY from the allowed list provided. Omit a dimension if nothing fits.
- If steps are absent, return an empty steps array — do not invent steps."""


def available() -> bool:
    return bool(config.ANTHROPIC_API_KEY)


def _require() -> None:
    if not available():
        raise FeatureUnavailable(
            "Claude extraction is off because no Anthropic API key is set. "
            "Add ANTHROPIC_API_KEY to your .env to enable screenshot/voice/URL-fallback imports.",
            needs="ANTHROPIC_API_KEY",
        )


def _client():
    _require()
    try:
        import anthropic  # lazy: keeps the app runnable without the package
    except ImportError as e:  # pragma: no cover
        raise FeatureUnavailable(
            "The 'anthropic' package isn't installed. Run: pip install -r requirements.txt",
            needs="anthropic package",
        ) from e
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


def _allowed_tags_block(allowed_by_category: dict[str, list[str]]) -> str:
    lines = [f"- {cat}: {', '.join(names)}" for cat, names in allowed_by_category.items()]
    return "Allowed tags (choose only from these):\n" + "\n".join(lines)


def _call(content: list[dict], *, model: str) -> str:
    client = _client()
    msg = client.messages.create(
        model=model,
        max_tokens=2048,
        system=_SYSTEM,
        messages=[{"role": "user", "content": content}],
    )
    # Concatenate any text blocks in the response.
    return "".join(getattr(b, "text", "") for b in msg.content).strip()


def _extract(content: list[dict], allowed_by_category: dict[str, list[str]]) -> ExtractedRecipe:
    """Call Claude, parse JSON. On parse failure retry once with the fallback model
    (spec §10). If still unparseable, raise ExtractionError with whatever we got so the
    router can still open a review screen."""
    tags_block = {"type": "text", "text": _allowed_tags_block(allowed_by_category)}
    body = content + [tags_block]

    last_raw = ""
    for model in (config.ANTHROPIC_MODEL, config.ANTHROPIC_FALLBACK_MODEL):
        last_raw = _call(body, model=model)
        try:
            return parse_extracted_json(last_raw)
        except ValueError:
            continue  # retry once with the stronger model
    raise ExtractionError(
        "Claude did not return valid recipe JSON. Opening the review screen so you can finish it.",
        partial={"raw": last_raw[:2000]},
    )


# --------------------------------------------------------------------------- #
# Public extraction entry points
# --------------------------------------------------------------------------- #
def extract_from_image(
    image_bytes: bytes, media_type: str, allowed_by_category: dict[str, list[str]]
) -> ExtractedRecipe:
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    content = [
        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
        {"type": "text", "text": "Extract the recipe from this screenshot as JSON per the schema."},
    ]
    return _extract(content, allowed_by_category)


def extract_from_images(
    images: list[tuple[bytes, str]],
    allowed_by_category: dict[str, list[str]],
    *,
    instruction: str | None = None,
) -> ExtractedRecipe:
    """Extract one recipe from several images at once — multiple screenshots of the same
    recipe, or frames sampled from a video. `images` is a list of (bytes, media_type)."""
    content: list[dict] = []
    for img, media_type in images:
        b64 = base64.standard_b64encode(img).decode("ascii")
        content.append(
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}}
        )
    content.append(
        {
            "type": "text",
            "text": instruction
            or (
                "These images are frames sampled in order from a short recipe video. Read any "
                "on-screen text, captions, and ingredient overlays, and look at the dish, to "
                "extract the recipe as JSON per the schema. If the video doesn't spell out the "
                "steps, write concise steps from what the frames show. Combine information "
                "across all the frames into one recipe."
            ),
        }
    )
    return _extract(content, allowed_by_category)


def structure_text(
    text: str, allowed_by_category: dict[str, list[str]], *, kind: str = "page text"
) -> ExtractedRecipe:
    content = [
        {"type": "text", "text": f"Structure this {kind} into recipe JSON per the schema:\n\n{text[:12000]}"},
    ]
    return _extract(content, allowed_by_category)
