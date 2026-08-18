# Build this yourself — a prompt for your own AI

This repo is a **self-hosted, phone-first food app** for a couple of people on a home network
(Raspberry Pi 4): a recipe library with kitchen-friendly scaling, four import methods, an
"eat out" places collection, a weekly meal planner with a consolidated grocery list, and an
AI recipe-variation builder. Backend is **Python + FastAPI + SQLite**; frontend is
**React + Vite + TypeScript + Tailwind** built to static files and served by FastAPI.

You can hand the whole thing to a coding agent (Claude Code, or similar) and have it built
from scratch. There are two ways to do it.

---

## Option A — hand over the design docs (highest fidelity) ✅ recommended

This repo already contains everything an agent needs, written as prompts:

- **`recipe-app-spec.md`** — the full design and source of truth (schema, the scaling ladder,
  tag taxonomy, every feature).
- **`CLAUDE.md`** — always-on guardrails the agent must follow every session.
- **`chunk-A-prompt.md` … `chunk-F-prompt.md`** — six build prompts, one per stage.
- **`BUILD-ORDER.md`** — how the chunks fit together and what to test between them.

**Do this:**
1. Put `recipe-app-spec.md`, `CLAUDE.md`, and the six `chunk-*-prompt.md` files in an empty
   repo (or just point your agent at a clone of this one).
2. Feed the chunk prompts **one at a time, in order A→F**. For each, paste:
   > Read `recipe-app-spec.md` and `CLAUDE.md`, then build exactly the chunk described in
   > `chunk-A-prompt.md`. Write the tests it asks for, run them, and show me how to run the
   > app. Do not build ahead to later chunks.
3. **Test between chunks.** Especially after Chunk A, verify the scaling engine (unit tests +
   type a recipe in by hand and check 2×/3×) before stacking anything on it.
4. Chunks **B** and **F** need an **Anthropic API key**; **B** also needs Google OAuth
   (Drive) and whisper.cpp (voice) if you want those paths. Everything degrades gracefully
   without them.

That's the same sequence this repo was built in.

---

## Option B — one paste, from scratch

If you'd rather drop a single self-contained brief into a fresh chat, paste everything in the
box below. It's opinionated and complete enough to produce a faithful build; for the exact
schema and edge cases, tell the agent to also read `recipe-app-spec.md` if you have it.

> ⚠️ The **scaling engine** is the one genuinely bug-prone piece — build and unit-test it in
> isolation first. The essentials are included below.

---

````text
You are building a self-hosted, phone-first "food app" for two people on a home LAN, running
on a Raspberry Pi 4 (4 GB). Build it in SIX additive chunks (A→F), one at a time, testing each
before the next. Do NOT build ahead. End every chunk by telling me what you built, how to run
the backend + frontend, and how to run the tests.

## Stack (keep it lean for a Pi 4)
- Backend: Python 3.11+, FastAPI + uvicorn, plain `sqlite3`. SQLite with WAL mode.
- Migrations: numbered .sql files applied idempotently at startup; NON-destructive to existing
  data (the schema grows across chunks).
- Frontend: React + Vite + TypeScript + Tailwind, built to static and served by FastAPI.
  Keep the bundle light.
- Scaling engine: a standalone TypeScript module with Vitest unit tests.
- Search: SQLite FTS5. Tests: pytest (backend), vitest (frontend).

## Golden rules (never violate)
1. The SQLite .db lives on the Pi's LOCAL disk only — never on a NAS/NFS/SMB mount (network
   filesystems corrupt SQLite). Media MAY live on the NAS; store only relative paths in the DB.
2. Enable WAL mode (two users may write at once).
3. Everything local & offline-capable. On import, DOWNLOAD remote images into the local media
   store — never hot-link. Device photo uploads are stored the same way; fix EXIF orientation
   and downscale/thumbnail on upload.
4. Config via environment / `.env`, never hardcoded. Secrets never committed. Ship `.env.example`.
5. Structured ingredients only: {quantity, unit, name, note, scalable}. Never free text.
6. Kitchen-friendly quantities only in scaled output (see the ladder below). No 0.7 tsp, no ⅜ cup.
7. Controlled tag vocabulary — auto-tagging picks only from existing tags; never invent tags.
8. Don't stub or fake. If blocked on a credential/device, make it configurable, mark a TODO,
   disable that feature gracefully, and keep going. Never fabricate data or pretend a call worked.
