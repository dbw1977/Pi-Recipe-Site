"""Backups: the weekly schedule, console settings, the one-file archive, restore, Drive, runner.

Google Drive is exercised against a fake service (no network here); the real thing is verified
on the Pi."""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import backup, backup_scheduler, backup_settings as bs, config, db
from app.extraction import drive as drive_mod

SUN_3AM = dict(day=6, hour=3)  # the default slot


# =========================================================================== #
# Helpers
# =========================================================================== #
def _recipe(client: TestClient, title="Backup Me") -> int:
    return client.post("/api/recipes", json={
        "title": title, "groups": [], "steps": [], "equipment": [], "tag_ids": [],
    }).json()["id"]


def _photo(rel="2026/10/a.jpg", data=b"JPEGDATA" * 50) -> Path:
    p = config.media_root() / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def _configure(**patch) -> bs.BackupSettings:
    conn = db.get_connection()
    try:
        return bs.update(conn, patch)
    finally:
        conn.close()


def _settings() -> bs.BackupSettings:
    conn = db.get_connection()
    try:
        return bs.load(conn)
    finally:
        conn.close()


def _archive_path() -> Path:
    return Path(_settings().local_dir) / config.BACKUP_FILENAME


def _log(kind: str) -> list[sqlite3.Row]:
    conn = db.get_connection()
    try:
        return conn.execute("SELECT * FROM backup_log WHERE kind = ? ORDER BY id", (kind,)).fetchall()
    finally:
        conn.close()


# =========================================================================== #
# Schedule math (pure)
# =========================================================================== #
def dt(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi)


# 2026-10-11 is a Sunday.
@pytest.mark.parametrize("now,expected", [
    (dt(2026, 10, 14, 10), dt(2026, 10, 11, 3)),   # Wednesday -> that Sunday
    (dt(2026, 10, 11, 2, 59), dt(2026, 10, 4, 3)),  # Sunday, one minute before the slot -> last week's
    (dt(2026, 10, 11, 3, 0), dt(2026, 10, 11, 3)),  # exactly on the slot
    (dt(2026, 10, 11, 23, 59), dt(2026, 10, 11, 3)),
    (dt(2026, 10, 12, 0, 0), dt(2026, 10, 11, 3)),  # Monday just after midnight
])
def test_last_scheduled(now, expected):
    assert bs.last_scheduled(now, **SUN_3AM) == expected


def test_next_scheduled_is_a_week_after_the_last_slot():
    assert bs.next_scheduled(dt(2026, 10, 14, 10), **SUN_3AM) == dt(2026, 10, 18, 3)
    assert bs.next_scheduled(dt(2026, 10, 11, 2, 59), **SUN_3AM) == dt(2026, 10, 11, 3)


def _s(**kw) -> bs.BackupSettings:
    base = dict(enabled=True, local_enabled=True, drive_enabled=False, **SUN_3AM)
    base.update(kw)
    return bs.BackupSettings(**base)


NOW = dt(2026, 10, 14, 10)  # Wednesday; the slot was Sunday 10/11 03:00


def test_nothing_due_when_weekly_is_off():
    assert bs.due_targets(_s(enabled=False), NOW, {}, {}) == []


def test_first_ever_run_is_due_immediately():
    assert bs.due_targets(_s(), NOW, {}, {}) == ["local"]


def test_not_due_once_this_weeks_backup_succeeded():
    assert bs.due_targets(_s(), NOW, {"local": dt(2026, 10, 11, 3, 5)}, {"local": dt(2026, 10, 11, 3, 5)}) == []


def test_a_manual_backup_after_the_slot_counts():
    assert bs.due_targets(_s(), NOW, {"local": dt(2026, 10, 13, 18)}, {"local": dt(2026, 10, 13, 18)}) == []


def test_due_when_last_success_is_from_before_the_slot():
    old = dt(2026, 10, 4, 3, 5)
    assert bs.due_targets(_s(), NOW, {"local": old}, {"local": old}) == ["local"]


def test_late_catch_up_after_the_pi_was_off():
    # Pi was off Sunday 3 AM; it's Monday afternoon and last week's backup is the latest.
    monday = dt(2026, 10, 12, 15)
    assert bs.due_targets(_s(), monday, {"local": dt(2026, 10, 4, 3, 5)}, {"local": dt(2026, 10, 4, 3, 5)}) == ["local"]


