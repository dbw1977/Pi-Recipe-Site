-- 006_ai_variations.sql
-- Chunk F: AI recipe variations. Additive & non-destructive — three nullable columns on
-- recipe to record lineage. source_type gains the value 'ai' (no schema change for that).

ALTER TABLE recipe ADD COLUMN generated INTEGER DEFAULT 0;              -- 1 = AI-generated
ALTER TABLE recipe ADD COLUMN derived_from_recipe_id INTEGER REFERENCES recipe(id);
ALTER TABLE recipe ADD COLUMN generation_prompt TEXT;                  -- the instruction used
