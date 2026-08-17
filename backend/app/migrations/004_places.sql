-- 004_places.sql
-- Chunk D: the "Eat Out / Places" collection (spec §14).
-- ADDITIVE and NON-DESTRUCTIVE: no recipe table is dropped or rewritten. The only change
-- to an existing table is MEDIA gaining a nullable place_id, so a photo/screenshot can
-- attach to a place as well as a recipe (exactly one of recipe_id / place_id is set).

-- Where to eat + what to order there.
CREATE TABLE IF NOT EXISTS place (
  id            INTEGER PRIMARY KEY,
  name          TEXT NOT NULL,
  place_type    TEXT,                          -- 'restaurant' | 'takeout' | 'cafe' | 'bar' | ...
  city          TEXT,                          -- also mirrored as a City/Area tag for filtering
  address       TEXT,
  maps_url      TEXT,                          -- pasted Google Maps link
  maps_place_id TEXT,                          -- optional; only if Places API is added later
  phone         TEXT,
  website       TEXT,
  price_level   INTEGER,                       -- 1–4 ($–$$$$)
  our_rating    INTEGER,                       -- optional 1–5
  our_notes     TEXT,                          -- why we like it
  source_name   TEXT,                          -- who recommended it (friend, IG account, ...)
  source_url    TEXT,
  hero_image    TEXT,                          -- relative media path
  visited       INTEGER DEFAULT 1,             -- 1 = been there; 0 = want to try
  status        TEXT DEFAULT 'published',      -- reuses the draft/review flow (spec §6)
  created_at    TEXT,
  updated_at    TEXT
);

-- The "foods to order out" — the eat-out parallel to a recipe's ingredients.
CREATE TABLE IF NOT EXISTS place_dish (
  id         INTEGER PRIMARY KEY,
  place_id   INTEGER REFERENCES place(id) ON DELETE CASCADE,
  name       TEXT NOT NULL,                    -- 'birria tacos'
  note       TEXT,                             -- 'get it with the extra consommé'
  must_order INTEGER DEFAULT 0,
  sort_order INTEGER
);

-- Places reuse the shared tag vocabulary (Cuisine especially).
CREATE TABLE IF NOT EXISTS place_tag (
  place_id INTEGER REFERENCES place(id) ON DELETE CASCADE,
  tag_id   INTEGER REFERENCES tag(id),
  PRIMARY KEY (place_id, tag_id)
);

-- Media reuse: attach photos/screenshots to a place too. Nullable, cascades on delete.
ALTER TABLE media ADD COLUMN place_id INTEGER REFERENCES place(id) ON DELETE CASCADE;

-- Which collection a tag dimension belongs to, so recipe filters and place filters stay
-- separate while Cuisine is shared: 'recipe' | 'place' | 'both'. Existing rows default to
-- 'recipe'; seed_taxonomy corrects Cuisine → 'both' and the new place dimensions → 'place'.
ALTER TABLE tag_category ADD COLUMN collection TEXT DEFAULT 'recipe';

-- Full-text search for places (parallel to recipe_fts): name + city + cuisine + dishes + notes.
CREATE VIRTUAL TABLE IF NOT EXISTS place_fts USING fts5(
  name,
  city,
  cuisine,
  dishes,
  notes,
  tokenize = 'unicode61'
);

CREATE INDEX IF NOT EXISTS idx_place_dish_place ON place_dish(place_id);
CREATE INDEX IF NOT EXISTS idx_place_tag_place  ON place_tag(place_id);
CREATE INDEX IF NOT EXISTS idx_place_tag_tag    ON place_tag(tag_id);
CREATE INDEX IF NOT EXISTS idx_media_place      ON media(place_id);
CREATE INDEX IF NOT EXISTS idx_place_city       ON place(city);