def test_failed_attempt_retries_hourly_not_every_check():
    ok = dt(2026, 10, 4, 3, 5)
    soon = NOW - timedelta(minutes=20)
    later = NOW - timedelta(minutes=90)
    assert bs.due_targets(_s(), NOW, {"local": ok}, {"local": soon}) == []
    assert bs.due_targets(_s(), NOW, {"local": ok}, {"local": later}) == ["local"]


def test_only_switched_on_destinations_are_considered_and_tracked_separately():
    both = _s(drive_enabled=True)
    done = dt(2026, 10, 11, 4)
    assert bs.due_targets(both, NOW, {"local": done}, {"local": done}) == ["drive"]  # drive still owed
    assert bs.due_targets(_s(local_enabled=False, drive_enabled=True), NOW, {}, {}) == ["drive"]


def test_log_timestamps_are_read_as_utc():
    parsed = bs.parse_log_time("2026-10-11 03:00:00")
    assert parsed == datetime(2026, 10, 11, 3, 0, tzinfo=None) + (datetime.now().astimezone().utcoffset() or timedelta(0))
    assert bs.parse_log_time(None) is None and bs.parse_log_time("garbage") is None


# =========================================================================== #
# Settings (stored in the DB, validated)
# =========================================================================== #
def test_defaults_are_safe(client: TestClient):
    s = _settings()
    assert s.enabled is False  # nothing runs until the admin switches it on
    assert s.local_enabled and not s.drive_enabled and s.include_media
    assert (s.day, s.hour) == (6, 3)
    assert s.local_dir == str(config.BACKUP_LOCAL_DIR)


def test_settings_roundtrip_through_the_api(client: TestClient, tmp_path):
    target = tmp_path / "nas" / "recipes"
    r = client.put("/api/backups/settings", json={
        "enabled": True, "local_dir": str(target), "include_media": False, "day": 2, "hour": 21,
    })
    assert r.status_code == 200, r.text
    got = r.json()["settings"]
    assert got["enabled"] and got["local_dir"] == str(target) and got["include_media"] is False
    assert (got["day"], got["hour"]) == (2, 21)
    assert target.is_dir()  # created, and proven writable
    assert r.json()["next_run"]  # a Wednesday 9 PM slot is announced
    # persisted, not just echoed
    again = client.get("/api/backups/status").json()["settings"]
    assert again == got


@pytest.mark.parametrize("patch,needle", [
    ({"local_dir": "relative/path"}, "starts with /"),
    ({"local_dir": "   "}, "folder"),
    ({"day": 7}, "day"),
    ({"hour": 24}, "hour"),
    ({"drive_enabled": True, "drive_folder_name": ""}, "name"),
    ({"drive_enabled": True, "drive_folder_name": "a/b"}, "/"),
])
def test_bad_settings_are_rejected_with_a_message(client: TestClient, patch, needle):
    r = client.put("/api/backups/settings", json=patch)
    assert r.status_code == 400
    assert needle.lower() in r.json()["detail"].lower()


def test_unwritable_folder_is_caught_when_saving(client: TestClient, tmp_path):
    blocker = tmp_path / "a-file"
    blocker.write_text("x")
    r = client.put("/api/backups/settings", json={"local_dir": str(blocker / "sub")})
    assert r.status_code == 400 and "can't write" in r.json()["detail"].lower()


def test_weekly_needs_somewhere_to_save(client: TestClient):
    r = client.put("/api/backups/settings", json={"enabled": True, "local_enabled": False, "drive_enabled": False})
    assert r.status_code == 400 and "at least one" in r.json()["detail"].lower()


def test_renaming_the_drive_folder_forgets_the_old_folder_id(client: TestClient):
    conn = db.get_connection()
    try:
        bs.save_internal(conn, drive_folder_id="OLD", drive_folder_name="Old Name")
    finally:
        conn.close()
    assert _settings().drive_folder_id == "OLD"
    _configure(drive_folder_name="New Name")
    assert _settings().drive_folder_id == ""


def test_legacy_env_folder_id_is_honoured_until_a_name_is_chosen(client: TestClient, monkeypatch):
    monkeypatch.setattr(config, "DRIVE_BACKUP_FOLDER_ID", "LEGACY123")
    assert _settings().drive_folder_id == "LEGACY123"
    _configure(drive_folder_name="Brand New")  # explicit choice wins
    assert _settings().drive_folder_id == ""