9. LAN-only, plain HTTP. Bind 0.0.0.0; serve at recipes.local via mDNS/Avahi. No auth, no HTTPS.
10. Never auto-publish an import or a generated recipe. Everything lands as a `draft` and needs
    an explicit human approval.
11. Clean, tight, content-first UI: a persistent header with a home/library link on every page;
    one primary action per screen, secondary actions in a "⋮" overflow menu; one consistent
    spacing/typography/button system.

## Data model (SQLite, essentials)
- recipe(id, title, description, source_type, source_name, source_url, source_handle,
  hero_image, servings_base, servings_unit, total_time, status['draft'|'published'],
  created_at, updated_at). Chunk F adds: generated, derived_from_recipe_id, generation_prompt.
- ingredient_group(id, recipe_id, name, sort_order); ingredient(id, group_id, quantity REAL
  nullable, unit, name, note, scalable[0|1], sort_order); step(id, recipe_id, text, sort_order);
  equipment(id, recipe_id, name, inferred[0|1], sort_order).
- tag_category(id, name) + tag(id, category_id, name) + recipe_tag(recipe_id, tag_id).
- media(id, recipe_id nullable, place_id nullable, kind, path, caption).
- recipe_fts (FTS5): title, description, source, ingredients, tags — rebuilt on save.
- Chunk C: featured_history(recipe_id, iso_week, pinned). Chunk D: place, place_dish,
  place_tag, place_fts. Chunk E: meal_plan, meal_plan_entry (recipe_id XOR place_id, per-entry
  scale), grocery_item (name, unit, quantity/display, aisle, checked, manual, source recipes).

## Scaling engine (build & unit-test FIRST — spec is precise here)
For each ingredient with scalable=1 and a numeric quantity:
1. Convert to a base unit within its family: volume→teaspoons (1 tbsp=3 tsp, 1 cup=48 tsp,
   1 fl oz=6 tsp), weight→grams (1 oz=28.35 g, 1 lb=453.6 g), count (clove/slice/egg)→pieces.
2. Multiply by the factor (2 or 3).
3. Re-express in the most sensible unit (tsp→tbsp→cup; g→oz/lb).
4. Snap to the measurable ladder. Allowed display fractions ONLY: ⅛ ¼ ⅓ ½ ⅔ ¾. If a value
   lands between rungs, express it as a SUM of measurable parts (e.g. "¼ cup + 2 tbsp"),
   fewest measuring ops. Count items round to a WHOLE number (never a fractional egg).
5. scalable=0 items and quantity-null items are shown as-is, never scaled.
Worked check (dressing ×3): olive oil ¼ cup→¾ cup; dijon 2 tbsp→"¼ cup + 2 tbsp";
honey 1½ tbsp→"¼ cup + 1½ tsp"; garlic 2 cloves→6 cloves; salt "to taste"→unchanged.
Write Vitest tests for the sum-of-parts and egg-rounding cases.

## Tag taxonomy (seed these; auto-tagger picks only from them)
Course (Breakfast, Lunch, Dinner, Appetizer, Side, Salad, Soup, Main, Dessert, Snack, Drink,
Sauce/Dressing, Marinade, Bread/Baked), Cuisine (American, Italian, Mexican, French,
Mediterranean, Indian, Thai, Chinese, Japanese, Korean, Greek, Cajun/Creole, Southern, BBQ…),
Protein (Beef, Chicken, Pork, Lamb, Turkey, Fish, Shellfish, Egg, Tofu/Tempeh, Beans/Legumes,
Cheese, Pasta, Grain/Rice), Dietary (Vegetarian, Vegan, Gluten-Free, Dairy-Free, Nut-Free,
Low-Carb/Keto, Paleo, High-Protein), Method (Grill, Oven/Roast, Stovetop, Slow Cooker,
Pressure Cooker, Air Fryer, Smoker, Sous Vide, No-Cook, Sheet Pan, One-Pot), Time (Quick
(<30 min), Weeknight, Make-Ahead, Meal Prep, Weekend Project), Occasion (Summer, Fall/Winter,
Holiday, Game Day, Party, Date Night), Status (Want to Cook, Have Cooked).
For Places (Chunk D): City/Area, Place Type, Price — and Cuisine is SHARED with recipes.

