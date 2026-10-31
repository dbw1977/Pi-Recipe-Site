"""The Google sign-in, exercised end to end against a local stand-in for Google's token server.

This is what catches library-level problems the mocked tests can't: modern Google OAuth
libraries add PKCE to the sign-in link, so the code exchange must present the matching secret
(`code_verifier`). The app builds the link and exchanges the code in two separate requests, so
it has to carry that secret between them."""
from __future__ import annotations

import base64
import hashlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app import config
from app.extraction import drive

DRIVE_FILE = "https://www.googleapis.com/auth/drive.file"
DRIVE_READONLY = "https://www.googleapis.com/auth/drive.readonly"


class FakeGoogle:
    """Plays Google's token endpoint: records each exchange and answers by what the code says."""

    def __init__(self):
        self.requests: list[dict[str, str]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # keep test output quiet
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
                form = {k: v[0] for k, v in parse_qs(body).items()}
                outer.requests.append(form)
                code = form.get("code", "")
                if code == "used":
                    status, payload = 400, {"error": "invalid_grant", "error_description": "Bad Request"}
                elif "code_verifier" not in form and outer.require_pkce:
                    status, payload = 400, {"error": "invalid_grant", "error_description": "Missing code verifier."}
                else:
                    scopes = f"{DRIVE_READONLY}" if code == "partial" else f"{DRIVE_FILE} {DRIVE_READONLY}"
                    status, payload = 200, {
                        "access_token": "ya29.test", "expires_in": 3599, "scope": scopes,
                        "token_type": "Bearer", **({} if code == "no-refresh" else {"refresh_token": "1//refresh"}),
                    }
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.require_pkce = True
        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/token"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self):
        self.server.shutdown()


@pytest.fixture()
def google(client: TestClient, tmp_path, monkeypatch) -> FakeGoogle:
    fake = FakeGoogle()
    secrets = tmp_path / "client_secret.json"
    secrets.write_text(json.dumps({"installed": {
        "client_id": "123.apps.googleusercontent.com", "project_id": "p",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": fake.url,
        "client_secret": "shh", "redirect_uris": ["http://localhost"],
    }}))
    monkeypatch.setattr(config, "GOOGLE_CLIENT_SECRETS", str(secrets))
    monkeypatch.setattr(config, "GOOGLE_TOKEN_PATH", tmp_path / "google_token.json")
    monkeypatch.setenv("OAUTHLIB_INSECURE_TRANSPORT", "1")  # the stand-in is plain http on localhost
    drive._pending.clear()
    yield fake
    fake.stop()


def _start(client: TestClient) -> dict[str, str]:
    """Tap "Connect Google": returns the sign-in link's query (state, code_challenge, ...)."""
    url = client.get("/api/google/auth-url").json()["url"]
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


def _redirect(state: str, code: str = "abc") -> str:
    """What the browser's address bar shows after approving."""
    return f"http://localhost/?state={state}&code={code}&scope=x"


def _s256(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def _connect(client: TestClient, text: str):
    return client.post("/api/google/connect", json={"code": text})


# --------------------------------------------------------------------------- #
def test_connecting_presents_the_pkce_secret_that_matches_the_sign_in_link(client, google):
    q = _start(client)
    assert "code_challenge" in q  # the installed library really does use PKCE
    r = _connect(client, _redirect(q["state"]))
    assert r.status_code == 200, r.text

    (sent,) = google.requests
    assert sent["code"] == "abc"
    assert _s256(sent["code_verifier"]) == q["code_challenge"]  # Google would accept this pairing
    assert client.get("/api/google/status").json()["authorized"] is True


def test_the_connection_is_saved_with_a_long_lived_refresh_token(client, google):
    q = _start(client)
    _connect(client, _redirect(q["state"]))
    saved = json.loads(config.GOOGLE_TOKEN_PATH.read_text())
    assert saved["refresh_token"] == "1//refresh"


def test_a_bare_code_works_too(client, google):
    _start(client)
    assert _connect(client, "abc").status_code == 200
    assert "code_verifier" in google.requests[0]


def test_pasting_the_code_from_an_earlier_link_uses_that_links_secret(client, google):
    first = _start(client)
    _start(client)  # tapped Connect Google again before pasting
    assert _connect(client, _redirect(first["state"])).status_code == 200
    assert _s256(google.requests[0]["code_verifier"]) == first["code_challenge"]


def test_pasting_without_starting_says_to_start_again(client, google):
    r = _connect(client, _redirect("state-from-before-a-restart"))
    assert r.status_code == 400 and "connect google" in r.json()["detail"].lower()
    assert google.requests == []  # never bothered Google with a code that can't work


def test_a_sign_in_link_older_than_half_an_hour_is_not_trusted(client, google, monkeypatch):
    q = _start(client)
    real = time.time
    monkeypatch.setattr(drive.time, "time", lambda: real() + 31 * 60)
    r = _connect(client, _redirect(q["state"]))
    assert r.status_code == 400 and "start again" in r.json()["detail"].lower()


def test_an_expired_or_used_code_gets_a_plain_explanation(client, google):
    q = _start(client)
    r = _connect(client, _redirect(q["state"], code="used"))
    assert r.status_code == 400
    assert "already used or has expired" in r.json()["detail"]
    assert not config.GOOGLE_TOKEN_PATH.exists()


def test_unticking_the_drive_permission_is_refused_and_explained(client, google):
    q = _start(client)
    r = _connect(client, _redirect(q["state"], code="partial"))
    assert r.status_code == 400 and "tick every box" in r.json()["detail"].lower()
    assert not config.GOOGLE_TOKEN_PATH.exists()  # a half-permitted connection is not saved


def test_a_response_without_a_refresh_token_is_refused(client, google):
    q = _start(client)
    r = _connect(client, _redirect(q["state"], code="no-refresh"))
    assert r.status_code == 400 and "permissions" in r.json()["detail"].lower()
    assert not config.GOOGLE_TOKEN_PATH.exists()


def test_the_library_not_using_pkce_still_connects(client, google, monkeypatch):
    """Older library versions don't add PKCE; nothing should require it."""
    google.require_pkce = False
    real = drive._make_flow

    def no_pkce(redirect_uri):
        flow = real(redirect_uri)
        flow.autogenerate_code_verifier = False
        flow.code_verifier = None
        return flow
    monkeypatch.setattr(drive, "_make_flow", no_pkce)
    q = _start(client)
    assert "code_challenge" not in q
    assert _connect(client, _redirect(q["state"])).status_code == 200
    assert "code_verifier" not in google.requests[0]
