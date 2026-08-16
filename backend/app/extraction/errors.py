"""Typed errors so routers can turn a missing credential into a clean 4xx, never a crash."""
from __future__ import annotations


class FeatureUnavailable(Exception):
    """A path is disabled because a credential/binary/dependency is missing.

    Carries a user-facing message and the .env key(s) the user must set. Routers surface
    this as HTTP 503 with the message — the feature is off, but the app keeps running
    (CLAUDE.md rule 8: never crash, never fake success)."""

    def __init__(self, message: str, *, needs: str | None = None):
        super().__init__(message)
        self.message = message
        self.needs = needs


class ExtractionError(Exception):
    """Extraction ran but could not produce a usable draft (bad page, unreadable image…)."""

    def __init__(self, message: str, *, partial: dict | None = None):
        super().__init__(message)
        self.message = message
        # Whatever fields did parse, so the router can still open a review screen (spec §10).
        self.partial = partial or {}
