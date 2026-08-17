"""Chunk D — Places: CRUD, city/tag filtering, tag scoping, screenshot import."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.extraction import claude
from app.extraction.draft import ExtractedPlace


def _cuisine_id(client: TestClient, name: str = "Thai") -> int:
    cats = client.get("/api/tags", params={"collection": "place"}).json()
    cuisine = next(c for c in cats if c["name"] == "Cuisine")
    return next(t["id"] for t in cuisine["tags"] if t["name"] == name)


def test_tag_scoping_recipe_vs_place(client: TestClient):
    recipe_cats = {c["name"] for c in client.get("/api/tags").json()}
    place_cats = {c["name"] for c in client.get("/api/tags", params={"collection": "place"}).json()}
    # Cuisine is shared; place-only dimensions never leak into the recipe UI, and vice-versa.
    assert "Cuisine" in recipe_cats and "Cuisine" in place_cats
    assert "Place Type" in place_cats and "Price" in place_cats and "City/Area" in place_cats
    assert "Place Type" not in recipe_cats and "Price" not in recipe_cats
    assert "Protein" in recipe_cats and "Protein" not in place_cats


def test_create_place_with_dishes_and_filters(client: TestClient):
    payload = {
        "name": "Birrieria La Plaza",
        "place_type": "restaurant",
        "city": "Gainesville",
        "maps_url": "https://maps.google.com/?q=birrieria",
        "price_level": 2,
        "our_rating": 5,
        "visited": 1,
        "dishes": [
            {"name": "birria tacos", "note": "extra consommé", "must_order": 1},
            {"name": "horchata", "must_order": 0},
        ],
        "tag_ids": [_cuisine_id(client, "Mexican")],
    }
    r = client.post("/api/places", json=payload)
    assert r.status_code == 201, r.text
    place = r.json()
    assert place["name"] == "Birrieria La Plaza"
    assert {d["name"] for d in place["dishes"]} == {"birria tacos", "horchata"}
    # City, Place Type, Price are mirrored into tags for filtering; Cuisine came in explicitly.
    tagnames = {t["name"] for t in place["tags"]}
    assert {"Gainesville", "Restaurant", "$$", "Mexican"} <= tagnames

    # Shows up under Eat Out, filterable by city and by a tag.
    assert len(client.get("/api/places").json()) == 1
    assert len(client.get("/api/places", params={"city": "Gainesville"}).json()) == 1
    assert len(client.get("/api/places", params={"city": "Austin"}).json()) == 0
    mex = _cuisine_id(client, "Mexican")
    assert len(client.get("/api/places", params={"tags": str(mex)}).json()) == 1
    # Cities endpoint reflects it.
    assert "Gainesville" in client.get("/api/places/cities").json()
    # Recipes are untouched by any of this.
    assert client.get("/api/recipes").json() == []


def test_place_search(client: TestClient):
    client.post("/api/places", json={"name": "Thai Basil", "city": "Gainesville",
                                     "dishes": [{"name": "drunken noodles"}]})
    assert len(client.get("/api/places", params={"q": "drunken"}).json()) == 1
    assert len(client.get("/api/places", params={"q": "sushi"}).json()) == 0


def test_place_update_and_delete(client: TestClient):
    pid = client.post("/api/places", json={"name": "Temp Spot", "city": "Gainesville"}).json()["id"]
    r = client.put(f"/api/places/{pid}", json={"name": "Renamed Spot", "city": "Austin", "visited": 0})
    assert r.status_code == 200 and r.json()["name"] == "Renamed Spot"
    assert r.json()["city"] == "Austin"
    assert client.delete(f"/api/places/{pid}").status_code == 204
    assert client.get(f"/api/places/{pid}").status_code == 404


def test_place_screenshot_import_and_approve(client: TestClient, monkeypatch):
    monkeypatch.setattr(claude, "available", lambda: True)
    monkeypatch.setattr(
        claude, "extract_place_from_images",
        lambda *a, **k: ExtractedPlace(
            name="Taco Spot", place_type="taco stand", city="Gainesville",
            our_notes="cash only", source_name="@foodie",
            dishes=[{"name": "al pastor", "must_order": 1}], cuisine=["Mexican"],
        ),
    )
    r = client.post("/api/imports/place/screenshot",
                    files={"file": ("rec.jpg", b"\xff\xd8x", "image/jpeg")})
    assert r.status_code == 200, r.text
    draft = r.json()["draft"]
    assert draft["status"] == "draft" and draft["name"] == "Taco Spot"
    assert draft["dishes"][0]["name"] == "al pastor"
    assert draft["hero_image"]
    # It's in the place drafts queue, not published yet.
    assert len(client.get("/api/places/drafts").json()) == 1
    assert len(client.get("/api/places").json()) == 0
    # Approve publishes it.
    assert client.post(f"/api/places/{draft['id']}/approve").status_code == 200
    assert len(client.get("/api/places").json()) == 1


def test_place_screenshot_without_key_is_503(client: TestClient, monkeypatch):
    monkeypatch.setattr(claude, "available", lambda: False)
    r = client.post("/api/imports/place/screenshot",
                    files={"file": ("rec.jpg", b"\xff\xd8x", "image/jpeg")})
    assert r.status_code == 503
    assert "ANTHROPIC_API_KEY" in r.json()["detail"]
