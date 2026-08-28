"""Anthropic API errors become clean FeatureUnavailable (503), not raw 500s."""
from __future__ import annotations

import anthropic

from app.extraction import claude
from app.extraction.errors import FeatureUnavailable


# Subclass the real error types with a no-arg __init__ so isinstance() matches without
# needing a live HTTP response to construct them.
class _FakeAuth(anthropic.AuthenticationError):
    def __init__(self):  # noqa: D401
        pass


class _FakeRate(anthropic.RateLimitError):
    def __init__(self):
        pass


def test_auth_error_maps_to_feature_unavailable():
    out = claude._translate_api_error(_FakeAuth())
    assert isinstance(out, FeatureUnavailable)
    assert "ANTHROPIC_API_KEY" in out.message


def test_rate_limit_maps_to_feature_unavailable():
    out = claude._translate_api_error(_FakeRate())
    assert isinstance(out, FeatureUnavailable)
    assert "rate" in out.message.lower()


def test_non_anthropic_error_passes_through():
    err = ValueError("something else")
    assert claude._translate_api_error(err) is err
