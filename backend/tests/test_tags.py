"""Tag vocabulary management: add + delete."""
from __future__ import annotations

from fastapi.testclient import TestClient


def _course_category_id(client: TestClient) -> int:
    cats = client.get("/api/tags").json()
    return next(c["id"] for c in cats if c["name"] == "Course")


def test_add_tag(client: TestClient):
    cid = _course_category_id(client)
    r = client.post("/api/tags", json={"category_id": cid, "name": "Taco Night"})
    assert r.status_code == 201, r.text
    assert r.json()["name"] == "Taco Night" and r.json()["category"] == "Course"
    # It now appears in the listing.
    names = {t["name"] for c in client.get("/api/tags").json() for t in c["tags"]}
    assert "Taco Night" in names


def test_add_tag_unknown_category_404(client: TestClient):
    r = client.post("/api/tags", json={"category_id": 9999, "name": "Nope"})
    assert r.status_code == 404


def test_delete_tag(client: TestClient):
    cid = _course_category_id(client)
    tid = client.post("/api/tags", json={"category_id": cid, "name": "Disposable"}).json()["id"]
    assert client.delete(f"/api/tags/{tid}").status_code == 204
    names = {t["name"] for c in client.get("/api/tags").json() for t in c["tags"]}
    assert "Disposable" not in names


def test_delete_missing_tag_404(client: TestClient):
    assert client.delete("/api/tags/999999").status_code == 404
