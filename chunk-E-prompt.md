# Chunk E — Meal Planner & Grocery List  (Build Prompt 5 · additive)

**Before you start, read `recipe-app-spec.md` §17 and `CLAUDE.md`.**

> **Final session:** Chunks E and F are the last two. They can be built **back-to-back in one session** — build **this (E) first**, verify it, then Chunk F. Keep them as separate, independently-tested steps.

## Where this fits
This is **Chunk E**, an **additive** chunk. **Chunks A–D are built and working.** This adds a weekly meal planner and a generated grocery list, and **must not disrupt existing features** — reuse the core (the **Chunk A scaling/unit engine**, search/filters, and the Chunk D export) rather than duplicating it. It can be built any time after Chunk A (eat-out days need Chunk D).

> **Check against the real codebase first.** The spec is the design; confirm the actual `recipe`, `ingredient`, and `place` table/column names and the scaling module's exported functions in the current repo, and match them. If anything diverges from the spec, follow the code and note it.

## Is this an AI chunk?
**Mostly no.** The core is deterministic and reuses the scaling engine to aggregate ingredients. The Anthropic API is used **only** for two optional enhancements (smarter ingredient merging, aisle categorization) and must **degrade gracefully** with no key (CLAUDE.md rule 8). Build the deterministic path first and completely; layer AI on top as optional.

## Goal
Pick a 7-day window, assign library recipes to days, and generate one consolidated, checkable, aisle-grouped grocery list of everything needed to cook.

## Build
1. **Schema** (spec §17) — add `meal_plan`, `meal_plan_entry`, `grocery_item`. Non-destructive migration. `meal_plan_entry` references either a `recipe_id` or a `place_id` (exactly one); a `place_id` entry is an eat-out day that contributes nothing to groceries. Include a per-entry `scale` factor.
2. **Planner board** — a start-date picker **defaulting to the upcoming Saturday** (but any start date allowed), and a 7-day board (Sat→Fri, or the chosen window). Per day: add recipe(s) through a picker that **reuses search/filters (§9)**; set an optional meal slot and a scale factor; reorder and remove. Optional: mark a day "eating out" and attach a Place (§14).
3. **"Add to meal plan"** quick action on the recipe view.
4. **Grocery list generation (deterministic core)** — spec §17:
   - Collect all ingredients from assigned recipes, each × its entry `scale` (normalized to the recipe's base servings).
   - **Normalize names** (lowercase, strip prep/size words, fold plurals) so "garlic cloves" + "minced garlic" → "garlic".
   - **Merge & sum** within a compatible unit family using the **existing scaling engine** (base-unit sum → kitchen-friendly snap). Incompatible units for the same name stay as separate, flagged lines.
   - **Quantity-less items** ("to taste", assembly items) listed once without a quantity.
   - **Categorize by aisle** via a built-in lookup; unknowns → "Other".
   - **Preserve state on regeneration:** keep `checked` and `manual` items (match on name+unit); refresh only recipe-derived quantities.
5. **Grocery list view** — grouped by aisle, each item checkable; add manual items; a "why" hint showing contributing recipes; **export/print** via the §14 image/PDF export plus a copy-as-text option.
6. **Optional AI enhancements** (only if `ANTHROPIC_API_KEY` present) — resolve tricky merges the normalizer misses, and categorize unknown items into aisles. Never required; the list must fully generate without a key.

## Out of scope — do NOT build
- **Pantry inventory + receipt-photo restocking** — that's the candidate **Chunk G** (spec §15, §17). Not here.
- Auto-suggesting *which* recipes to cook (future idea; this chunk is manual selection).
- HTTPS/auth/wake-lock (deferred, spec §12).

## Acceptance
- Create a plan starting any date (default = upcoming Saturday); assign multiple recipes across the 7 days, with scale factors; reorder/remove.
- Generate a grocery list that **correctly sums** repeated ingredients (e.g. garlic across recipes → "6 cloves"), snaps to kitchen-friendly units, groups by aisle, and lists quantity-less items.
- Check items off; add a manual item; **regenerate preserves** checks and manual items.
- Export/print the list.
- **Existing recipes/places are untouched.** With **no API key**, generation still works (AI merge/categorize simply skipped) — no crash.

## When done
Summarize what was built, how the grocery aggregation was tested (show the summed-garlic case), and how to run it. This completes Chunk E.
