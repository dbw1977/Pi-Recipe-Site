-- 001_initial.sql
-- Chunk A schema: recipe-side tables only (spec §4).
-- The place* tables (spec §14) are intentionally deferred to Chunk D.
-- Migrations are applied idempotently at startup; keep this non-destructive.

-- A recipe
CREATE TABLE IF NOT EXISTS recipe (
  id            INTEGER PRIMARY KEY,
  title         TEXT NOT NULL,
  description   TEXT,                          -- short, optional; NOT the blog story
  source_type   TEXT,                          -- 'url' | 'instagram' | 'drive' | 'voice' | 'manual'
  source_name   TEXT,                          -- e.g. 'chacekitchen', 'playswellwithbutter.com'
  source_url    TEXT,                          -- original link if any
  source_handle TEXT,                          -- e.g. '@chacekitchen'
  hero_image    TEXT,                          -- relative media path
  servings_base INTEGER,                       -- base yield the quantities correspond to
  servings_unit TEXT,                          -- 'servings' | 'salads' | 'cups' etc.
  total_time    INTEGER,                        -- minutes, optional
  created_at    TEXT,
  updated_at    TEXT,
  status        TEXT DEFAULT 'published'       -- 'draft' (in review) | 'published'
);

-- Ingredient groups (e.g. "For the salad", "Honey dijon dressing")
CREATE TABLE IF NOT EXISTS ingredient_group (
  id         INTEGER PRIMARY KEY,
  recipe_id  INTEGER REFERENCES recipe(id) ON DELETE CASCADE,
  name       TEXT,                             -- nullable = default/ungrouped
  sort_order INTEGER
);

-- Structured ingredients (never store as free text)
CREATE TABLE IF NOT EXISTS ingredient (
  id          INTEGER PRIMARY KEY,
  group_id    INTEGER REFERENCES ingredient_group(id) ON DELETE CASCADE,
  quantity    REAL,                            -- nullable (e.g. "to taste")
  unit        TEXT,                            -- canonical unit: 'tsp','tbsp','cup','g','oz','clove', ...
  name        TEXT NOT NULL,                   -- 'olive oil'
  note        TEXT,                            -- 'minced', 'to taste', 'I used habanero cheddar'
  scalable    INTEGER DEFAULT 1,               -- 0 = never scale (e.g. "salt to taste")
  sort_order  INTEGER
);

-- Steps
CREATE TABLE IF NOT EXISTS step (
  id         INTEGER PRIMARY KEY,
  recipe_id  INTEGER REFERENCES recipe(id) ON DELETE CASCADE,
  text       TEXT NOT NULL,
  sort_order INTEGER
);

-- Tag taxonomy: a tag belongs to a dimension (category)
CREATE TABLE IF NOT EXISTS tag_category (   -- 'Course','Cuisine','Protein','Dietary','Method','Time','Occasion'
  id   INTEGER PRIMARY KEY,
  name TEXT UNIQUE
);
CREATE TABLE IF NOT EXISTS tag (
  id          INTEGER PRIMARY KEY,
  category_id INTEGER REFERENCES tag_category(id),
  name        TEXT,
  UNIQUE(category_id, name)
);
CREATE TABLE IF NOT EXISTS recipe_tag (
  recipe_id INTEGER REFERENCES recipe(id) ON DELETE CASCADE,
  tag_id    INTEGER REFERENCES tag(id),
  PRIMARY KEY (recipe_id, tag_id)
);

-- Media attached to a recipe (originals live on NAS; store relative path)
CREATE TABLE IF NOT EXISTS media (
  id         INTEGER PRIMARY KEY,
  recipe_id  INTEGER REFERENCES recipe(id) ON DELETE CASCADE,
  kind       TEXT,                             -- 'image' | 'audio' | 'video'
  path       TEXT,                             -- relative to media root
  caption    TEXT
);

-- Required cooking utensils / equipment (grill, whisk, mixing bowl, sheet pan, ...)
CREATE TABLE IF NOT EXISTS equipment (
  id         INTEGER PRIMARY KEY,
  recipe_id  INTEGER REFERENCES recipe(id) ON DELETE CASCADE,
  name       TEXT NOT NULL,
  inferred   INTEGER DEFAULT 0,                -- 1 = AI-inferred from the steps (used in Chunk B)
  sort_order INTEGER
);

-- Full-text search index (SQLite FTS5). One row per recipe (rowid = recipe.id),
-- kept in sync from title + description + source + ingredient names + tags.
--
-- NOTE ON DESIGN: the spec sketches a `content=''` (contentless) FTS table. We use a
-- plain (self-contained) FTS5 table instead: it stores its own copy of the searchable
-- text, so sync is a robust DELETE-by-rowid + INSERT on every save. A contentless table
-- would require replaying the *previous* column values to delete a row, which is easy to
-- get wrong. The disk cost is negligible for a two-person library, and the external
-- behavior (fast local search, always in sync) is identical.
CREATE VIRTUAL TABLE IF NOT EXISTS recipe_fts USING fts5(
  title,
  description,
  source,
  ingredients,
  tags,
  tokenize = 'unicode61'
);

-- Recipe of the Week (§9): history of auto/manual picks (populated in Chunk C).
CREATE TABLE IF NOT EXISTS featured_history (
  id         INTEGER PRIMARY KEY,
  recipe_id  INTEGER REFERENCES recipe(id) ON DELETE CASCADE,
  iso_week   TEXT,                             -- e.g. '2026-W33'
  pinned     INTEGER DEFAULT 0                 -- 1 = manually pinned, 0 = auto-selected
);

-- Helpful indexes for the joins the app makes constantly.
CREATE INDEX IF NOT EXISTS idx_group_recipe      ON ingredient_group(recipe_id);
CREATE INDEX IF NOT EXISTS idx_ingredient_group  ON ingredient(group_id);
CREATE INDEX IF NOT EXISTS idx_step_recipe        ON step(recipe_id);
CREATE INDEX IF NOT EXISTS idx_equipment_recipe   ON equipment(recipe_id);
CREATE INDEX IF NOT EXISTS idx_recipe_tag_recipe  ON recipe_tag(recipe_id);
CREATE INDEX IF NOT EXISTS idx_recipe_tag_tag     ON recipe_tag(tag_id);
CREATE INDEX IF NOT EXISTS idx_media_recipe       ON media(recipe_id);
