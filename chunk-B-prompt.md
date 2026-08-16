# Chunk B — Imports  (Build Prompt 2 of 4)

**Before you start, read `recipe-app-spec.md` and `CLAUDE.md`.**

## Where this fits
This is **Chunk B of 4**. **Chunk A is already built and working** (manual recipe app + scaling engine + FTS search). Build on it — **do not rebuild or refactor it without reason.** Chunk C (polish + backups) and Chunk D (places) are separate, later prompts — **do not build them.**

## Prereqs the user sets up (these gate parts of B)
Make each configurable via `.env` and **fail gracefully with a clear message if missing** — never crash, never fake success:
- **Anthropic API key** (spec §10) → `ANTHROPIC_API_KEY`. Default model `claude-haiku-4-5-20251001`; fall back to `claude-sonnet-5` for low-confidence/messy extractions.
- **Google OAuth credentials** for Drive (spec §5c) → client secret + stored token.
- **whisper.cpp** locally (on the Pi or offloaded to Tedlasso) → configurable binary + model path.

## Goal
Recipes flow in from **four sources**, each landing as a **draft** in the review / Drafts queue before publish. All four share one extraction → review → publish pipeline.

## Build — the four ingestion paths (spec §5)
1. **URL import** — `recipe-scrapers`; fall back to Claude structuring for unsupported sites. Parse ingredient strings into structured rows `{quantity, unit, name, note, scalable}`. **Download the hero image locally.** Test target: the Plays Well With Butter marinade (spec §13 note).
2. **Screenshot import** — Claude **vision** (spec §10): returns title, source handle, ingredient groups, structured ingredients, steps (if any), **equipment inference (mark inferred items)**, and suggested tags **from the controlled list only**. Store the screenshot + optional video/extra photos as `media` on the NAS. Test target: the steak-salad fixture (spec §13).
3. **Voice import** — whisper.cpp transcription (local) → Claude structuring → draft. Attach audio + any photos as media.
4. **Google Drive import** — OAuth; point at a folder ID; **manual "Scan" button** (no polling); per-file extraction; track processed file IDs so re-scans skip them; **exclude the backup folder**. Files become a batch of drafts.

## Review / Drafts queue (spec §6)
- **Editable review screen:** every field, ingredient rows, equipment (inferred items visibly flagged), steps, tags (from the controlled list), and a **scaled preview** (2x/3x) to sanity-check.
- **Drafts queue** with per-row **Approve / Edit / Discard** + **Approve-all**, so a bulk load of ~100 doesn't become a one-at-a-time wall. Drafts persist across sessions.
- **Duplicate flag** at import — match on source URL or fuzzy title — shown in the queue (spec §15).
- **Claude JSON contract:** prompt for JSON-only output matching the draft schema; retry once on parse failure, then drop whatever parsed into the review screen for the user to finish. Send the allowed tag list into the tagging prompt.

## Out of scope — do NOT build
- Recipe of the Week, thumbnail generation, backups → Chunk C.
- Places / eating-out → Chunk D.

## Acceptance (user tests before Chunk C)
- Each of the four paths turns a real input into a correct, reviewable, publishable draft.
- The steak-salad screenshot and the PWWB URL both import cleanly and match the fixture / structured expectations.
- **Bulk:** importing several at once fills the Drafts queue; **Approve-all** publishes them; duplicates are flagged.
- Missing credentials disable only the affected path, with a clear message — nothing crashes.

## When done
Summarize: what was built, the `.env` keys required, how to set up Google OAuth and whisper.cpp, and how to test each of the four paths. Then **stop** for user testing.
