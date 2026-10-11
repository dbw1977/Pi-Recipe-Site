-- 008_recipe_rating.sql
-- Our own 1-5 star rating for a recipe. Additive & non-destructive: one nullable column
-- (NULL = not rated yet), so every existing recipe is simply "unrated" afterwards.
-- Set through its own endpoint, so editing a recipe never overwrites it.

ALTER TABLE recipe ADD COLUMN rating INTEGER CHECK (rating IS NULL OR rating BETWEEN 1 AND 5);
