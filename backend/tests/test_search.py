"""FTS search + tag filter tests (spec §9)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from .fixtures import steak_salad_payload


def _tag_id(client: TestClient, category: str, name: str) -> int:
    for c in client.get("/api/tags").json():
        if c["name"] == category:
            for t in c["tags"]:
                if t["name"] == name:
                    return t["id"]
    raise AssertionError(f"tag {category}/{name} not seeded")


def _seed(client: TestClient) -> int:
    tags = [
        _tag_id(client, "Course", "Salad"),
        _tag_id(client, "Protein", "Beef"),
        _tag_id(client, "Method", "Grill"),
    ]
    return client.post("/api/recipes", json=steak_salad_payload(tags)).json()["id"]


def test_search_by_title(client: TestClient):
    _seed(client)
    assert len(client.get("/api/recipes", params={"q": "steak"}).json()) == 1
    assert len(client.get("/api/recipes", params={"q": "nonexistent"}).json()) == 0


def test_search_by_ingredient(client: TestClient):
    _seed(client)
    assert len(client.get("/api/recipes", params={"q": "dijon"}).json()) == 1


def test_search_by_source_handle(client: TestClient):
    _seed(client)
    assert len(client.get("/api/recipes", params={"q": "chacekitchen"}).json()) == 1


def test_search_by_tag_text(client: TestClient):
    _seed(client)
    # "grill" appears as a tag name; FTS indexes tag names too.
    assert len(client.get("/api/recipes", params={"q": "grill"}).json()) == 1


def test_prefix_match(client: TestClient):
    _seed(client)
    # "avo" -> avocado (from the assembly list ingredient "avocado slices")
    assert len(client.get("/api/recipes", params={"q": "avo"}).json()) == 1


def test_tag_filter(client: TestClient):
    _seed(client)
    beef = _tag_id(client, "Protein", "Beef")
    chicken = _tag_id(client, "Protein", "Chicken")
    assert len(client.get("/api/recipes", params={"tags": str(beef)}).json()) == 1
    assert len(client.get("/api/recipes", params={"tags": str(chicken)}).json()) == 0


def test_tag_filter_combines_with_search(client: TestClient):
    _seed(client)
    beef = _tag_id(client, "Protein", "Beef")
    # matching search + matching tag
    assert len(client.get("/api/recipes", params={"q": "steak", "tags": str(beef)}).json()) == 1
    # matching tag but non-matching search
    assert len(client.get("/api/recipes", params={"q": "zzz", "tags": str(beef)}).json()) == 0


def test_multi_tag_is_and(client: TestClient):
    _seed(client)
    salad = _tag_id(client, "Course", "Salad")
    grill = _tag_id(client, "Method", "Grill")
    dessert = _tag_id(client, "Course", "Dessert")
    # has both salad AND grill
    assert len(client.get("/api/recipes", params={"tags": f"{salad},{grill}"}).json()) == 1
    # does not have dessert
    assert len(client.get("/api/recipes", params={"tags": f"{salad},{dessert}"}).json()) == 0


def test_fts_stays_in_sync_on_update(client: TestClient):
    rid = _seed(client)
    # Rename an ingredient to a token that appears nowhere else, then verify the index
    # follows the rename (old token gone, new token found). ("chives" appears only once.)
    assert len(client.get("/api/recipes", params={"q": "chives"}).json()) == 1
    payload = steak_salad_payload()
    payload["groups"][1]["ingredients"][6]["name"] = "zztarragon"  # was "fresh chives"
    client.put(f"/api/recipes/{rid}", json=payload)
    assert len(client.get("/api/recipes", params={"q": "chives"}).json()) == 0
    assert len(client.get("/api/recipes", params={"q": "zztarragon"}).json()) == 1
