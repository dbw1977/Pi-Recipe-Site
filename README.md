# Pi Recipe Site

A self-hosted, phone-first recipe app for two people on a home LAN, running on a
Raspberry Pi 4. This repo is being built in four chunks (A → D); see `BUILD-ORDER.md`
and `recipe-app-spec.md`. **`CLAUDE.md` holds the always-on guardrails.**

**Current status: Chunk A — the working manual app.** Type recipes in by hand, view them,
scale 1×/2×/3× with kitchen-friendly measurements, and search the library. No AI, no
imports, no network calls (those arrive in Chunk B).

---

## What's in Chunk A

- **Backend** — FastAPI + SQLite (WAL), full recipe-side schema (spec §4), idempotent
  startup migrations, seeded tag taxonomy (spec §8), recipe CRUD, and FTS5 search.
- **Frontend** — React + Vite + TypeScript + Tailwind, built to static files and served by
  FastAPI. Library grid, the "just the recipe" view, and a manual recipe editor.
- **Scaling engine** — a standalone, unit-tested TypeScript module
  (`frontend/src/lib/scaling.ts`) that snaps scaled amounts to kitchen-friendly fractions
  and expresses in-between values as sums of measurable parts (spec §7).

## Repo layout

```
backend/
  app/
    main.py            FastAPI app + static serving (binds 0.0.0.0)
    db.py              sqlite connection (WAL, foreign keys)
    migrations_runner.py + migrations/NNN_*.sql
    seed.py            controlled tag vocabulary (spec §8)
    crud.py            recipe aggregate + FTS sync
    routers/           recipes, tags
  tests/               pytest (CRUD + search)
frontend/
  src/lib/scaling.ts   scaling engine  (+ scaling.test.ts — Vitest)
  src/pages/           Library, RecipeView, RecipeEdit
recipe-app-spec.md · CLAUDE.md · chunk-*-prompt.md · BUILD-ORDER.md
.env.example
```

---

## Run it (development)

Two terminals. The backend serves the API; Vite serves the frontend with hot reload and
proxies `/api` to the backend.

**Backend**
```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Frontend**
```bash
cd frontend
npm install
npm run dev        # http://localhost:5173  (proxies /api → :8000)
```

## Run it (production / on the Pi)

Build the frontend once; FastAPI then serves everything on a single port.

```bash
cd frontend && npm install && npm run build     # produces frontend/dist/
cd ../backend && . .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000  # serves API + the built app
```

Copy `.env.example` to `.env` and set at least `RECIPE_DB_PATH` to a **local-disk** path
(never a NAS mount — see the golden rule below).

## Tests

```bash
# Backend — CRUD, search, FTS sync
cd backend && . .venv/bin/activate && pytest -q

# Frontend — the scaling engine (the piece everything trusts)
cd frontend && npm test
```

The scaling suite covers the spec §7 worked examples, including the tricky sum-of-parts
cases: honey `1½ tbsp ×3 → "¼ cup + 1½ tsp"` and dijon `2 tbsp ×3 → "¼ cup + 2 tbsp"`, plus
clean cases (`¼ cup ×3 → ¾ cup`) and egg/count rounding.

## Seed / test fixture

The steak-salad fixture (spec §13) lives at `backend/tests/fixtures.py`. To load it into a
running instance:

```bash
cd backend && . .venv/bin/activate
python3 - <<'PY'
import json, urllib.request, sys
sys.path.insert(0, "tests")
from fixtures import steak_salad_payload
req = urllib.request.Request(
    "http://localhost:8000/api/recipes",
    data=json.dumps(steak_salad_payload()).encode(),
    headers={"Content-Type": "application/json"},
)
print("created recipe id:", json.load(urllib.request.urlopen(req))["id"])
PY
```

Open the recipe and toggle 2×/3× — the honey-dijon dressing scales to the spec §7 values.

---

## `recipes.local` via mDNS/Avahi (host setup)

So nobody types an IP address, publish the Pi as `recipes.local` on the LAN. This is host
configuration (done once on the Pi), not part of the app:

```bash
sudo apt install avahi-daemon        # usually preinstalled on Raspberry Pi OS
sudo hostnamectl set-hostname recipes
sudo systemctl restart avahi-daemon
```

The Pi is then reachable at `http://recipes.local:8000` from any phone/laptop on the same
network. (To drop the `:8000`, put nginx or a systemd-run reverse proxy on port 80 — optional.)

Apple devices resolve `.local` out of the box; most Android/desktop browsers do too. If a
device can't, use the Pi's LAN IP as a fallback.

---

## Golden rules (from `CLAUDE.md`)

1. **The SQLite `.db` lives on LOCAL DISK ONLY** — never on a NAS/NFS/SMB mount (network
   filesystems corrupt SQLite). Media may live on the NAS; the database may not.
2. **WAL mode is on** — two people may write concurrently.
3. **Structured ingredients only** and **kitchen-friendly quantities only** in scaled output.
4. **LAN-only, plain HTTP**, no auth in v1.

## Not in this chunk (by design)

Imports (URL / screenshot / voice / Drive) and any Claude/Anthropic call → **Chunk B**.
Recipe of the Week, thumbnails, backups → **Chunk C**. Places / eating-out → **Chunk D**.
No external network calls happen anywhere in Chunk A.
