from agent.forum import Forum
from agent.identity import Identity, save_identity
from agent.ledger import Ledger
from agent.mcp_client import MCPError
from tests.conftest import FakeMCPClient


def _forum(cfg, responses):
    save_identity(cfg.identity_file, Identity(handle="tester", secret="s3cr3t"))
    led = Ledger(cfg.db_file)
    run = led.start_run()
    return Forum(FakeMCPClient(responses), led, cfg, run), led


def test_vote_records_and_dedupes(cfg):
    forum, led = _forum(cfg, {"vote": {"ok": True}})
    r1 = forum.vote("post", 5, "great point")
    assert r1["status"] == "ok"
    assert led.count_today("vote") == 1
    # Second identical vote is skipped, no new action.
    r2 = forum.vote("post", 5)
    assert r2["status"] == "skipped"
    assert led.count_today("vote") == 1
    led.close()


def test_vote_budget_enforced(cfg):
    cfg.max_votes_per_day = 2
    forum, led = _forum(cfg, {"vote": {"ok": True}})
    assert forum.vote("post", 1)["status"] == "ok"
    assert forum.vote("post", 2)["status"] == "ok"
    assert forum.vote("post", 3)["status"] == "skipped"
    assert led.count_today("vote") == 2
    led.close()


def test_secret_attached_but_not_logged(cfg):
    client = FakeMCPClient({"vote": {"ok": True}})
    save_identity(cfg.identity_file, Identity(handle="tester", secret="TOP-SECRET"))
    led = Ledger(cfg.db_file)
    run = led.start_run()
    forum = Forum(client, led, cfg, run)
    forum.vote("post", 9)
    # Secret went to the wire...
    assert client.calls[0][1]["secret"] == "TOP-SECRET"
    # ...but is not stored in the ledger payload.
    row = led.conn.execute("SELECT payload FROM actions WHERE kind='vote'").fetchone()
    assert "TOP-SECRET" not in (row["payload"] or "")
    led.close()


def test_dry_run_makes_no_calls(cfg):
    cfg.dry_run = True
    client = FakeMCPClient({"post": {"id": 1}})
    save_identity(cfg.identity_file, Identity(handle="t", secret="x"))
    led = Ledger(cfg.db_file)
    run = led.start_run()
    forum = Forum(client, led, cfg, run)
    res = forum.post("Title", "Body")
    assert res["status"] == "dry_run"
    assert client.calls == []          # nothing sent to the forum
    assert led.count_today("post") == 0  # dry-run doesn't consume budget
    led.close()


def test_comment_failure_recorded(cfg):
    def boom(_args):
        raise MCPError("rate limited")

    forum, led = _forum(cfg, {"comment": boom})
    res = forum.comment(3, "hello")
    assert res["status"] == "error"
    assert led.count_today("comment") == 0
    row = led.conn.execute("SELECT success, error FROM actions WHERE kind='comment'").fetchone()
    assert row["success"] == 0 and "rate limited" in row["error"]
    led.close()


def test_ensure_registered_stores_secret(cfg):
    client = FakeMCPClient({"register": {"handle": "newbie", "secret": "abc123"}})
    led = Ledger(cfg.db_file)
    run = led.start_run()
    forum = Forum(client, led, cfg, run)
    ident = forum.ensure_registered()
    assert ident.secret == "abc123"
    # Persisted for next run.
    assert cfg.identity_file.exists()
    led.close()
