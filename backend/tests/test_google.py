"""Google connect endpoints (OAuth code-paste flow). No live Google calls."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.extraction import drive


def test_status_unconfigured(client: TestClient):
    s = client.get("/api/google/status").json()
    assert s["configured"] is False
    assert s["authorized"] is False
    assert s["drive_backup_ready"] is False


def test_auth_url_without_secrets_is_503(client: TestClient):
    r = client.get("/api/google/auth-url")
    assert r.status_code == 503
    assert "GOOGLE_CLIENT_SECRETS" in r.json()["detail"]


def test_connect_requires_a_code(client: TestClient):
    assert client.post("/api/google/connect", json={"code": "  "}).status_code == 400


def test_status_reflects_authorization(client: TestClient, monkeypatch, tmp_path):
    # Pretend a token exists and secrets + a backup folder are configured.
    monkeypatch.setattr(drive, "client_configured", lambda: True)
    monkeypatch.setattr(drive, "authorized", lambda: True)
    from app import config
    monkeypatch.setattr(config, "DRIVE_BACKUP_FOLDER_ID", "folder123")
    s = client.get("/api/google/status").json()
    assert s["configured"] is True and s["authorized"] is True
    assert s["drive_backup_ready"] is True