def test_same_disk_warning_detects_a_folder_on_the_pi_itself(client: TestClient, tmp_path):
    # The test DB and the backup folder are both under tmp_path -> same filesystem.
    assert bs.same_disk_as_db(str(tmp_path / "backups")) is True


# =========================================================================== #
# The archive: one file, atomic, photos included
# =========================================================================== #
def test_local_backup_is_one_zip_with_db_photos_and_manifest(client: TestClient):
    rid = _recipe(client)
    photo = _photo()
    res = backup.run_now({"local"})["local"]
    assert res.ok, res.message

    final = _archive_path()
    assert [p.name for p in final.parent.iterdir()] == [config.BACKUP_FILENAME]  # no .partial, no extras
    with zipfile.ZipFile(final) as z:
        names = set(z.namelist())
        assert {"recipes.db", "manifest.json", "media/2026/10/a.jpg"} <= names
        assert z.read("media/2026/10/a.jpg") == photo.read_bytes()
        manifest = json.loads(z.read("manifest.json"))
        assert manifest["includes_media"] and manifest["media_files"] == 1
        assert manifest["format"] == 1 and manifest["migrations"]  # restore compatibility info
        z.extract("recipes.db", final.parent)
    snap = sqlite3.connect(final.parent / "recipes.db")
    assert snap.execute("SELECT title FROM recipe WHERE id = ?", (rid,)).fetchone()[0] == "Backup Me"
    snap.close()


def test_photos_can_be_left_out(client: TestClient):
    _photo()
    _configure(include_media=False)
    assert backup.run_now({"local"})["local"].ok
    with zipfile.ZipFile(_archive_path()) as z:
        assert not [n for n in z.namelist() if n.startswith("media/")]
        assert json.loads(z.read("manifest.json"))["includes_media"] is False


def test_backup_folder_inside_the_photo_folder_is_not_zipped_into_itself(client: TestClient):
    _photo()
    inside = config.media_root() / "backups"
    _configure(local_dir=str(inside))
    assert backup.run_now({"local"})["local"].ok
    assert backup.run_now({"local"})["local"].ok  # second run: the first zip is now in that folder
    with zipfile.ZipFile(inside / config.BACKUP_FILENAME) as z:
        assert not [n for n in z.namelist() if "backups" in n]


def test_each_run_replaces_the_one_file(client: TestClient):
    _recipe(client, "First")
    backup.run_now({"local"})
    first = _archive_path().read_bytes()
    _recipe(client, "Second")
    backup.run_now({"local"})
    assert _archive_path().read_bytes() != first
    assert len(list(_archive_path().parent.iterdir())) == 1


def test_a_failed_run_never_destroys_the_last_good_backup(client: TestClient, monkeypatch):
    _recipe(client)
    backup.run_now({"local"})
    good = _archive_path().read_bytes()

    def boom(path):
        raise backup.BackupError("disk went bad")
    monkeypatch.setattr(backup, "verify_archive", boom)
    res = backup.run_now({"local"})["local"]

    assert not res.ok and "disk went bad" in res.message
    assert _archive_path().read_bytes() == good  # untouched
    assert [p.name for p in _archive_path().parent.iterdir()] == [config.BACKUP_FILENAME]  # no .partial left
    assert _log("local")[-1]["ok"] == 0


def test_not_enough_free_space_fails_clearly_and_keeps_the_old_backup(client: TestClient, monkeypatch):
    _recipe(client)
    backup.run_now({"local"})
    good = _archive_path().read_bytes()
    real = backup.shutil.disk_usage
    monkeypatch.setattr(backup.shutil, "disk_usage", lambda p: type(real(p))(100, 100, 0))
    res = backup.run_now({"local"})["local"]
    assert not res.ok and "free space" in res.message.lower()
    assert _archive_path().read_bytes() == good


def test_unwritable_destination_at_run_time_is_recorded_not_raised(client: TestClient):
    _configure(local_dir=str(config.BACKUP_LOCAL_DIR))
    conn = db.get_connection()
    try:  # simulate the NAS going away after settings were saved
        conn.execute("UPDATE app_setting SET value = '/proc/nope/never' WHERE key = 'backup.local_dir'")
        conn.commit()
    finally:
        conn.close()
    res = backup.run_now({"local"})["local"]
    assert not res.ok and "can't write" in res.message.lower()
    assert _log("local")[-1]["ok"] == 0


