import json

from agent.identity import Identity, save_identity
from agent.ledger import Ledger
from agent.report import build_report
from agent.runner import run_daily
from tests.conftest import FakeMCPClient


def test_report_renders_sections(cfg):
    save_identity(cfg.identity_file, Identity(handle="tester", secret="x"))
    led = Ledger(cfg.db_file)
    run = led.start_run()
    led.record_action(run, "post", summary="A thought", payload={"body": "hello"}, success=True)
    led.record_action(run, "comment", target_type="post", target_id=7,
                      payload={"body": "good idea"}, success=True)
    led.record_action(run, "vote", target_type="post", target_id=3,
                      summary="upvote post #3 — solid", success=True)
    led.record_observation(run, "reflection", "The forum debated agent identity today.")
    report = build_report(cfg, led)
    led.close()

    assert "@tester" in report["subject"]
    assert "1 post, 1 comments, 1 votes" in report["subject"]
    assert "A thought" in report["markdown"]
    assert "good idea" in report["markdown"]
    assert "debated agent identity" in report["markdown"]
    assert "<html" not in report["html"].lower()  # fragment, no doctype
    assert "🤖" in report["html"]


def test_run_daily_end_to_end_no_email(cfg, monkeypatch):
    """Full cycle with fake MCP + fake brain, email unconfigured -> file only."""
    save_identity(cfg.identity_file, Identity(handle="tester", secret="x"))

    front = {"posts": [{"id": 1, "title": "First"}, {"id": 2, "title": "Second"}]}
    responses = {
        "pulse": {"marks": 0},
        "me": {"messages": []},
        "front_page": front,
        "stats": {"citizens": 42},
        "read_post": lambda a: {"id": a["post_id"], "comments": []},
        "vote": {"ok": True},
        "comment": {"id": 99},
        "post": {"id": 100},
    }
    client = FakeMCPClient(responses)

    class Brain:
        messages = None

        def __init__(self):
            self.messages = self

        def create(self, **kw):
            plan = {
                "reflection": "Good threads today.",
                "votes": [{"target_type": "post", "target_id": 1, "reason": "insightful"}],
                "comments": [{"post_id": 2, "parent_id": None, "body": "Agreed, and…", "reason": "engage"}],
                "post": {"make": False, "title": "", "body": "", "reason": "nothing new"},
            }

            class R:
                stop_reason = "end_turn"
                content = [type("B", (), {"type": "text", "text": json.dumps(plan)})()]

            return R()

    summary = run_daily(cfg, brain_client=Brain(), mcp_client=client)

    assert summary["votes"] == 1
    assert summary["comments"] == 1
    assert summary["posts"] == 0
    assert summary["emailed"] is False          # SMTP not configured
    assert summary["report_file"]               # but a file was written
    # The forum actually received the write calls.
    called = [name for name, _ in client.calls]
    assert "vote" in called and "comment" in called and "post" not in called


def test_run_daily_survives_forum_failure(cfg):
    save_identity(cfg.identity_file, Identity(handle="tester", secret="x"))

    def explode(_a):
        from agent.mcp_client import MCPError
        raise MCPError("forum down")

    client = FakeMCPClient({
        "pulse": explode, "me": explode, "front_page": explode, "stats": explode,
    })

    class Brain:
        def __init__(self):
            self.messages = self

        def create(self, **kw):
            class R:
                stop_reason = "end_turn"
                content = [type("B", (), {"type": "text", "text": "{}"})()]
            return R()

    summary = run_daily(cfg, brain_client=Brain(), mcp_client=client)
    # Even with everything failing, we still produced a report.
    assert summary["report_file"]
    assert summary["errors"]
