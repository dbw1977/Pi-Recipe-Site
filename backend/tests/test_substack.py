"""Substack import: URL mapping, HTML->text, paywall handling, wiring (no live network).

The JSON fixtures are modelled on Substack's /api/v1/posts responses; the code reads them
defensively (every field optional except body_html), so a shape change degrades to the
generic importer rather than crashing."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.extraction import claude, url_import
from app.extraction.draft import ExtractedRecipe
from app.extraction.errors import FeatureUnavailable


class _FakeResp:
    def __init__(self, payload=None, status=200, json_error=False):
        self._payload, self.status_code, self._json_error = payload, status, json_error

    def raise_for_status(self):
        pass

    def json(self):
        if self._json_error:
            raise ValueError("not json")
        return self._payload


BODY = (
    "<p>I have been making this all winter.</p>"
    "<h3>Ingredients</h3>"
    "<ul><li><p>1 cup lentils</p></li><li><p>2 tbsp olive oil</p></li>"
    "<li><p>Salt &amp; pepper</p></li></ul>"
    "<h3>Method</h3><ol><li><p>Simmer the lentils.</p></li></ol>"
    '<div><img src="https://substackcdn.com/image/body.jpg"></div>'
)


def _post(**over):
    post = {
        "title": "Winter Lentil Soup",
        "subtitle": "Cheap, fast, good",
        "body_html": BODY,
        "audience": "everyone",
        "cover_image": "https://substackcdn.com/image/cover.jpg",
        "canonical_url": "https://cooking.example.substack.com/p/winter-lentil-soup",
        "publication": {"name": "Weeknight Pantry"},
        "publishedBylines": [{"name": "Sam Cook"}],
    }
    post.update(over)
    return post


# --- URL mapping ----------------------------------------------------------- #
@pytest.mark.parametrize("url,api", [
    ("https://substack.com/home/post/p-219437719",
     "https://substack.com/api/v1/posts/by-id/219437719"),
    ("https://substack.com/home/post/p-219437719?utm_source=share",
     "https://substack.com/api/v1/posts/by-id/219437719"),
    ("https://cooking.substack.com/p/winter-lentil-soup",
     "https://cooking.substack.com/api/v1/posts/winter-lentil-soup"),
    ("https://cooking.substack.com/p/winter-lentil-soup/?r=abc&utm_campaign=post",
     "https://cooking.substack.com/api/v1/posts/winter-lentil-soup"),
    ("https://newsletter.mysite.com/p/soup",  # custom domain
     "https://newsletter.mysite.com/api/v1/posts/soup"),
])
def test_api_url_mapping(url, api):
    assert url_import._substack_api_url(url) == api


@pytest.mark.parametrize("url", [
    "https://substack.com/@someone/note/c-123",
    "https://substack.com/@someone",
    "https://playswellwithbutter.com/grill-marinade/",
    "https://www.reddit.com/r/recipes/comments/abc/x/",
])
def test_api_url_ignores_non_posts(url):
    assert url_import._substack_api_url(url) is None


# --- HTML -> text ---------------------------------------------------------- #
def test_html_to_text_keeps_one_ingredient_per_line():
    text = url_import._html_to_text(BODY)
    lines = text.splitlines()
    assert "- 1 cup lentils" in lines
    assert "- 2 tbsp olive oil" in lines
    assert "- Salt & pepper" in lines  # entity decoded
    assert "- Simmer the lentils." in lines


def test_html_to_text_drops_scripts_and_styles():
    text = url_import._html_to_text("<p>Soup</p><script>var x=1;</script><style>p{}</style>")
    assert text == "Soup"


# --- fetching -------------------------------------------------------------- #
def test_post_fields(monkeypatch):
    monkeypatch.setattr("requests.get", lambda *a, **k: _FakeResp(_post()))
    out = url_import._substack_post("https://substack.com/home/post/p-219437719")
    assert out["publication"] == "Weeknight Pantry" and out["author"] == "Sam Cook"
    assert out["image"] == "https://substackcdn.com/image/cover.jpg"
    assert out["canonical_url"].endswith("/p/winter-lentil-soup")
    assert out["text"].startswith("Title: Winter Lentil Soup")
    assert "- 1 cup lentils" in out["text"]


def test_post_image_falls_back_to_first_body_image(monkeypatch):
    monkeypatch.setattr("requests.get", lambda *a, **k: _FakeResp(_post(cover_image=None)))
    out = url_import._substack_post("https://cooking.substack.com/p/winter-lentil-soup")
    assert out["image"] == "https://substackcdn.com/image/body.jpg"


def test_paywalled_post_is_a_clear_error(monkeypatch):
    monkeypatch.setattr("requests.get", lambda *a, **k: _FakeResp(_post(audience="only_paid")))
    with pytest.raises(FeatureUnavailable) as e:
        url_import._substack_post("https://cooking.substack.com/p/winter-lentil-soup")
    assert "paid subscribers" in e.value.message and "screenshot" in e.value.message


@pytest.mark.parametrize("resp", [
    _FakeResp(status=404),
    _FakeResp(status=403),
    _FakeResp(json_error=True),
    _FakeResp(["not", "a", "dict"]),
    _FakeResp({"title": "no body"}),
    _FakeResp({"body_html": "   "}),
])
def test_unreadable_responses_return_none(monkeypatch, resp):
    monkeypatch.setattr("requests.get", lambda *a, **k: resp)
    assert url_import._substack_post("https://cooking.substack.com/p/x") is None


def test_network_error_returns_none(monkeypatch):
    def boom(*a, **k):
        raise OSError("down")
    monkeypatch.setattr("requests.get", boom)
    assert url_import._substack_post("https://cooking.substack.com/p/x") is None


# --- wiring ---------------------------------------------------------------- #
def test_import_without_key_is_503(client: TestClient, monkeypatch):
    monkeypatch.setattr(claude, "available", lambda: False)
    monkeypatch.setattr("requests.get", lambda *a, **k: _FakeResp(_post()))
    r = client.post("/api/imports/url", json={"url": "https://substack.com/home/post/p-219437719"})
    assert r.status_code == 503
    assert "ANTHROPIC_API_KEY" in r.json()["detail"]


def test_paywalled_import_is_503_with_screenshot_hint(client: TestClient, monkeypatch):
    monkeypatch.setattr(claude, "available", lambda: True)
    monkeypatch.setattr("requests.get", lambda *a, **k: _FakeResp(_post(audience="only_paid")))
    r = client.post("/api/imports/url", json={"url": "https://cooking.substack.com/p/x"})
    assert r.status_code == 503 and "screenshot" in r.json()["detail"]


def test_full_import_lands_as_draft(client: TestClient, monkeypatch):
    seen = {}

    def fake_structure(text, allowed, *, kind="page text", max_chars=12000):
        seen.update(text=text, kind=kind, max_chars=max_chars)
        return ExtractedRecipe(
            title="Winter Lentil Soup",
            groups=[{"name": None, "ingredients": [
                {"quantity": 1, "unit": "cup", "name": "lentils", "scalable": 1},
            ]}],
            steps=["Simmer the lentils."], equipment=[], tags={},
        )

    monkeypatch.setattr(claude, "available", lambda: True)
    monkeypatch.setattr(claude, "structure_text", fake_structure)
    monkeypatch.setattr("requests.get", lambda *a, **k: _FakeResp(_post()))
    monkeypatch.setattr(url_import.media, "download_image", lambda u: "2026/10/hero.jpg")

    r = client.post("/api/imports/url", json={"url": "https://substack.com/home/post/p-219437719"})
    assert r.status_code == 200, r.text
    draft = r.json()["draft"]
    assert draft["status"] == "draft"  # never auto-published
    assert draft["source_name"] == "Weeknight Pantry"
    # Stored with the post's real address, not the app share link.
    assert draft["source_url"] == "https://cooking.example.substack.com/p/winter-lentil-soup"
    assert draft["hero_image"] == "2026/10/hero.jpg"
    assert "- 1 cup lentils" in seen["text"]
    assert seen["max_chars"] > 12000  # the recipe may sit deep in a long post
    assert len(client.get("/api/recipes").json()) == 0
    assert len(client.get("/api/drafts").json()) == 1


def test_unreadable_substack_falls_through_to_generic(client: TestClient, monkeypatch):
    """If the API can't be read, the generic scraper path still gets its turn."""
    monkeypatch.setattr(claude, "available", lambda: False)
    monkeypatch.setattr("requests.get", lambda *a, **k: _FakeResp(status=404))
    monkeypatch.setattr(
        url_import, "_try_scraper",
        lambda url: {"title": "Soup", "ingredients": ["1 cup lentils"], "instructions_list": ["Simmer."],
                     "image": None, "host": "cooking.substack.com", "author": None,
                     "total_time": None, "yields": None},
    )
    r = client.post("/api/imports/url", json={"url": "https://cooking.substack.com/p/x"})
    assert r.status_code == 200, r.text
    assert r.json()["draft"]["title"] == "Soup"


# --- generic fallback: prefer the article body ------------------------------ #
def test_readable_text_prefers_article_over_page_chrome():
    chrome = "<nav>" + ("Subscribe sign in menu " * 800) + "</nav>"  # > 12k chars of junk
    article = "<article><p>" + ("Intro. " * 100) + "</p><ul><li>1 cup lentils</li></ul></article>"
    out = url_import._readable_from_html(f"<html><body>{chrome}{article}</body></html>")
    assert "1 cup lentils" in out  # would be truncated away without the article preference


def test_readable_text_without_article_unchanged():
    out = url_import._readable_from_html("<html><body><p>Just 1 cup lentils</p></body></html>")
    assert "Just 1 cup lentils" in out
