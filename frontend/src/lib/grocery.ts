/**
 * Grocery-list aggregation (Chunk E) — the deterministic core.
 *
 * Collects ingredients from the recipes assigned to a meal plan, each scaled by its entry's
 * factor, then normalizes names, merges compatible units, and sums them in base units using
 * the SAME engine the app scales recipes with (renderVolume / renderWeight / formatOriginal —
 * base-unit sum → kitchen-friendly snap). Incompatible units for one name stay separate.
 * No AI here: this must fully work offline. (Optional AI aisle categorization layers on top.)
 */
import {
  formatOriginal,
  isMetricWeight,
  renderVolume,
  renderWeight,
  toBaseUnit,
  unitFamily,
  type Ingredient,
  type UnitFamily,
} from './scaling';

export interface PlanRecipe {
  title: string;
  scale: number;
  ingredients: Ingredient[];
}

export interface GroceryLine {
  name: string;
  unit: string | null;
  display: string | null; // null = quantity-less ("to taste", assembly)
  base: number | null; // summed base amount (tsp / g / count); null for quantity-less
  family: UnitFamily | 'none';
  aisle: string;
  recipes: string[]; // contributing recipe titles (the "why" hint)
}

// --------------------------------------------------------------------------- //
// Name normalization: "garlic cloves", "minced garlic", "Garlic (peeled)" → "garlic"
// --------------------------------------------------------------------------- //
// Prep / size / state adjectives that don't change what you buy.
const STOPWORDS = new Set([
  'fresh', 'freshly', 'chopped', 'minced', 'diced', 'sliced', 'shredded', 'grated', 'ground',
  'crushed', 'whole', 'large', 'small', 'medium', 'extra', 'ripe', 'boneless', 'skinless',
  'cooked', 'raw', 'peeled', 'halved', 'quartered', 'thinly', 'roughly', 'finely', 'packed',
  'softened', 'melted', 'cold', 'warm', 'hot', 'room', 'temperature', 'plus', 'optional',
  'divided', 'to', 'taste', 'for', 'garnish', 'of', 'a', 'the', 'about', 'approximately',
  'heaping', 'level', 'generous', 'good', 'quality', 'organic', 'low', 'reduced', 'fat',
]);

// Unit-like nouns embedded in a name ("2 cloves garlic" stored as name "garlic cloves").
const UNIT_NOUNS = new Set([
  'clove', 'cloves', 'sprig', 'sprigs', 'head', 'heads', 'can', 'cans', 'package', 'packages',
  'pkg', 'bunch', 'bunches', 'slice', 'slices', 'stick', 'sticks', 'stalk', 'stalks',
  'strip', 'strips', 'fillet', 'fillets', 'piece', 'pieces',
]);

function singularize(word: string): string {
  if (word.length <= 3) return word;
  if (word.endsWith('ies')) return word.slice(0, -3) + 'y'; // berries -> berry
  if (word.endsWith('oes')) return word.slice(0, -2); // tomatoes -> tomato, potatoes -> potato
  if (word.endsWith('ses') || word.endsWith('shes') || word.endsWith('ches')) return word.slice(0, -2);
  if (word.endsWith('s') && !word.endsWith('ss')) return word.slice(0, -1);
  return word;
}

export function normalizeName(raw: string): string {
  const cleaned = (raw || '')
    .toLowerCase()
    .replace(/\([^)]*\)/g, ' ') // drop parentheticals
    .replace(/[^a-z\s-]/g, ' ') // drop digits/punct
    .replace(/\s+/g, ' ')
    .trim();
  const kept = cleaned
    .split(' ')
    .map((w) => singularize(w))
    .filter((w) => w && !STOPWORDS.has(w) && !UNIT_NOUNS.has(singularize(w)) && !UNIT_NOUNS.has(w));
  const name = kept.join(' ').trim();
  return name || cleaned || (raw || '').toLowerCase().trim();
}

