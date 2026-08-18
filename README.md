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

## Chunk B — imports (URL · screenshot · voice · Drive)

Recipes now flow in from four sources, each landing as a **draft** in the Drafts queue for
review before it joins the library (nothing auto-publishes). Every path is **optional and
fails gracefully**: a missing credential disables only that path, with a clear message.

Enable them by adding keys to `.env` (see `.env.example`). Easiest first:

| Path | Needs | Notes |
|---|---|---|
| **URL** | *nothing* for supported sites | Uses `recipe-scrapers` offline. Unsupported sites (and Reddit posts) use the Claude fallback (needs the Anthropic key). |
| **Screenshot** | `ANTHROPIC_API_KEY` | Claude vision reads the image(s). Select **multiple** screenshots of one recipe (caption + steps on separate screens) and they're combined into a single recipe. |
| **Video** | `ANTHROPIC_API_KEY` + `ffmpeg` | Same importer as screenshots: ffmpeg samples frames from a downloaded clip, Claude reads them. `sudo apt install ffmpeg`. |
| **Voice** | `WHISPER_BIN` + `WHISPER_MODEL` + `ANTHROPIC_API_KEY` | whisper.cpp transcribes locally, Claude structures. |
| **Google Drive** | `GOOGLE_CLIENT_SECRETS` + `DRIVE_FOLDER_ID` | One-time OAuth, then a manual "Scan" button. |

The screenshot/video importer also takes an optional **cover photo** — add a picture of the
finished dish and it becomes the recipe's hero image (otherwise the screenshot, or a frame
from the video, is used). **Tags** are auto-selected on every import and confirmed in the
review screen; manage the tag vocabulary (add/delete) under **Settings → Tags**.

**Set up the Anthropic key** (unlocks screenshot + fallbacks):
1. Create a key at console.anthropic.com and add a little credit (imports cost fractions of a cent).
2. Put `ANTHROPIC_API_KEY=sk-ant-...` in `.env`, then `sudo systemctl restart recipes`.

