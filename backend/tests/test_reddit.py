"""Reddit import: JSON parsing + wiring (no live network)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.extraction import claude, url_import
from app.extraction.draft import ExtractedRecipe


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _reddit_payload(selftext="", comments=None):
    post = {
        "title": "Best Grill Marinade",
        "selftext": selftext,
        "subreddit": "recipes",
        "subreddit_name_prefixed": "r/recipes",
        "author": "grillchef",
        "url_overridden_by_dest": "https://i.redd.it/abc.jpg",
        "post_hint": "image",
    }
    comment_children = [
        {"kind": "t1", "data": {"author": a, "body": b}} for a, b in (comments or [])
    ]
    return [
        {"data": {"children": [{"kind": "t3", "data": post}]}},
        {"data": {"children": comment_children}},
    ]


def test_json_url_normalization():
    assert url_import._reddit_json_url(
        "https://www.reddit.com/r/recipes/comments/abc/best_marinade/"
    ) == "https://www.reddit.com/r/recipes/comments/abc/best_marinade.json?raw_json=1"
    assert url_import._is_reddit("https://old.reddit.com/r/x/comments/y/z/")
    assert url_import._is_reddit("https://redd.it/abc123")
    assert not url_import._is_reddit("https://playswellwithbutter.com/x")


def test_post_body_and_image(monkeypatch):
    monkeypatch.setattr(
        "requests.get",
        lambda *a, **k: _FakeResp(_reddit_payload(selftext="1/2 cup olive oil\n2 tbsp dijon\nWhisk it.")),
    )
    out = url_import._reddit_post_text("https://www.reddit.com/r/recipes/comments/abc/x/")
    assert "olive oil" in out["text"]
    assert out["subreddit"] == "r/recipes" and out["author"] == "u/grillchef"
    assert out["image"] == "https://i.redd.it/abc.jpg"


def test_top_comment_fallback_when_body_thin(monkeypatch):
    # Empty body (a GIF/image post) → the recipe lives in the meatiest top comment.
    payload = _reddit_payload(
        selftext="",
        comments=[
            ("AutoModerator", "Please follow the rules."),
            ("grillchef", "INGREDIENTS: 1/2 cup olive oil, 2 tbsp dijon, 3 cloves garlic. Whisk and marinate 2h."),
            ("someone", "looks great!"),
        ],
    )
    monkeypatch.setattr("requests.get", lambda *a, **k: _FakeResp(payload))
    out = url_import._reddit_post_text("https://www.reddit.com/r/GifRecipes/comments/abc/x/")
    assert "olive oil" in out["text"] and "dijon" in out["text"]
    assert "Please follow the rules" not in out["text"]  # AutoModerator filtered out


def test_reddit_import_without_key_is_503(client: TestClient, monkeypatch):
    monkeypatch.setattr(claude, "available", lambda: False)
    monkeypatch.setattr(
        url_import, "_reddit_post_text",
        lambda url: {"title": "X", "text": "stuff", "subreddit": "r/recipes", "author": "u/c", "image": None},
    )
    r = client.post("/api/imports/url", json={"url": "https://www.reddit.com/r/recipes/comments/a/x/"})
    assert r.status_code == 503
    assert "ANTHROPIC_API_KEY" in r.json()["detail"]


def test_reddit_import_with_key(client: TestClient, monkeypatch):
    monkeypatch.setattr(claude, "available", lambda: True)
    monkeypatch.setattr(
        url_import, "_reddit_post_text",
        lambda url: {
            "title": "Best Grill Marinade", "text": "1/2 cup olive oil ...",
            "subreddit": "r/recipes", "author": "u/grillchef", "image": None,
        },
    )
    monkeypatch.setattr(
        claude, "structure_text",
        lambda *a, **k: ExtractedRecipe(
            title="Best Grill Marinade",
            groups=[{"name": None, "ingredients": [
                {"quantity": 0.5, "unit": "cup", "name": "olive oil", "scalable": 1},
            ]}],
            tags={"Course": ["Marinade"]},
        ),
    )
    r = client.post("/api/imports/url", json={"url": "https://www.reddit.com/r/recipes/comments/a/x/"})
    assert r.status_code == 200, r.text
    draft = r.json()["draft"]
    assert draft["source_type"] == "reddit"
    assert draft["source_name"] == "r/recipes" and draft["source_handle"] == "u/grillchef"
    assert draft["groups"][0]["ingredients"][0]["name"] == "olive oil"
