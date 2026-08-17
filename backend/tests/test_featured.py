"""Recipe of the Week (spec §9)."""
from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from app import db, featured


def _make(client: TestClient, title: str) -> int:
    return client.post("/api/recipes", json={
        "title": title, "groups": [], "steps": [], "equipment": [], "tag_ids": [],
    }).json()["id"]


def test_empty_library_has_no_feature(client: TestClient):
    r = client.get("/api/featured").json()
    assert r["recipe"] is None


def test_deterministic_and_stable_within_week(client: TestClient):
    ids = [_make(client, f"Recipe {i}") for i in range(5)]
    conn = db.get_connection()
    try:
        week = date(2026, 8, 17)
        first = featured.get_featured(conn, today=week)
        assert first["recipe"]["id"] in ids
        # Same week → same pick, every time.
        again = featured.get_featured(conn, today=week)
        assert again["recipe"]["id"] == first["recipe"]["id"]
        assert again["pinned"] is False
    finally:
        conn.close()


def test_pick_avoids_recent_until_cycled(client: TestClient):
    ids = [_make(client, f"R{i}") for i in range(4)]
    conn = db.get_connection()
    try:
        picks = []
        # Four consecutive ISO weeks should cover all four recipes before repeating.
        for wk in [date(2026, 8, 17), date(2026, 8, 24), date(2026, 8, 31), date(2026, 9, 7)]:
            picks.append(featured.get_featured(conn, today=wk)["recipe"]["id"])
        assert set(picks) == set(ids)  # cycled through the whole library
    finally:
        conn.close()


def test_manual_pin_overrides(client: TestClient):
    ids = [_make(client, f"P{i}") for i in range(3)]
    target = ids[-1]
    r = client.post(f"/api/featured/{target}/pin").json()
    assert r["recipe"]["id"] == target and r["pinned"] is True
    # Still pinned on a plain GET.
    assert client.get("/api/featured").json()["recipe"]["id"] == target
    # Unpin reverts to the automatic pick.
    r2 = client.delete("/api/featured/pin").json()
    assert r2["pinned"] is False


def test_pin_unknown_recipe_404(client: TestClient):
    assert client.post("/api/featured/9999/pin").status_code == 404
