# Local Recipe Website — Build Spec

A self-hosted recipe library for two people (you + your wife), running on a Raspberry Pi on your home LAN. Import recipes from URLs, Instagram screenshots, a Google Drive folder, or voice notes. Auto-categorize with tags, strip the life-story filler, show clean instructions, and scale 1x/2x/3x with kitchen-friendly measurements.

This document is the scope hand-off for Claude Code. Build it in three chunks (see §16).

---

## 1. Goals & Non-Goals

**Goals**
- Nice, phone-first front end for two users on the home network.
- Import recipes via: (a) URL, (b) Instagram screenshot, (c) Google Drive folder, (d) voice note (± photos).
- Auto-tag each recipe into a multi-dimensional taxonomy; show source/author.
- Clean "just the recipe" view — ingredients, steps, no blog narrative.
- 1x / 2x / 3x scaling with **only kitchen-measurable quantities**.
- **All data stored locally.** No third-party recipe cloud.

**Non-goals (v1)**
- Screen wake-lock (needs HTTPS — deferred, see §12).
- User accounts / login (home network only for v1 — see §12).
- Public internet exposure.

---

## 2. Architecture & Where Things Run

Two Pis are available:
- **Recipe Pi** (Pi 4, 4 GB) — runs the app: FastAPI backend, SQLite DB, static frontend.
- **Tedlasso** (Pi 4 + OMV NAS) — bulk media storage over a network mount.

```
 Phone / laptop ── http://recipes.local ──► Recipe Pi
                                              ├─ FastAPI (uvicorn)
                                              ├─ SQLite  (LOCAL DISK ONLY)
                                              ├─ /media  → mounted from Tedlasso NAS
                                              └─ Whisper (local transcription)
                                                     │
                                              Anthropic API (extraction + tagging only)
```

### ⚠️ Critical data-locality rule
- **The SQLite database file lives on the Recipe Pi's local disk (e.g. `/home/pi/recipes/data/recipes.db`).**
- **Do NOT place the `.db` file on the OMV/NAS share (NFS/SMB).** SQLite relies on POSIX locking that network filesystems implement incorrectly; this causes silent corruption. This is non-negotiable.
- **Bulk media MAY live on the NAS.** Mount the NAS share at `/media` (or similar) and store original screenshots, voice recordings, videos, and large images there. Store only the *relative path* in the DB.
- Suggested split:
  - Local disk: `recipes.db`, thumbnails/derived small images (fast, safe).
  - NAS mount: originals (screenshots, audio, video, full-res photos).
- **Backups:** the whole library is one DB file + the media folder — see **§11 (Backup & Restore)** for the full strategy (consistent snapshots, nightly local + weekly off-site to Google Drive).

---

## 3. Tech Stack

| Layer | Choice | Why |
|---|---|---|
| DB | **SQLite** | Single-file, zero-admin, trivial backup, plenty for two users. |
| Backend | **Python + FastAPI** (uvicorn) | Access to `recipe-scrapers`; clean async API. |
| URL extraction | **`recipe-scrapers`** library | Pulls structured recipe data from hundreds of sites; drops the blog story automatically. |
| AI extraction/tagging | **Anthropic API** (Claude) | Vision for screenshots, structuring for messy text/voice, auto-tagging. See §10. |
| Voice transcription | **whisper.cpp** (local) | Keeps audio on-device. Runs on Pi (slow) or Tedlasso (offload option). |
| Frontend | **React** (Vite build → static files served by FastAPI) | Snappy phone UX; scaling math runs client-side. Keep the bundle light for the Pi 4. |
| Hostname | **mDNS / Avahi** → `recipes.local` | So nobody types an IP address. |

Keep the frontend lean (the Pi 4 serves it and the users are on phones). Avoid heavy UI frameworks; Tailwind or plain CSS is fine.

---

## 4. Data Model (SQLite Schema)

Ingredients are stored **structured**, not as free text — this is what makes clean scaling possible (§7).

