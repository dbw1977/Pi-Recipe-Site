import json

import pytest

from agent.mcp_client import MCPClient, MCPError, _content_to_value


class FakeResponse:
    def __init__(self, body, content_type="application/json", status=200, headers=None):
        self._body = body
        self.status_code = status
        self.headers = {"Content-Type": content_type, **(headers or {})}

    @property
    def text(self):
        return self._body

    def json(self):
        return json.loads(self._body)


class FakeSession:
    def __init__(self, response):
        self._response = response
        self.posts = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.posts.append({"url": url, "json": json, "headers": headers})
        return self._response


def _client(response):
    return MCPClient("http://x/mcp", session=FakeSession(response))


def test_parse_plain_json_result():
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"tools": [{"name": "post"}]}})
    c = _client(FakeResponse(body))
    assert c.list_tools() == [{"name": "post"}]


def test_parse_sse_result():
    sse = (
        "event: message\n"
        'data: {"jsonrpc":"2.0","id":1,"result":{"content":[{"type":"text","text":"{\\"ok\\":true}"}]}}\n'
        "\n"
    )
    c = _client(FakeResponse(sse, content_type="text/event-stream"))
    assert c.call_tool("pulse") == {"ok": True}


def test_jsonrpc_error_raises():
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "error": {"code": -32601, "message": "no method"}})
    c = _client(FakeResponse(body))
    with pytest.raises(MCPError) as exc:
        c.list_tools()
    assert exc.value.code == -32601


def test_tool_is_error_raises():
    body = json.dumps({
        "jsonrpc": "2.0", "id": 1,
        "result": {"isError": True, "content": [{"type": "text", "text": "handle taken"}]},
    })
    c = _client(FakeResponse(body))
    with pytest.raises(MCPError):
        c.call_tool("register", {"handle": "x"})


def test_session_id_captured_and_sent():
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}})
    session = FakeSession(FakeResponse(body, headers={"Mcp-Session-Id": "sess-42"}))
    c = MCPClient("http://x/mcp", session=session)
    c.initialize()
    c.list_tools()
    # Second call should carry the session id captured from the first.
    assert session.posts[-1]["headers"]["Mcp-Session-Id"] == "sess-42"


def test_content_to_value_variants():
    assert _content_to_value([{"type": "text", "text": '{"a":1}'}]) == {"a": 1}
    assert _content_to_value([{"type": "text", "text": "plain"}]) == "plain"
    assert _content_to_value([]) is None
