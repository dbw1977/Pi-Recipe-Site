"""A small, dependency-light MCP client over HTTP (Streamable-HTTP transport).

The 1f916 forum speaks MCP / JSON-RPC 2.0 at POST /mcp (full) and POST
/mcp/read (read-only). Three JSON-RPC methods matter to us: `initialize`,
`tools/list`, and `tools/call`. Responses may come back as either a plain JSON
body or a `text/event-stream` (SSE) with the JSON-RPC message on a `data:`
line — we handle both. A Cloudflare-Worker MCP server may be effectively
stateless, so `initialize` is best-effort and we tolerate its absence.
"""

from __future__ import annotations

import json
import time
from typing import Any

import requests

PROTOCOL_VERSION = "2025-06-18"


class MCPError(RuntimeError):
    """A JSON-RPC error, or a tool result flagged isError=true."""

    def __init__(self, message: str, *, code: int | None = None, data: Any = None):
        super().__init__(message)
        self.code = code
        self.data = data


class MCPClient:
    def __init__(
        self,
        url: str,
        *,
        timeout: float = 30.0,
        user_agent: str = "1f916-agent/0.1",
        max_retries: int = 4,
        session: requests.Session | None = None,
    ):
        self.url = url
        self.timeout = timeout
        self.user_agent = user_agent
        self.max_retries = max_retries
        self._session = session or requests.Session()
        self._session_id: str | None = None
        self._rpc_id = 0
        self._initialized = False

    # -- low-level ---------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": self.user_agent,
            "MCP-Protocol-Version": PROTOCOL_VERSION,
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        return headers

    @staticmethod
    def _parse_body(resp: requests.Response) -> dict[str, Any]:
        """Return the JSON-RPC message from a JSON or SSE response body."""
        ctype = resp.headers.get("Content-Type", "")
        text = resp.text
        if "text/event-stream" in ctype:
            # Grab the last non-empty `data:` payload that parses as JSON.
            message: dict[str, Any] | None = None
            for line in text.splitlines():
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                payload = line[len("data:"):].strip()
                if not payload or payload == "[DONE]":
                    continue
                try:
                    message = json.loads(payload)
                except json.JSONDecodeError:
                    continue
            if message is None:
                raise MCPError(f"no JSON-RPC message in SSE stream: {text[:200]!r}")
            return message
        # Plain JSON.
        try:
            return resp.json()
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise MCPError(f"non-JSON response ({resp.status_code}): {text[:200]!r}") from exc

    def _request(self, method: str, params: dict[str, Any] | None, *, notify: bool = False) -> Any:
        self._rpc_id += 1
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        if not notify:
            payload["id"] = self._rpc_id

        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                resp = self._session.post(
                    self.url, json=payload, headers=self._headers(), timeout=self.timeout
                )
                sid = resp.headers.get("Mcp-Session-Id")
                if sid:
                    self._session_id = sid
                # Retry transient server/network conditions with backoff.
                if resp.status_code >= 500 or resp.status_code == 429:
                    raise requests.HTTPError(f"HTTP {resp.status_code}")
                if notify:
                    return None
                message = self._parse_body(resp)
                if isinstance(message, dict) and message.get("error"):
                    err = message["error"]
                    raise MCPError(
                        err.get("message", "JSON-RPC error"),
                        code=err.get("code"),
                        data=err.get("data"),
                    )
                return message.get("result") if isinstance(message, dict) else message
            except MCPError:
                raise  # application-level error — don't retry
            except (requests.RequestException, MCPError) as exc:
                last_exc = exc
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)  # 1s, 2s, 4s, 8s
        raise MCPError(f"MCP request '{method}' failed after retries: {last_exc}")

    # -- MCP methods -------------------------------------------------------
    def initialize(self, client_name: str = "1f916-agent", client_version: str = "0.1.0") -> dict[str, Any]:
        """Best-effort handshake. Returns server info; never fatal on failure."""
        try:
            result = self._request(
                "initialize",
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": client_name, "version": client_version},
                },
            )
            # Per spec, follow up with the initialized notification.
            try:
                self._request("notifications/initialized", {}, notify=True)
            except MCPError:
                pass
            self._initialized = True
            return result or {}
        except MCPError:
            # Stateless server that rejects initialize — proceed anyway.
            self._initialized = True
            return {}

    def list_tools(self) -> list[dict[str, Any]]:
        result = self._request("tools/list", {})
        if isinstance(result, dict):
            return result.get("tools", [])
        return []

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """Call a tool and return its normalized result.

        Prefers `structuredContent`; otherwise concatenates text blocks and
        tries to JSON-decode them. Raises MCPError when the result is flagged
        as an error.
        """
        result = self._request("tools/call", {"name": name, "arguments": arguments or {}})
        if not isinstance(result, dict):
            return result

        is_error = bool(result.get("isError"))
        if "structuredContent" in result and result["structuredContent"] is not None:
            value = result["structuredContent"]
        else:
            value = _content_to_value(result.get("content", []))

        if is_error:
            raise MCPError(f"tool '{name}' returned an error", data=value)
        return value


def _content_to_value(content: list[dict[str, Any]]) -> Any:
    """Turn an MCP content array into a Python value.

    Text blocks are concatenated; if the whole thing parses as JSON we return
    the decoded object, else the raw string. Non-text blocks are returned as-is.
    """
    texts: list[str] = []
    others: list[Any] = []
    for block in content or []:
        if isinstance(block, dict) and block.get("type") == "text":
            texts.append(block.get("text", ""))
        else:
            others.append(block)
    joined = "".join(texts).strip()
    if joined:
        try:
            return json.loads(joined)
        except json.JSONDecodeError:
            return joined
    if others:
        return others
    return None
