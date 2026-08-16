# Chunk A — Working Manual App  (Build Prompt 1 of 4)

**Before you start, read `recipe-app-spec.md` in full and `CLAUDE.md` (the always-on guardrails).**

## Where this fits
This is **Chunk A of a 4-chunk build (A → B → C → D)**. You are building the foundation only. Chunk B (imports), Chunk C (polish + backups), and Chunk D (eating-out/places) are **separate prompts that come later** — **do not build them now and do not stub them.** The user will test this chunk before requesting the next.

One forward-looking exception: design the DB schema so later chunks won't need destructive changes, but **only create the recipe-side tables now** (the `place*` tables arrive in Chunk D).

## Goal
A fully usable, **AI-free, network-free** recipe app: type a recipe in by hand, view it, scale it correctly, and search the library. This chunk deliberately contains the riskiest logic — the scaling engine — so it must be independently verifiable before anything stacks on top.

## Build
1. **Skeleton**
   - FastAPI + uvicorn; SQLite with WAL enabled; schema from spec §4 (recipe, ingredient_group, ingredient, step, tag_category, tag, recipe_tag, media, equipment, recipe_fts, featured_history — **skip the place tables**).
   - Migration runner (numbered SQL, idempotent, applied at startup).
   - Seed the tag taxonomy from spec §8 into `tag_category` + `tag`.
   - React + Vite + TS + Tailwind frontend, built and served by FastAPI as static files. Bind `0.0.0.0`.
   - Document the `recipes.local` (Avahi/mDNS) step in the README (the actual Avahi install is host config).
2. **Recipe CRUD + core UI**
   - Create / edit / view / delete a recipe by hand: title, description, source fields, **ingredient groups + structured ingredients**, **equipment/utensils list**, steps.
   - **Library home:** grid of recipe cards (image, title, source, key tags).
   - **Recipe view** (the "just the recipe" page, spec §9): hero image, **1x / 2x / 3x toggle**, grouped ingredients with tick-off checkboxes, **equipment list**, numbered steps, collapsible notes. No blog narrative anywhere.
3. **Scaling engine — the core deliverable** (spec §7)
   - Standalone TS module: convert to a base unit → multiply → promote units (tsp→tbsp→cup) → **snap to the kitchen-friendly ladder** → express as sums of measurable parts. Round count items (eggs) to whole. Never scale `scalable = 0` or quantity-null items.
   - **Vitest unit tests** covering the spec's worked examples — especially honey `1.5 tbsp ×3 → "¼ cup + 1½ tsp"`, dijon `2 tbsp ×3 → "¼ cup + 2 tbsp"`, clean cases (`¼ cup ×3 → ¾ cup`), and egg rounding. Tests must pass.
4. **Search + filters** (spec §9)
   - FTS5 index over title + ingredient names + tags + source + notes, kept in sync on every save.
   - Search box (live, debounced, prefix match) + tag filters (any dimension, combinable). Empty query = full grid.

## Design direction (the front end must feel nice — it's for daily phone use by two people)
Phone-first, one-handed, large tap targets. Clean and warm/appetizing, not a generic admin template — thoughtful typography, generous spacing, good use of the hero images, fast. Legible step text for use while cooking. Keep the bundle light for the Pi 4.

## Out of scope — do NOT build
- Any import (URL / screenshot / voice / Drive) → Chunk B.
- Any Anthropic/Claude API call → Chunk B.
- Recipe of the Week, thumbnail pipeline, backups → Chunk C.
- Places / eating-out → Chunk D.
**Manual entry only. No external network calls at all in this chunk.**

## Acceptance (how the user will test before Chunk B)
- Add, edit, and view a recipe by hand with grouped ingredients + equipment + steps.
- The **steak-salad fixture (spec §13)** can be entered and displays correctly; the dressing scales to the §7 values at 2x/3x — verify on screen and via Vitest.
- `vitest` passes the scaling suite; `pytest` passes backend tests.
- Search finds a recipe by title, ingredient, tag, and source; tag filters work and combine with search.
- Runs on the Pi and is reachable from a phone on the LAN.

## When done
Summarize: what was built, how to run backend + frontend, how to run the tests, and the `recipes.local` setup step. Then **stop** — the user will test before requesting Chunk B.
