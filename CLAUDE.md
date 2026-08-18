# CLAUDE.md — Local Food App (recipes + places)

Project conventions and guardrails. This file applies to **every session and every chunk**. Read `recipe-app-spec.md` for the full design; this file is the always-on rulebook. If anything here conflicts with a request, follow this file and flag the conflict.

## What this is
A self-hosted, phone-first food app for **two users on a home LAN**, running on a **Raspberry Pi 4 (4 GB)**. Two collections: **Recipes** (cook) and **Places** (eat out), plus a **weekly meal planner** and an **AI recipe-variation builder**. Built in **chunks (A→F)** — see spec §16 and the `chunk-*-prompt.md` files. You are always building exactly one chunk; do not build ahead.

## Golden rules (do not violate)
1. **SQLite lives on LOCAL DISK ONLY.** Never place the `.db` file on the NAS/NFS/SMB mount — network filesystems corrupt SQLite. Media may live on the NAS; the database may not.
2. **Enable WAL mode** (`PRAGMA journal_mode=WAL;`) — two users may write concurrently.
3. **Everything local & offline-capable.** No third-party cloud for recipe data. On import, **download remote images into the local media store** — never hot-link (source pages rot). **Device photo uploads** are stored the same way (originals on the NAS); fix EXIF orientation and downscale/thumbnail on upload.
4. **Config via environment / `.env`,** never hardcoded. Secrets (Anthropic key, Google creds) are never committed. Ship a `.env.example`.
5. **Structured ingredients only** — `{quantity, unit, name, note, scalable}`. Never store ingredients as free text.
6. **Kitchen-friendly quantities only** in scaled output — the allowed-fraction ladder in spec §7. No `0.7 tsp`, no `⅜ cup`. Count items (eggs) round to whole.
7. **Controlled tag vocabulary** — auto-tagging picks only from existing tags (spec §8). Never invent tags per import.
8. **Do not stub or fake.** If blocked on a credential or device, make it configurable, mark a clear `TODO`, disable that feature gracefully, and keep going on everything else. Never fabricate data or pretend an external call succeeded.
9. **LAN-only, plain HTTP.** Bind `0.0.0.0`; serve at `recipes.local` via mDNS/Avahi. No auth in v1. No HTTPS (wake-lock is deferred, spec §12).
10. **Never auto-publish an import.** Everything imported lands as a `draft` and requires an explicit human approval (spec §6).
11. **Clean, tight, content-first UI.** A **persistent header with a home/library link** on every page; **one primary action per screen, secondary actions in a "⋮" overflow menu**; one consistent spacing/typography/button system; chrome recedes so content leads (spec §9). Keep screens uncrowded as features are added.

## Stack (keep it lean for a Pi 4)
- **Backend:** Python 3.11+, FastAPI + uvicorn. SQLite via SQLModel (or plain `sqlite3` if simpler for a piece).
- **Migrations:** numbered SQL files applied idempotently at startup. Schema evolves across chunks (place tables arrive in Chunk D) — migrations must be **non-destructive** to existing data.
- **Frontend:** React + Vite + TypeScript + Tailwind. Build to static; FastAPI serves it. Minimal dependencies.
- **Scaling engine:** a standalone **TypeScript** module (runs client-side) with **Vitest** unit tests.
- **Search:** SQLite **FTS5**.
- **Tests:** `pytest` (backend), `vitest` (frontend + scaling).

## Suggested repo layout
```
backend/   app, models, migrations/ (NNN_*.sql), routers, tests/
frontend/  React app (src/, src/lib/scaling.ts + scaling.test.ts)
recipe-app-spec.md
CLAUDE.md
.env.example
README.md
```

## Working style
- Small, verifiable increments. **End each chunk** with: what was built, how to run backend + frontend, how to run the tests, and any host setup the user must do.
- Comment the non-obvious (scaling snap logic, FTS sync triggers, backup snapshot).
- Ask before adding a heavyweight dependency or changing the stack above.
