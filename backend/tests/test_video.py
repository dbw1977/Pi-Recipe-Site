"""Video import: frame sampling gate + wiring (ffmpeg and Claude mocked)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.extraction import claude, video
from app.extraction.draft import ExtractedRecipe


def _fake_extracted() -> ExtractedRecipe:
    return ExtractedRecipe(
        title="One-Pan Chicken",
        groups=[{"name": None, "ingredients": [
            {"quantity": 2, "unit": "tbsp", "name": "olive oil", "scalable": 1},
        ]}],
        steps=["Sear the chicken.", "Simmer 10 minutes."],
        tags={"Protein": ["Chicken"]},
    )


def test_status_reports_video(client: TestClient, monkeypatch):
    monkeypatch.setattr(claude, "available", lambda: True)
    monkeypatch.setattr(video, "frames_available", lambda: True)
    assert client.get("/api/imports/status").json()["video"] is True

    monkeypatch.setattr(video, "frames_available", lambda: False)
    assert client.get("/api/imports/status").json()["video"] is False


def test_video_without_key_is_503(client: TestClient, monkeypatch):
    monkeypatch.setattr(claude, "available", lambda: False)
    r = client.post("/api/imports/screenshot", files={"file": ("clip.mp4", b"\x00\x00", "video/mp4")})
    assert r.status_code == 503
    assert "ANTHROPIC_API_KEY" in r.json()["detail"]


def test_video_without_ffmpeg_is_503(client: TestClient, monkeypatch):
    monkeypatch.setattr(claude, "available", lambda: True)
    monkeypatch.setattr(video, "frames_available", lambda: False)
    r = client.post("/api/imports/screenshot", files={"file": ("clip.mp4", b"\x00\x00", "video/mp4")})
    assert r.status_code == 503
    assert "ffmpeg" in r.json()["detail"].lower()


def test_video_import_samples_frames_and_sets_hero(client: TestClient, monkeypatch):
    monkeypatch.setattr(claude, "available", lambda: True)
    monkeypatch.setattr(video, "frames_available", lambda: True)
    # Pretend ffmpeg gave us three frames; capture what vision was asked to read.
    seen = {}
    monkeypatch.setattr(video, "extract_frames", lambda *a, **k: [b"f1", b"f2", b"f3"])

    def fake_images(images, allowed, **k):
        seen["n"] = len(images)
        return _fake_extracted()

    monkeypatch.setattr(claude, "extract_from_images", fake_images)

    r = client.post("/api/imports/screenshot", files={"file": ("clip.mp4", b"\x00\x00", "video/mp4")})
    assert r.status_code == 200, r.text
    draft = r.json()["draft"]
    assert seen["n"] == 3  # all frames handed to vision
    assert draft["source_type"] == "video"
    assert draft["hero_image"]  # a frame was saved and set as the hero
    assert {t["name"] for t in draft["tags"]} >= {"Chicken"}


def test_video_cover_photo_overrides_frame_hero(client: TestClient, monkeypatch):
    monkeypatch.setattr(claude, "available", lambda: True)
    monkeypatch.setattr(video, "frames_available", lambda: True)
    monkeypatch.setattr(video, "extract_frames", lambda *a, **k: [b"f1", b"f2"])
    monkeypatch.setattr(claude, "extract_from_images", lambda *a, **k: _fake_extracted())

    r = client.post(
        "/api/imports/screenshot",
        files=[
            ("file", ("clip.mp4", b"\x00\x00", "video/mp4")),
            ("extra", ("cover.jpg", b"\xff\xd8cover", "image/jpeg")),
        ],
    )
    assert r.status_code == 200, r.text
    draft = r.json()["draft"]
    assert draft["hero_image"].endswith((".jpg", ".jpeg"))