```sql
-- A recipe
CREATE TABLE recipe (
  id            INTEGER PRIMARY KEY,
  title         TEXT NOT NULL,
  description   TEXT,                 -- short, optional; NOT the blog story
  source_type   TEXT,                 -- 'url' | 'instagram' | 'drive' | 'voice' | 'manual'
  source_name   TEXT,                 -- e.g. 'chacekitchen', 'playswellwithbutter.com'
  source_url    TEXT,                 -- original link if any
  source_handle TEXT,                 -- e.g. '@chacekitchen'
  hero_image    TEXT,                 -- relative media path
  servings_base INTEGER,              -- base yield the quantities correspond to
  servings_unit TEXT,                 -- 'servings' | 'salads' | 'cups' etc.
  total_time    INTEGER,              -- minutes, optional
  created_at    TEXT,
  updated_at    TEXT,
  status        TEXT DEFAULT 'published'  -- 'draft' (in review) | 'published'
);

-- Ingredient groups (e.g. "For the salad", "Honey dijon dressing")
CREATE TABLE ingredient_group (
  id         INTEGER PRIMARY KEY,
  recipe_id  INTEGER REFERENCES recipe(id) ON DELETE CASCADE,
  name       TEXT,                    -- nullable = default/ungrouped
  sort_order INTEGER
);

-- Structured ingredients
CREATE TABLE ingredient (
  id          INTEGER PRIMARY KEY,
  group_id    INTEGER REFERENCES ingredient_group(id) ON DELETE CASCADE,
  quantity    REAL,                   -- nullable (e.g. "to taste")
  unit        TEXT,                   -- canonical unit: 'tsp','tbsp','cup','g','oz','clove','slice','whole', ...
  name        TEXT NOT NULL,          -- 'olive oil'
  note        TEXT,                   -- 'minced', 'to taste', 'I used habanero cheddar'
  scalable    INTEGER DEFAULT 1,      -- 0 = never scale (e.g. "salt to taste")
  sort_order  INTEGER
);

-- Steps
CREATE TABLE step (
  id         INTEGER PRIMARY KEY,
  recipe_id  INTEGER REFERENCES recipe(id) ON DELETE CASCADE,
  text       TEXT NOT NULL,
  sort_order INTEGER
);

-- Tag taxonomy: a tag belongs to a dimension (category)
CREATE TABLE tag_category (   -- 'Course','Cuisine','Protein','Dietary','Method','Time','Occasion'
  id   INTEGER PRIMARY KEY,
  name TEXT UNIQUE
);
CREATE TABLE tag (
  id          INTEGER PRIMARY KEY,
  category_id INTEGER REFERENCES tag_category(id),
  name        TEXT,
  UNIQUE(category_id, name)
);
CREATE TABLE recipe_tag (
  recipe_id INTEGER REFERENCES recipe(id) ON DELETE CASCADE,
  tag_id    INTEGER REFERENCES tag(id),
  PRIMARY KEY (recipe_id, tag_id)
);

-- Media attached to a recipe (originals live on NAS; store relative path)
CREATE TABLE media (
  id         INTEGER PRIMARY KEY,
  recipe_id  INTEGER REFERENCES recipe(id) ON DELETE CASCADE,
  kind       TEXT,   -- 'image' | 'audio' | 'video'
  path       TEXT,   -- relative to media root
  caption    TEXT
);

-- Required cooking utensils / equipment (grill, whisk, mixing bowl, sheet pan, ...)
CREATE TABLE equipment (
  id         INTEGER PRIMARY KEY,
  recipe_id  INTEGER REFERENCES recipe(id) ON DELETE CASCADE,
  name       TEXT NOT NULL,
  inferred   INTEGER DEFAULT 0,   -- 1 = AI-inferred from the steps, not explicitly stated in the source
  sort_order INTEGER
);

-- Full-text search index (SQLite FTS5). One row per recipe, rebuilt/kept in sync
-- from title + description + source + ingredient names + tags. See "Search" in §9.
CREATE VIRTUAL TABLE recipe_fts USING fts5(
  title, description, source, ingredients, tags,
  content=''                 -- external-content/contentless; populated by the app on save
);
-- On recipe save/update, the app rebuilds that recipe's FTS row by concatenating its
-- ingredient names, tag names, and source into the matching columns.

-- Recipe of the Week (§9): history of auto/manual picks so recent ones aren't repeated,
-- and so a manual pin can override the deterministic weekly choice.
CREATE TABLE featured_history (
  id         INTEGER PRIMARY KEY,
  recipe_id  INTEGER REFERENCES recipe(id) ON DELETE CASCADE,
  iso_week   TEXT,                -- e.g. '2026-W33'
  pinned     INTEGER DEFAULT 0    -- 1 = manually pinned by a user, 0 = auto-selected
);
```

**Controlled tag vocabulary:** the `tag` table is seeded from the taxonomy in §8. The AI tagger must pick only from existing tags (pass the allowed list in the prompt) to prevent 40 near-duplicate tags. New tags can be added manually in the UI, not invented per-import.

---

## 5. Ingestion Pipelines

All four paths converge on the **same normalized draft** → the review screen (§6) → save. None writes directly to the published library.

### 5a. URL
1. `recipe-scrapers` attempts structured extraction (handles most recipe sites, incl. Plays Well With Butter). Returns ingredients, steps, yield, author, image.
2. If the site is unsupported or returns junk → fall back to fetching the page HTML and sending the readable text to Claude (§10) to structure it.
3. Parse ingredient strings into `{quantity, unit, name, note}`. (`recipe-scrapers` returns strings; run them through a Claude structuring pass or a parser like `ingredient-parser` to get structured rows.)
4. Auto-tag (§10). → draft.

### 5b. Instagram screenshot (+ optional video/photos)
1. User uploads the **screenshot** image (this is what extraction reads and is always available).
2. User may **also** attach the original **video** and/or extra photos when they have them — Instagram doesn't always allow downloading the video, so these are strictly optional. Do **not** attempt to scrape/download from Instagram programmatically (unreliable and against their terms); the user supplies any video file manually.
3. Send the screenshot to Claude vision (§10). Prompt returns: title, source handle (read from the post header, e.g. `chacekitchen`), ingredient groups, structured ingredients, steps (if present), and suggested tags.
4. Store the screenshot, plus any attached video/photos, as `media` rows (originals on NAS; `kind = 'image' | 'video'`). Pick a `hero_image` from the screenshot or a supplied photo. → draft.

