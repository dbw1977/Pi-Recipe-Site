# Chunk F — AI Recipe Builder + UI Clean-Up + Photo Upload  (Build Prompt 6)

**Before you start, read `recipe-app-spec.md` §18 and §9 ("Navigation & density"), plus `CLAUDE.md`.**

> **Final session:** Chunks E and F are the last two. They can be built **back-to-back in one session** — build **Chunk E first**, verify it, then this one. Keep them as separate, independently-tested steps.

## Where this fits
This is **Chunk F**. **Chunks A–E are built and working.** It ships **three things together as one update**:
- **Part 1 — AI recipe variations** (additive; reuses Chunk B's Anthropic integration + the review/Drafts pipeline).
- **Part 2 — a focused UI clean-up** (a *refactor* of existing screens): tighten density + add a persistent home link.
- **Part 3 — direct photo upload** (upload/take a hero photo from your device).

> **This chunk edits existing UI.** Part 2 touches screens built in A/D/E. Treat it as a careful polish pass: **preserve all existing behavior and routes**, change layout/hierarchy only. **Check the real codebase** — component names, router, existing action buttons, the media/thumbnail code — and reuse what's there.

---

## PART 1 — AI Recipe Builder / Variations (spec §18)

**Is this AI?** Yes — the most AI-native feature in the app. It *generates* a recipe, so use a **stronger model**: default **`claude-sonnet-5`** (optionally Opus for complex transforms). Gated by `ANTHROPIC_API_KEY`; **degrade gracefully** with no key (CLAUDE.md rule 8).

**Goal:** from a **saved recipe** + a **natural-language instruction** ("make me a patty melt version"), generate a **realistic, structured variation**, **saved as a draft**.

**Build**
1. **Schema (non-destructive)** — add to `recipe`: `generated INTEGER DEFAULT 0`, `derived_from_recipe_id INTEGER REFERENCES recipe(id)`, `generation_prompt TEXT`; extend `source_type` with `'ai'`.
2. **Generation endpoint** — prompt = a recipe-developer **system prompt** + the **full structured source recipe** + the instruction + the **strict draft JSON schema** (identical to imports) + constraints (realistic & coherent; structured ingredients; **kitchen-friendly quantities §7**; tags from the **controlled list §8**; equipment inferred-flagged; keep servings unless asked). **JSON only.** Call **`claude-sonnet-5`**; retry once on parse failure.
3. **Save as a draft immediately** — persist the result with `status='draft'`, `generated=1`, `derived_from_recipe_id`, `generation_prompt`, `source_type='ai'` **before showing it**, so it appears in the **Drafts queue (§6)** and is never lost if the user navigates away; then open it in the **review screen**. **Never auto-publish.**
4. **Iterate / refine** — from a generated draft, another instruction ("make it cheesier") re-runs the flow with the current draft as source.
5. **Attribution rule** — **never** credit the original human creator for an AI variation. Store lineage only; the new recipe's author is the app/AI. Mark generated recipes **AI-generated · untested — review before cooking**, with an **"AI variation of [source]"** badge linking to the original.

---

## PART 2 — UI Clean-Up (spec §9 "Navigation & density")

**Goal:** clean, tight, content-first UI with a persistent way home. A polish pass over existing screens; behavior unchanged.

**Build**
1. **Persistent header on every page** — app name/logo on the left that **links to the home/library** (the requested "return to homepage" link), the **Cook ⇄ Eat Out** toggle, and a search affordance. **Sticky and compact on mobile; quiet** (recedes, doesn't compete with content). One shared header component used everywhere.
2. **Consolidate recipe-view actions into a single "⋮" overflow menu** — Edit, Add to meal plan, **Create AI variation**, **Add/take photo**, Share/Export, Delete. **Keep only the 1x/2x/3x scale toggle inline.** The page should read as *the recipe*, not a wall of buttons.
3. **Consistency pass** — one spacing scale, restrained typography (stop bolding everything), one button system (primary / secondary / ghost), and the **same detail-page + overflow pattern** across recipe, place, planner, and review screens. Content-first.
4. **Don't break anything** — every existing action still works, just relocated; all routes/deep links intact.

---

## PART 3 — Direct Photo Upload (spec §18 "Direct photo upload")

**Goal:** set a recipe's hero image (or add gallery photos) from your **own device** — camera or photo library — for dishes you cook yourself. **No schema change** (reuses `media` + `hero_image`).

**Build**
1. **Uploader** — on the recipe edit/review screen and in the recipe-view **⋮ menu**, an **"Add / take photo"** action using a standard file input with `accept="image/*"` and `capture="environment"`, so phones offer **camera or library**. Works over plain LAN HTTP (no `getUserMedia`/HTTPS).
2. **Store & process** — save the original to the **local media store** (originals on the NAS mount), **fix EXIF orientation**, **downscale** oversized images, and **generate a thumbnail** (reuse the Chunk C pipeline). Set it as the **hero** or add to the **gallery**.
3. Reuse the same uploader for **places** (dish photos) if trivial — optional.

---

## Out of scope — do NOT build
- Pantry inventory + receipt restocking — candidate **Chunk G** (spec §15, §17).
- Unprompted/automatic variation suggestions — user-initiated only.
- A full visual redesign or new design language — this is tightening, not reinventing.
- HTTPS/auth/wake-lock (deferred, spec §12).

## Acceptance
**Part 1 — AI variations**
- On the saved **Bacon Jam Burgers** recipe, *"make me a patty melt version"* returns a **realistic structured draft** (e.g. griddled rye, Swiss, caramelized onion, sandwich assembly) that is **saved to the Drafts queue immediately** and opened in the review screen — **not auto-published**, and still there if you navigate away and come back.
- The result is marked **AI-generated + untested**, links to its source as lineage, and the **original creator is not credited as author**.
- Quantities realistic + **kitchen-friendly**; tags from the **controlled list**; equipment inferred-flagged.
- *"Make it cheesier"* **iterates** into a refined draft.
- **No API key → cleanly disabled** (clear message, no crash); existing recipes untouched.

**Part 2 — UI**
- Every page shows the **persistent header**; tapping the logo/name **returns to the homepage** from anywhere (recipe, place, planner, review).
- The recipe view shows **only the scale toggle inline**; Edit / Add to plan / Create AI variation / Add photo / Share / Delete live in the **⋮ menu**, and **all still work**.
- The recipe view feels **noticeably less crowded**; spacing/typography/buttons are consistent across screens; the mobile header is **sticky and compact**.

**Part 3 — Photo upload**
- From a phone, **take or choose a photo** and set it as a recipe's **hero**; it displays **right-side-up** (EXIF fixed), loads fast (downscaled + thumbnail), and persists.
- Uploaded originals land in the **local media store** (NAS), not hot-linked.

## When done
Summarize what was built/changed across all three parts, the model used (**Sonnet 5**) and rough per-variation cost, and confirm no existing behavior regressed. This completes Chunk F — and, with Chunk E, the planned feature set.