// --------------------------------------------------------------------------- //
// Aisle lookup (built-in; unknowns → "Other"). Keyword match on the normalized name.
// --------------------------------------------------------------------------- //
const AISLE_RULES: [string, string[]][] = [
  ['Produce', ['lettuce', 'spinach', 'kale', 'arugula', 'tomato', 'onion', 'garlic', 'ginger',
    'pepper', 'bell', 'carrot', 'celery', 'potato', 'cucumber', 'zucchini', 'squash', 'broccoli',
    'cauliflower', 'mushroom', 'avocado', 'lime', 'lemon', 'apple', 'banana', 'berry', 'cilantro',
    'parsley', 'basil', 'mint', 'scallion', 'shallot', 'cabbage', 'corn', 'lime', 'herb', 'greens']],
  ['Meat & Seafood', ['chicken', 'beef', 'steak', 'pork', 'bacon', 'sausage', 'turkey', 'lamb',
    'shrimp', 'salmon', 'fish', 'tuna', 'crab', 'ground', 'chorizo', 'prosciutto', 'ham']],
  ['Dairy & Eggs', ['milk', 'butter', 'cream', 'cheese', 'parmesan', 'cheddar', 'mozzarella',
    'feta', 'yogurt', 'egg', 'ricotta', 'sour']],
  ['Bakery', ['bread', 'tortilla', 'bun', 'roll', 'bagel', 'pita', 'baguette', 'naan']],
  ['Pantry', ['flour', 'sugar', 'rice', 'pasta', 'noodle', 'bean', 'lentil', 'chickpea', 'oat',
    'quinoa', 'stock', 'broth', 'tomato paste', 'canned', 'coconut milk', 'oil', 'olive oil',
    'vinegar', 'honey', 'syrup', 'peanut', 'nut', 'almond', 'cornstarch', 'yeast', 'baking']],
  ['Condiments', ['soy sauce', 'hoisin', 'sriracha', 'mustard', 'dijon', 'ketchup', 'mayo',
    'mayonnaise', 'salsa', 'sauce', 'dressing', 'worcestershire', 'fish sauce', 'tahini']],
  ['Spices', ['salt', 'pepper', 'cumin', 'paprika', 'cinnamon', 'oregano', 'thyme', 'chili',
    'cayenne', 'turmeric', 'coriander', 'nutmeg', 'clove', 'bay', 'spice', 'seasoning', 'vanilla']],
  ['Frozen', ['frozen', 'ice cream', 'peas']],
  ['Beverages', ['wine', 'beer', 'juice', 'soda', 'water', 'coffee', 'tea', 'broth']],
];

export function aisleFor(name: string): string {
  const n = ` ${name} `; // space-bounded so "corn" never matches "unicorn"
  for (const [aisle, keys] of AISLE_RULES) {
    for (const k of keys) {
      if (n.includes(` ${k} `)) return aisle;
    }
  }
  return 'Other';
}

// --------------------------------------------------------------------------- //
// Aggregation
// --------------------------------------------------------------------------- //
interface Acc {
  name: string;
  unit: string | null;
  family: UnitFamily;
  base: number;
  anyImperialWeight: boolean;
  recipes: Set<string>;
}

export function aggregateGroceries(recipes: PlanRecipe[]): GroceryLine[] {
  const measured = new Map<string, Acc>();
  const qtyless = new Map<string, { name: string; recipes: Set<string> }>();

  for (const r of recipes) {
    for (const ing of r.ingredients) {
      if (!ing.name || !ing.name.trim()) continue;
      const name = normalizeName(ing.name);

      // Quantity-less items ("to taste", assembly) → listed once, no amount.
      if (ing.quantity === null || ing.quantity === undefined) {
        const e = qtyless.get(name) || { name, recipes: new Set<string>() };
        e.recipes.add(r.title);
        qtyless.set(name, e);
        continue;
      }

      const scalable = ing.scalable === undefined ? 1 : ing.scalable;
      const qty = ing.quantity * (scalable ? r.scale : 1);
      const family = unitFamily(ing.unit);
      // Key by name + family (+ unit for counts, so cloves and heads don't merge).
      const key = family === 'count' ? `${name}|count|${(ing.unit || '').toLowerCase().trim()}` : `${name}|${family}`;

      const acc = measured.get(key) || {
        name,
        unit: ing.unit,
        family,
        base: 0,
        anyImperialWeight: false,
        recipes: new Set<string>(),
      };
      acc.base += toBaseUnit(qty, ing.unit);
      if (family === 'weight' && !isMetricWeight(ing.unit)) acc.anyImperialWeight = true;
      acc.recipes.add(r.title);
      measured.set(key, acc);
    }
  }

  const lines: GroceryLine[] = [];

  for (const acc of measured.values()) {
    let display: string;
    if (acc.family === 'volume') {
      display = renderVolume(acc.base);
    } else if (acc.family === 'weight') {
      display = renderWeight(acc.base, acc.anyImperialWeight ? 'oz' : 'g');
    } else {
      display = formatOriginal(acc.base, acc.unit); // counts: "6 cloves", "2 eggs", "3"
    }
    lines.push({
      name: acc.name,
      unit: acc.unit,
      display,
      base: acc.base,
      family: acc.family,
      aisle: aisleFor(acc.name),
      recipes: [...acc.recipes],
    });
  }

  for (const e of qtyless.values()) {
    // Skip if the same item already appears with a real quantity.
    if (lines.some((l) => l.name === e.name)) continue;
    lines.push({
      name: e.name,
      unit: null,
      display: null,
      base: null,
      family: 'none',
      aisle: aisleFor(e.name),
      recipes: [...e.recipes],
    });
  }

  // Stable, shopper-friendly order: by aisle, then name.
  lines.sort((a, b) => a.aisle.localeCompare(b.aisle) || a.name.localeCompare(b.name));
  return lines;
}