def test_success_is_logged_with_a_readable_summary(client: TestClient):
    _recipe(client)
    _photo()
    backup.run_now({"local"})
    row = _log("local")[-1]
    assert row["ok"] == 1 and row["size_bytes"] > 0
    assert row["message"] == "1 recipe, 0 places, 1 photo"  # singular when it's one


# =========================================================================== #
# Restore
# =========================================================================== #
def test_restore_rebuilds_the_library_and_the_photos(client: TestClient):
    rid = _recipe(client)
    photo = _photo()
    data = photo.read_bytes()
    backup.run_now({"local"})
    archive = _archive_path()

    # The disaster: the recipe and the photo are gone.
    assert client.delete(f"/api/recipes/{rid}").status_code == 204
    photo.unlink()

    info = backup.restore(str(archive))
    assert info["photos"] == 1
    assert client.get(f"/api/recipes/{rid}").status_code == 200
    assert photo.read_bytes() == data
    # The pre-restore library is kept so a mistaken restore can be undone.
    assert list(config.DB_PATH.parent.glob(f"{config.DB_PATH.name}.before-restore-*"))


def test_restore_can_skip_photos(client: TestClient):
    photo = _photo()
    backup.run_now({"local"})
    photo.unlink()
    info = backup.restore(str(_archive_path()), with_media=False)
    assert info["photos"] == 0 and not photo.exists()


def test_restored_library_comes_back_already_configured(client: TestClient, tmp_path):
    target = tmp_path / "nas"
    _configure(local_dir=str(target), enabled=True, day=1, hour=22)
    backup.run_now({"local"})
    conn = db.get_connection()
    conn.execute("DELETE FROM app_setting")  # a fresh Pi knows nothing
    conn.commit()
    conn.close()
    backup.restore(str(target / config.BACKUP_FILENAME))
    s = _settings()
    assert s.enabled and (s.day, s.hour) == (1, 22) and s.local_dir == str(target)


def test_restore_still_reads_a_legacy_bare_db_snapshot(client: TestClient, tmp_path):
    rid = _recipe(client)
    legacy = tmp_path / "recipes-20260101.db"
    backup.snapshot(legacy)
    client.delete(f"/api/recipes/{rid}")
    backup.restore(str(legacy))
    assert client.get(f"/api/recipes/{rid}").status_code == 200


def test_restore_refuses_a_backup_from_a_newer_app(client: TestClient, tmp_path):
    backup.run_now({"local"})
    src = _archive_path()
    with zipfile.ZipFile(src) as z:
        z.extract("recipes.db", tmp_path)
    c = sqlite3.connect(tmp_path / "recipes.db")
    c.execute("INSERT INTO schema_migrations(filename) VALUES ('999_from_the_future.sql')")
    c.commit()
    c.close()
    newer = tmp_path / "newer.zip"
    with zipfile.ZipFile(newer, "w") as z:
        z.write(tmp_path / "recipes.db", "recipes.db")
    before = config.DB_PATH.read_bytes()
    with pytest.raises(backup.BackupError, match="newer version"):
        backup.restore(str(newer))
    assert config.DB_PATH.read_bytes() == before  # nothing was overwritten


@pytest.mark.parametrize("make,needle", [
    (lambda p: None, "not found"),
    (lambda p: p.write_bytes(b"definitely not sqlite at all"), "not a sqlite"),
])
def test_restore_rejects_missing_and_bogus_files(client: TestClient, tmp_path, make, needle):
    p = tmp_path / "x.db"
    make(p)
    with pytest.raises(backup.BackupError, match=f"(?i){needle}"):
        backup.restore(str(p))


def test_restore_rejects_a_zip_that_is_not_a_backup(client: TestClient, tmp_path):
    z = tmp_path / "other.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("hello.txt", "hi")
    with pytest.raises(backup.BackupError, match="no recipes.db"):
        backup.restore(str(z))


def test_restore_never_writes_outside_the_photo_folder(client: TestClient, tmp_path):
    backup.run_now({"local"})
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(_archive_path()) as src, zipfile.ZipFile(evil, "w") as out:
        out.writestr("recipes.db", src.read("recipes.db"))
        out.writestr("media/../../escaped.txt", "pwned")
    backup.restore(str(evil))
    assert not (config.media_root().parent / "escaped.txt").exists()
    assert not (config.media_root().parent.parent / "escaped.txt").exists()


