"""CRUD + fixture round-trip tests."""
from __future__ import annotations

from fastapi.testclient import TestClient

from .fixtures import steak_salad_payload


def _tag_id(client: TestClient, category: str, name: str) -> int:
    cats = client.get("/api/tags").json()
    for c in cats:
        if c["name"] == category:
            for t in c["tags"]:
                if t["name"] == name:
                    return t["id"]
    raise AssertionError(f"tag {category}/{name} not seeded")


def test_health(client: TestClient):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_taxonomy_seeded(client: TestClient):
    cats = client.get("/api/tags").json()
    names = {c["name"] for c in cats}
    assert {"Course", "Cuisine", "Protein", "Dietary", "Method", "Time", "Occasion"} <= names
    # A couple of specific tags from spec §8.
    assert _tag_id(client, "Method", "No-Cook")
    assert _tag_id(client, "Course", "Salad")


def test_create_and_get_fixture(client: TestClient):
    tags = [
        _tag_id(client, "Course", "Salad"),
        _tag_id(client, "Course", "Main"),
        _tag_id(client, "Cuisine", "American"),
        _tag_id(client, "Protein", "Beef"),
        _tag_id(client, "Method", "Grill"),
        _tag_id(client, "Method", "No-Cook"),
        _tag_id(client, "Time", "Quick (<30 min)"),
    ]
    r = client.post("/api/recipes", json=steak_salad_payload(tags))
    assert r.status_code == 201, r.text
    created = r.json()
    rid = created["id"]

    got = client.get(f"/api/recipes/{rid}").json()
    assert got["title"] == "Apple Cheddar Steak Salad"
    assert got["source_handle"] == "@chacekitchen"
    assert len(got["groups"]) == 2
    # Assembly group has no-quantity items; dressing has the scalable ones.
    salad, dressing = got["groups"]
    assert salad["name"] == "For the salad"
    assert all(i["quantity"] is None for i in salad["ingredients"])
    honey = next(i for i in dressing["ingredients"] if i["name"] == "honey")
    assert honey["quantity"] == 1.5 and honey["unit"] == "tbsp" and honey["scalable"] == 1
    saltpep = next(i for i in dressing["ingredients"] if i["name"] == "salt and pepper")
    assert saltpep["scalable"] == 0
    assert len(got["equipment"]) == 5
    assert all(e["inferred"] == 1 for e in got["equipment"])
    assert got["steps"] == []
    assert len(got["tags"]) == 7


def test_update_recipe(client: TestClient):
    rid = client.post("/api/recipes", json=steak_salad_payload()).json()["id"]
    payload = steak_salad_payload()
    payload["title"] = "Apple Cheddar Steak Salad (v2)"
    payload["steps"] = [{"text": "Grill the steak, slice, assemble, dress.", "sort_order": 0}]
    r = client.put(f"/api/recipes/{rid}", json=payload)
    assert r.status_code == 200
    got = client.get(f"/api/recipes/{rid}").json()
    assert got["title"].endswith("(v2)")
    assert len(got["steps"]) == 1


def test_delete_recipe(client: TestClient):
    rid = client.post("/api/recipes", json=steak_salad_payload()).json()["id"]
    assert client.delete(f"/api/recipes/{rid}").status_code == 204
    assert client.get(f"/api/recipes/{rid}").status_code == 404


def test_empty_query_returns_full_grid(client: TestClient):
    client.post("/api/recipes", json=steak_salad_payload())
    cards = client.get("/api/recipes").json()
    assert len(cards) == 1
    assert cards[0]["title"] == "Apple Cheddar Steak Salad"