*Video handling:* if a video is present it's attached to the recipe and playable in the recipe view (§9); if not, the view just falls back to the hero image. Nothing depends on the video existing. Videos can be large — keep them on the NAS mount, never on the local disk.

*Note:* Instagram captions often list ingredients but few/no steps (see the fixture in §13). The draft screen must gracefully allow empty steps and let the user add them.

### 5c. Google Drive folder
1. One-time OAuth to a Google account; store token locally. Point at a specific "Recipes" folder ID.
2. A **manual "Scan Drive" button** (v1 — no background polling) lists new files in the folder. **Scan only the recipes folder** — never the backup folder (§11), so the app doesn't try to import its own `.db` backup as a recipe.
3. Per file: images/PDFs/docs → same extraction as screenshots (vision) or text structuring. Track processed file IDs so re-scans skip them.
4. Each becomes a draft for review (batch review is fine). Originals copied to NAS media.

### 5d. Voice note (± photos)
1. User records in the browser (MediaRecorder API) or uploads an audio file; optionally attach photos.
2. Audio → **whisper.cpp** transcription (local). Run on the Pi (small model, slow) or offload to Tedlasso if it's faster; make the transcription host configurable.
3. Transcript (+ any photo captions via vision) → Claude structuring (§10) → title, ingredients, steps, tags.
4. Store audio + photos as media. → draft.

Anthropic's API does not transcribe audio; that's why Whisper is local. Keeping audio on-device also satisfies the data-locality goal.

---

## 6. Review & Correct Before Save (required)

Every import produces a **draft** (`recipe.status = 'draft'`). The user lands on an editable review screen and **nothing enters the library until they hit Save.**

The review screen must let the user:
- Edit title, description, source/author, hero image.
- Edit ingredient groups and every structured ingredient field (qty, unit, name, note, scalable toggle).
- **Edit the equipment / utensils list** — add, remove, rename. AI-inferred items (§10) are visibly marked so the user can confirm or delete guesses.
- Add/edit/reorder/delete steps.
- **Correct the auto-assigned tags** — see current tags per dimension, remove wrong ones, add from the controlled list.
- Preview the scaled (2x/3x) output before saving, to sanity-check the scaling.
- Save (→ published) or Discard.

Show the AI's confidence lightly if easy (e.g. mark low-confidence fields), but the main point is: everything is editable, and the correction is the last step before commit.

**Bulk / batch review (important for large initial loads).** When seeding the library with dozens–100+ recipes fast, a one-at-a-time review screen becomes the bottleneck. Add a **Drafts queue**: all pending drafts (from any source) in one list, each with a compact preview and a per-row **Approve**, **Edit**, or **Discard**. Approving publishes without opening the full editor; **Edit** opens the full review screen only for the ones that look off; **Approve all** clears a clean batch in one action. Drafts persist (`status='draft'`), so you can import a big pile now and work through the queue over several sittings without losing anything. The correct-before-publish guarantee is preserved — nothing auto-publishes; approval is still an explicit tap, just faster at volume.

---

## 7. Scaling Engine (kitchen-friendly)

**Requirement:** scaled amounts must be measurable on common kitchen equipment. No `0.999 cup`, no `0.7 tsp`, no `⅜ cup`. Runs client-side from the structured ingredient rows.

### Algorithm
For each ingredient with `scalable = 1` and a numeric `quantity`:

1. **Convert to a base unit** within its measurement family:
   - Volume → **teaspoons** (1 tbsp = 3 tsp, 1 cup = 48 tsp, 1 fl oz = 6 tsp).
   - Weight → **grams** (1 oz = 28.35 g, 1 lb = 453.6 g).
   - Count (clove, slice, egg, whole) → **pieces**.
2. **Multiply** by the factor (2 or 3).
3. **Re-express in the most sensible unit**, promoting upward when clean (tsp → tbsp → cup; g → oz/lb).
4. **Snap to the measurable ladder** for that unit:
   - **Spoons:** increments of ⅛ tsp down low; ¼ tsp, ½ tsp, ¾ tsp, 1 tsp; ½ tbsp (=1½ tsp), 1 tbsp.
   - **Cups:** ⅛, ¼, ⅓, ½, ⅔, ¾, 1 (and whole-number multiples).
   - Allowed fractions to display: {⅛, ¼, ⅓, ½, ⅔, ¾}. Never render others (⅜, ⅝, 0.7, etc.).
   - If a value lands between two ladder rungs, express as a **sum of measurable parts** (e.g. `¼ cup + 2 tbsp`) rather than an odd fraction, choosing the fewest measuring operations.
5. **Count items** (eggs, cloves, whole vegetables): round to a **whole number**. Never output a fractional egg. If rounding is significant, flag it in the note.
6. **`scalable = 0` items** (salt/pepper "to taste", garnishes): display unchanged with their original note.
7. Items with **no quantity** (assembly lists like "sliced steak"): display as-is, never scaled.

