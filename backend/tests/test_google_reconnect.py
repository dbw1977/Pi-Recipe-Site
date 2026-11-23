"""When Google stops accepting the saved sign-in ("invalid_grant" on refresh).

Seen on a real Pi: Drive backup worked once, then every try failed with the raw Google error
`('invalid_grant: Bad Request', {...})` while Settings kept saying "Connected". This pins down what
should happen instead: a plain instruction, a card that says "reconnect", no pointless hourly
retries, and everything clearing once the person signs in again."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import backup, backup_scheduler, config, db
from app.extraction import drive
from app.extraction.errors import FeatureUnavailable

from .test_google_oauth_flow import DRIVE_FILE, DRIVE_READONLY, FakeGoogle, _connect, _redirect, _start  # noqa: F401
from . import test_google_oauth_flow as flow_mod  # noqa: F401  (reuses its `google` fixture below)


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
    monkeypatch.setenv("OAUTHLIB_INSECURE_TRANSPORT", "1")
    # google-auth ignores the token URL saved in the file and always uses Google's real one (a
    # security measure). Point it at the stand-in, or these tests would call the real Google.
    monkeypatch.setattr("google.oauth2.credentials._GOOGLE_OAUTH2_TOKEN_ENDPOINT", fake.url)
    drive._pending.clear()
    yield fake
    fake.stop()


def _save_expired_token(google: FakeGoogle) -> None:
    """A connection made a while ago: valid refresh token on file, access token long expired."""
    config.GOOGLE_TOKEN_PATH.write_text(json.dumps({
        "token": "ya29.old", "refresh_token": "1//saved", "token_uri": google.url,
        "client_id": "123.apps.googleusercontent.com", "client_secret": "shh",
        "scopes": [DRIVE_READONLY, DRIVE_FILE], "expiry": "2020-01-01T00:00:00Z",
    }))


def _status(client: TestClient) -> dict:
    return client.get("/api/google/status").json()


def _drive_backup():
    conn = db.get_connection()
    try:
        conn.execute("DELETE FROM app_setting WHERE key LIKE 'backup.%'")
        conn.commit()
        from app import backup_settings as bs
        bs.update(conn, {"drive_enabled": True, "local_enabled": False})
    finally:
        conn.close()
    return backup.run_now({"drive"})["drive"]


# --------------------------------------------------------------------------- #
def test_a_rejected_sign_in_is_explained_not_dumped_as_a_raw_google_error(client, google):
    _save_expired_token(google)
    google.refresh_ok = False
    res = _drive_backup()

    assert not res.ok
    assert "no longer accepts the saved sign-in" in res.message
    assert "Connect Google again" in res.message
    assert "invalid_grant" not in res.message and "{" not in res.message  # no raw Google payload
    assert len(res.message) <= 300  # fits what the log keeps, so none of it is cut off


def test_the_card_stops_claiming_connected_and_asks_to_reconnect(client, google):
    _save_expired_token(google)
    assert _status(client)["reconnect_needed"] is False      # nothing wrong yet
    google.refresh_ok = False
    _drive_backup()

    s = _status(client)
    assert s["authorized"] is True                           # a token file exists...
    assert s["reconnect_needed"] is True                     # ...but Google rejected it
    assert s["drive_backup_ready"] is False and s["drive_import_ready"] is False


def test_a_working_sign_in_that_just_needs_renewing_is_renewed_quietly(client, google):
    _save_expired_token(google)
    google.refresh_ok = True
    service = backup._drive_service()
    assert service is not None
    assert json.loads(config.GOOGLE_TOKEN_PATH.read_text())["token"] == "ya29.renewed"  # saved for next time
    assert _status(client)["reconnect_needed"] is False


def test_signing_in_again_clears_the_warning(client, google):
    _save_expired_token(google)
    google.refresh_ok = False
    _drive_backup()
    assert _status(client)["reconnect_needed"] is True

    q = _start(client)
    assert _connect(client, _redirect(q["state"])).status_code == 200
    s = _status(client)
    assert s["reconnect_needed"] is False and s["drive_backup_ready"] is True


def test_disconnecting_clears_the_warning_too(client, google):
    _save_expired_token(google)
    google.refresh_ok = False
    _drive_backup()
    assert client.post("/api/google/disconnect").status_code == 200
    s = _status(client)
    assert s["authorized"] is False and s["reconnect_needed"] is False
    # The status hides the flag when there's no sign-in, so check the stored flag itself: a leftover
    # one would wrongly flash "reconnect" the next time someone connects.
    assert drive.reconnect_needed() is False


def test_the_warning_only_applies_while_a_sign_in_exists(client, google):
    drive._set_reconnect_needed(True)         # a stale marker (e.g. restored from a backup onto a new Pi)
    assert _status(client)["authorized"] is False
    assert _status(client)["reconnect_needed"] is False


def test_drive_import_gets_the_same_plain_message(client, google, monkeypatch):
    monkeypatch.setattr(config, "DRIVE_FOLDER_ID", "folder123")
    _save_expired_token(google)
    google.refresh_ok = False
    with pytest.raises(FeatureUnavailable) as e:
        drive._load_credentials()
    assert "no longer accepts the saved sign-in" in e.value.message
    assert _status(client)["reconnect_needed"] is True


def test_other_google_refusals_are_still_reported_without_the_misleading_advice(client, google, monkeypatch):
    from google.auth.exceptions import RefreshError

    class Boom:
        def refresh(self, request):
            raise RefreshError("invalid_client: The OAuth client was not found.", {"error": "invalid_client"})
    with pytest.raises(FeatureUnavailable) as e:
        drive.refresh_credentials(Boom())
    assert "didn't accept the saved sign-in" in e.value.message and "invalid_client" in e.value.message
    assert _status(client)["reconnect_needed"] is False      # that's a setup problem, not an expired sign-in


# --------------------------------------------------------------------------- #
# The weekly schedule must not hammer Google with a sign-in that is known to be dead.
# --------------------------------------------------------------------------- #
def _enable_weekly(drive_on=True, local_on=False):
    from app import backup_settings as bs
    conn = db.get_connection()
    try:
        bs.update(conn, {"enabled": True, "drive_enabled": drive_on, "local_enabled": local_on})
    finally:
        conn.close()


def test_the_schedule_skips_drive_while_its_sign_in_is_dead(client, google, monkeypatch):
    started = []
    monkeypatch.setattr(backup, "start_background", lambda t: started.append(sorted(t)) or True)
    _enable_weekly(drive_on=True, local_on=False)

    drive._set_reconnect_needed(True)
    assert backup_scheduler.tick(datetime.now()) == [] and started == []   # nothing to retry

    drive._set_reconnect_needed(False)                                      # signed in again
    assert backup_scheduler.tick(datetime.now()) == ["drive"]


def test_a_dead_drive_does_not_stop_the_local_backup(client, google, monkeypatch):
    started = []
    monkeypatch.setattr(backup, "start_background", lambda t: started.append(sorted(t)) or True)
    _enable_weekly(drive_on=True, local_on=True)
    drive._set_reconnect_needed(True)
    assert backup_scheduler.tick(datetime.now()) == ["local"]
    assert started == [["local"]]
