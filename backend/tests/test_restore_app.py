"""Restoring a backup from inside the running app: stage -> preview -> confirm -> apply."""
from __future__ import annotations

import sqlite3
import threading
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import backup, backup_settings as bs, config, db
from app.extraction import drive as drive_mod

RAW = {"Content-Type": "application/octet-stream"}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _recipe(client: TestClient, title: str) -> int:
    return client.post("/api/recipes", json={
        "title": title, "groups": [], "steps": [], "equipment": [], "tag_ids": [],
    }).json()["id"]


def _photo(rel="2026/10/a.jpg", data=b"JPEGDATA" * 50) -> Path:
    p = config.media_root() / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def _make_backup() -> bytes:
    """A real backup of the current library, as bytes (what a person would carry to a new Pi)."""
    conn = db.get_connection()
    try:
        bs.update(conn, {"local_dir": str(config.BACKUP_LOCAL_DIR)})
    finally:
        conn.close()
    res = backup.run_now({"local"})["local"]
    assert res.ok, res.message
    return Path(res.path).read_bytes()


def _upload(client: TestClient, data: bytes):
    return client.post("/api/backups/restore/upload", content=data, headers=RAW)


def _wait_idle(timeout=15):
    end = time.time() + timeout
    while backup.current()["running"] and time.time() < end:
        time.sleep(0.02)
    assert not backup.current()["running"], "restore did not finish"


def _titles(client: TestClient) -> set[str]:
    return {r["title"] for r in client.get("/api/recipes").json()}


# --------------------------------------------------------------------------- #
# Staging + preview
# --------------------------------------------------------------------------- #
def test_upload_previews_what_is_inside_next_to_what_you_have_now(client: TestClient):
    _recipe(client, "A")
    _recipe(client, "B")
    _photo()
    data = _make_backup()
    _recipe(client, "C")  # library has moved on since the backup

    r = _upload(client, data)
    assert r.status_code == 200, r.text
    p = r.json()
    assert (p["recipes"], p["places"], p["media_files"]) == (2, 0, 1)
    assert p["includes_media"] and p["kind"] == "zip" and p["source"] == "uploaded file"
    assert p["current"] == {"recipes": 3, "places": 0}
    assert p["created_at"] and p["size_bytes"] == len(data)
    # Nothing has changed yet.
    assert _titles(client) == {"A", "B", "C"}


def test_staged_backup_survives_a_page_reload_and_can_be_discarded(client: TestClient):
    _recipe(client, "A")
    _upload(client, _make_backup())
    assert client.get("/api/backups/restore/staged").json()["recipes"] == 1
    assert client.delete("/api/backups/restore/staged").status_code == 204
    assert client.get("/api/backups/restore/staged").json() is None
    assert not backup.staged_file().exists()


def test_a_new_upload_replaces_the_previous_staged_one(client: TestClient):
    _recipe(client, "A")
    first = _make_backup()
    _recipe(client, "B")
    second = _make_backup()
    _upload(client, first)
    assert _upload(client, second).json()["recipes"] == 2
    assert client.get("/api/backups/restore/staged").json()["recipes"] == 2


@pytest.mark.parametrize("body,needle", [
    (b"", "isn't a recipe backup"),
    (b"just some text, not a backup at all", "isn't a recipe backup"),
])
def test_junk_uploads_are_refused_clearly_and_leave_nothing_staged(client: TestClient, body, needle):
    r = _upload(client, body)
    assert r.status_code == 400 and needle in r.json()["detail"]
    assert not list(backup.staging_dir().iterdir())  # nothing left behind (checked on disk, not via GET)


def test_a_zip_that_is_not_a_backup_is_refused(client: TestClient, tmp_path):
    z = tmp_path / "other.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("hello.txt", "hi")
    r = _upload(client, z.read_bytes())
    assert r.status_code == 400 and "no recipes.db" in r.json()["detail"]
    assert not list(backup.staging_dir().iterdir())


def test_a_backup_from_a_newer_app_is_refused(client: TestClient, tmp_path):
    data = _make_backup()
    (tmp_path / "b.zip").write_bytes(data)
    with zipfile.ZipFile(tmp_path / "b.zip") as z:
        z.extract("recipes.db", tmp_path)
    c = sqlite3.connect(tmp_path / "recipes.db")
    c.execute("INSERT INTO schema_migrations(filename) VALUES ('999_future.sql')")
    c.commit()
    c.close()
    newer = tmp_path / "newer.zip"
    with zipfile.ZipFile(newer, "w") as z:
        z.write(tmp_path / "recipes.db", "recipes.db")
    r = _upload(client, newer.read_bytes())
    assert r.status_code == 400 and "newer version" in r.json()["detail"]
    assert not list(backup.staging_dir().iterdir())