# =========================================================================== #
# Google Drive (fake service)
# =========================================================================== #
class FakeDrive:
    """Just enough of the Drive v3 client for backup.py: folders, one file per name, uploads."""

    def __init__(self):
        self.items: dict[str, dict] = {}
        self.queries: list[str] = []
        self.n = 0
        self.lie_about_size: int | None = None
        self.creates = 0
        self.updates = 0

    def files(self):
        return self

    def _new(self, **kw):
        self.n += 1
        fid = f"id{self.n}"
        self.items[fid] = dict(kw, trashed=False)
        return fid

    def _name(self, q: str) -> str:
        m = re.match(r"name = '((?:\\.|[^'\\])*)'", q)
        return re.sub(r"\\(.)", r"\1", m.group(1))

    def list(self, q, fields=None, pageSize=None, orderBy=None):
        self.queries.append(q)
        name = self._name(q)
        is_folder = "mimeType = 'application/vnd.google-apps.folder'" in q
        hits = [
            {"id": i, "name": v["name"], "modifiedTime": "2026-10-11T03:00:00Z", "size": str(len(v.get("data", b"")))}
            for i, v in self.items.items()
            if v["name"] == name and not v["trashed"] and bool(v.get("folder")) == is_folder
            and (is_folder or f"'{v.get('parent')}' in parents" in q or "in parents" not in q)
        ]
        return _Req(lambda: {"files": hits})

    def get(self, fileId, fields=None):
        def go():
            if fileId not in self.items:
                raise RuntimeError("404 not found")
            return {"id": fileId, "trashed": self.items[fileId]["trashed"]}
        return _Req(go)

    def create(self, body, media_body=None, fields=None):
        self.creates += 1
        if media_body is None:
            fid = self._new(name=body["name"], folder=True)
            return _Req(lambda: {"id": fid})
        fid = self._new(name=body["name"], parent=body["parents"][0], data=media_body.getbytes(0, media_body.size()))
        return _Req(lambda: self._resp(fid), chunked=True)

    def update(self, fileId, media_body, fields=None):
        self.updates += 1
        self.items[fileId]["data"] = media_body.getbytes(0, media_body.size())
        return _Req(lambda: self._resp(fileId), chunked=True)

    def _resp(self, fid):
        size = self.lie_about_size if self.lie_about_size is not None else len(self.items[fid]["data"])
        return {"id": fid, "size": str(size)}

    def get_media(self, fileId):
        return self.items[fileId]["data"]


class _Req:
    def __init__(self, fn, chunked=False):
        self.fn = fn

    def execute(self):
        return self.fn()

    def next_chunk(self):
        return None, self.fn()


@pytest.fixture()
def fake_drive(client: TestClient, monkeypatch) -> FakeDrive:
    d = FakeDrive()
    monkeypatch.setattr(backup, "_drive_service", lambda: d)
    return d


def _folders(d: FakeDrive):
    return [v for v in d.items.values() if v.get("folder")]


def _drive_files(d: FakeDrive):
    return [v for v in d.items.values() if not v.get("folder")]


def test_drive_backup_creates_the_named_folder_and_uploads_the_zip(client, fake_drive):
    _recipe(client)
    _photo()
    _configure(drive_enabled=True, local_enabled=False, drive_folder_name="Our Recipe Backups")
    res = backup.run_now({"drive"})["drive"]
    assert res.ok, res.message
    assert [f["name"] for f in _folders(fake_drive)] == ["Our Recipe Backups"]
    (up,) = _drive_files(fake_drive)
    assert up["name"] == config.BACKUP_FILENAME
    assert zipfile.is_zipfile(__import__("io").BytesIO(up["data"]))  # a real, complete archive
    assert _settings().drive_folder_id  # remembered for next time
    assert _log("drive")[-1]["ok"] == 1


def test_second_drive_run_replaces_the_file_instead_of_piling_up(client, fake_drive):
    _configure(drive_enabled=True, local_enabled=False)
    backup.run_now({"drive"})
    backup.run_now({"drive"})
    assert len(_folders(fake_drive)) == 1 and len(_drive_files(fake_drive)) == 1
    assert fake_drive.updates == 1  # the existing file was updated (Drive keeps its version history)


