"""Eat Out paging + sorting (mirrors the recipe library; rating = our_rating)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import db


def _make(client: TestClient, name: str, added: str | None = None, **extra) -> int:
    pid = client.post("/api/places", json={"name": name, **extra}).json()["id"]
    if added:  # pin both timestamps so ordering doesn't depend on the clock
        conn = db.get_connection()
        try:
            conn.execute(
                "UPDATE place SET created_at = ?, updated_at = ? WHERE id = ?", (added, added, pid)
            )
            conn.commit()
        finally:
            conn.close()
    return pid


def _names(client: TestClient, **params) -> list[str]:
    r = client.get("/api/places", params=params)
    assert r.status_code == 200, r.text
    return [c["name"] for c in r.json()]


# --- paging ---------------------------------------------------------------- #
def test_pages_and_total_header(client: TestClient):
    for i in range(5):
        _make(client, f"Place {i}", added=f"2026-01-0{i + 1}T00:00:00+00:00")
    seen = []
    for offset, expected in ((0, 2), (2, 2), (4, 1), (6, 0)):
        r = client.get("/api/places", params={"sort": "oldest", "limit": 2, "offset": offset})
        assert r.status_code == 200
        assert r.headers["X-Total-Count"] == "5"  # total, not the page size
        assert len(r.json()) == expected
        seen += [c["name"] for c in r.json()]
    assert seen == [f"Place {i}" for i in range(5)]  # no gaps or repeats across pages


def test_no_limit_returns_everything_with_total(client: TestClient):
    for i in range(3):
        _make(client, f"P{i}")
    r = client.get("/api/places")
    assert len(r.json()) == 3 and r.headers["X-Total-Count"] == "3"


def test_total_respects_search_city_and_tags(client: TestClient):
    cats = client.get("/api/tags", params={"collection": "place"}).json()
    cuisine = next(c for c in cats if c["name"] == "Cuisine")
    thai = next(t["id"] for t in cuisine["tags"] if t["name"] == "Thai")
    _make(client, "Thai Basil", city="Gainesville", tag_ids=[thai])
    _make(client, "Thai Orchid", city="Austin")
    _make(client, "Pizza Place", city="Gainesville")
    r = client.get("/api/places", params={"q": "thai", "limit": 1})
    assert len(r.json()) == 1 and r.headers["X-Total-Count"] == "2"
    r = client.get("/api/places", params={"city": "Gainesville", "limit": 1})
    assert len(r.json()) == 1 and r.headers["X-Total-Count"] == "2"
    r = client.get("/api/places", params={"tags": str(thai), "limit": 5})
    assert r.headers["X-Total-Count"] == "1"


@pytest.mark.parametrize("params", [
    {"limit": 0}, {"limit": 201}, {"offset": -1}, {"sort": "random"},
])
def test_bad_paging_params_are_rejected(client: TestClient, params):
    assert client.get("/api/places", params=params).status_code == 422


def test_drafts_queue_is_unaffected(client: TestClient):
    _make(client, "Published Spot")
    assert client.get("/api/places/drafts").json() == []
    assert len(client.get("/api/places").json()) == 1


# --- sorting --------------------------------------------------------------- #
def test_sort_by_date_added(client: TestClient):
    _make(client, "Middle", added="2026-02-01T00:00:00+00:00")
    _make(client, "Oldest", added="2026-01-01T00:00:00+00:00")
    _make(client, "Newest", added="2026-03-01T00:00:00+00:00")
    assert _names(client, sort="newest") == ["Newest", "Middle", "Oldest"]
    assert _names(client, sort="oldest") == ["Oldest", "Middle", "Newest"]


def test_editing_a_place_does_not_make_it_newest(client: TestClient):
    old = _make(client, "Old Faithful", added="2026-01-01T00:00:00+00:00")
    _make(client, "Fresh", added="2026-03-01T00:00:00+00:00")
    client.put(f"/api/places/{old}", json={"name": "Old Faithful", "visited": 1})  # bumps updated_at only
    assert _names(client, sort="newest") == ["Fresh", "Old Faithful"]


def test_sort_alphabetical_ignores_case(client: TestClient):
    for n in ("banana bar", "Apple Cafe", "cherry cantina"):
        _make(client, n)
    assert _names(client, sort="title_asc") == ["Apple Cafe", "banana bar", "cherry cantina"]
    assert _names(client, sort="title_desc") == ["cherry cantina", "banana bar", "Apple Cafe"]


def test_default_order_unchanged_when_no_sort(client: TestClient):
    a = _make(client, "A")
    _make(client, "B")
    conn = db.get_connection()
    try:  # make A the most recently updated
        conn.execute("UPDATE place SET updated_at = '2999-01-01T00:00:00+00:00' WHERE id = ?", (a,))
        conn.commit()
    finally:
        conn.close()
    assert _names(client)[0] == "A"


def test_sort_combines_with_search(client: TestClient):
    _make(client, "Zesty Taqueria")
    _make(client, "Amazing Taqueria")
    _make(client, "Pizza Place")
    assert _names(client, q="taqueria", sort="title_asc") == ["Amazing Taqueria", "Zesty Taqueria"]


def test_relevance_without_a_query_falls_back_to_newest(client: TestClient):
    _make(client, "Old", added="2026-01-01T00:00:00+00:00")
    _make(client, "New", added="2026-03-01T00:00:00+00:00")
    assert _names(client, sort="relevance") == ["New", "Old"]


def test_sort_by_rating_puts_unrated_last_both_ways(client: TestClient):
    _make(client, "Three", our_rating=3)
    _make(client, "Five", our_rating=5)
    _make(client, "Unrated")
    assert _names(client, sort="rating_desc") == ["Five", "Three", "Unrated"]
    assert _names(client, sort="rating_asc") == ["Three", "Five", "Unrated"]


def test_equal_ratings_fall_back_to_name_then_page_stably(client: TestClient):
    for n in ("Cc", "Aa", "Bb"):
        _make(client, n, our_rating=4)
    assert _names(client, sort="rating_desc") == ["Aa", "Bb", "Cc"]
    pages = [_names(client, sort="rating_desc", limit=1, offset=o) for o in range(3)]
    assert pages == [["Aa"], ["Bb"], ["Cc"]]


def test_clearing_a_rating_moves_it_to_the_unrated_end(client: TestClient):
    a = _make(client, "Aa", our_rating=5)
    _make(client, "Bb", our_rating=2)
    client.put(f"/api/places/{a}", json={"name": "Aa", "our_rating": None})
    assert _names(client, sort="rating_desc") == ["Bb", "Aa"]
