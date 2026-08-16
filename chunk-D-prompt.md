# Chunk D — Eating Out / Places  (Build Prompt 4 of 4 · additive)

**Before you start, read `recipe-app-spec.md` §14 and `CLAUDE.md`.**

## Where this fits
This is **Chunk D of 4**, the final, **additive** chunk. **Chunks A–C are built and working.** This adds a second collection and **must not disrupt the existing recipe features** — reuse the core (tags, media, Drafts queue, search, backups) rather than duplicating it. It can be built any time after Chunk A.

## Goal
A second collection: save **where to eat** and **what to order there**, filter by city, and export a curated list to share with visitors.

## Build
1. **Schema** (spec §14) — add `place`, `place_dish`, `place_tag`; add a **nullable `place_id`** to `media` and make `recipe_id` nullable (exactly one set); add `place_fts`. New tag categories: **City/Area, Place Type, Price**. **Cuisine reuses the existing recipe vocabulary.** The migration must be **non-destructive** to existing recipe data.
2. **Cook ⇄ Eat Out toggle** — top-level nav switching collections. Reuse the grid, search, filters, and review/Drafts flow for places.
3. **Place entry + view** — name, type, **city (defaults to the configured home city)**, address, **pasted Google Maps link + "Open in Maps / Directions" button**, price level, our rating, our notes, source (who recommended it), **visited / want-to-try** flag, and the **recommended dishes list** (`place_dish`, with a must-order flag). This dish list is the eat-out parallel to a recipe's ingredients — make it prominent.
4. **Import** — reuse the pipeline: add a place manually, or extract one from a **screenshot** via Claude vision (name, city, dishes mentioned). Drafts queue applies.
5. **Sharing** (spec §14) — curated-list **export**: filter by city/tag → generate a clean, screenshot-friendly card or a **one-page PDF** ("Our [city] picks") to save/text/email. (LAN-only means export, not shareable links.)

## Out of scope — do NOT build
- Google Places API autocomplete (optional future; v1 is a pasted Maps link).
- Public link sharing / exposing the site (deferred, spec §12).

## Acceptance
- Add a place with dishes; it appears under **Eat Out**, filterable by **city** and cuisine, with an Open-in-Maps button.
- **Existing recipes are untouched**; the toggle cleanly separates the two collections; search works within each.
- A screenshot of a friend's recommendation imports into a place draft.
- Exporting a city filter produces a shareable image / PDF list.

## When done
Summarize what was built and how to use the export. This **completes the four-chunk build**.
