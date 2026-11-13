"""Pytest fixtures: each test gets a throwaway SQLite DB on local disk."""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch) -> TestClient:
    # Point the app at a fresh temp DB before it runs migrations.
    from app import config, db

    test_db = tmp_path / "test-recipes.db"
    monkeypatch.setattr(config, "DB_PATH", test_db)
    # Keep imported media, thumbnails, and backups out of the repo during tests.
    monkeypatch.setattr(config, "MEDIA_ROOT", tmp_path / "media")
    monkeypatch.setattr(config, "THUMBS_DIR", tmp_path / "thumbs")
    monkeypatch.setattr(config, "BACKUP_LOCAL_DIR", tmp_path / "backups")

    # main imports config at module load; reload so create_app() sees the patched path
    # via db.get_connection() (which reads config.DB_PATH lazily at call time).
    from app import main
    importlib.reload(main)

    app = main.create_app()
    with TestClient(app) as c:  # triggers startup -> migrations + seed
        yield c
        # Backups/restores run on background threads that read config.DB_PATH when they run. If one
        # outlives its test it would write into the NEXT test's database, so wait for it here.
        import time

        from app import backup

        deadline = time.time() + 20
        while backup.current()["running"] and time.time() < deadline:
            time.sleep(0.02)
        assert not backup.current()["running"], "a background backup/restore outlived its test"
