"""Backup & restore (spec §11) — one file that can rebuild the whole library on a new Pi.

`recipes-backup.zip` holds:
  recipes.db     a consistent snapshot (`VACUUM INTO`, never a live-file copy)
  media/...      the photos (optional) — the DB only stores their relative paths
  manifest.json  what's inside + which schema migrations it was made with

It is REPLACED each time (one file, not a pile of dated ones): built under a temporary name,
checked, then swapped in atomically — a failed run can never destroy the last good backup.
Destinations (chosen in the admin console, see backup_settings): a folder on this Pi / a NAS /
a USB drive, and/or a Google Drive folder the app creates (Drive keeps version history).

Runs from the app (weekly schedule + the "Back up now" button) and from the CLI:

    python -m app.backup local|drive|both     # use the saved destinations
    python -m app.backup restore /path/recipes-backup.zip --yes
    python -m app.backup restore-drive --yes  # fetch the newest backup from Google Drive
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import backup_settings, config
from .db import get_connection
from .extraction import drive as drive_mod

ARCHIVE_NAME = config.BACKUP_FILENAME
FORMAT_VERSION = 1
# Photos are already compressed; deflating them again burns Pi CPU for ~0 savings.
_STORED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".mp4", ".mov", ".zip"}


class BackupError(Exception):
    """A backup step failed in a way the admin can act on; the message is shown to them."""


class BackupBusy(BackupError):
    pass


# --------------------------------------------------------------------------- #
# Progress shared with the UI while a run is in flight
# --------------------------------------------------------------------------- #
_lock = threading.Lock()
# kind: "backup" | "restore" while running. restore_result keeps the last in-app restore's
# outcome so the page can show it after the work finishes (and after a reload).
_state: dict = {"running": False, "kind": None, "step": "", "targets": [], "started_at": None, "restore_result": None}


def current() -> dict:
    return dict(_state)


def _begin(kind: str, targets: set[str] | None = None) -> None:
    _state.update(running=True, kind=kind, step="Starting…", targets=sorted(targets or ()),
                  started_at=datetime.now().isoformat(timespec="seconds"))


def _end() -> None:
    _state.update(running=False, kind=None, step="", targets=[])


def _step(message: str) -> None:
    _state["step"] = message


# --------------------------------------------------------------------------- #
# Snapshot + archive
# --------------------------------------------------------------------------- #
def snapshot(dest: Path) -> None:
    """Write a consistent, compacted copy of the live DB to `dest` via VACUUM INTO."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()  # VACUUM INTO refuses to overwrite an existing file
    conn = sqlite3.connect(str(config.DB_PATH))
    try:
        try:
            conn.execute("VACUUM INTO ?", (str(dest),))
        except sqlite3.OperationalError:
            conn.execute(f"VACUUM INTO '{str(dest)}'")
    finally:
        conn.close()


def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except (ValueError, OSError):
        return False


def iter_media(exclude: list[Path]) -> list[tuple[Path, str]]:
    """(absolute path, path relative to MEDIA_ROOT) for every photo, skipping our own backup
    folders — the default backup dir lives inside MEDIA_ROOT and must not be zipped into itself."""
    root = config.media_root()
    out: list[tuple[Path, str]] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        here = Path(dirpath)
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and not any(_is_under(here / d, x) for x in exclude)]
        for name in filenames:
            if name.startswith(".") or name.endswith((".tmp", ".partial")):
                continue
            p = here / name
            if p.is_file() and not p.is_symlink():
                out.append((p, p.relative_to(root).as_posix()))
    return out


def media_estimate(exclude: list[Path]) -> dict:
    files = iter_media(exclude)
    size = 0
    for p, _ in files:
        try:
            size += p.stat().st_size
        except OSError:
            pass
    return {"files": len(files), "bytes": size}


def _db_counts(db_file: Path) -> dict:
    conn = sqlite3.connect(str(db_file))
    try:
        def n(sql: str) -> int:
            try:
                return conn.execute(sql).fetchone()[0]
            except sqlite3.Error:
                return 0
        migrations = [r[0] for r in conn.execute("SELECT filename FROM schema_migrations ORDER BY filename")]
        return {
            "recipes": n("SELECT COUNT(*) FROM recipe WHERE status = 'published'"),
            "places": n("SELECT COUNT(*) FROM place WHERE status = 'published'"),
            "migrations": migrations,
        }
    finally:
        conn.close()


