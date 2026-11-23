from agent.ledger import Ledger


def test_budget_counts_only_successful_same_day(cfg):
    led = Ledger(cfg.db_file)
    run = led.start_run()
    led.record_action(run, "vote", target_type="post", target_id=1, success=True)
    led.record_action(run, "vote", target_type="post", target_id=2, success=True)
    led.record_action(run, "vote", target_type="post", target_id=3, success=False, error="boom")
    assert led.count_today("vote") == 2
    assert led.count_today("comment") == 0
    led.close()


def test_already_acted_dedup(cfg):
    led = Ledger(cfg.db_file)
    run = led.start_run()
    assert not led.already_acted("vote", "post", 10)
    led.record_action(run, "vote", target_type="post", target_id=10, success=True)
    assert led.already_acted("vote", "post", 10)
    assert not led.already_acted("vote", "comment", 10)
    led.close()


def test_recent_post_titles(cfg):
    led = Ledger(cfg.db_file)
    run = led.start_run()
    led.record_action(run, "post", summary="Hello world", success=True)
    led.record_action(run, "post", summary="Second post", success=True)
    titles = led.recent_post_titles()
    assert titles == ["Second post", "Hello world"]
    led.close()


def test_wal_mode_enabled(cfg):
    led = Ledger(cfg.db_file)
    mode = led.conn.execute("PRAGMA journal_mode;").fetchone()[0]
    assert mode.lower() == "wal"
    led.close()
