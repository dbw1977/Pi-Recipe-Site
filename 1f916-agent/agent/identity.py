"""Persisted forum identity: handle + secret key.

The secret is issued once at registration and is the only thing that proves who
we are. It is written to a 0600 file in the state directory and is NEVER
committed (the state dir is gitignored). We keep it out of the ledger DB too.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class Identity:
    handle: str
    secret: str
    declared_model: str | None = None
    registered_at: str | None = None
    extra: dict | None = None


def load_identity(path: str | Path) -> Identity | None:
    p = Path(path)
    if not p.is_file():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    return Identity(
        handle=data["handle"],
        secret=data["secret"],
        declared_model=data.get("declared_model"),
        registered_at=data.get("registered_at"),
        extra={k: v for k, v in data.items()
               if k not in {"handle", "secret", "declared_model", "registered_at"}} or None,
    )


def save_identity(path: str | Path, identity: Identity) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "handle": identity.handle,
        "secret": identity.secret,
        "declared_model": identity.declared_model,
        "registered_at": identity.registered_at or datetime.now(timezone.utc).isoformat(),
    }
    if identity.extra:
        payload.update(identity.extra)
    # Write then tighten permissions to owner read/write only.
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    try:
        os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)  # 0600
    except OSError:
        pass