def test_upload_that_would_not_fit_is_refused_before_writing(client: TestClient, monkeypatch):
    real = backup.shutil.disk_usage
    monkeypatch.setattr("app.routers.backups.shutil.disk_usage", lambda p: type(real(p))(100, 100, 5_000))
    r = client.post("/api/backups/restore/upload", content=b"x" * 1000, headers=RAW)
    assert r.status_code == 507 and "free space" in r.json()["detail"].lower()
    assert not backup.staged_file().exists()


# --------------------------------------------------------------------------- #
# Apply
# --------------------------------------------------------------------------- #
def test_restore_replaces_the_library_and_brings_the_photos_back(client: TestClient):
    a = _recipe(client, "Original")
    photo = _photo()
    photo_bytes = photo.read_bytes()
    data = _make_backup()

    # The disaster, plus a recipe that did NOT exist at backup time.
    client.delete(f"/api/recipes/{a}")
    _recipe(client, "Made Afterwards")
    photo.unlink()

    assert _upload(client, data).status_code == 200
    r = client.post("/api/backups/restore/apply", json={"include_media": True})
    assert r.status_code == 200, r.text
    _wait_idle()

    # Replaced (not merged): the backup's library, exactly.
    assert _titles(client) == {"Original"}
    assert photo.read_bytes() == photo_bytes
    st = client.get("/api/backups/status").json()
    assert st["running"] is False and st["kind"] is None
    res = st["restore_result"]
    assert res["ok"] and res["recipes"] == 1 and res["photos_restored"] == 1
    # Staging is cleaned up, and the app is still serving.
    assert client.get("/api/backups/restore/staged").json() is None
    assert client.get("/api/health").status_code == 200

    # The pre-restore library was kept, so this can be undone — and it holds what we replaced.
    (safety,) = config.DB_PATH.parent.glob("before-restore-*.db")
    assert res["safety_copy"] == str(safety)
    kept = sqlite3.connect(safety)
    assert [r[0] for r in kept.execute("SELECT title FROM recipe")] == ["Made Afterwards"]
    kept.close()


def test_restore_can_leave_the_photos_alone(client: TestClient):
    photo = _photo()
    data = _make_backup()
    photo.unlink()
    _upload(client, data)
    client.post("/api/backups/restore/apply", json={"include_media": False})
    _wait_idle()
    assert not photo.exists()
    assert client.get("/api/backups/status").json()["restore_result"]["photos_restored"] == 0


def test_restoring_an_older_backup_adds_the_tables_it_lacks(client: TestClient, tmp_path):
    _recipe(client, "From the past")
    data = _make_backup()
    (tmp_path / "b.zip").write_bytes(data)
    with zipfile.ZipFile(tmp_path / "b.zip") as z:
        z.extract("recipes.db", tmp_path)
    # Make it look like a backup from before migration 009 existed.
    c = sqlite3.connect(tmp_path / "recipes.db")
    c.execute("DROP TABLE app_setting")
    c.execute("DELETE FROM schema_migrations WHERE filename LIKE '009%'")
    c.commit()
    c.close()
    old = tmp_path / "old.zip"
    with zipfile.ZipFile(old, "w") as z:
        z.write(tmp_path / "recipes.db", "recipes.db")

    assert _upload(client, old.read_bytes()).status_code == 200
    client.post("/api/backups/restore/apply", json={})
    _wait_idle()
    assert client.get("/api/backups/status").json()["restore_result"]["ok"]
    assert "From the past" in _titles(client)
    conn = db.get_connection()
    try:  # the missing table is back, so settings and backups keep working
        assert conn.execute("SELECT COUNT(*) FROM app_setting").fetchone()[0] >= 0
        assert conn.execute("SELECT 1 FROM schema_migrations WHERE filename LIKE '009%'").fetchone()
    finally:
        conn.close()


def test_a_legacy_bare_db_backup_can_be_restored_too(client: TestClient, tmp_path):
    rid = _recipe(client, "Legacy")
    legacy = tmp_path / "recipes-20260101.db"
    backup.snapshot(legacy)
    client.delete(f"/api/recipes/{rid}")
    p = _upload(client, legacy.read_bytes()).json()
    assert p["kind"] == "db" and not p["includes_media"]
    client.post("/api/backups/restore/apply", json={})
    _wait_idle()
    assert "Legacy" in _titles(client)


def test_a_failed_restore_leaves_the_library_exactly_as_it_was(client: TestClient):
    _recipe(client, "Precious")
    _upload(client, _make_backup())
    backup.staged_file().write_bytes(b"corrupted after staging")  # e.g. a bad SD card
    r = client.post("/api/backups/restore/apply", json={})
    assert r.status_code == 200
    _wait_idle()
    res = client.get("/api/backups/status").json()["restore_result"]
    assert res["ok"] is False and res["message"]
    assert _titles(client) == {"Precious"}
    assert not list(config.DB_PATH.parent.glob("before-restore-*.db"))  # failed the re-check before touching anything


