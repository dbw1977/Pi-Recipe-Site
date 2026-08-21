"""High-level forum operations built on the MCP client + ledger.

This layer knows the forum's actual tool names (from src/mcp.ts): register,
front_page, read_post, newest_feed, changes, pulse, me, me_ack, history, stats,
tags, citizen, post, comment, vote, tag. Read helpers just proxy to the MCP
client. Write helpers (`vote`, `comment`, `post`) are budget-checked,
dedup-checked, dry-run-aware, and always recorded in the ledger.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .config import Config
from .identity import Identity, load_identity, save_identity
from .ledger import Ledger
from .mcp_client import MCPClient, MCPError


class BudgetExceeded(RuntimeError):
    pass


class Forum:
    def __init__(self, client: MCPClient, ledger: Ledger, config: Config, run_id: int):
        self.client = client
        self.ledger = ledger
        self.cfg = config
        self.run_id = run_id
        self.identity: Identity | None = load_identity(config.identity_file)

    @property
    def secret(self) -> str | None:
        return self.identity.secret if self.identity else None

    # -- registration ------------------------------------------------------
    def ensure_registered(self) -> Identity:
        """Return our identity, registering a new citizen if we have none."""
        if self.identity:
            return self.identity

        result = self.client.call_tool(
            "register", {"handle": self.cfg.handle, "model": self.cfg.declared_model}
        )
        secret = _extract_secret(result)
        if not secret:
            raise MCPError(f"register returned no secret: {result!r}")
        identity = Identity(
            handle=self.cfg.handle,
            secret=secret,
            declared_model=self.cfg.declared_model,
            registered_at=datetime.now(timezone.utc).isoformat(),
            extra={k: v for k, v in (result.items() if isinstance(result, dict) else [])
                   if k not in {"secret", "key", "token"}} or None,
        )
        save_identity(self.cfg.identity_file, identity)
        self.identity = identity
        self.ledger.record_action(
            self.run_id, "register", summary=f"registered as @{identity.handle}",
            payload={"handle": self.cfg.handle, "model": self.cfg.declared_model},
            result={"registered": True}, success=True,
        )
        return identity

    # -- read helpers (no side effects) -----------------------------------
    def pulse(self) -> Any:
        return self.client.call_tool("pulse", _with_secret({}, self.secret))

    def front_page(self, order: str = "top", limit: int = 25, tag: str | None = None) -> Any:
        args: dict[str, Any] = {"order": order, "limit": limit}
        if tag:
            args["tag"] = tag
        return self.client.call_tool("front_page", args)

    def newest_feed(self, limit: int = 25) -> Any:
        return self.client.call_tool("newest_feed", {"limit": limit})

    def changes(self, since: int | None = None) -> Any:
        args = {} if since is None else {"since": since}
        return self.client.call_tool("changes", args)

    def read_post(self, post_id: int) -> Any:
        return self.client.call_tool("read_post", _with_secret({"post_id": post_id}, self.secret))

    def inbox(self) -> Any:
        return self.client.call_tool("me", _with_secret({}, self.secret))

    def history(self) -> Any:
        return self.client.call_tool("history", _with_secret({}, self.secret))

    def stats(self) -> Any:
        return self.client.call_tool("stats", {})

    def tag_list(self) -> Any:
        return self.client.call_tool("tags", {})

    def citizen(self, handle: str) -> Any:
        return self.client.call_tool("citizen", {"handle": handle})

    def ack_inbox(self, up_to: Any) -> Any:
        return self.client.call_tool("me_ack", _with_secret({"up_to": up_to}, self.secret))

    # -- write helpers (budgeted, logged) ---------------------------------
    def _budget_ok(self, kind: str, limit: int) -> bool:
        return self.ledger.count_today(kind) < limit

    def vote(self, target_type: str, target_id: int, reason: str = "") -> dict[str, Any]:
        kind = "vote"
        if self.ledger.already_acted(kind, target_type, target_id):
            return _skipped("already voted on this target")
        if not self._budget_ok(kind, self.cfg.max_votes_per_day):
            return _skipped("daily vote budget reached")
        args = _with_secret({"target_type": target_type, "target_id": target_id}, self.secret)
        summary = f"upvote {target_type} #{target_id}" + (f" — {reason}" if reason else "")
        return self._do_write(kind, args, summary, target_type=target_type, target_id=target_id)

    def comment(self, post_id: int, body: str, parent_id: int | None = None, reason: str = "") -> dict[str, Any]:
        kind = "comment"
        if not self._budget_ok(kind, self.cfg.max_comments_per_day):
            return _skipped("daily comment budget reached")
        args: dict[str, Any] = {"post_id": post_id, "body": body}
        if parent_id is not None:
            args["parent_id"] = parent_id
        args = _with_secret(args, self.secret)
        summary = f"comment on post #{post_id}" + (f" — {reason}" if reason else "")
        return self._do_write(kind, args, summary, target_type="post", target_id=post_id,
                              body=body)

    def post(self, title: str, body: str, url: str | None = None, reason: str = "") -> dict[str, Any]:
        kind = "post"
        if not self._budget_ok(kind, self.cfg.max_posts_per_day):
            return _skipped("daily post budget reached")
        args: dict[str, Any] = {"title": title, "body": body}
        if url:
            args["url"] = url
        args = _with_secret(args, self.secret)
        return self._do_write(kind, args, title, body=body)

    def _do_write(
        self, kind: str, args: dict[str, Any], summary: str,
        *, target_type: str | None = None, target_id: int | None = None, body: str | None = None,
    ) -> dict[str, Any]:
        payload = {k: v for k, v in args.items() if k != "secret"}
        if self.cfg.dry_run:
            self.ledger.record_action(
                self.run_id, kind, target_type=target_type, target_id=target_id,
                summary=f"[DRY-RUN] {summary}", payload=payload,
                result={"dry_run": True}, success=False, error="dry_run",
            )
            return {"status": "dry_run", "summary": summary}
        try:
            result = self.client.call_tool(kind, args)
            new_id = _extract_id(result)
            self.ledger.record_action(
                self.run_id, kind,
                target_type=target_type, target_id=target_id if target_id is not None else new_id,
                summary=summary, payload=payload, result=result, success=True,
            )
            return {"status": "ok", "summary": summary, "result": result, "id": new_id, "body": body}
        except MCPError as exc:
            self.ledger.record_action(
                self.run_id, kind, target_type=target_type, target_id=target_id,
                summary=summary, payload=payload, result={"data": exc.data},
                success=False, error=str(exc),
            )
            return {"status": "error", "summary": summary, "error": str(exc)}


# -- helpers ---------------------------------------------------------------
def _with_secret(args: dict[str, Any], secret: str | None) -> dict[str, Any]:
    if secret:
        args = dict(args)
        args["secret"] = secret
    return args


def _skipped(reason: str) -> dict[str, Any]:
    return {"status": "skipped", "reason": reason}


def _extract_secret(result: Any) -> str | None:
    if isinstance(result, dict):
        for key in ("secret", "key", "token", "secret_key"):
            if result.get(key):
                return str(result[key])
    return None


def _extract_id(result: Any) -> int | None:
    if isinstance(result, dict):
        for key in ("id", "post_id", "comment_id", "target_id"):
            if isinstance(result.get(key), int):
                return result[key]
    return None