### Worked scaling (from the §13 fixture, dressing at 3x)
| Ingredient | 1x | ×3 result | Rendered (kitchen-friendly) |
|---|---|---|---|
| Olive oil | ¼ cup | ¾ cup | `¾ cup` ✓ |
| Apple cider vinegar | 1 tbsp | 3 tbsp | `3 tbsp` ✓ |
| Dijon | 2 tbsp | 6 tbsp | `¼ cup + 2 tbsp` |
| Honey | 1½ tbsp | 4½ tbsp | `¼ cup + 1½ tsp` |
| Minced garlic | 2 cloves | 6 cloves | `6 cloves` (whole count) ✓ |
| Fresh dill | 1 tbsp | 3 tbsp | `3 tbsp` ✓ |
| Fresh chives | 1 tbsp | 3 tbsp | `3 tbsp` ✓ |
| Salt & pepper | to taste | — | `to taste` (not scaled) |

Include unit tests for the snapping logic (esp. the honey/dijon "sum of parts" cases and egg rounding).

---

## 8. Starter Tag Taxonomy

Multi-dimensional (a recipe gets tags across several categories). Seed the `tag` table with these. This is a starting point — prune/extend to taste in the UI.

**Course / Meal**
Breakfast · Brunch · Lunch · Dinner · Appetizer · Side · Salad · Soup · Main · Dessert · Snack · Drink · Sauce/Dressing · Marinade · Bread/Baked

**Cuisine**
American · Italian · Mexican · French · Mediterranean · Middle Eastern · Indian · Thai · Chinese · Japanese · Korean · Vietnamese · Greek · Spanish · Cajun/Creole · Southern · BBQ · Other

**Main Protein / Base**
Beef · Chicken · Pork · Lamb · Turkey · Fish · Shellfish · Egg · Tofu/Tempeh · Beans/Legumes · Vegetable · Cheese · Pasta · Grain/Rice

**Dietary**
Vegetarian · Vegan · Gluten-Free · Dairy-Free · Nut-Free · Low-Carb/Keto · Paleo · High-Protein

**Method / Equipment**
Grill · Oven/Roast · Stovetop · Slow Cooker · Pressure Cooker · Air Fryer · Smoker · Sous Vide · No-Cook · Sheet Pan · One-Pot

**Time / Effort**
Quick (<30 min) · Weeknight · Make-Ahead · Meal Prep · Weekend Project

**Occasion (optional)**
Summer · Fall/Winter · Holiday · Game Day · Party · Date Night

*Example tagging (the §13 fixture):* Course=Salad + Main · Cuisine=American · Protein=Beef · Method=Grill + No-Cook · Time=Quick.

---

## 9. Frontend (phone-first)

**Pages**
- **Library / home:**
  - **Recipe of the Week** — a featured hero card pinned at the very top (large image, title, source, a "View recipe" tap). See "Recipe of the Week" below for how it's chosen.
  - Below it, the **search bar** (see "Search" below), then **tag filters** (filter by any dimension; combine filters), then the **grid of recipe cards** (hero image, title, source, key tags).
- **Recipe view (the "just the recipe" page):**
  - Title, source/author (with @handle and link to original if any).
  - **Media:** if the recipe has an attached video, show a video player at the top (muted, tap to play); otherwise show the hero image. Extra photos in a small gallery.
  - **1x / 2x / 3x** toggle at the top; changing it re-renders all scalable quantities instantly.
  - **Ingredients**, grouped by section, with checkboxes to tick off while shopping/cooking.
  - **Equipment / Utensils** — a clear, separate list of what you need (grill, whisk, mixing bowl, sheet pan, etc.). AI-inferred items may be shown with a subtle marker. When the scale is set above 1x, show a light reminder that larger or additional vessels may be needed (e.g. a bigger pot / a second sheet pan) — equipment itself is not scaled.
  - **Steps**, numbered, large and legible.
  - No blog narrative, no story. Optional collapsed "notes" section for the maker's asides (e.g. "I used habanero cheddar").
- **Import:** four entry points (paste URL · upload screenshot · scan Drive · record/upload voice) → each routes to the **review screen** (§6).
- **Review/edit screen** (§6).

**Search**
- Backed by **SQLite FTS5** (`recipe_fts` in §4) — fast, local, no extra service.
- A single search box matches across **title, ingredients, source/author, tags, and description/notes**. So "chicken", "@chacekitchen", "grill", "no-cook", or "dijon" all find the right recipes.
- Live results as you type (debounced); combine freely with the tag filters (search *within* an active filter set).
- Support simple prefix matching (e.g. "avo" → avocado). Rank title/ingredient hits above notes hits.
- Empty query = show the full library grid (with Recipe of the Week still pinned on top).

