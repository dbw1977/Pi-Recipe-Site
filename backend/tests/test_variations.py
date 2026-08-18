"""Chunk F — AI recipe variations + photo upload (Claude mocked)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.extraction import claude
from app.extraction.draft import ExtractedRecipe


def _make_recipe(client: TestClient, title="Bacon Jam Burgers") -> int:
    return client.post("/api/recipes", json={
        "title": title, "status": "published", "servings_base": 4, "servings_unit": "burgers",
        "source_name": "Over The Fire Cooking", "source_handle": "@overthefirecooking",
        "groups": [{"name": None, "ingredients": [{"quantity": 1, "unit": "lb", "name": "ground beef", "scalable": 1}]}],
        "steps": [{"text": "Grill the patties."}], "equipment": [{"name": "grill", "inferred": 0}], "tag_ids": [],
    }).json()["id"]


def test_variation_without_key_is_503(client: TestClient, monkeypatch):
    monkeypatch.setattr(claude, "available", lambda: False)
    rid = _make_recipe(client)
    r = client.post(f"/api/recipes/{rid}/variations", json={"instruction": "patty melt version"})
    assert r.status_code == 503
    assert "ANTHROPIC_API_KEY" in r.json()["detail"]


def test_variation_creates_marked_draft(client: TestClient, monkeypatch):
    monkeypatch.setattr(claude, "available", lambda: True)
    seen = {}

    def fake_gen(source, instruction, allowed):
        seen["instruction"] = instruction
        seen["source_title"] = source["title"]
        return ExtractedRecipe(
            title="Patty Melt Burgers",
            groups=[{"name": None, "ingredients": [
                {"quantity": 1, "unit": "lb", "name": "ground beef", "scalable": 1},
                {"quantity": 4, "unit": "slice", "name": "swiss cheese", "scalable": 1},
            ]}],
            steps=["Griddle the rye.", "Assemble and griddle the sandwich."],
            equipment=[{"name": "griddle", "inferred": 1}],
            tags={"Course": ["Main"]},
        )

    monkeypatch.setattr(claude, "generate_variation", fake_gen)
    rid = _make_recipe(client)
    r = client.post(f"/api/recipes/{rid}/variations", json={"instruction": "make me a patty melt version"})
    assert r.status_code == 200, r.text
    draft = r.json()["draft"]
    assert seen["source_title"] == "Bacon Jam Burgers"
    # Persisted as a draft, marked generated, lineage stored, source_type 'ai'.
    assert draft["status"] == "draft"
    assert draft["generated"] == 1
    assert draft["derived_from_recipe_id"] == rid
    assert draft["derived_from_title"] == "Bacon Jam Burgers"
    assert draft["generation_prompt"] == "make me a patty melt version"
    assert draft["source_type"] == "ai"
    # Original human creator is NOT credited on the variation.
    assert draft["source_name"] != "Over The Fire Cooking"
    assert draft["source_handle"] != "@overthefirecooking"
    # Base servings kept from the source since the model didn't set them.
    assert draft["servings_base"] == 4
    # It's in the Drafts queue, not published.
    assert len(client.get("/api/drafts").json()) == 1
    assert len(client.get("/api/recipes").json()) == 1  # only the original


def test_variation_missing_instruction_400(client: TestClient, monkeypatch):
    monkeypatch.setattr(claude, "available", lambda: True)
    rid = _make_recipe(client)
    assert client.post(f"/api/recipes/{rid}/variations", json={"instruction": "  "}).status_code == 400


def test_photo_upload_sets_hero(client: TestClient):
    rid = _make_recipe(client)
    # A tiny valid PNG (1x1). Pillow processes it; if absent, it's stored raw — both fine.
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000d49444154789c6360000002000100" "05fe02fe" "dccc59e70000000049454e44ae426082"
    )
    up = client.post("/api/media/upload", files={"file": ("photo.png", png, "image/png")})
    assert up.status_code == 200, up.text
    path = up.json()["path"]
    assert path
    r = client.post(f"/api/recipes/{rid}/hero", json={"hero_image": path})
    assert r.status_code == 200
    assert r.json()["hero_image"] == path


def test_photo_upload_rejects_non_image(client: TestClient):
    r = client.post("/api/media/upload", files={"file": ("x.txt", b"hello", "text/plain")})
    assert r.status_code == 400
