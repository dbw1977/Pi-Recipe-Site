"""Orchestrate one daily cycle: observe → plan → act → report.

Every stage is defensive: a failure in gathering, planning, or acting is logged
to the ledger and the run continues so the daily report is always produced and
sent. The report is the contract with the human — it must arrive even on a bad
day.
"""

from __future__ import annotations

import logging
from typing import Any

from .brain import decide
from .config import Config
from .forum import Forum
from .ledger import Ledger
from .mcp_client import MCPClient, MCPError
from .report import build_report, send_email, write_report_file

log = logging.getLogger("1f916-agent")


def run_daily(cfg: Config, *, brain_client: Any = None, mcp_client: MCPClient | None = None) -> dict[str, Any]:
    """Execute a full day. Returns a summary dict."""
    cfg.ensure_dirs()
    ledger = Ledger(cfg.db_file)
    run_id = ledger.start_run()
    summary: dict[str, Any] = {"run_id": run_id, "posts": 0, "comments": 0, "votes": 0, "errors": []}

    client = mcp_client or MCPClient(
        cfg.mcp_url, timeout=cfg.http_timeout, user_agent=cfg.user_agent
    )
    forum = Forum(client, ledger, cfg, run_id)

    try:
        client.initialize()

        # 1. Identity ------------------------------------------------------
        forum.ensure_registered()

        # 2. Observe (read-only) ------------------------------------------
        context = _gather_context(cfg, forum, ledger, run_id, summary)

        # 3. Plan ----------------------------------------------------------
        plan = decide(context, cfg, client=brain_client)
        ledger.record_observation(run_id, "reflection", plan.get("reflection", ""))

        # 4. Act -----------------------------------------------------------
        _execute_plan(plan, forum, summary)

        # 5. Advance inbox so we don't re-answer the same replies tomorrow -
        _ack_inbox(forum, context)

        ledger.finish_run(run_id, status="ok")
    except MCPError as exc:
        log.error("run failed: %s", exc)
        summary["errors"].append(str(exc))
        ledger.record_observation(run_id, "error", {"stage": "run", "error": str(exc)})
        ledger.finish_run(run_id, status="error", notes=str(exc))
    except Exception as exc:  # noqa: BLE001
        log.exception("unexpected failure")
        summary["errors"].append(str(exc))
        ledger.record_observation(run_id, "error", {"stage": "run", "error": str(exc)})
        ledger.finish_run(run_id, status="error", notes=str(exc))

    # 6. Report — always, even after failure --------------------------------
    try:
        report = build_report(cfg, ledger)
        path = write_report_file(cfg, report)
        summary["report_file"] = str(path)
        summary["emailed"] = send_email(cfg, report)
    except Exception as exc:  # noqa: BLE001
        log.exception("report failed")
        summary["errors"].append(f"report: {exc}")
    finally:
        ledger.close()

    return summary


def _gather_context(cfg: Config, forum: Forum, ledger: Ledger, run_id: int, summary: dict) -> dict[str, Any]:
    context: dict[str, Any] = {
        "budgets": {
            "posts": max(0, cfg.max_posts_per_day - ledger.count_today("post")),
            "comments": max(0, cfg.max_comments_per_day - ledger.count_today("comment")),
            "votes": max(0, cfg.max_votes_per_day - ledger.count_today("vote")),
        },
        "recent_titles": ledger.recent_post_titles(20),
    }

    def _safe(label: str, fn):
        try:
            value = fn()
            ledger.record_observation(run_id, label, value)
            return value
        except MCPError as exc:
            log.warning("gather %s failed: %s", label, exc)
            summary["errors"].append(f"{label}: {exc}")
            return None

    _safe("pulse", forum.pulse)
    context["inbox"] = _safe("inbox", forum.inbox)
    front = _safe("feed", lambda: forum.front_page(order="top", limit=cfg.feed_limit))
    context["front_page"] = front
    context["stats"] = _safe("stats", forum.stats)

    # Open the top few threads in full so the brain can comment meaningfully.
    threads: list[Any] = []
    for pid in _top_post_ids(front, cfg.threads_to_read):
        try:
            threads.append(forum.read_post(pid))
        except MCPError as exc:
            log.warning("read_post %s failed: %s", pid, exc)
    context["threads"] = threads
    return context


def _execute_plan(plan: dict[str, Any], forum: Forum, summary: dict) -> None:
    for v in plan.get("votes", []):
        try:
            res = forum.vote(str(v["target_type"]), int(v["target_id"]), v.get("reason", ""))
            if res.get("status") == "ok":
                summary["votes"] += 1
        except (KeyError, ValueError, TypeError):
            continue

    for c in plan.get("comments", []):
        try:
            parent = c.get("parent_id")
            res = forum.comment(
                int(c["post_id"]), str(c["body"]),
                parent_id=int(parent) if parent is not None else None,
                reason=c.get("reason", ""),
            )
            if res.get("status") == "ok":
                summary["comments"] += 1
        except (KeyError, ValueError, TypeError):
            continue

    post = plan.get("post") or {}
    if post.get("make") and post.get("title") and post.get("body"):
        res = forum.post(str(post["title"]), str(post["body"]), reason=post.get("reason", ""))
        if res.get("status") == "ok":
            summary["posts"] += 1


def _ack_inbox(forum: Forum, context: dict[str, Any]) -> None:
    """Advance the inbox cursor past what we saw, best-effort."""
    inbox = context.get("inbox")
    up_to = None
    if isinstance(inbox, dict):
        up_to = inbox.get("cursor") or inbox.get("up_to") or inbox.get("latest")
    if up_to is not None:
        try:
            forum.ack_inbox(up_to)
        except MCPError:
            pass


def _top_post_ids(front: Any, n: int) -> list[int]:
    """Best-effort extraction of post ids from a front_page result."""
    items = _as_item_list(front)
    ids: list[int] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        pid = item.get("id") or item.get("post_id")
        if isinstance(pid, int):
            ids.append(pid)
        if len(ids) >= n:
            break
    return ids


def _as_item_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("posts", "items", "results", "front_page", "data"):
            if isinstance(value.get(key), list):
                return value[key]
    return []
