"""Thumbnails + backup/restore (Chunk C)."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import backup, config, db


def _write_png(rel: str) -> None:
    from PIL import Image

    dest = config.media_root() / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1200, 900), (200, 120, 60)).save(dest, "PNG")


def test_thumbnail_generated_and_served(client: TestClient):
    _write_png("2026/08/shot.png")
    r = client.get("/thumb/2026/08/shot.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/webp"
    # Cached on local disk, downscaled to the configured max edge.
    cached = config.THUMBS_DIR / "2026/08/shot.png.webp"
    assert cached.is_file()
    from PIL import Image

    with Image.open(cached) as im:
        assert max(im.size) <= config.THUMB_MAX_PX


def test_thumbnail_missing_source_404(client: TestClient):
    assert client.get("/thumb/nope/missing.png").status_code == 404


def test_local_backup_and_restore_roundtrip(client: TestClient):
    rid = client.post("/api/recipes", json={
        "title": "Backup Me", "groups": [], "steps": [], "equipment": [], "tag_ids": [],
    }).json()["id"]

    # Nightly local snapshot.
    snap = backup.run_local()
    assert snap.is_file()
    with open(snap, "rb") as f:
        assert f.read(16) == b"SQLite format 3\x00"  # a real, consistent DB

    # Status recorded and surfaced.
    status = client.get("/api/backups/status").json()
    assert status["local"]["ok"] == 1
    assert status["local"]["size_bytes"] > 0

    # Simulate data loss, then restore from the snapshot.
    assert client.delete(f"/api/recipes/{rid}").status_code == 204
    assert client.get(f"/api/recipes/{rid}").status_code == 404
    backup.restore(str(snap))
    assert client.get(f"/api/recipes/{rid}").status_code == 200  # library reproduced


def test_local_backup_rotates(client: TestClient, monkeypatch):
    monkeypatch.setattr(config, "BACKUP_KEEP", 3)
    # Seed 5 old-looking snapshots, then a run should prune to the newest 3 (+today).
    config.BACKUP_LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    for day in range(1, 6):
        (config.BACKUP_LOCAL_DIR / f"recipes-2026010{day}.db").write_bytes(b"SQLite format 3\x00")
    backup.run_local()
    remaining = sorted(config.BACKUP_LOCAL_DIR.glob("recipes-*.db"))
    assert len(remaining) == 3


def test_drive_backup_skips_without_config(client: TestClient, monkeypatch):
    monkeypatch.setattr(config, "DRIVE_BACKUP_FOLDER_ID", "")
    assert backup.run_drive() is None
    status = client.get("/api/backups/status").json()
    assert status["drive"]["ok"] == 0  # recorded as a clear skip, not a crash
