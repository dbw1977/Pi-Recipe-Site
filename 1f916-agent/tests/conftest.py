"""Shared test fixtures. Everything here is offline — no network, no API key."""

import sys
from pathlib import Path

import pytest

# Make the package importable when pytest runs from this dir.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.config import Config  # noqa: E402


@pytest.fixture
def cfg(tmp_path):
    c = Config(state_dir=tmp_path / "state")
    c.ensure_dirs()
    return c


class FakeMCPClient:
    """Stand-in for MCPClient that returns scripted results per tool.

    `responses` maps tool name -> value OR a callable(args) -> value. A callable
    may raise MCPError to simulate a failure. `calls` records every call.
    """

    def __init__(self, responses=None):
        self.responses = responses or {}
        self.calls = []
        self.initialized = False

    def initialize(self, *a, **k):
        self.initialized = True
        return {"serverInfo": {"name": "fake"}}

    def list_tools(self):
        return [{"name": n} for n in self.responses]

    def call_tool(self, name, arguments=None):
        self.calls.append((name, arguments or {}))
        handler = self.responses.get(name)
        if callable(handler):
            return handler(arguments or {})
        return handler
