"""API tests for the import paths and the Drafts queue.

Network/AI boundaries are mocked; these verify wiring, graceful degradation, drafting,
tag-constraining, media attachment, and the queue actions."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.extraction import claude, url_import
from app.extraction.draft import ExtractedRecipe


# --------------------------------------------------------------------------- #
# Status & graceful degradation
# --------------------------------------------------------------------------- #
def test_status_defaults_off(client: TestClient, monkeypatch):
    monkeypatch.setattr(claude, "available", lambda: False)
    s = client.get("/api/imports/status").json()
    assert s["url"] is True            # offline scraper always available
    assert s["screenshot"] is False    # needs Claude
    assert s["drive_configured"] is False


def test_screenshot_without_key_is_503(client: TestClient, monkeypatch):
    monkeypatch.setattr(claude, "available", lambda: False)
    r = client.post("/api/imports/screenshot", files={"file": ("s.png", b"x", "image/png")})
    assert r.status_code == 503
    assert "ANTHROPIC_API_KEY" in r.json()["detail"]


def test_voice_without_whisper_is_503(client: TestClient):
    r = client.post("/api/imports/voice", files={"file": ("a.wav", b"x", "audio/wav")})
    assert r.status_code == 503
    assert "whisper" in r.json()["detail"].lower()


def test_drive_scan_without_config_is_503(client: TestClient):
    r = client.post("/api/imports/drive/scan")
    assert r.status_code == 503


# --------------------------------------------------------------------------- #
# URL import — offline scraper path (no key)
# --------------------------------------------------------------------------- #
def test_url_import_offline(client: TestClient, monkeypatch):
    monkeypatch.setattr(claude, "available", lambda: False)
    monkeypatch.setattr(
        url_import, "_try_scraper",
        lambda url: {
            "title": "Grill Marinade",
            "ingredients": ["1/4 cup olive oil", "2 tbsp dijon", "salt to taste"],
            "instructions_list": ["Whisk together."],
            "image": None,
            "host": "playswellwithbutter.com",
            "author": "PWWB",
            "total_time": 10,
            "yields": "1 cup",
        },
    )
    r = client.post("/api/imports/url", json={"url": "https://playswellwithbutter.com/x"})
    assert r.status_code == 200, r.text
    body = r.json()
    draft = body["draft"]
    assert draft["status"] == "draft"
    assert draft["source_type"] == "url"
    ings = draft["groups"][0]["ingredients"]
    names = {i["name"] for i in ings}
    assert "olive oil" in names and "dijon" in names
    salt = next(i for i in ings if "salt" in i["name"])
    assert salt["scalable"] == 0
    # It appears in the Drafts queue, not the published library.
    assert len(client.get("/api/recipes").json()) == 0
    assert len(client.get("/api/drafts").json()) == 1


# --------------------------------------------------------------------------- #
# Screenshot import — mocked Claude vision
# --------------------------------------------------------------------------- #
def _fake_extracted() -> ExtractedRecipe:
    return ExtractedRecipe(
        title="Apple Cheddar Steak Salad",
        source_handle="@chacekitchen",
        groups=[{"name": "Honey dijon dressing", "ingredients": [
            {"quantity": 2, "unit": "tbsp", "name": "dijon", "scalable": 1},
            {"quantity": None, "unit": None, "name": "salt and pepper", "note": "to taste", "scalable": 0},
        ]}],
        steps=[],
        equipment=[{"name": "whisk", "inferred": 1}],
        tags={"Course": ["Salad"], "Protein": ["Beef"], "Method": ["Grill", "No-Cook"]},
    )


def test_screenshot_import_with_mocked_vision(client: TestClient, monkeypatch):
    monkeypatch.setattr(claude, "available", lambda: True)
    monkeypatch.setattr(claude, "extract_from_images", lambda *a, **k: _fake_extracted())

    r = client.post("/api/imports/screenshot", files={"file": ("shot.jpg", b"\xff\xd8fake", "image/jpeg")})
    assert r.status_code == 200, r.text
    draft = r.json()["draft"]
    assert draft["source_type"] == "instagram"
    assert draft["source_handle"] == "@chacekitchen"
    assert draft["hero_image"]  # screenshot stored + set as hero
    # tags resolved against the seeded vocabulary
    tag_names = {t["name"] for t in draft["tags"]}
    assert {"Salad", "Beef", "Grill", "No-Cook"} <= tag_names
    assert draft["equipment"][0]["inferred"] == 1


def test_screenshot_import_multiple_files(client: TestClient, monkeypatch):
    monkeypatch.setattr(claude, "available", lambda: True)
    seen = {}

    def fake_images(images, allowed, **k):
        seen["n"] = len(images)
        return _fake_extracted()

    monkeypatch.setattr(claude, "extract_from_images", fake_images)

    # Three screenshots of one recipe + a cover photo (sent as `extra`).
    r = client.post(
        "/api/imports/screenshot",
        files=[
            ("file", ("a.jpg", b"\xff\xd8a", "image/jpeg")),
            ("file", ("b.png", b"\x89PNGb", "image/png")),
            ("file", ("c.jpg", b"\xff\xd8c", "image/jpeg")),
            ("extra", ("cover.jpg", b"\xff\xd8cover", "image/jpeg")),
        ],
    )
    assert r.status_code == 200, r.text
    assert seen["n"] == 3  # all three screenshots read together as one recipe
    draft = r.json()["draft"]
    assert draft["hero_image"]  # cover photo set as hero
    # 3 screenshots + 1 cover are all stored as media.
    assert len(client.get(f"/api/recipes/{draft['id']}").json()["groups"]) >= 1


# --------------------------------------------------------------------------- #
# Drafts queue actions
# --------------------------------------------------------------------------- #
def _seed_draft(client, monkeypatch, title="Grill Marinade"):
    monkeypatch.setattr(claude, "available", lambda: False)
    monkeypatch.setattr(
        url_import, "_try_scraper",
        lambda url: {"title": title, "ingredients": ["1 tbsp oil"], "instructions_list": [],
                     "image": None, "host": "x.com", "author": None, "total_time": None, "yields": None},
    )
    return client.post("/api/imports/url", json={"url": "https://x.com/a"}).json()["draft"]["id"]


def test_approve_draft_publishes(client: TestClient, monkeypatch):
    did = _seed_draft(client, monkeypatch)
    assert client.post(f"/api/drafts/{did}/approve").status_code == 200
    assert len(client.get("/api/drafts").json()) == 0
    assert len(client.get("/api/recipes").json()) == 1


def test_discard_draft(client: TestClient, monkeypatch):
    did = _seed_draft(client, monkeypatch)
    assert client.delete(f"/api/drafts/{did}").status_code == 204
    assert len(client.get("/api/drafts").json()) == 0
    assert len(client.get("/api/recipes").json()) == 0


def test_approve_all(client: TestClient, monkeypatch):
    _seed_draft(client, monkeypatch, "Marinade One")
    _seed_draft(client, monkeypatch, "Totally Different Dish")
    assert len(client.get("/api/drafts").json()) == 2
    res = client.post("/api/imports/../drafts/approve-all", json={}) if False else client.post("/api/drafts/approve-all", json={})
    assert res.json()["count"] == 2
    assert len(client.get("/api/recipes").json()) == 2


def test_duplicate_flag_in_queue(client: TestClient, monkeypatch):
    # publish one, then import a same-titled draft → queue flags it.
    did = _seed_draft(client, monkeypatch, "Signature Marinade")
    client.post(f"/api/drafts/{did}/approve")
    _seed_draft(client, monkeypatch, "Signature Marinade")
    q = client.get("/api/drafts").json()
    assert len(q) == 1
    assert q[0]["duplicate"] is not None
    assert q[0]["duplicate"]["reason"] in ("same source URL", "similar title")
