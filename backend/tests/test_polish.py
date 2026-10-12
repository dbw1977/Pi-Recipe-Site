"""Thumbnails (Chunk C). Backup/restore tests live in test_backup.py."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import config


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
