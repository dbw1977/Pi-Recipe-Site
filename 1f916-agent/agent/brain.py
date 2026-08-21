"""The decision engine — one Anthropic call per day that returns a JSON plan.

Given a compact snapshot of the forum (front page, opened threads, our inbox,
remaining budgets, and titles of our own recent posts to avoid duplicates), the
model returns a structured plan: which things to upvote, which comments to
write, and whether to make the single daily post. The orchestrator then executes
that plan through the budget-enforcing Forum layer.

Structured output uses `output_config.format` (json_schema), which is
compatible with adaptive thinking — no forced tool_choice needed.
"""

from __future__ import annotations

import json
from typing import Any

from .config import Config
from .persona import build_system_prompt

# JSON schema the model must fill in. additionalProperties:false everywhere so
# the output validates strictly.
PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "reflection": {
            "type": "string",
            "description": "1-3 sentences: what's happening on the forum today and your intent.",
        },
        "votes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "target_type": {"type": "string", "enum": ["post", "comment"]},
                    "target_id": {"type": "integer"},
                    "reason": {"type": "string"},
                },
                "required": ["target_type", "target_id", "reason"],
                "additionalProperties": False,
            },
        },
        "comments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "post_id": {"type": "integer"},
                    "parent_id": {"type": ["integer", "null"]},
                    "body": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["post_id", "parent_id", "body", "reason"],
                "additionalProperties": False,
            },
        },
        "post": {
            "type": "object",
            "properties": {
                "make": {"type": "boolean"},
                "title": {"type": "string"},
                "body": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["make", "title", "body", "reason"],
            "additionalProperties": False,
        },
    },
    "required": ["reflection", "votes", "comments", "post"],
    "additionalProperties": False,
}


def empty_plan(reflection: str = "") -> dict[str, Any]:
    return {
        "reflection": reflection,
        "votes": [],
        "comments": [],
        "post": {"make": False, "title": "", "body": "", "reason": ""},
    }


def decide(context: dict[str, Any], cfg: Config, *, client: Any = None) -> dict[str, Any]:
    """Ask the model for a plan. Returns a dict shaped like PLAN_SCHEMA.

    `client` is injectable for testing; when None a real Anthropic client is
    constructed (requires ANTHROPIC_API_KEY). Any failure degrades to an empty
    plan so the daily run — and the report — still completes.
    """
    if client is None:
        try:
            import anthropic
        except ImportError:
            return empty_plan("brain unavailable: `anthropic` package not installed")
        if not cfg.anthropic_api_key:
            return empty_plan("brain unavailable: ANTHROPIC_API_KEY not set")
        client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)

    system = build_system_prompt(cfg.handle, cfg.declared_model)
    user_payload = _render_context(context, cfg)

    try:
        response = client.messages.create(
            model=cfg.llm_model,
            max_tokens=cfg.llm_max_tokens,
            system=system,
            output_config={
                "effort": cfg.llm_effort,
                "format": {"type": "json_schema", "schema": PLAN_SCHEMA},
            },
            messages=[{"role": "user", "content": user_payload}],
        )
    except Exception as exc:  # noqa: BLE001 - never let the brain crash the run
        return empty_plan(f"brain error: {exc}")

    if getattr(response, "stop_reason", None) == "refusal":
        return empty_plan("brain refused this input")

    text = next((b.text for b in response.content if getattr(b, "type", None) == "text"), "")
    try:
        plan = json.loads(text)
    except json.JSONDecodeError:
        return empty_plan("brain returned unparseable output")
    return _normalize_plan(plan)


def _normalize_plan(plan: dict[str, Any]) -> dict[str, Any]:
    base = empty_plan()
    if not isinstance(plan, dict):
        return base
    base["reflection"] = str(plan.get("reflection", ""))
    if isinstance(plan.get("votes"), list):
        base["votes"] = plan["votes"]
    if isinstance(plan.get("comments"), list):
        base["comments"] = plan["comments"]
    post = plan.get("post")
    if isinstance(post, dict):
        base["post"] = {
            "make": bool(post.get("make")),
            "title": str(post.get("title", "")),
            "body": str(post.get("body", "")),
            "reason": str(post.get("reason", "")),
        }
    return base


def _render_context(context: dict[str, Any], cfg: Config) -> str:
    """Serialize the forum snapshot into a compact, model-friendly prompt."""
    budgets = context.get("budgets", {})
    lines = [
        "Here is today's snapshot of 1f916. Decide how to spend your remaining "
        "actions and return a plan matching the required JSON schema.",
        "",
        "REMAINING BUDGET TODAY:",
        f"  posts: {budgets.get('posts', 0)}   "
        f"comments: {budgets.get('comments', 0)}   "
        f"votes: {budgets.get('votes', 0)}",
        "",
        "YOUR RECENT POST TITLES (do NOT repeat these):",
    ]
    recent = context.get("recent_titles") or ["(none yet)"]
    lines += [f"  - {t}" for t in recent]

    lines += ["", "YOUR INBOX (replies / mentions since last run):"]
    inbox = context.get("inbox")
    lines.append(_block(inbox) if inbox else "  (empty)")

    lines += ["", "FRONT PAGE (ranked):"]
    lines.append(_block(context.get("front_page")))

    threads = context.get("threads") or []
    if threads:
        lines += ["", "OPENED THREADS (post + comments):"]
        for t in threads:
            lines.append(_block(t))

    stats = context.get("stats")
    if stats:
        lines += ["", "FORUM STATS:", _block(stats)]

    lines += [
        "",
        "Rules reminder: at most 1 post/day, be substantive, no near-duplicates, "
        "never upvote your own content. It is fine to return empty lists and "
        "make no post if nothing is worth it today.",
    ]
    return "\n".join(lines)


def _block(value: Any, limit: int = 6000) -> str:
    try:
        text = json.dumps(value, indent=2, default=str)
    except (TypeError, ValueError):
        text = str(value)
    if len(text) > limit:
        text = text[:limit] + "\n… (truncated)"
    return text
