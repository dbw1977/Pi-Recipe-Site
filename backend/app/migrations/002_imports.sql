-- 002_imports.sql (Chunk B)
-- Non-destructive: adds only new tables/indexes; existing recipe data is untouched.

-- Track Google Drive files already imported, so re-scans skip them (spec §5c).
CREATE TABLE IF NOT EXISTS drive_processed (
  file_id      TEXT PRIMARY KEY,
  recipe_id    INTEGER REFERENCES recipe(id) ON DELETE SET NULL,
  name         TEXT,
  processed_at TEXT
);

-- Drafts are just recipes with status='draft'; index it so the Drafts queue is fast.
CREATE INDEX IF NOT EXISTS idx_recipe_status ON recipe(status);
