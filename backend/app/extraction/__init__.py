"""Import/extraction pipelines (Chunk B).

All four ingestion paths (URL, screenshot, voice, Drive) converge on the same normalized
draft (`ExtractedRecipe`), which becomes a `recipe` row with status='draft' for review.
Nothing here auto-publishes (CLAUDE.md rule 10)."""