**Set up whisper.cpp** (voice), on the Pi:
```bash
git clone https://github.com/ggerganov/whisper.cpp && cd whisper.cpp
cmake -B build && cmake --build build -j --config Release
bash ./models/download-ggml-model.sh base.en
```
Then set `WHISPER_BIN=.../build/bin/whisper-cli` and `WHISPER_MODEL=.../models/ggml-base.en.bin`.
(ffmpeg is used to convert audio to 16 kHz if it's installed: `sudo apt install ffmpeg`.)

**Set up Google Drive** (bulk loader): create OAuth **Desktop app** credentials in Google
Cloud, download `client_secret.json`, set `GOOGLE_CLIENT_SECRETS` + `DRIVE_FOLDER_ID`, then
click **Connect Google Drive** in the app (Import page) once to authorize. The OAuth redirect
URI to register is `http://<host>/api/imports/drive/callback`. The scan reads **only** that
folder and skips files it already imported.

**Testing Chunk B:** URL — paste the Plays Well With Butter marinade; Screenshot — the
steak-salad Instagram image (spec §13); the Drafts queue supports per-row Approve / Edit /
Discard and **Approve-all**; likely duplicates are flagged in the queue.

## Chunk C — polish + backups

Makes the app pleasant to live with and the data genuinely safe.

- **Recipe of the Week** — a deterministic weekly hero pinned at the top of the library,
  keyed to the ISO week (stable all week, identical for both users, computed on load — no
  cron). Recent picks are skipped until the library cycles. Any recipe can be **pinned**
  ("Feature as Recipe of the Week") to override the automatic pick for the current week.
- **Thumbnails** — the grid serves small WebP thumbnails generated on first view and cached
  on **local disk** (`THUMBS_DIR`); originals stay wherever `MEDIA_ROOT` points (e.g. the NAS).
- **NAS media mount** — set `MEDIA_ROOT` to a mounted NAS path; the DB stores only relative
  paths, so originals resolve through the mount. The **database always stays on local disk**.
- **Backups** — consistent `VACUUM INTO` snapshots (never a live-file copy): a nightly local
  snapshot (keep last `BACKUP_KEEP`) and a weekly Google Drive copy that overwrites one file
  in a dedicated folder (Drive keeps version history for rollback). Health shows in **Settings**.

### Mount the NAS for media (optional, OMV example)

```bash
sudo mkdir -p /srv/nas/recipes
# NFS export from the NAS, for example:
echo 'nas.local:/export/recipes  /srv/nas/recipes  nfs  defaults,_netmount,x-systemd.automount  0  0' | sudo tee -a /etc/fstab
sudo mount -a
```
Then set `MEDIA_ROOT=/srv/nas/recipes/media` (and optionally `BACKUP_LOCAL_DIR=/srv/nas/recipes/backups`) in `.env` and restart. **Never** point `RECIPE_DB_PATH` at the NAS.

### Run backups on a schedule (systemd timers)

The backup engine is a standalone script (`python -m app.backup`) so it runs even while the
app restarts. Create a service + two timers (nightly local, weekly Drive):

```bash
sudo tee /etc/systemd/system/recipes-backup@.service >/dev/null <<EOF
[Unit]
Description=Pi Recipe Site backup (%i)
[Service]
Type=oneshot
User=$USER
WorkingDirectory=$HOME/pi-recipe-site/backend
ExecStart=$HOME/pi-recipe-site/backend/.venv/bin/python -m app.backup %i
EOF

sudo tee /etc/systemd/system/recipes-backup-local.timer >/dev/null <<'EOF'
[Unit]
Description=Nightly local recipe backup
[Timer]
OnCalendar=*-*-* 02:30:00
Persistent=true
Unit=recipes-backup@local.service
[Install]
WantedBy=timers.target
EOF

sudo tee /etc/systemd/system/recipes-backup-drive.timer >/dev/null <<'EOF'
[Unit]
Description=Weekly Drive recipe backup
[Timer]
OnCalendar=Sun *-*-* 03:00:00
Persistent=true
Unit=recipes-backup@drive.service
[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now recipes-backup-local.timer recipes-backup-drive.timer
systemctl list-timers 'recipes-backup*'   # confirm next run times
```
(You can also tap **Back up now** in the app's Settings page to run one on demand.)

### Restore

1. Stop the app: `sudo systemctl stop recipes`
2. Pick a snapshot — a local one from `BACKUP_LOCAL_DIR` (e.g. `recipes-YYYYMMDD.db`), or
   download `recipes-backup.db` from the Drive backup folder (or an older Drive *version*).
3. Restore it over the live DB:
   ```bash
   cd ~/pi-recipe-site/backend && . .venv/bin/activate
   python -m app.backup restore /path/to/recipes-YYYYMMDD.db --yes
   ```
4. Start the app: `sudo systemctl start recipes`

Media paths still resolve because the NAS layout is unchanged. **Test a restore once on
purpose** — a backup you've never restored is a hope, not a backup.

## Chunk D — Eat Out / Places (spec §14)

A second collection: **where to eat** and **what to order there**. A top-level **Cook ⇄ Eat
Out** toggle switches the whole UI between recipes and places; places reuse the same grid,
search, tag filters, review/Drafts flow, media, and backups — it's additive, not a second app.

- **A place is where to go + what to order.** Each place carries name, type, **city** (defaults
  to `HOME_CITY`), address, a pasted **Google Maps link** with an **Open in Maps / Directions**
  button, price ($–$$$$), our rating, notes, who recommended it, a **visited / want-to-try**
  flag, and the prominent **recommended dishes** list (with a must-order star) — the eat-out
  parallel to a recipe's ingredients.
- **Tags:** new **City/Area**, **Place Type**, **Price** dimensions; **Cuisine is shared** with
  recipes. City / type / price are set as fields and mirrored into tags automatically, so the
  Eat Out grid filters by city and cuisine through the same tag mechanism recipes use. Manage
  the whole vocabulary under **Settings → Tags**.
- **Import:** add a place by hand, or from a **screenshot** of a friend's rec / an IG post
  (Claude vision pulls out name, city, and the dishes mentioned). Lands as a draft to review.
- **Share (LAN-friendly):** **Eat Out → Export a list** filters by city and produces a clean,
  screenshot-friendly / one-page-PDF **"Our [city] picks"** to text or email. (The site stays on
  your home network, so this is export, not a public link.)

Set your home city in `.env` so new places default to it:
```
HOME_CITY=Gainesville
```
The Chunk D migration is additive and non-destructive — existing recipes are untouched.

## Chunk E — Meal planner & grocery list

Plan a week of cooking and turn it into one consolidated shopping list. Reuses the **Chunk A
scaling engine** to sum ingredients and the **Chunk D print/export** for the list — the core
is fully deterministic and works with **no API key**.

- **Planner board** (📅 in the header): start-date picker **defaulting to the upcoming
  Saturday**, a 7-day board, and a per-day picker that **reuses recipe search** (or attach a
  **Place** for an eat-out day, which contributes nothing to groceries). Each recipe entry has
  a **scale** factor. There's also an **"Add to meal plan"** button on every recipe.
- **Grocery generation (deterministic):** collects every assigned recipe's ingredients × its
  scale, **normalizes names** ("garlic cloves" + "minced garlic" → `garlic`), **merges & sums**
  compatible units in base units then snaps to kitchen-friendly amounts (so garlic across
  recipes → **"6 cloves"**, and ¼ cup + 2 tbsp oil → **"¼ cup + 2 tbsp"**). Incompatible units
  for one name stay as separate lines; "to taste"/assembly items are listed once without a
  quantity; everything is **grouped by aisle**.
- **Grocery view:** check items off, **add manual items**, see a "for <recipes>" hint, and
  **copy-as-text** or **Save-as-PDF**. **Regenerating preserves** your checkmarks and manual
  items (matched on name+unit) and only refreshes recipe-derived quantities.
- **Optional AI:** with `ANTHROPIC_API_KEY` set, items the built-in lookup left in *Other* get
  tidied into aisles. Without a key this is silently skipped — generation always works.

The aggregation logic lives in `frontend/src/lib/grocery.ts` with Vitest tests
(`grocery.test.ts`, incl. the summed-garlic case); the plan/list state is persisted by the
backend (`/api/meal-plans`). The Chunk E migration adds tables only — nothing existing changes.

## Chunk F — AI variations · UI clean-up · photo upload

Three things in one update (spec §18, §9). The AI part needs `ANTHROPIC_API_KEY`; the UI
polish and photo upload apply regardless.

- **AI recipe variations.** On any saved recipe, **⋮ → Create AI variation**, type an
  instruction ("make me a patty melt version") or tap a preset (vegetarian, spicier, air
  fryer, for a crowd…). It calls **`claude-sonnet-5`** (a reasoning task, unlike Haiku
  extraction — ~cents per variation), returns a **structured draft** saved to the Drafts
  queue immediately (never lost, never auto-published), and opens it for review. Generated
  recipes are marked **AI variation of [source] · untested** and are **never credited to the
  original human creator**. Iterate by varying a generated draft again. Lineage is stored in
  new `recipe` columns (`generated`, `derived_from_recipe_id`, `generation_prompt`;
  `source_type='ai'`) via a non-destructive migration.
- **UI clean-up.** A persistent header with a **home link** (the 🍲 wordmark returns to the
  library from anywhere) plus the Cook ⇄ Eat Out toggle. Recipe-view actions collapse into a
  single **"⋮" overflow menu** (Edit, Add to meal plan, Create AI variation, Add photo, Save
  as PDF, Feature, Delete) — only the **1x/2x/3x scale toggle stays inline**. The same
  overflow pattern is applied to the place view.
- **Device photo upload.** On the recipe editor and the recipe-view ⋮ menu, **Add / take
  photo** (`accept="image/*"` + `capture="environment"`, so phones offer camera or library —
  works over plain LAN HTTP). The image is stored locally (originals on the NAS), **EXIF
  orientation fixed**, **downscaled**, and thumbnailed (Chunk C pipeline), then set as the
  hero. No schema change (reuses `media` + `hero_image`).

Without a key, the AI action is cleanly disabled and everything else still works. This
completes the six-chunk build (A–F).

## Not in these chunks (by design)

- Google Places API autocomplete (v1 uses a pasted Maps link) and public link sharing
  (needs exposing the site — deliberately deferred, spec §12).
- Pantry inventory + receipt-photo restocking (candidate **Chunk G**), and auto-suggesting
  *which* recipes to cook — the planner is manual selection.