def test_a_deleted_drive_folder_is_recreated(client, fake_drive):
    _configure(drive_enabled=True, local_enabled=False)
    backup.run_now({"drive"})
    for v in fake_drive.items.values():
        v["trashed"] = True
    res = backup.run_now({"drive"})["drive"]
    assert res.ok
    assert len([f for f in _folders(fake_drive) if not f["trashed"]]) == 1


def test_folder_names_with_apostrophes_are_escaped_in_the_query(client, fake_drive):
    _configure(drive_enabled=True, local_enabled=False, drive_folder_name="Dan's Backups")
    assert backup.run_now({"drive"})["drive"].ok
    assert any("Dan\\'s Backups" in q for q in fake_drive.queries)


def test_an_upload_that_did_not_arrive_intact_is_not_trusted(client, fake_drive):
    _configure(drive_enabled=True, local_enabled=False)
    fake_drive.lie_about_size = 5
    res = backup.run_now({"drive"})["drive"]
    assert not res.ok and "not trusted" in res.message
    assert _log("drive")[-1]["ok"] == 0


def test_drive_without_a_google_connection_says_so(client, monkeypatch):
    monkeypatch.setattr(backup, "_drive_service", lambda: None)
    _configure(drive_enabled=True, local_enabled=False)
    res = backup.run_now({"drive"})["drive"]
    assert not res.ok and "connect it in settings" in res.message.lower()


def test_drive_and_local_succeed_or_fail_independently(client, fake_drive, monkeypatch):
    _configure(drive_enabled=True)
    fake_drive.lie_about_size = 1  # Drive will fail...
    out = backup.run_now({"local", "drive"})
    assert out["local"].ok and not out["drive"].ok  # ...local is unaffected

    fake_drive.lie_about_size = None
    monkeypatch.setattr(backup, "verify_archive", lambda p: (_ for _ in ()).throw(backup.BackupError("bad")))
    out = backup.run_now({"local", "drive"})
    assert not out["local"].ok and not out["drive"].ok  # a corrupt archive is never uploaded


def test_drive_only_run_leaves_no_scratch_files_behind(client, fake_drive, monkeypatch, tmp_path):
    made = []
    real = backup.tempfile.mkdtemp
    monkeypatch.setattr(backup.tempfile, "mkdtemp", lambda *a, **k: made.append(real(*a, **k)) or made[-1])
    _configure(drive_enabled=True, local_enabled=False)
    backup.run_now({"drive"})
    assert made and not any(Path(m).exists() for m in made)


def test_restore_from_drive_downloads_then_restores(client, fake_drive, monkeypatch, tmp_path):
    rid = _recipe(client)
    _configure(drive_enabled=True, local_enabled=False)
    backup.run_now({"drive"})
    client.delete(f"/api/recipes/{rid}")

    class FakeDownload:
        def __init__(self, fh, request, chunksize=None):
            self.fh, self.request = fh, request

        def next_chunk(self):
            self.fh.write(self.request)
            return None, True
    monkeypatch.setattr("googleapiclient.http.MediaIoBaseDownload", FakeDownload)

    got = backup.fetch_from_drive(tmp_path)
    assert got.name == config.BACKUP_FILENAME
    backup.restore(str(got))
    assert client.get(f"/api/recipes/{rid}").status_code == 200


def test_restore_from_drive_without_google_or_file_is_clear(client, monkeypatch, tmp_path):
    monkeypatch.setattr(backup, "_drive_service", lambda: None)
    with pytest.raises(backup.BackupError, match="connect it in Settings"):
        backup.fetch_from_drive(tmp_path)
    monkeypatch.setattr(backup, "_drive_service", lambda: FakeDrive())
    with pytest.raises(backup.BackupError, match="No 'recipes-backup.zip'"):
        backup.fetch_from_drive(tmp_path)


# =========================================================================== #
# The runner + API
# =========================================================================== #
def _wait_idle(timeout=10):
    end = time.time() + timeout
    while backup.current()["running"] and time.time() < end:
        time.sleep(0.02)
    assert not backup.current()["running"], "backup did not finish"


def test_run_now_endpoint_starts_in_background_and_finishes(client: TestClient):
    _recipe(client)
    r = client.post("/api/backups/run", json={})
    assert r.status_code == 200, r.text
    _wait_idle()
    st = client.get("/api/backups/status").json()
    assert st["running"] is False and st["local"]["ok"] == 1
    assert _archive_path().is_file()