def build_archive(dest: Path, *, include_media: bool, exclude: list[Path]) -> dict:
    """Write the backup zip at `dest` and return its manifest. `dest` is a temporary name —
    the caller verifies it and swaps it into place."""
    media = iter_media(exclude) if include_media else []
    media_bytes = sum(p.stat().st_size for p, _ in media if p.exists())

    with tempfile.TemporaryDirectory(dir=dest.parent) as td:
        snap = Path(td) / "recipes.db"
        _step("Copying the database…")
        snapshot(snap)
        db_bytes = snap.stat().st_size

        need = int((db_bytes + media_bytes) * 1.05) + 10_000_000
        free = shutil.disk_usage(dest.parent).free
        if free < need:
            raise BackupError(
                f"Not enough free space in {dest.parent}: need about {need // 1_000_000} MB, "
                f"{free // 1_000_000} MB free."
            )

        counts = _db_counts(snap)
        manifest = {
            "format": FORMAT_VERSION,
            "app": "Pi Recipe Site",
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "recipes": counts["recipes"],
            "places": counts["places"],
            "migrations": counts["migrations"],
            "includes_media": bool(include_media),
            "media_files": len(media),
            "media_bytes": media_bytes,
        }
        with zipfile.ZipFile(dest, "w", allowZip64=True) as z:
            z.write(snap, "recipes.db", compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)
            for i, (path, rel) in enumerate(media, 1):
                if i == 1 or i % 25 == 0 or i == len(media):
                    _step(f"Packing photos… {i} of {len(media)}")
                kind = zipfile.ZIP_STORED if path.suffix.lower() in _STORED_SUFFIXES else zipfile.ZIP_DEFLATED
                try:
                    z.write(path, f"media/{rel}", compress_type=kind)
                except FileNotFoundError:
                    manifest["media_files"] -= 1  # deleted while we were packing — fine
            z.writestr("manifest.json", json.dumps(manifest, indent=2))
    return manifest


def verify_archive(path: Path) -> None:
    """Re-read what we just wrote. An unreadable backup is worse than none — it looks fine."""
    _step("Checking the backup…")
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            if "recipes.db" not in names or "manifest.json" not in names:
                raise BackupError("The backup file is incomplete (missing database or manifest).")
            bad = z.testzip()
            if bad:
                raise BackupError(f"The backup file is damaged ({bad}).")
    except zipfile.BadZipFile as e:
        raise BackupError("The backup file is damaged and can't be opened.") from e


# --------------------------------------------------------------------------- #
# Log
# --------------------------------------------------------------------------- #
def _record(kind: str, target: str, ok: bool, message: str, size: int | None) -> None:
    try:
        conn = get_connection()
        conn.execute(
            "INSERT INTO backup_log(kind, target, ok, message, size_bytes) VALUES (?, ?, ?, ?, ?)",
            (kind, target, 1 if ok else 0, message, size),
        )
        conn.commit()
        conn.close()
    except Exception as e:  # never let logging failure mask the backup result
        print(f"(warning) could not record backup status: {e}", file=sys.stderr)


