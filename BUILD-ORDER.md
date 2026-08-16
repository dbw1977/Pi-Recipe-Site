# Build Order — how to use these prompts with Claude Code

This package hands the food app to Claude Code in **four chunks**. Feed **one prompt at a time**, test, then move to the next. It's chunked (not one giant prompt) on purpose: you want to test between stages, the scaling engine needs isolated verification before anything stacks on it, and Chunk B is gated by credentials only you can set up.

## Files (keep all in the repo root)
- `recipe-app-spec.md` — the full design and source of truth.
- `CLAUDE.md` — always-on guardrails; **Claude Code reads this automatically every session.**
- `chunk-A-prompt.md` … `chunk-D-prompt.md` — paste one at a time into Claude Code.

## The order
```
A  Working manual app (CRUD + scaling engine + search)   → TEST
B  Imports (URL · screenshot · voice · Google Drive)      → TEST
C  Polish + backups (Recipe of the Week, thumbnails, backup/restore) → TEST
D  Eating Out / Places (optional, additive)               → done
```
Each chunk's prompt tells Claude Code exactly where it sits, what already exists, and what **not** to build yet.

## Do this between chunks
- **After A:** run the scaling tests (`vitest`), enter the steak-salad fixture by hand, and confirm 2x/3x looks right on your phone. Don't move on until the scaling is correct — everything trusts it.
- **Before / with B (set these up yourself):**
  - Create an **Anthropic API key** and add a little billing credit → put it in `.env`.
  - Set up **Google Cloud OAuth** credentials for Drive access.
  - Install **whisper.cpp** (on the Pi, or on Tedlasso if you want it faster) and note the binary + model path.
  - Never commit `.env`.
- **After C:** do one **real test restore** from a backup — a backup you've never restored is only a hope.
- **D is optional** and can come any time after A.

## How to run a chunk
1. Make sure `recipe-app-spec.md` and `CLAUDE.md` are in the repo root.
2. Paste that chunk's prompt into Claude Code and let it build.
3. Work through the **Acceptance** list at the bottom of the prompt.
4. Only move to the next chunk once it passes.

## Reminder of the deferred items (not in any chunk)
Screen wake-lock (needs HTTPS), any login/auth, background Drive auto-sync, and Google Places autocomplete. These are conscious "laters," documented in spec §12 and §15.