## The six chunks
A. Manual app: full schema, seeded tags, CRUD for recipes (structured ingredients, equipment,
   steps), the library grid + recipe view, the scaling engine WITH its unit tests, and FTS5
   search + tag filters. Done = a usable recipe app with no AI.
B. Imports (all land as drafts in a review/Drafts queue; nothing auto-publishes):
   URL (recipe-scrapers + a browser User-Agent fetch; Reddit via the post .json + AI), screenshot
   & video (Claude vision; video = sample frames with ffmpeg), voice (whisper.cpp → transcript
   → structure), Google Drive folder scan (OAuth, manual "Scan"). Uses the Anthropic API
   (Claude) for vision/structuring/tagging/equipment-inference; JSON-only extraction contract,
   retry once, pass the allowed tag list. Add a deterministic offline auto-tagger too.
C. Polish + backups: Recipe of the Week (deterministic weekly pick + manual pin), thumbnails
   (Pillow, WebP, cached on local disk), NAS media mount, VACUUM-INTO snapshots (nightly local
   rotation + weekly Google Drive overwrite), "last backup" status in the UI, and a real restore.
D. Eat Out / Places (additive, reuse tags/media/drafts/search/backups): place + place_dish +
   place_tag + place_fts; nullable media.place_id; a Cook⇄Eat Out toggle; place entry/view with
   a pasted Google Maps link + "Open in Maps" button, price, rating, visited/want-to-try, and a
   prominent recommended-dishes list; screenshot import of a place; a printable "Our [city]
   picks" export. City defaults to a configured HOME_CITY.
E. Meal planner + grocery list (mostly deterministic; AI optional): meal_plan/meal_plan_entry/
   grocery_item; a 7-day board (default upcoming Saturday) whose picker reuses recipe search;
   an "Add to meal plan" recipe action; generate a consolidated grocery list by REUSING the
   scaling engine to sum ingredients (normalize names so "garlic cloves"+"minced garlic"→garlic;
   incompatible units stay separate; quantity-less items listed once; group by aisle);
   regeneration preserves checked + manual items; check off, add manual items, copy-as-text +
   print. Optional AI only tidies aisle categorization.
F. AI recipe variations + UI clean-up + photo upload. Variations: recipe gains generated /
   derived_from_recipe_id / generation_prompt and source_type 'ai'; from a saved recipe + a
   natural-language instruction, generate a realistic STRUCTURED variation with claude-sonnet-5
   (JSON schema identical to imports, kitchen-friendly, controlled tags, equipment inferred,
   retry once), saved immediately as a DRAFT (never auto-published, never credited to the
   original human creator, marked "AI variation of [source] · untested"); iterate on a draft.
   A generated draft should be COOKABLE from the normal recipe view while still a draft, with a
   "Save to library" (publish) vs "Discard" choice. UI: persistent header with a home link + the
   Cook⇄Eat Out toggle; promote the primary action and move the rest into a "⋮" menu (keep the
   1×/2×/3× scale toggle inline); the menu must not be clipped by an overflow-hidden parent and
   should scroll. Photo upload: a file input with accept="image/*" capture="environment" →
   store locally, fix EXIF orientation, downscale, thumbnail, set as hero (no schema change).

## Deferred (do NOT build): HTTPS/wake-lock, auth/accounts, background Drive sync, Google Places
autocomplete, and pantry-inventory/receipt-photo restocking (a possible later "Chunk G").

Start with Chunk A and confirm the scaling is correct before moving on — everything trusts it.
````

---

## Running it (once built)
- Backend: `cd backend && python -m venv .venv && . .venv/bin/activate && pip install -r
  requirements.txt && uvicorn app.main:app --host 0.0.0.0 --port 8000`
- Frontend: `cd frontend && npm ci && npm run build` (FastAPI serves the build).
- Tests: `pytest` in `backend/`, `npx vitest run` in `frontend/`.
- Optional keys live in `.env` (see `.env.example`): `ANTHROPIC_API_KEY` unlocks
  screenshot/video/Reddit/voice imports and AI variations; Google OAuth unlocks Drive import
  and the weekly Drive backup; `HOME_CITY` defaults new places' city.

The full, authoritative design is in `recipe-app-spec.md`; the always-on rules are in `CLAUDE.md`.
