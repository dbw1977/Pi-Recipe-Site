"""Chunk E — meal planner + grocery persistence (aggregation itself is tested in TS)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.extraction import claude


def _make_recipe(client: TestClient, title: str) -> int:
    return client.post("/api/recipes", json={
        "title": title, "status": "published",
        "groups": [{"name": None, "ingredients": [{"quantity": 3, "unit": "clove", "name": "garlic", "scalable": 1}]}],
        "steps": [], "equipment": [], "tag_ids": [],
    }).json()["id"]


def test_plan_and_entries(client: TestClient):
    rid = _make_recipe(client, "Stir Fry")
    plan = client.post("/api/meal-plans", json={"start_date": "2026-08-22", "title": "This week"}).json()
    pid = plan["id"]
    # Add a recipe entry
    e = client.post(f"/api/meal-plans/{pid}/entries", json={"day_index": 0, "recipe_id": rid, "scale": 2})
    assert e.status_code == 201, e.text
    entry = e.json()
    assert entry["kind"] == "recipe" and entry["title"] == "Stir Fry" and entry["scale"] == 2
    # Exactly-one rule enforced
    bad = client.post(f"/api/meal-plans/{pid}/entries", json={"day_index": 1, "recipe_id": rid, "place_id": 1})
    assert bad.status_code == 400
    # Plan lists the entry
    got = client.get(f"/api/meal-plans/{pid}").json()
    assert len(got["entries"]) == 1
    # Remove it
    assert client.delete(f"/api/meal-plans/{pid}/entries/{entry['id']}").status_code == 204
    assert len(client.get(f"/api/meal-plans/{pid}").json()["entries"]) == 0


def test_grocery_generate_preserves_state(client: TestClient):
    plan = client.post("/api/meal-plans", json={"start_date": "2026-08-22"}).json()
    pid = plan["id"]

    # First generation: two computed lines (as the TS aggregator would post them).
    items = [
        {"name": "garlic", "unit": "clove", "display": "6 cloves", "base": 6, "family": "count", "aisle": "Produce", "recipes": ["Stir Fry", "Marinade"]},
        {"name": "olive oil", "unit": "cup", "display": "¼ cup + 2 tbsp", "base": 18, "family": "volume", "aisle": "Pantry", "recipes": ["Stir Fry"]},
    ]
    g = client.post(f"/api/meal-plans/{pid}/grocery/generate", json={"items": items}).json()
    assert {i["name"] for i in g} == {"garlic", "olive oil"}
    garlic = next(i for i in g if i["name"] == "garlic")
    assert garlic["display"] == "6 cloves" and garlic["recipes"] == ["Stir Fry", "Marinade"]

    # Check garlic off, add a manual item.
    client.patch(f"/api/meal-plans/{pid}/grocery/items/{garlic['id']}", json={"checked": True})
    client.post(f"/api/meal-plans/{pid}/grocery/items", json={"name": "paper towels", "aisle": "Other"})

    # Regenerate with an updated garlic quantity → checked state preserved, manual item kept.
    items2 = [
        {"name": "garlic", "unit": "clove", "display": "9 cloves", "base": 9, "family": "count", "aisle": "Produce", "recipes": ["Stir Fry", "Marinade", "Soup"]},
    ]
    g2 = client.post(f"/api/meal-plans/{pid}/grocery/generate", json={"items": items2}).json()
    names = {i["name"] for i in g2}
    assert "paper towels" in names  # manual survived
    garlic2 = next(i for i in g2 if i["name"] == "garlic")
    assert garlic2["display"] == "9 cloves"  # quantity refreshed
    assert garlic2["checked"] == 1  # checked state preserved on name+unit match
    assert "olive oil" not in names  # no longer contributed → dropped


def test_categorize_without_key_is_graceful(client: TestClient, monkeypatch):
    monkeypatch.setattr(claude, "available", lambda: False)
    r = client.post("/api/meal-plans/grocery/categorize", json={"names": ["dragonfruit"]})
    assert r.status_code == 200
    assert r.json() == {"available": False, "aisles": {}}
