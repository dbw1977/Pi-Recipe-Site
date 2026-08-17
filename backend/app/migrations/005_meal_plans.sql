-- 005_meal_plans.sql
-- Chunk E: weekly meal planner + generated grocery list. Additive & non-destructive.
-- A plan holds 7 days of entries; each entry points at EITHER a recipe (contributes to the
-- grocery list) OR a place (an eat-out day that contributes nothing). Grocery items persist
-- their checked/manual state so regeneration can refresh quantities without losing it.

CREATE TABLE IF NOT EXISTS meal_plan (
  id         INTEGER PRIMARY KEY,
  start_date TEXT NOT NULL,             -- ISO date of day 0 (defaults to upcoming Saturday in UI)
  title      TEXT,
  created_at TEXT,
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS meal_plan_entry (
  id         INTEGER PRIMARY KEY,
  plan_id    INTEGER REFERENCES meal_plan(id) ON DELETE CASCADE,
  day_index  INTEGER NOT NULL DEFAULT 0,   -- 0..6 within the window
  meal_slot  TEXT,                          -- optional: 'breakfast'|'lunch'|'dinner'|'snack'
  recipe_id  INTEGER REFERENCES recipe(id) ON DELETE CASCADE,
  place_id   INTEGER REFERENCES place(id) ON DELETE CASCADE,
  scale      REAL NOT NULL DEFAULT 1,       -- per-entry multiplier on the recipe's base servings
  sort_order INTEGER,
  -- exactly one of recipe_id / place_id is set
  CHECK ((recipe_id IS NULL) <> (place_id IS NULL))
);

CREATE TABLE IF NOT EXISTS grocery_item (
  id         INTEGER PRIMARY KEY,
  plan_id    INTEGER REFERENCES meal_plan(id) ON DELETE CASCADE,
  name       TEXT NOT NULL,        -- normalized display name ('garlic', 'olive oil')
  unit       TEXT,                 -- representative unit token (nullable for pure counts)
  display    TEXT,                 -- kitchen-friendly quantity string ('6 cloves', '¼ cup + 2 tbsp')
  base       REAL,                 -- summed amount in the family's base unit (tsp / g / count)
  family     TEXT,                 -- 'volume'|'weight'|'count'|'none'
  aisle      TEXT DEFAULT 'Other',
  checked    INTEGER DEFAULT 0,
  manual     INTEGER DEFAULT 0,    -- 1 = user-added, preserved across regeneration
  recipes    TEXT,                 -- contributing recipe titles (comma-separated), for the "why" hint
  sort_order INTEGER
);

CREATE INDEX IF NOT EXISTS idx_mpe_plan     ON meal_plan_entry(plan_id);
CREATE INDEX IF NOT EXISTS idx_grocery_plan ON grocery_item(plan_id);
