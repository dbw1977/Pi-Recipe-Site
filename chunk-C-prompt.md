# Chunk C — Polish + Backups  (Build Prompt 3 of 4)

**Before you start, read `recipe-app-spec.md` and `CLAUDE.md`.**

## Where this fits
This is **Chunk C of 4**. **Chunks A and B are built and working** (manual app + scaling + search; all four import paths + Drafts queue). Chunk D (places) is a separate, later prompt — **do not build it.**

## Goal
Make the app pleasant to live with, and make the data genuinely safe.

## Build
1. **Recipe of the Week** (spec §9)
   - Deterministic weekly pick keyed to the ISO week (stable all week, identical for both users, computed on load — no cron).
   - Use `featured_history` to avoid repeating recent picks until the library cycles.
   - Manual **"Feature this"** pin on any recipe that overrides the auto-pick until the next week.
   - Show it as a hero card pinned at the top of the home page.
2. **Thumbnails** — generate and serve small derived images for the grid. Store **derived thumbnails on local disk**; originals stay on the NAS. Keep generation light on the Pi 4.
3. **NAS media mount** — media root configurable to the OMV/NAS mount; DB stores **relative** paths; verify originals resolve through the mount.
4. **Backups** (spec §11)
   - Consistent snapshot via `VACUUM INTO` (never copy a live DB).
   - **Nightly local snapshot** to the NAS, keep ~7 days — independent of Drive.
   - **Weekly Google Drive backup** (reuse Chunk B's Drive OAuth): **overwrite the same file** in a **dedicated backup folder**, separate from the import folder so the Drive scanner never touches it. Rely on Drive's native version history for rollback.
   - Record `last_backup_at` + status; surface it in a small **settings/status** view (warn if the last backup is >10 days old).
   - Provide a documented **restore procedure** + script.
   - Schedule via **systemd timer or cron** (document the setup).

## Out of scope — do NOT build
- Places / eating-out → Chunk D.
- No HTTPS, auth, or wake-lock (deferred, spec §12).
- Off-site *media* sync (spec §11 optional, later) — DB backup only this chunk.

## Acceptance (user tests before Chunk D)
- Recipe of the Week displays, rotates by week, and respects a manual pin.
- Grid uses thumbnails; originals load from the NAS mount.
- Running the backup script produces a consistent DB copy locally on the NAS **and** in Drive (same file overwritten); status shows in the UI.
- A **test restore** from both a local snapshot and the Drive copy reproduces the library, with media paths still resolving.

## When done
Summarize: what was built, the backup schedule setup (systemd/cron), and the exact restore steps. Then **stop** for user testing (including one real test restore).