**Recipe of the Week**
- Default: a **deterministic weekly pick** derived from the ISO week number, so it's stable for the whole week and identical for both of you, and rotates automatically each week — no cron job needed, it's computed on load.
- Don't repeat recently featured recipes: keep a small `featured_history` (recipe_id + week) and exclude the last several picks until the library has cycled.
- **Manual override:** a "Feature this" action on any recipe pins it as Recipe of the Week until the next week (or until un-pinned). Manual pin always beats the automatic pick.
- Needs a handful of recipes to feel meaningful; with an empty/tiny library, just show the most recent recipe or hide the hero.

**UX notes**
- Big tap targets, high contrast, works one-handed.
- Fast on a Pi 4: static build, lazy-load images, thumbnails for the grid.
- Wake-lock button is **deferred** (§12) — leave a clear spot for it later.

---

## 10. Anthropic (Claude) API Setup

You don't have a key yet — here's the whole setup.

**Get a key**
1. Create an account at the Claude Developer Platform / Console (console.anthropic.com).
2. Add a small amount of credit (this workload costs cents — see below).
3. Create an API key. Store it on the Recipe Pi as an environment variable (`ANTHROPIC_API_KEY`), never in the frontend, never committed to git.

**Models** (current as of Aug 15, 2026 — verify in the console, model IDs change):
- **Default workhorse: `claude-haiku-4-5-20251001`** — vision-capable, cheapest, fast. Great for screenshot extraction, text structuring, and tagging.
- **Fallback for hard extractions: `claude-sonnet-5`** — use when Haiku's output is low-confidence or the source is messy.

**Cost** — trivial for personal use. Haiku 4.5 is about \$1 per million input tokens / \$5 per million output. A screenshot + prompt is on the order of ~1–2K input tokens and a few hundred output; each recipe costs a fraction of a cent. Even hundreds of imports total a few cents. Batch API (50% off) and prompt caching (cached input at ~10% of base) are available if you ever want them, but you won't need them at this volume.

**Where Claude is called** (server-side, in FastAPI):
1. **Screenshot / image extraction** — vision. Send the image; get structured recipe JSON + source handle + tags.
2. **URL fallback** — when `recipe-scrapers` fails, structure the page text.
3. **Ingredient structuring** — turn ingredient strings into `{quantity, unit, name, note, scalable}`.
4. **Voice structuring** — turn the Whisper transcript into a recipe.
5. **Auto-tagging** — assign tags from the controlled §8 list only.
6. **Equipment inference** — list the required utensils/equipment. Use items explicitly named in the source, and *infer* the obvious ones from the steps (e.g. "grill the steak" → grill; "whisk the dressing" → whisk + mixing bowl; "slice the apple" → knife + cutting board). Mark every inferred item with `inferred: 1` so the review screen (§6) can flag it for the user to confirm or delete. Don't over-invent — only tools a step clearly requires.

**Extraction contract:** prompt Claude to return **JSON only** (no prose, no markdown fences) matching the draft schema, so the backend can parse it directly. Always pass the **allowed tag list** into the tagging prompt and instruct it to choose only from that list. Handle parse failures by retrying once, then dropping the recipe into the review screen with whatever fields did parse (the user fixes the rest). Use the Messages API; images are sent as base64 image blocks.

