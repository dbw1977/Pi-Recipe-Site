-- Add a `tags` column to the places full-text index so typing a tag name in the
-- Eat Out search box matches (recipes already index their tags — this brings places
-- to parity). FTS5 has no ALTER ADD COLUMN, so we drop and recreate the standalone
-- index, then backfill every existing place in one pass.

DROP TABLE IF EXISTS place_fts;

CREATE VIRTUAL TABLE place_fts USING fts5(
  name,
  city,
  cuisine,
  dishes,
  notes,
  tags,
  tokenize = 'unicode61'
);

-- Backfill from live data. cuisine stays the Cuisine-category tags (kept for its own
-- bm25 weight); `tags` is every tag across all categories so any of them is searchable.
INSERT INTO place_fts(rowid, name, city, cuisine, dishes, notes, tags)
SELECT
  p.id,
  COALESCE(p.name, ''),
  COALESCE(p.city, ''),
  COALESCE((
    SELECT group_concat(t.name, ' ')
    FROM tag t
    JOIN place_tag pt ON pt.tag_id = t.id
    JOIN tag_category c ON t.category_id = c.id
    WHERE pt.place_id = p.id AND c.name = 'Cuisine'
  ), ''),
  COALESCE((
    SELECT group_concat(TRIM(d.name || ' ' || COALESCE(d.note, '')), ' ')
    FROM place_dish d
    WHERE d.place_id = p.id
  ), ''),
  COALESCE(p.our_notes, ''),
  COALESCE((
    SELECT group_concat(t.name, ' ')
    FROM tag t
    JOIN place_tag pt ON pt.tag_id = t.id
    WHERE pt.place_id = p.id
  ), '')
FROM place p;
