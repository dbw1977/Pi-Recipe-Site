-- 003_backups.sql (Chunk C)
-- Non-destructive: adds a small log table so the UI can surface backup health.
-- (featured_history already exists from 001; Recipe of the Week uses it.)

CREATE TABLE IF NOT EXISTS backup_log (
  id          INTEGER PRIMARY KEY,
  kind        TEXT,    -- 'local' | 'drive'
  target      TEXT,    -- path or Drive file id
  ok          INTEGER, -- 1 success, 0 failure
  message     TEXT,
  size_bytes  INTEGER,
  created_at  TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_backup_log_kind ON backup_log(kind, created_at);