def test_progress_is_visible_while_running_and_a_second_start_is_refused(client: TestClient, monkeypatch):
    gate, started = threading.Event(), threading.Event()

    def slow_run(targets):
        started.set()
        backup._step("Packing photos… 3 of 9")
        gate.wait(5)
        return {}
    monkeypatch.setattr(backup, "_run", slow_run)

    assert client.post("/api/backups/run", json={}).status_code == 200
    assert started.wait(5)
    st = client.get("/api/backups/status").json()
    assert st["running"] is True and st["step"] == "Packing photos… 3 of 9"
    assert st["media"] is None  # no slow folder walk while a run is in flight
    again = client.post("/api/backups/run", json={})
    assert again.status_code == 409 and "already running" in again.json()["detail"]
    gate.set()
    _wait_idle()
    assert client.get("/api/backups/status").json()["running"] is False


def test_run_refuses_with_a_clear_message_when_nothing_is_switched_on(client: TestClient):
    _configure(local_enabled=False)
    r = client.post("/api/backups/run", json={})
    assert r.status_code == 400 and "choose where" in r.json()["detail"].lower()


def test_drive_run_requires_a_google_connection(client: TestClient, monkeypatch):
    monkeypatch.setattr(drive_mod, "authorized", lambda: False)
    r = client.post("/api/backups/run", json={"kind": "drive"})
    assert r.status_code == 400 and "connect google" in r.json()["detail"].lower()


def test_unknown_run_kind_is_rejected(client: TestClient):
    assert client.post("/api/backups/run", json={"kind": "bogus"}).status_code == 400


def test_status_reports_photo_estimate_and_google_state(client: TestClient):
    _photo(data=b"x" * 1000)
    st = client.get("/api/backups/status").json()
    assert st["media"]["files"] == 1 and st["media"]["bytes"] == 1000
    assert set(st["google"]) == {"configured", "authorized"}
    assert st["day_names"][6] == "Sunday"


# =========================================================================== #
# The scheduler tick
# =========================================================================== #
def test_tick_does_nothing_while_weekly_is_off(client: TestClient):
    assert backup_scheduler.tick(NOW) == []
    assert not _archive_path().exists()


def test_tick_runs_a_due_backup_then_leaves_it_alone(client: TestClient):
    _recipe(client)
    _configure(enabled=True)
    started = backup_scheduler.tick(datetime.now())
    assert started == ["local"]
    _wait_idle()
    assert _archive_path().is_file()
    # Done for this week: the next checks must not start another one.
    assert backup_scheduler.tick(datetime.now()) == []
    assert backup_scheduler.tick(datetime.now() + timedelta(days=3)) == []


def test_tick_retries_after_an_hour_when_the_attempt_failed(client: TestClient, monkeypatch):
    _configure(enabled=True)
    conn = db.get_connection()
    conn.execute(
        "INSERT INTO backup_log(kind, target, ok, message, created_at) VALUES ('local', '', 0, 'nas offline', datetime('now'))"
    )
    conn.commit()
    conn.close()
    started = []
    monkeypatch.setattr(backup, "start_background", lambda t: started.append(sorted(t)) or True)
    assert backup_scheduler.tick(datetime.now() + timedelta(minutes=10)) == []   # too soon to retry
    assert backup_scheduler.tick(datetime.now() + timedelta(minutes=90)) == ["local"]


# =========================================================================== #
# CLI
# =========================================================================== #
def test_cli_backup_and_restore(client: TestClient, capsys):
    rid = _recipe(client)
    assert backup.main(["local"]) == 0
    client.delete(f"/api/recipes/{rid}")
    with pytest.raises(SystemExit, match="--yes"):
        backup.main(["restore", str(_archive_path())])
    assert backup.main(["restore", str(_archive_path()), "--yes"]) == 0
    assert client.get(f"/api/recipes/{rid}").status_code == 200
    assert "Restored" in capsys.readouterr().out


def test_cli_reports_failure_with_a_nonzero_exit(client: TestClient, monkeypatch, capsys):
    monkeypatch.setattr(backup, "_drive_service", lambda: None)
    _configure(drive_enabled=True)
    assert backup.main(["drive"]) == 1
    assert "FAILED" in capsys.readouterr().err
