"""URL import robustness: JSON-LD fallback + graceful fetch failures (no live network)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.extraction import claude, url_import
from app.extraction.draft import ExtractedRecipe
from app.extraction.errors import FeatureUnavailable


def test_readable_from_html_pulls_jsonld_recipe():
    html = (
        '<html><head>'
        '<script type="application/ld+json">{"@type":"Recipe","name":"French Onion Mashed Potatoes",'
        '"recipeIngredient":["2 lb potatoes","1 onion"]}</script>'
        '</head><body><p>blog story here</p></body></html>'
    )
    out = url_import._readable_from_html(html)
    assert "JSON-LD" in out
    assert "recipeIngredient" in out and "French Onion Mashed Potatoes" in out


def test_fetch_readable_text_failure_is_feature_unavailable(monkeypatch):
    def boom(*a, **k):
        raise OSError("blocked by site")
    monkeypatch.setattr("requests.get", boom)
    with pytest.raises(FeatureUnavailable):
        url_import._fetch_readable_text("https://www.foodandwine.com/x")


class _Resp:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


def test_403_points_user_to_screenshot(monkeypatch):
    monkeypatch.setattr("requests.get", lambda *a, **k: _Resp(403))
    with pytest.raises(FeatureUnavailable) as ei:
        url_import._fetch_readable_text("https://www.foodandwine.com/x")
    assert "screenshot" in ei.value.message.lower()


def test_scraper_without_ingredients_falls_back_to_claude(client: TestClient, monkeypatch):
    # Simulate an article page recipe-scrapers half-parses: a title but zero ingredients.
    monkeypatch.setattr(claude, "available", lambda: True)
    monkeypatch.setattr(
        url_import, "_try_scraper",
        lambda url: {"title": "French Onion Mashed Potatoes", "ingredients": [],
                     "instructions_list": [], "image": None, "host": "foodandwine.com",
                     "author": None, "total_time": None, "yields": None},
    )
    monkeypatch.setattr(url_import, "_fetch_readable_text", lambda url: "STRUCTURED RECIPE DATA ...")
    monkeypatch.setattr(
        claude, "structure_text",
        lambda *a, **k: ExtractedRecipe(
            title="French Onion Mashed Potatoes",
            groups=[{"name": None, "ingredients": [
                {"quantity": 2, "unit": "lb", "name": "potatoes", "scalable": 1},
                {"quantity": 1, "unit": None, "name": "onion", "scalable": 1},
            ]}],
            tags={"Course": ["Side"]},
        ),
    )
    r = client.post("/api/imports/url", json={"url": "https://www.foodandwine.com/french-onion-mashed-potatoes-12067150"})
    assert r.status_code == 200, r.text
    draft = r.json()["draft"]
    assert draft["source_type"] == "url"
    names = {i["name"] for g in draft["groups"] for i in g["ingredients"]}
    assert "potatoes" in names and "onion" in names


def test_blocked_site_returns_clean_503_not_500(client: TestClient, monkeypatch):
    monkeypatch.setattr(claude, "available", lambda: True)
    monkeypatch.setattr(url_import, "_try_scraper", lambda url: None)  # scraper couldn't parse

    def boom(*a, **k):
        raise OSError("403 blocked")
    monkeypatch.setattr("requests.get", boom)
    r = client.post("/api/imports/url", json={"url": "https://www.foodandwine.com/x"})
    assert r.status_code == 503  # graceful, not an unhandled 500
    assert "screenshot" in r.json()["detail"].lower() or "by hand" in r.json()["detail"].lower()
