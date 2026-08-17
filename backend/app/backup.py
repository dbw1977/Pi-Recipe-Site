"""Backup & restore (spec §11) — a standalone script, decoupled from the web app so it
runs even while the app is restarting.

- Consistent snapshots via `VACUUM INTO` (never copy a live DB file).
- Nightly LOCAL snapshot (often the NAS mount), keeping the last N.
- Weekly DRIVE backup: overwrite one file in a dedicated folder (Drive keeps version
  history for rollback), reusing the Chunk B Google OAuth token.
- Every run records success/failure in `backup_log` so the UI can surface health.

Usage (inside the backend venv):
    python -m app.backup local        # nightly
    python -m app.backup drive        # weekly
    python -m app.backup both
    python -m app.backup restore /path/to/snapshot.db --yes
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import date
from pathlib import Path

from . import config
from .db import get_connection
from .extraction import drive as drive_mod


# --------------------------------------------------------------------------- #
# Snapshot
# --------------------------------------------------------------------------- #
def snapshot(dest: Path) -> None:
    """Write a consistent, compacted copy of the live DB to `dest` via VACUUM INTO."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()  # VACUUM INTO refuses to overwrite an existing file
    conn = sqlite3.connect(str(config.DB_PATH))
    try:
        # Bound parameter works on modern SQLite; fall back to a quoted literal if not.
        try:
            conn.execute("VACUUM INTO ?", (str(dest),))
        except sqlite3.OperationalError:
            conn.execute(f"VACUUM INTO '{str(dest)}'")
    finally:
        conn.close()


def _record(kind: str, target: str, ok: bool, message: str, size: int | None) -> None:
    try:
        conn = get_connection()
        conn.execute(
            "INSERT INTO backup_log(kind, target, ok, message, size_bytes) "
            "VALUES (?, ?, ?, ?, ?)",
            (kind, target, 1 if ok else 0, message, size),
        )
        conn.commit()
        conn.close()
    except Exception as e:  # never let logging failure mask the backup result
        print(f"(warning) could not record backup status: {e}", file=sys.stderr)


# --------------------------------------------------------------------------- #
# Local nightly
# --------------------------------------------------------------------------- #
def _prune_local() -> None:
    snaps = sorted(config.BACKUP_LOCAL_DIR.glob("recipes-*.db"))
    for old in snaps[: max(0, len(snaps) - config.BACKUP_KEEP)]:
        try:
            old.unlink()
        except OSError:
            pass


def run_local() -> Path:
    dest = config.BACKUP_LOCAL_DIR / f"recipes-{date.today():%Y%m%d}.db"
    try:
        snapshot(dest)
        _prune_local()
        _record("local", str(dest), True, "ok", dest.stat().st_size)
        print(f"Local backup written: {dest} ({dest.stat().st_size} bytes)")
        return dest
    except Exception as e:
        _record("local", str(config.BACKUP_LOCAL_DIR), False, str(e)[:300], None)
        raise


# --------------------------------------------------------------------------- #
# Weekly Drive
# --------------------------------------------------------------------------- #
def _drive_service():
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
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


def _upload_drive(service, snap: Path) -> str:
    from googleapiclient.http import MediaFileUpload

    q = (
        f"name = '{config.DRIVE_BACKUP_FILENAME}' and "
        f"'{config.DRIVE_BACKUP_FOLDER_ID}' in parents and trashed = false"
    )
    existing = service.files().list(q=q, fields="files(id)").execute().get("files", [])
    media = MediaFileUpload(str(snap), mimetype="application/x-sqlite3", resumable=False)
    if existing:
        fid = existing[0]["id"]
        service.files().update(fileId=fid, media_body=media).execute()  # keeps version history
        return fid
    meta = {"name": config.DRIVE_BACKUP_FILENAME, "parents": [config.DRIVE_BACKUP_FOLDER_ID]}
    return service.files().create(body=meta, media_body=media, fields="id").execute()["id"]


def run_drive() -> str | None:
    if not config.DRIVE_BACKUP_FOLDER_ID:
        msg = "Drive backup skipped: set DRIVE_BACKUP_FOLDER_ID in .env"
        _record("drive", "", False, msg, None)
        print(msg)
        return None
    service = _drive_service()
    if service is None:
        msg = "Drive backup skipped: Google not authorized (connect Drive in the app first)"
        _record("drive", "", False, msg, None)
        print(msg)
        return None

    tmp = config.BACKUP_LOCAL_DIR / ".drive-snapshot.tmp.db"
    try:
        snapshot(tmp)
        size = tmp.stat().st_size
        fid = _upload_drive(service, tmp)
        _record("drive", fid, True, "ok", size)
        print(f"Drive backup uploaded (fileId={fid}, {size} bytes)")
        return fid
    except Exception as e:
        _record("drive", "", False, str(e)[:300], None)
        raise
    finally:
        if tmp.exists():
            tmp.unlink()


# --------------------------------------------------------------------------- #
# Restore
# --------------------------------------------------------------------------- #
def restore(snapshot_path: str) -> None:
    """Copy a snapshot over the live DB. STOP the app first (see README)."""
    import shutil

    src = Path(snapshot_path)
    if not src.is_file():
        raise SystemExit(f"Snapshot not found: {src}")
    # Sanity-check it's actually a SQLite database.
    with open(src, "rb") as f:
        if f.read(16) != b"SQLite format 3\x00":
            raise SystemExit(f"Not a SQLite database file: {src}")
    dest = config.DB_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Remove WAL/SHM sidecars so the restored DB isn't shadowed by stale journals.
    for side in (dest.with_suffix(dest.suffix + "-wal"), dest.with_suffix(dest.suffix + "-shm")):
        if side.exists():
            side.unlink()
    shutil.copy2(src, dest)
    print(f"Restored {src} -> {dest}. Start the app again (systemctl start recipes).")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    cmd = args[0] if args else "both"
    if cmd == "local":
        run_local()
    elif cmd == "drive":
        run_drive()
    elif cmd == "both":
        run_local()
        run_drive()
    elif cmd == "restore":
        if len(args) < 2:
            raise SystemExit("Usage: python -m app.backup restore /path/to/snapshot.db --yes")
        if "--yes" not in args:
            raise SystemExit("Refusing to restore without --yes (this overwrites the live DB).")
        restore(args[1])
    else:
        raise SystemExit(f"Unknown command: {cmd} (use local|drive|both|restore)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