def test_only_the_newest_safety_copies_are_kept(client: TestClient):
    for day in range(1, 6):
        (config.DB_PATH.parent / f"before-restore-2026010{day}-000000.db").write_bytes(b"x")
    backup._save_current_copy()
    kept = sorted(p.name for p in config.DB_PATH.parent.glob("before-restore-*.db"))
    assert len(kept) == backup.KEEP_SAFETY_COPIES
    assert "before-restore-20260101-000000.db" not in kept


# --------------------------------------------------------------------------- #
# Guard rails
# --------------------------------------------------------------------------- #
def test_apply_needs_something_staged(client: TestClient):
    r = client.post("/api/backups/restore/apply", json={})
    assert r.status_code == 400 and "choose a backup" in r.json()["detail"].lower()


def test_nothing_can_be_staged_or_applied_while_a_backup_is_running(client: TestClient):
    _recipe(client, "A")
    data = _make_backup()
    _upload(client, data)
    assert backup._lock.acquire(blocking=False)
    backup._begin("backup", {"local"})
    try:
        assert client.post("/api/backups/restore/apply", json={}).status_code == 409
        assert _upload(client, data).status_code == 409
        assert client.delete("/api/backups/restore/staged").status_code == 409
        assert client.post("/api/backups/restore/stage", json={"source": "folder"}).status_code == 409
        assert backup.start_background({"local"}) is False  # the schedule can't start one mid-restore either
    finally:
        backup._end()
        backup._lock.release()


def test_progress_reports_a_restore_in_flight(client: TestClient, monkeypatch):
    _recipe(client, "A")
    _upload(client, _make_backup())
    gate, started = threading.Event(), threading.Event()

    def slow(source, *, with_media=True):
        started.set()
        backup._step("Restoring photos… 3 of 9")
        gate.wait(5)
        return {"recipes": 1, "places": 0, "photos_restored": 0, "safety_copy": None}
    monkeypatch.setattr(backup, "apply_restore_live", slow)

    assert client.post("/api/backups/restore/apply", json={}).status_code == 200
    assert started.wait(5)
    st = client.get("/api/backups/status").json()
    assert st["running"] and st["kind"] == "restore" and st["step"] == "Restoring photos… 3 of 9"
    assert client.post("/api/backups/restore/apply", json={}).status_code == 409  # no double-click damage
    gate.set()
    _wait_idle()
    assert client.get("/api/backups/status").json()["restore_result"]["ok"]


# --------------------------------------------------------------------------- #
# Other sources: the saved folder, Google Drive
# --------------------------------------------------------------------------- #
def test_stage_from_the_saved_folder(client: TestClient):
    _recipe(client, "Saved")
    _make_backup()
    st = client.get("/api/backups/status").json()
    assert st["local_backup"]["size_bytes"] > 0  # offered as a source
    r = client.post("/api/backups/restore/stage", json={"source": "folder"})
    assert r.status_code == 200 and r.json()["source"] == "saved folder" and r.json()["recipes"] == 1


def test_no_saved_backup_in_the_folder_says_where_it_looked(client: TestClient):
    assert client.get("/api/backups/status").json()["local_backup"] is None
    r = client.post("/api/backups/restore/stage", json={"source": "folder"})
    assert r.status_code == 404 and config.BACKUP_FILENAME in r.json()["detail"]


def test_stage_from_drive(client: TestClient, monkeypatch):
    _recipe(client, "On Drive")
    data = _make_backup()

    def fake_fetch(dest_dir: Path) -> Path:
        out = dest_dir / config.BACKUP_FILENAME
        out.write_bytes(data)
        return out
    monkeypatch.setattr(drive_mod, "authorized", lambda: True)
    monkeypatch.setattr(backup, "fetch_from_drive", fake_fetch)
    r = client.post("/api/backups/restore/stage", json={"source": "drive"})
    assert r.status_code == 200 and r.json()["source"] == "Google Drive"
    assert list(backup.staging_dir().iterdir()) == [backup.staged_file()]  # no stray download left


def test_drive_restore_needs_google_and_reports_failures(client: TestClient, monkeypatch):
    monkeypatch.setattr(drive_mod, "authorized", lambda: False)
    r = client.post("/api/backups/restore/stage", json={"source": "drive"})
    assert r.status_code == 400 and "connect google" in r.json()["detail"].lower()

    monkeypatch.setattr(drive_mod, "authorized", lambda: True)
    def nothing_there(dest_dir):
        raise backup.BackupError("No 'recipes-backup.zip' found on the connected Google Drive.")
    monkeypatch.setattr(backup, "fetch_from_drive", nothing_there)
    r = client.post("/api/backups/restore/stage", json={"source": "drive"})
    assert r.status_code == 400 and "found on the connected" in r.json()["detail"]
    assert client.get("/api/backups/restore/staged").json() is None


def test_unknown_source_is_rejected(client: TestClient):
    assert client.post("/api/backups/restore/stage", json={"source": "carrier-pigeon"}).status_code == 400
