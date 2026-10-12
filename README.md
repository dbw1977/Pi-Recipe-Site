# Pi Recipe Site

A self-hosted, phone-first **food app** for two people on a home LAN, running on a
Raspberry Pi 4. Built in six chunks (A → F); see `BUILD-ORDER.md` and `recipe-app-spec.md`.
**`CLAUDE.md` holds the always-on guardrails.**

**Status: complete (Chunks A–F).** A recipe library with kitchen-friendly 1×/2×/3× scaling
and FTS search; four import methods (URL/Reddit, screenshot/video, voice, Google Drive) with
a review/Drafts queue and auto-tagging; Recipe of the Week, thumbnails, and backup/restore;
an **Eat Out / Places** collection with a printable city export; a **weekly meal planner** with
a consolidated grocery list; and an **AI recipe-variation** builder — plus device photo upload.

> **Want to build your own?** See **[`BUILD-IT-YOURSELF.md`](BUILD-IT-YOURSELF.md)** — a
> ready-to-paste prompt (and the file set) to hand this whole app to your own coding AI.

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

### Updating the Pi

```bash
~/pi-recipe-site/scripts/update.sh          # pull · deps · frontend build · restart
~/pi-recipe-site/scripts/update.sh --apt    # same, after `apt update && apt upgrade` first
```

`apt upgrade` alone only updates system packages (ffmpeg, avahi, …) — it never pulls this
repo, rebuilds the frontend, or restarts the service. The script does all of it and checks
`/api/health` at the end. New DB migrations apply automatically on restart.

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
| **Video** | `ANTHROPIC_API_KEY` + `ffmpeg` (+ optional whisper.cpp) | ffmpeg samples frames from a downloaded clip and Claude **watches** them; if whisper.cpp is configured it also **transcribes the narration** and Claude reads that too — so it captures spoken amounts/steps, not just on-screen text. Frames-only without whisper. `sudo apt install ffmpeg`. |
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

**Set up Google** (Drive import **and** Drive backup — one connection covers both):
create an OAuth **Desktop app** client in Google Cloud (Google rejects `http://recipes.local`
redirects, so the app uses a copy-paste code flow with a `localhost` redirect), download its
`client_secret.json`, set `GOOGLE_CLIENT_SECRETS` (+ `DRIVE_FOLDER_ID` for import; the backup
folder is chosen in the app), restart, then **Settings → Google account → Connect
Google** in the app: approve in the popup, and paste back the code (or the whole `localhost`
URL) from your browser's address bar. The import scan reads **only** the recipes folder and
skips files it already imported.

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
- **Backups** — set up in the app (**Settings → Backups**): one file, `recipes-backup.zip`
  (database + photos), replaced each run. See [Backups](#backups-set-up-in-the-app) below.

### Mount the NAS for media (optional, OMV example)

```bash
sudo mkdir -p /srv/nas/recipes
# NFS export from the NAS, for example:
echo 'nas.local:/export/recipes  /srv/nas/recipes  nfs  defaults,_netmount,x-systemd.automount  0  0' | sudo tee -a /etc/fstab
sudo mount -a
```
Then set `MEDIA_ROOT=/srv/nas/recipes/media` (and optionally `BACKUP_LOCAL_DIR=/srv/nas/recipes/backups`) in `.env` and restart. **Never** point `RECIPE_DB_PATH` at the NAS.

### Backups (set up in the app)

Everything is chosen on **Settings → Backups** — no `.env` or systemd editing:

- **Where to save** — a folder (on this Pi, a NAS, or a USB drive), **and/or** Google Drive. The
  folder path is test-written when you save, so a typo or an unmounted NAS is caught right
  then. A folder on the Pi's own SD card is flagged: it would die with the Pi, so use a NAS/USB
  path or add Google Drive. For Drive, give a folder name; the app creates it in your Drive
  (Drive keeps version history of the file).
- **One file, replaced each time** — `recipes-backup.zip` holds the database, the photos
  (optional, on by default — needed to rebuild a new Pi), and a manifest. It's built under a
  temporary name, checked, and only then swapped in, so a failed run never destroys the last
  good backup. It needs free space of about the archive size; if there isn't enough, it fails
  with a message instead of filling the disk.
- **Weekly, automatically** — switch it on and pick a day and time. The app runs it itself
  (checks every ~10 minutes). If the Pi was off at that time, it backs up when it's next
  running. A failed destination retries hourly.
- **Back up now** — runs whatever is switched on, in the background, with live progress.
- Settings are stored in the database, so a restored library comes back already configured.

> **Upgrading from the old setup?** The nightly/weekly systemd timers from earlier versions
> (`recipes-backup-*.timer`) are no longer needed — turn them off so they don't double up:
> `sudo systemctl disable --now recipes-backup-local.timer recipes-backup-drive.timer`.
> Old dated `recipes-YYYYMMDD.db` files and a `recipes-backup.db` on Drive are left alone;
> delete them whenever you like. The old `DRIVE_BACKUP_FOLDER_ID` setting is only a fallback
> until you name a Drive folder in the app (Google's `drive.file` permission can't write into a
> folder you made by hand, so the app makes its own).

### Restore (after a hardware failure)

Photos live outside the database, which is why the backup includes them. On the replacement Pi:
install the app (this README), then:

```bash
sudo systemctl stop recipes
cd ~/pi-recipe-site/backend && . .venv/bin/activate

# from a folder / NAS / USB:
python -m app.backup restore /path/to/recipes-backup.zip --yes
# or straight from Google Drive (connect Google in Settings first, using the same Google Cloud client):
python -m app.backup restore-drive --yes

sudo systemctl start recipes
```

- Add `--no-media` to restore only the database.
- Your current database is kept next to the live one as `recipes.db.before-restore-<time>`, so a
  mistaken restore can be undone.
- It refuses a backup made by a **newer** version of the app (update first with
  `scripts/update.sh`); older backups are fine — new migrations apply on start.
- Not in the backup (they're secrets): `.env` and your Google connection. Reconnect Google in
  Settings and re-enter the keys.
- **Test a restore once, on purpose** — a backup you've never restored is a hope, not a backup.

The same engine is available from the command line: `python -m app.backup local|drive|both`
(uses the destinations saved in Settings).

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

### Library: paging, sorting, star ratings

- **Paging** — the Cook and Eat Out libraries show **20 / 50 / 100** recipes per page (picker under the grid,
  remembered per device, separately for each collection). The API takes `limit` + `offset` and returns the total in an
  `X-Total-Count` header on both `/api/recipes` and `/api/places`; the body stays a plain list,
  so other callers (planner picker, export, drafts) are unaffected.
- **Sorting** — newest/oldest **added** (editing never makes a recipe "new"), A→Z / Z→A, highest /
  lowest rated (unrated always last), plus **Best match** while searching. `?sort=` on the API.
  For places, "name" is the place name and "rating" is `our_rating`.
- **Recipe ratings** — our own 1–5 stars, tapped on the recipe page (tap the same star again to clear)
  and shown on library cards. Stored in `recipe.rating` (migration 008, nullable — existing
  recipes simply start unrated) via `PUT /api/recipes/{id}/rating`, separate from the edit form
  so saving an edit can't wipe it.

## Not in these chunks (by design)

- Google Places API autocomplete (v1 uses a pasted Maps link) and public link sharing
  (needs exposing the site — deliberately deferred, spec §12).
- Pantry inventory + receipt-photo restocking (candidate **Chunk G**), and auto-suggesting
  *which* recipes to cook — the planner is manual selection.