def _n(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def _summary(manifest: dict) -> str:
    bits = [_n(manifest["recipes"], "recipe"), _n(manifest["places"], "place")]
    bits.append(_n(manifest["media_files"], "photo") if manifest["includes_media"] else "no photos")
    return ", ".join(bits)


@dataclass
class Result:
    ok: bool
    message: str
    path: str = ""
    size: int | None = None


# --------------------------------------------------------------------------- #
# Destinations
# --------------------------------------------------------------------------- #
def _exclude_dirs(settings: backup_settings.BackupSettings) -> list[Path]:
    dirs = [config.BACKUP_LOCAL_DIR]
    if settings.local_dir:
        dirs.append(Path(settings.local_dir).expanduser())
    return dirs


def _write_local(settings: backup_settings.BackupSettings) -> tuple[Path, dict]:
    target_dir = backup_settings.check_local_dir(settings.local_dir)
    partial = target_dir / f".{ARCHIVE_NAME}.partial"
    final = target_dir / ARCHIVE_NAME
    try:
        manifest = build_archive(partial, include_media=settings.include_media, exclude=_exclude_dirs(settings))
        verify_archive(partial)
        os.replace(partial, final)  # atomic: the old backup stays intact until this instant
    finally:
        partial.unlink(missing_ok=True)
    return final, manifest


def _drive_service():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        return None
    token = Path(config.GOOGLE_TOKEN_PATH)
    if not token.exists():
        return None
    creds = Credentials.from_authorized_user_file(str(token), drive_mod.SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token.write_text(creds.to_json())
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _q(value: str) -> str:
    """Escape a value for a Drive search query."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _ensure_drive_folder(service, settings: backup_settings.BackupSettings) -> str:
    """The Drive folder id to upload into: the saved one if it still exists, else find-or-create
    the folder by name in My Drive. The app creates (and so may write to) its own folder — Google's
    `drive.file` permission can't write into a folder you made by hand."""
    if settings.drive_folder_id:
        try:
            f = service.files().get(fileId=settings.drive_folder_id, fields="id,trashed").execute()
            if not f.get("trashed"):
                return f["id"]
        except Exception:
            pass  # gone or not ours — fall through and make a fresh one
    q = (
        f"name = '{_q(settings.drive_folder_name)}' and "
        "mimeType = 'application/vnd.google-apps.folder' and 'root' in parents and trashed = false"
    )
    found = service.files().list(q=q, fields="files(id)", pageSize=1).execute().get("files", [])
    if found:
        fid = found[0]["id"]
    else:
        meta = {"name": settings.drive_folder_name, "mimeType": "application/vnd.google-apps.folder"}
        fid = service.files().create(body=meta, fields="id").execute()["id"]
    conn = get_connection()
    try:
        backup_settings.save_internal(conn, drive_folder_id=fid)
    finally:
        conn.close()
    return fid


def _upload_drive(service, path: Path, folder_id: str) -> str:
    """Replace the single backup file in the folder (or create it). Resumable, so a multi-hundred-MB
    archive survives a flaky connection; `update` keeps Drive's version history for rollback."""
    from googleapiclient.http import MediaFileUpload

    q = f"name = '{_q(ARCHIVE_NAME)}' and '{folder_id}' in parents and trashed = false"
    existing = service.files().list(q=q, fields="files(id)").execute().get("files", [])
    media = MediaFileUpload(str(path), mimetype="application/zip", resumable=True, chunksize=8 * 1024 * 1024)
    fields = "id,size"
    if existing:
        req = service.files().update(fileId=existing[0]["id"], media_body=media, fields=fields)
    else:
        meta = {"name": ARCHIVE_NAME, "parents": [folder_id]}
        req = service.files().create(body=meta, media_body=media, fields=fields)
    response = None
    while response is None:
        status, response = req.next_chunk()
        if status:
            _step(f"Uploading to Google Drive… {int(status.progress() * 100)}%")
    sent = int(response.get("size", -1))
    if sent != path.stat().st_size:
        raise BackupError(f"Google Drive stored {sent} bytes but the backup is {path.stat().st_size} — upload not trusted.")
    return response["id"]


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def _run(targets: set[str]) -> dict[str, Result]:
    conn = get_connection()
    try:
        settings = backup_settings.load(conn)
    finally:
        conn.close()

    results: dict[str, Result] = {}
    archive: Path | None = None
    manifest: dict | None = None
    scratch: str | None = None
    try:
        if "local" in targets:
            _step("Starting the backup…")
            try:
                archive, manifest = _write_local(settings)
                size = archive.stat().st_size
                msg = _summary(manifest)
                _record("local", str(archive), True, msg, size)
                results["local"] = Result(True, msg, str(archive), size)
            except Exception as e:
                msg = str(e)[:300] or e.__class__.__name__
                _record("local", settings.local_dir, False, msg, None)
                results["local"] = Result(False, msg)

        if "drive" in targets:
            try:
                service = _drive_service()
                if service is None:
                    raise BackupError("Google isn't connected yet — connect it in Settings first.")
                if archive is None:  # Drive-only run (or local failed): build in a scratch folder
                    scratch = tempfile.mkdtemp(prefix="recipes-backup-")
                    archive = Path(scratch) / ARCHIVE_NAME
                    manifest = build_archive(archive, include_media=settings.include_media, exclude=_exclude_dirs(settings))
                    verify_archive(archive)
                _step("Connecting to Google Drive…")
                folder_id = _ensure_drive_folder(service, settings)
                file_id = _upload_drive(service, archive, folder_id)
                size = archive.stat().st_size
                msg = _summary(manifest or {"recipes": 0, "places": 0, "includes_media": False, "media_files": 0})
                _record("drive", file_id, True, msg, size)
                results["drive"] = Result(True, msg, file_id, size)
            except Exception as e:
                msg = str(e)[:300] or e.__class__.__name__
                _record("drive", "", False, msg, None)
                results["drive"] = Result(False, msg)
    finally:
        if scratch:
            shutil.rmtree(scratch, ignore_errors=True)
    return results


def run_now(targets: set[str]) -> dict[str, Result]:
    """Run synchronously (CLI, tests). Raises BackupBusy if another run is in flight."""
    if not _lock.acquire(blocking=False):
        raise BackupBusy("A backup is already running.")
    _begin("backup", targets)
    try:
        return _run(targets)
    finally:
        _end()
        _lock.release()


def start_background(targets: set[str]) -> bool:
    """Start a run on a worker thread (the web request returns immediately and the page polls
    progress). False when a run is already in flight."""
    if not _lock.acquire(blocking=False):
        return False
    _begin("backup", targets)

    def worker() -> None:
        try:
            _run(targets)
        except Exception as e:  # _run records per-target failures; this is a last-resort net
            print(f"(warning) backup crashed: {e}", file=sys.stderr)
        finally:
            _end()
            _lock.release()

    threading.Thread(target=worker, name="backup", daemon=True).start()
    return True


# Back-compat wrappers (CLI + older callers). They raise when their one target fails.
def run_local() -> Path:
    r = run_now({"local"})["local"]
    if not r.ok:
        raise BackupError(r.message)
    return Path(r.path)


def run_drive() -> str | None:
    r = run_now({"drive"})["drive"]
    if not r.ok:
        raise BackupError(r.message)
    return r.path


# --------------------------------------------------------------------------- #
# Restore
# --------------------------------------------------------------------------- #
def _known_migrations() -> set[str]:
    from .migrations_runner import _MIGRATIONS_DIR

    return {p.name for p in _MIGRATIONS_DIR.glob("*.sql")}


def _check_db_file(path: Path) -> list[str]:
    """It must be a SQLite file made by a version of the app we understand. Returns its migrations."""
    with open(path, "rb") as f:
        if f.read(16) != b"SQLite format 3\x00":
            raise BackupError(f"Not a SQLite database: {path}")
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        applied = [r[0] for r in conn.execute("SELECT filename FROM schema_migrations")]
    except sqlite3.Error as e:
        raise BackupError("That database isn't from this app (no migration history).") from e
    finally:
        conn.close()
    newer = sorted(set(applied) - _known_migrations())
    if newer:
        raise BackupError(
            f"This backup was made by a newer version of the app (it has {', '.join(newer)}). "
            "Update the app first (scripts/update.sh), then restore."
        )
    return applied


def restore(source: str, *, with_media: bool = True) -> dict:
    """Restore a backup (.zip, or a bare .db) over the live library. STOP the app first.

    The current database is kept alongside as `<db>.before-restore-<time>` so a mistaken
    restore can be undone. Photos are unpacked into MEDIA_ROOT (same names → same files)."""
    src = Path(source)
    if not src.is_file():
        raise BackupError(f"Backup not found: {src}")

    media_members: list[zipfile.ZipInfo] = []
    with tempfile.TemporaryDirectory() as td:
        if zipfile.is_zipfile(src):
            zf = zipfile.ZipFile(src)
            if "recipes.db" not in zf.namelist():
                raise BackupError("That zip isn't a recipe backup (no recipes.db inside).")
            db_file = Path(td) / "recipes.db"
            with zf.open("recipes.db") as a, open(db_file, "wb") as b:
                shutil.copyfileobj(a, b)
            media_members = [m for m in zf.infolist() if m.filename.startswith("media/") and not m.is_dir()]
        else:
            zf = None
            db_file = src
        _check_db_file(db_file)

        dest = config.DB_PATH
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and dest.stat().st_size > 0:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            shutil.copy2(dest, dest.with_name(f"{dest.name}.before-restore-{stamp}"))
        # Remove WAL/SHM sidecars so the restored DB isn't shadowed by stale journals.
        for side in (dest.with_suffix(dest.suffix + "-wal"), dest.with_suffix(dest.suffix + "-shm")):
            side.unlink(missing_ok=True)
        shutil.copy2(db_file, dest)

        restored_media = _unpack_media(zf, media_members) if zf is not None and with_media else 0
        if zf is not None:
            zf.close()
    return {"database": str(dest), "photos": restored_media, "photos_in_backup": len(media_members)}


def _unpack_media(zf: zipfile.ZipFile, members: list[zipfile.ZipInfo]) -> int:
    """Write the photos into MEDIA_ROOT (same names = same files). Never writes outside it."""
    root = config.media_root().resolve()
    done = 0
    for i, m in enumerate(members, 1):
        rel = m.filename[len("media/"):]
        target = (root / rel).resolve()
        if root not in target.parents:  # zip-slip guard
            continue
        if i == 1 or i % 25 == 0 or i == len(members):
            _step(f"Restoring photos… {i} of {len(members)}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(m) as a, open(target, "wb") as b:
            shutil.copyfileobj(a, b)
        done += 1
    return done


# --------------------------------------------------------------------------- #
# In-app restore: stage -> check -> (confirm) -> apply, while the app keeps running
# --------------------------------------------------------------------------- #
KEEP_SAFETY_COPIES = 3


def staging_dir() -> Path:
    d = config.DB_PATH.parent / "restore-staging"
    d.mkdir(parents=True, exist_ok=True)
    return d


def staged_file() -> Path:
    return staging_dir() / "staged-backup"


def clear_staged() -> None:
    for p in staging_dir().glob("*"):
        p.unlink(missing_ok=True)


def current_counts() -> dict:
    conn = get_connection()
    try:
        def n(sql: str) -> int:
            try:
                return conn.execute(sql).fetchone()[0]
            except sqlite3.Error:
                return 0
        return {
            "recipes": n("SELECT COUNT(*) FROM recipe WHERE status = 'published'"),
            "places": n("SELECT COUNT(*) FROM place WHERE status = 'published'"),
        }
    finally:
        conn.close()


def inspect_backup(path: Path) -> dict:
    """Check a backup file and describe it, changing nothing. Raises BackupError (with a message
    meant for the admin) if it can't be restored by this version of the app."""
    if not path.is_file():
        raise BackupError(f"Backup not found: {path.name}")
    manifest: dict = {}
    media: list[zipfile.ZipInfo] = []
    with tempfile.TemporaryDirectory(dir=staging_dir()) as td:
        if zipfile.is_zipfile(path):
            kind = "zip"
            with zipfile.ZipFile(path) as zf:
                names = zf.namelist()
                if "recipes.db" not in names:
                    raise BackupError("That zip isn't a recipe backup (no recipes.db inside).")
                db_file = Path(td) / "recipes.db"
                with zf.open("recipes.db") as a, open(db_file, "wb") as b:
                    shutil.copyfileobj(a, b)
                media = [m for m in zf.infolist() if m.filename.startswith("media/") and not m.is_dir()]
                if "manifest.json" in names:
                    try:
                        manifest = json.loads(zf.read("manifest.json"))
                    except ValueError:
                        manifest = {}
        else:
            kind, db_file = "db", path
            with open(path, "rb") as f:
                if f.read(16) != b"SQLite format 3\x00":
                    raise BackupError("That file isn't a recipe backup. Choose the recipes-backup.zip file.")
        _check_db_file(db_file)
        counts = _db_counts(db_file)
    created = manifest.get("created_at") or datetime.fromtimestamp(
        path.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds")
    return {
        "kind": kind,
        "created_at": created,
        "size_bytes": path.stat().st_size,
        "recipes": counts["recipes"],
        "places": counts["places"],
        "media_files": len(media),
        "media_bytes": sum(m.file_size for m in media),
        "includes_media": bool(media),
    }


def _save_current_copy() -> str | None:
    """Keep the library as it is right now, so a restore can be undone. Newest few are kept."""
    if not config.DB_PATH.exists() or config.DB_PATH.stat().st_size == 0:
        return None
    dest = config.DB_PATH.parent / f"before-restore-{datetime.now():%Y%m%d-%H%M%S}.db"
    snapshot(dest)
    old = sorted(config.DB_PATH.parent.glob("before-restore-*.db"))
    for p in old[: max(0, len(old) - KEEP_SAFETY_COPIES)]:
        p.unlink(missing_ok=True)
    return str(dest)


def _replace_live_db(db_file: Path) -> None:
    """Swap the library's contents with SQLite's backup API: transactional, safe while the app
    is running (a plain file copy over a live WAL database is not)."""
    src = sqlite3.connect(f"{db_file.resolve().as_uri()}?mode=ro", uri=True)
    dest = sqlite3.connect(str(config.DB_PATH), timeout=60)
    try:
        src.backup(dest)
    finally:
        dest.close()
        src.close()


def apply_restore_live(source: Path, *, with_media: bool = True) -> dict:
    """Restore `source` over the running library. The caller holds the backup lock."""
    info = inspect_backup(source)  # re-check: never trust the staged file blindly
    _step("Saving a copy of the current library…")
    safety = _save_current_copy()
    photos = 0
    with tempfile.TemporaryDirectory(dir=staging_dir()) as td:
        zf = None
        try:
            if info["kind"] == "zip":
                zf = zipfile.ZipFile(source)
                db_file = Path(td) / "recipes.db"
                with zf.open("recipes.db") as a, open(db_file, "wb") as b:
                    shutil.copyfileobj(a, b)
            else:
                db_file = source
            _step("Replacing the library…")
            _replace_live_db(db_file)
            from .migrations_runner import run_migrations

            run_migrations()  # an older backup gets the newer tables it's missing
            if zf is not None and with_media:
                members = [m for m in zf.infolist() if m.filename.startswith("media/") and not m.is_dir()]
                photos = _unpack_media(zf, members)
        finally:
            if zf is not None:
                zf.close()
    return {**info, "photos_restored": photos, "safety_copy": safety}


def start_restore(source: Path, with_media: bool) -> bool:
    """Apply a staged backup on a worker thread; the page polls /status. False if a backup or
    another restore is in flight."""
    if not _lock.acquire(blocking=False):
        return False
    _begin("restore")
    _state["restore_result"] = None

    def worker() -> None:
        try:
            result = apply_restore_live(source, with_media=with_media)
            _state["restore_result"] = {"ok": True, **result}
            clear_staged()
        except Exception as e:
            msg = str(e)[:300] or e.__class__.__name__
            _state["restore_result"] = {"ok": False, "message": msg}
        finally:
            _end()
            _lock.release()

    threading.Thread(target=worker, name="restore", daemon=True).start()
    return True


def fetch_from_drive(dest_dir: Path) -> Path:
    """Download the newest backup this app can see on Google Drive (for a brand-new Pi: connect
    Google in Settings first — the same Google Cloud client sees the files it created before)."""
    service = _drive_service()
    if service is None:
        raise BackupError("Google isn't connected on this Pi — connect it in Settings, then try again.")
    q = f"name = '{_q(ARCHIVE_NAME)}' and trashed = false"
    files = service.files().list(
        q=q, orderBy="modifiedTime desc", pageSize=1, fields="files(id,name,modifiedTime,size)"
    ).execute().get("files", [])
    if not files:
        raise BackupError(f"No '{ARCHIVE_NAME}' found on the connected Google Drive.")
    from googleapiclient.http import MediaIoBaseDownload

    out = dest_dir / ARCHIVE_NAME
    with open(out, "wb") as fh:
        dl = MediaIoBaseDownload(fh, service.files().get_media(fileId=files[0]["id"]), chunksize=8 * 1024 * 1024)
        done = False
        while not done:
            _, done = dl.next_chunk()
    print(f"Downloaded {ARCHIVE_NAME} (modified {files[0]['modifiedTime']}) from Google Drive.")
    return out


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _print_results(results: dict[str, Result]) -> int:
    failed = 0
    for kind, r in results.items():
        if r.ok:
            print(f"{kind}: OK — {r.message} ({(r.size or 0) // 1024} KB) {r.path}")
        else:
            failed += 1
            print(f"{kind}: FAILED — {r.message}", file=sys.stderr)
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    cmd = args[0] if args else "both"
    try:
        if cmd in ("local", "drive"):
            return _print_results(run_now({cmd}))
        if cmd in ("both", "run"):
            return _print_results(run_now({"local", "drive"}))
        if cmd in ("restore", "restore-drive"):
            if "--yes" not in args:
                raise SystemExit("Refusing to restore without --yes (this replaces the live library). Stop the app first.")
            with_media = "--no-media" not in args
            if cmd == "restore":
                rest = [a for a in args[1:] if not a.startswith("--")]
                if not rest:
                    raise SystemExit("Usage: python -m app.backup restore /path/to/recipes-backup.zip --yes")
                info = restore(rest[0], with_media=with_media)
            else:
                with tempfile.TemporaryDirectory() as td:
                    info = restore(str(fetch_from_drive(Path(td))), with_media=with_media)
            print(f"Restored the database to {info['database']} and {info['photos']} of "
                  f"{info['photos_in_backup']} photos. Start the app again (sudo systemctl start recipes).")
            return 0
    except BackupError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    raise SystemExit(f"Unknown command: {cmd} (use local|drive|both|restore|restore-drive)")


if __name__ == "__main__":
    raise SystemExit(main())
