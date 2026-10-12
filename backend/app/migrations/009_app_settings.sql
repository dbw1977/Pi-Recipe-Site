-- 009_app_settings.sql
-- Admin-console settings as simple key/value rows (backup destination, schedule, ...).
-- Stored in the database on purpose: they travel inside every backup, so a restored
-- library comes back already configured. Additive; nothing existing is touched.

CREATE TABLE IF NOT EXISTS app_setting (
  key        TEXT PRIMARY KEY,
  value      TEXT,
  updated_at TEXT DEFAULT (datetime('now'))
);