**Privacy note:** only the *content being imported* (a screenshot, a page's text, a transcript) is sent to the API for structuring. The recipe library itself stays entirely on your Pi.

---

## 11. Backup & Restore

Two tiers: a fast **local snapshot** (safety net if the SD card/app disk dies) and a **weekly off-site copy to Google Drive** (safety net if the whole house/NAS is lost). Both back up the same consistent snapshot of the DB.

### What gets backed up
- **The SQLite database** — the crown jewels. It's one small file that holds every recipe, tag, and media *path*. This is the priority.
- **Media (screenshots, photos, video, audio)** is bulkier and already lives on the NAS. v1 does **not** push media to Drive weekly (video especially would blow past Drive quotas). Instead, media is protected by the NAS. If you want off-site media too, run a separate, less-frequent archive (see "Optional" below) — but the DB is what the weekly job guarantees.

### Making a consistent snapshot (don't copy a live DB)
Never `cp` a database that's being written — you can capture a half-written file. Produce a clean snapshot first:
```bash
sqlite3 /home/pi/recipes/data/recipes.db "VACUUM INTO '/tmp/recipes-backup.db'"
```
`VACUUM INTO` writes a fully consistent, compacted copy safe to upload.

### Weekly Google Drive backup (overwrite in place)
Reuses the same Google OAuth credential you set up for Drive import (§5c) — no new auth.

1. A scheduled job (**systemd timer** or cron, weekly, e.g. Sunday 3 AM) runs a small standalone script — decoupled from the web app so it runs even if the app is restarting.
2. The script: makes the `VACUUM INTO` snapshot → uploads it to a **dedicated backup folder** in Drive (e.g. `/RecipeApp/backups/`, **separate** from the import folder so the scanner in §5c never touches it) → updates the **same file** each week (same Drive `fileId`) via the Drive API's `update` call, so it **overwrites the previous version** as you asked. Filename e.g. `recipes-backup.db`.
3. Record `last_backup_at` + status in a tiny table and **show it in the UI** (e.g. a small "Last backup: Sun 3 AM ✓" line in settings). A backup that's been silently failing for six weeks is worthless — surface success/failure. Log errors; optionally show a banner if the last backup is >10 days old.

**Safety note on "overwrite":** overwriting a single file means if a backup ever captures a corrupted DB, it replaces your only good copy. Two things mitigate this cheaply:
- **Google Drive keeps native version history.** Because you update the *same* file, Drive retains prior versions (~30 days for binary files) — so "overwrite" still leaves a rollback path without any extra copies. This satisfies the single-file request *and* gives a safety net.
- The **local nightly snapshot** (below) is an independent second line of defense.

If you'd rather keep a few explicit weekly copies instead of relying on Drive's version history, keep the last 4 (`recipes-backup-1..4.db`, rotating) — one extra line of code. Your call; the overwrite-single-file default is what's specified.

### Local nightly snapshot (fast, independent)
Independently of Drive, run a **nightly** `VACUUM INTO` to the NAS mount (e.g. `/media/backups/recipes-YYYYMMDD.db`), keeping the last ~7 days. This is instant to restore from and covers the common case (bad migration, accidental delete) without a network round-trip.

### Restore
1. Stop the app (`systemctl stop recipes`).
2. Copy the chosen snapshot over `recipes.db` (from the NAS nightly folder, or download `recipes-backup.db` from Drive — or an older Drive *version* if the latest is bad).
3. Restart. Done — media paths in the DB still resolve because the NAS layout is unchanged.

**Test the restore once, on purpose.** A backup you've never restored is a hope, not a backup. After building this, do a dry-run restore to a throwaway copy to confirm the whole loop works.

### Optional: off-site media archive (later)
If you want media off-site too, a monthly `rclone` sync of the NAS media folder to Drive (or another cloud) covers it. Left out of v1 to keep Drive usage small and the weekly job fast.

---

## 12. Deferred / Future

- **Screen wake-lock** ("don't auto-lock while cooking"): the browser Screen Wake Lock API requires a *secure context* (HTTPS or `localhost`). Plain `http://recipes.local` won't qualify, so it's deferred per your call. When you want it: either put the app behind a locally-trusted cert (e.g. Caddy issuing a cert your two phones trust) or use Tailscale's HTTPS — you've said the Tailscale UX isn't right for your wife, so the local-cert route is the better eventual path. Leave a placeholder button.
- **Auth / accounts:** none in v1 (home network only). If you later expose it or want per-user favorites, add a simple single-shared-password gate or per-user logins.
- **Drive auto-sync:** v1 is a manual "Scan" button; a background watcher can come later.

---

## 13. Built-in Test Fixture (from your Instagram screenshot)

Use this real example (chacekitchen, saved May 11 2025) as a seed/test recipe. It exercises: two ingredient groups, an assembly list with no quantities, a dressing with scalable quantities, "to taste" non-scaling items, source handle capture, and empty steps.

```json
{
  "title": "Apple Cheddar Steak Salad",
  "description": "Steak Salad Sundays Part 63 — an apple cheddar moment.",
  "source_type": "instagram",
  "source_name": "chacekitchen",
  "source_handle": "@chacekitchen",
  "servings_base": 2,
  "servings_unit": "salads",
  "groups": [
    {
      "name": "For the salad",
      "ingredients": [
        {"quantity": null, "unit": null, "name": "sliced steak", "scalable": 0},
        {"quantity": null, "unit": null, "name": "butter lettuce", "scalable": 0},
        {"quantity": null, "unit": null, "name": "honeycrisp apple slices", "scalable": 0},
        {"quantity": null, "unit": null, "name": "sliced shallot", "scalable": 0},
        {"quantity": null, "unit": null, "name": "avocado slices", "scalable": 0},
        {"quantity": null, "unit": null, "name": "sweet and spicy pecans", "scalable": 0},
        {"quantity": null, "unit": null, "name": "cheddar cubes", "note": "used habanero cheddar (Cabot)", "scalable": 0},
        {"quantity": null, "unit": null, "name": "cheddar crisps", "note": "used Tillamook", "scalable": 0},
        {"quantity": null, "unit": null, "name": "honey dijon dressing", "note": "see below", "scalable": 0}
      ]
    },
    {
      "name": "Honey dijon dressing",
      "ingredients": [
        {"quantity": 0.25, "unit": "cup",  "name": "olive oil", "scalable": 1},
        {"quantity": 1,    "unit": "tbsp", "name": "apple cider vinegar", "scalable": 1},
        {"quantity": 2,    "unit": "tbsp", "name": "dijon", "scalable": 1},
        {"quantity": 1.5,  "unit": "tbsp", "name": "honey", "scalable": 1},
        {"quantity": 2,    "unit": "clove","name": "garlic", "note": "minced", "scalable": 1},
        {"quantity": 1,    "unit": "tbsp", "name": "fresh dill", "scalable": 1},
        {"quantity": 1,    "unit": "tbsp", "name": "fresh chives", "scalable": 1},
        {"quantity": null, "unit": null,   "name": "salt and pepper", "note": "to taste", "scalable": 0}
      ]
    }
  ],
  "steps": [],
  "equipment": [
    {"name": "grill or grill pan", "inferred": 1},
    {"name": "chef's knife", "inferred": 1},
    {"name": "cutting board", "inferred": 1},
    {"name": "mixing bowl", "inferred": 1},
    {"name": "whisk", "inferred": 1}
  ],
  "tags": {
    "Course": ["Salad", "Main"],
    "Cuisine": ["American"],
    "Protein": ["Beef"],
    "Method": ["Grill", "No-Cook"],
    "Time": ["Quick (<30 min)"]
  }
}
```

*(Every equipment item here is `inferred: 1` — the caption names no tools, so these come from reading the ingredients/steps. In the review screen they'd all be flagged for the user to confirm. This is the normal case for Instagram captions.)*

The second import example you gave — `https://playswellwithbutter.com/all-purpose-grill-marinade/` — should be your URL-path test: `recipe-scrapers` supports that site, so it exercises the clean structured path (and it's a marinade, so it tests the Sauce/Dressing + Marinade tags and the grill method).

---

## 14. Eating Out — Places & Orders (widened scope)

Same app, second collection. A top-level toggle switches the UI between **Cook** (recipes) and **Eat Out** (places). Places reuse the recipe machinery — tags, media, the review/Drafts queue (§6), search (§9), backups (§11) — so this is mostly additive, not a second app. (The project is now a food app broadly, not just recipes.)

**Core idea:** a Place isn't just a restaurant name — it's *where to go* plus *what to order there*. Each place carries a list of recommended dishes ("get the X"), the eat-out parallel to a recipe's ingredients.

### Data model additions
```sql
CREATE TABLE place (
  id            INTEGER PRIMARY KEY,
  name          TEXT NOT NULL,
  place_type    TEXT,     -- 'restaurant' | 'takeout' | 'cafe' | 'bar' | 'food truck' | ...
  city          TEXT,     -- also mirrored as a City tag for filtering
  address       TEXT,
  maps_url      TEXT,     -- pasted Google Maps link
  maps_place_id TEXT,     -- optional, only if Places API is added later
  phone         TEXT,
  website       TEXT,
  price_level   INTEGER,  -- 1–4 ($–$$$$)
  our_rating    INTEGER,  -- optional 1–5
  our_notes     TEXT,     -- why we like it
  source_name   TEXT,     -- who recommended it (friend, IG account, ...)
  source_url    TEXT,
  hero_image    TEXT,
  visited       INTEGER DEFAULT 1,  -- 1 = been there; 0 = want to try
  status        TEXT DEFAULT 'published',  -- reuses the draft/review flow
  created_at    TEXT,
  updated_at    TEXT
);

CREATE TABLE place_dish (   -- the "foods to order out"
  id         INTEGER PRIMARY KEY,
  place_id   INTEGER REFERENCES place(id) ON DELETE CASCADE,
  name       TEXT NOT NULL,   -- 'birria tacos'
  note       TEXT,            -- 'get it with the extra consommé'
  must_order INTEGER DEFAULT 0,
  sort_order INTEGER
);

CREATE TABLE place_tag (
  place_id INTEGER REFERENCES place(id) ON DELETE CASCADE,
  tag_id   INTEGER REFERENCES tag(id),
  PRIMARY KEY (place_id, tag_id)
);
```
- **Media & tags reuse:** add a nullable `place_id` to `media` and make `recipe_id` nullable (exactly one set), so photos/screenshots attach to places too. Add a parallel `place_fts` search table (name + city + cuisine + dishes + notes).
- **New tag categories:** **City/Area** (their main axis), **Place Type**, **Price**. **Cuisine reuses the recipe vocabulary** — one shared list, so "Thai" means the same thing whether you cook it or order it.

### Tags & the local assumption
~99% are local, so City **defaults to your home city** on new entries (one tap to change when traveling). Filtering by city gives both "our local go-tos" and, when you travel, "what we saved in Austin."

### Google Maps
v1 is lightweight: paste a Maps link (or an address); the place page shows an **Open in Maps / Directions** button. Matches the "just links, mostly local" instinct and needs no API key. Optional later: the Google Places API for name autocomplete + auto-filled address/hours — another key + billing (like Drive), only worth it if manual entry gets tedious.

### Sharing recommendations to visitors
Honest constraint: the site is **LAN-only (§2)**, so you can't just send a friend a link — they can't reach `recipes.local` from outside the house. Realistic paths:
- **Export a curated list** — pick a city/tag filter ("Our [city] picks") and generate a clean, screenshot-friendly card or a one-page PDF to text/email. This is the v1 answer and matches how people actually share recs.
- **Google Maps list** — since you store Maps links, you can also keep a shareable Google saved-list in Maps itself for the fully-external case.
- True in-app link sharing would require exposing the site (HTTPS/Tailscale) — the thing you deliberately deferred. Export-to-image/PDF sidesteps it.

### Reused as-is
The **Drafts queue (§6)**, **search + filters (§9)**, and **backups (§11)** all apply to places with no new design. A place can even be imported from a screenshot (a friend's text, an IG post) via the same Claude vision path (§10), extracting name, city, and the dishes mentioned.

---

## 15. Open Decisions & Likely Next Steps (blind-spot check)

Things not yet nailed down — worth a decision now or a conscious "later," because they're the gaps you'd otherwise hit mid-build.

**Decide now**
- **Sharing = export, not links.** Because the app is LAN-only (§2, §14), anything shared outside the house is an exported image/PDF/text, not a URL. Real shareable links = the HTTPS/Tailscale step you deferred.
- **Store remote images locally.** On URL import, download the hero image into your media store rather than hot-linking — source pages and IG posts vanish, and you want the app to work offline. Reinforces data-locality and makes the app a hedge against link rot.
- **Duplicate handling at bulk load.** ~100 fast + the same dish saved by URL *and* screenshot = dupes. Add a light check at import (match on source URL, or fuzzy title match) that flags "possible duplicate" in the Drafts queue.
- **Editing after publish + living notes.** A home cookbook is never write-once. Keep published recipes/places fully editable, and add a simple **"what we changed" notes field** you append to over time ("doubled the garlic," "too salty at 3x"). Often the most-loved feature in a personal recipe app.
- **Favorites / want-to-try / made-it.** A tiny status flag on recipes (want to make / made it) and places (`visited` 0/1) turns the library into a decision tool, not just an archive.
- **SQLite WAL mode.** Two people may write at once; enable WAL so concurrent access doesn't collide.

**Likely next wants (not v1, but design so they slot in)**
- **Meal planning + combined grocery list.** Pick a few recipes → merge their (scaled) ingredients into one shopping list. The obvious high-value follow-on to the shopping checkboxes already in scope.
- **Off-site media backup.** The weekly Drive backup covers the DB, not the photos/videos on the NAS — if the NAS dies, media is gone. A periodic `rclone` sync of media closes that gap (§11 optional).

**Consciously out of scope (a choice, not an oversight):** nutrition/calorie data, calendar meal scheduling, and public/multi-household sharing. All addable later; none needed for two people on day one.

---

## 16. Build Plan (three chunks)

Grouped into three chunks you hand to Claude Code one at a time, verifying each before the next. Chunk A is kept separate on purpose — it holds the foundation and the one genuinely bug-prone piece (the scaling engine), so it's worth getting right in isolation before anything auto-extracted stacks on top. Chunks B and C can each be built in a single pass.

### Chunk A — Working manual app (build and verify on its own)
The whole app, usable, with no AI and no imports yet.
- **Skeleton:** FastAPI + SQLite, full schema from §4, seed the tag taxonomy (§8), static React shell, `recipes.local` resolving via Avahi.
- **Core UI:** create/edit/view a recipe by hand — ingredients, equipment/utensils, steps; the library grid; the recipe view.
- **Scaling engine (§7) with its unit tests** — the kitchen-friendly fraction snapping. This is the reason Chunk A stands alone: prove it against recipes you typed in yourself.
- **FTS5 search + tag filters (§9)** — so a fast-growing library stays navigable the moment Chunk B starts filling it.
- **Done =** a real, usable recipe app. You could stop here and it would work.

### Chunk B — All four import methods
They share the same extraction → **review/Drafts queue (§6)** → publish pipeline, so there's little reason to space them out once setup is done.
- **URL import:** `recipe-scrapers` + ingredient structuring. Test with the Plays Well With Butter marinade.
- **Claude API + screenshot import:** wire up the API (§10), vision extraction incl. equipment inference. Test with the steak-salad fixture (§13).
- **Voice import:** local whisper.cpp → transcript → structure.
- **Google Drive import:** OAuth + manual folder scan — your bulk loader.
- **Prereqs you must do first** (these gate this chunk): create the Anthropic API key + billing (§10), and set up the Google Cloud OAuth credentials for Drive (§5c).
- **Done =** recipes flow in from links, screenshots, voice, and Drive folders.

### Chunk C — Polish + backups
- **Recipe of the Week (§9)**, thumbnails, NAS media mount.
- **Backups (§11):** nightly local snapshot + weekly Google Drive backup, "last backup" status in the UI, and one real test restore.
- **Done =** pleasant to use and your data is safe.

### Chunk D — Eating Out / Places (optional, additive)
The widened scope (§14). Because it reuses the core (tags, media, Drafts queue, search, backups), it can slot in any time **after Chunk A** — it doesn't block anything.
- Add the `place` / `place_dish` / `place_tag` tables and the Cook ⇄ Eat Out toggle.
- Reuse the import + review pipeline; add the Maps-link field and the curated-list export for sharing.
- **Done =** you can save where to eat and what to order, filter by city, and export a list to share with visitors.

### Deferred (not a chunk — real blockers)
- **Screen wake-lock (§12)** — needs HTTPS, which you chose to skip for now.
- **Auth** — none in v1 (home network only).
- **Drive auto-sync** — background watcher; v1 is the manual Scan button.

Build Chunk A first and confirm the scaling is correct before moving on — it's the foundation everything else rests on.
