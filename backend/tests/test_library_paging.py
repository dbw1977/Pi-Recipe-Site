"""Library paging, sorting and star ratings."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import db

from .fixtures import steak_salad_payload


def _make(client: TestClient, title: str, added: str | None = None, tag_ids=None) -> int:
    payload = steak_salad_payload(tag_ids)
    payload["title"] = title
    rid = client.post("/api/recipes", json=payload).json()["id"]
    if added:  # pin the timestamps so date ordering doesn't depend on the clock
        conn = db.get_connection()
        try:
            conn.execute(
                "UPDATE recipe SET created_at = ?, updated_at = ? WHERE id = ?", (added, added, rid)
            )
            conn.commit()
        finally:
            conn.close()
    return rid


def _titles(client: TestClient, **params) -> list[str]:
    r = client.get("/api/recipes", params=params)
    assert r.status_code == 200, r.text
    return [c["title"] for c in r.json()]


def _rate(client: TestClient, rid: int, rating):
    return client.put(f"/api/recipes/{rid}/rating", json={"rating": rating})


# --- paging ---------------------------------------------------------------- #
def test_pages_and_total_header(client: TestClient):
    for i in range(5):
        _make(client, f"Recipe {i}", added=f"2026-01-0{i + 1}T00:00:00+00:00")
    seen = []
    for offset, expected in ((0, 2), (2, 2), (4, 1), (6, 0)):
        r = client.get("/api/recipes", params={"sort": "oldest", "limit": 2, "offset": offset})
        assert r.status_code == 200
        assert r.headers["X-Total-Count"] == "5"  # total, not the page size
        assert len(r.json()) == expected
        seen += [c["title"] for c in r.json()]
    assert seen == [f"Recipe {i}" for i in range(5)]  # no gaps, no repeats across pages


def test_no_limit_returns_everything_with_total(client: TestClient):
    for i in range(3):
        _make(client, f"R{i}")
    r = client.get("/api/recipes")
    assert len(r.json()) == 3 and r.headers["X-Total-Count"] == "3"


def test_total_respects_search_and_tags(client: TestClient):
    tag = client.get("/api/tags").json()[0]["tags"][0]["id"]
    _make(client, "Lentil Soup", tag_ids=[tag])
    _make(client, "Lentil Stew")
    _make(client, "Pancakes")
    r = client.get("/api/recipes", params={"q": "lentil", "limit": 1})
    assert len(r.json()) == 1 and r.headers["X-Total-Count"] == "2"
    r = client.get("/api/recipes", params={"tags": str(tag), "limit": 5})
    assert r.headers["X-Total-Count"] == "1"


@pytest.mark.parametrize("params", [
    {"limit": 0}, {"limit": 201}, {"offset": -1}, {"sort": "random"},
])
def test_bad_paging_params_are_rejected(client: TestClient, params):
    assert client.get("/api/recipes", params=params).status_code == 422


# --- sorting --------------------------------------------------------------- #
def test_sort_by_date_added(client: TestClient):
    _make(client, "Middle", added="2026-02-01T00:00:00+00:00")
    _make(client, "Oldest", added="2026-01-01T00:00:00+00:00")
    _make(client, "Newest", added="2026-03-01T00:00:00+00:00")
    assert _titles(client, sort="newest") == ["Newest", "Middle", "Oldest"]
    assert _titles(client, sort="oldest") == ["Oldest", "Middle", "Newest"]


def test_editing_a_recipe_does_not_make_it_newest(client: TestClient):
    old = _make(client, "Old Faithful", added="2026-01-01T00:00:00+00:00")
    _make(client, "Fresh", added="2026-03-01T00:00:00+00:00")
    payload = steak_salad_payload()
    payload["title"] = "Old Faithful"
    client.put(f"/api/recipes/{old}", json=payload)  # bumps updated_at only
    assert _titles(client, sort="newest") == ["Fresh", "Old Faithful"]


def test_sort_alphabetical_ignores_case(client: TestClient):
    for t in ("banana bread", "Apple Pie", "cherry tart"):
        _make(client, t)
    assert _titles(client, sort="title_asc") == ["Apple Pie", "banana bread", "cherry tart"]
    assert _titles(client, sort="title_desc") == ["cherry tart", "banana bread", "Apple Pie"]


def test_default_order_unchanged_when_no_sort(client: TestClient):
    a = _make(client, "A")
    _make(client, "B")
    conn = db.get_connection()
    try:  # make A the most recently updated
        conn.execute("UPDATE recipe SET updated_at = '2999-01-01T00:00:00+00:00' WHERE id = ?", (a,))
        conn.commit()
    finally:
        conn.close()
    assert _titles(client)[0] == "A"


def test_sort_combines_with_search(client: TestClient):
    _make(client, "Zesty Lentil Soup")
    _make(client, "Amazing Lentil Stew")
    _make(client, "Pancakes")
    assert _titles(client, q="lentil", sort="title_asc") == ["Amazing Lentil Stew", "Zesty Lentil Soup"]


def test_relevance_without_a_query_falls_back_to_newest(client: TestClient):
    _make(client, "Old", added="2026-01-01T00:00:00+00:00")
    _make(client, "New", added="2026-03-01T00:00:00+00:00")
    assert _titles(client, sort="relevance") == ["New", "Old"]


# --- ratings --------------------------------------------------------------- #
def test_rate_and_clear(client: TestClient):
    rid = _make(client, "Soup")
    assert client.get(f"/api/recipes/{rid}").json()["rating"] is None  # unrated by default
    r = _rate(client, rid, 4)
    assert r.status_code == 200 and r.json()["rating"] == 4
    assert client.get("/api/recipes").json()[0]["rating"] == 4  # cards carry it too
    assert _rate(client, rid, None).json()["rating"] is None


@pytest.mark.parametrize("bad", [0, 6, -1, "five", 2.5])
def test_rating_must_be_1_to_5(client: TestClient, bad):
    rid = _make(client, "Soup")
    assert _rate(client, rid, bad).status_code == 422


def test_rating_unknown_recipe_is_404(client: TestClient):
    assert _rate(client, 99999, 3).status_code == 404


def test_rating_survives_editing_and_does_not_bump_updated_at(client: TestClient):
    rid = _make(client, "Soup")
    before = client.get(f"/api/recipes/{rid}").json()["updated_at"]
    _rate(client, rid, 5)
    assert client.get(f"/api/recipes/{rid}").json()["updated_at"] == before
    payload = steak_salad_payload()
    payload["title"] = "Soup (edited)"
    client.put(f"/api/recipes/{rid}", json=payload)  # a full edit must not wipe the stars
    assert client.get(f"/api/recipes/{rid}").json()["rating"] == 5


def test_sort_by_rating_puts_unrated_last_both_ways(client: TestClient):
    three = _make(client, "Three")
    five = _make(client, "Five")
    _make(client, "Unrated")
    _rate(client, three, 3)
    _rate(client, five, 5)
    assert _titles(client, sort="rating_desc") == ["Five", "Three", "Unrated"]
    assert _titles(client, sort="rating_asc") == ["Three", "Five", "Unrated"]


def test_equal_ratings_fall_back_to_title_then_page_stably(client: TestClient):
    ids = [_make(client, t) for t in ("Cc", "Aa", "Bb")]
    for rid in ids:
        _rate(client, rid, 4)
    assert _titles(client, sort="rating_desc") == ["Aa", "Bb", "Cc"]
    pages = [_titles(client, sort="rating_desc", limit=1, offset=o) for o in range(3)]
    assert pages == [["Aa"], ["Bb"], ["Cc"]]


def test_migration_leaves_existing_recipes_unrated(client: TestClient):
    # The column is nullable with a range CHECK; the DB itself refuses out-of-range values.
    rid = _make(client, "Soup")
    conn = db.get_connection()
    try:
        with pytest.raises(Exception):
            conn.execute("UPDATE recipe SET rating = 9 WHERE id = ?", (rid,))
    finally:
        conn.close()
