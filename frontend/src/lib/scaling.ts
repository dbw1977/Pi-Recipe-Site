/**
 * Kitchen-friendly scaling engine (spec §7, CLAUDE.md rule 6).
 *
 * Scaled amounts must be measurable on common kitchen equipment: no 0.7 tsp, no ⅜ cup.
 * Only the fractions {⅛, ¼, ⅓, ½, ⅔, ¾} may ever be rendered. When a scaled value lands
 * between ladder rungs it is expressed as a SUM of measurable parts (e.g. "¼ cup + 2 tbsp"),
 * choosing the fewest measuring operations. Count items (eggs, cloves) round to whole.
 *
 * This module is pure and framework-free so it can be unit-tested in isolation (Vitest).
 */

export interface Ingredient {
  quantity: number | null;
  unit: string | null;
  name: string;
  note?: string | null;
  scalable?: number; // 1 = scale (default), 0 = never scale
}

export interface ScaledQuantity {
  /** The quantity+unit string, e.g. "¾ cup", "6 cloves". `null` for no-quantity items. */
  display: string | null;
  /** True when a count item had to be rounded by a meaningful amount (spec §7.5). */
  rounded?: boolean;
}

const EPS = 1e-6;

// --------------------------------------------------------------------------- //
// Unit families
// --------------------------------------------------------------------------- //
// Volume → teaspoons (the base unit). 1 tbsp = 3 tsp, 1 cup = 48 tsp, 1 fl oz = 6 tsp.
const VOLUME_TO_TSP: Record<string, number> = {
  tsp: 1, teaspoon: 1, teaspoons: 1,
  tbsp: 3, tbs: 3, tablespoon: 3, tablespoons: 3,
  cup: 48, cups: 48,
  'fl oz': 6, 'fluid ounce': 6, 'fluid ounces': 6,
  pint: 96, pints: 96, quart: 192, quarts: 192,
};

// Weight → grams. 1 oz = 28.35 g, 1 lb = 453.6 g.
const WEIGHT_TO_G: Record<string, number> = {
  g: 1, gram: 1, grams: 1, gm: 1,
  kg: 1000, kilogram: 1000, kilograms: 1000,
  oz: 28.35, ounce: 28.35, ounces: 28.35,
  lb: 453.6, lbs: 453.6, pound: 453.6, pounds: 453.6,
};

const CUP = 48;
const TBSP = 3;

// Allowed display fractions. ⅛ is deliberately NOT used for cups (it renders as 2 tbsp).
const ALLOWED_FRACTIONS: [number, string][] = [
  [1 / 8, '⅛'], [1 / 4, '¼'], [1 / 3, '⅓'], [1 / 2, '½'], [2 / 3, '⅔'], [3 / 4, '¾'],
];
const CUP_SINGLE_FRACTIONS: [number, string][] = [
  [1 / 4, '¼'], [1 / 3, '⅓'], [1 / 2, '½'], [2 / 3, '⅔'], [3 / 4, '¾'],
];

// Unit abbreviations that never pluralize ("3 tbsp", not "3 tbsps"). Word units do ("cups").
const INVARIABLE_UNITS = new Set(['tsp', 'tbsp', 'oz', 'lb', 'lbs', 'g', 'kg', 'ml', 'l', 'fl oz']);

// --------------------------------------------------------------------------- //
// Number / fraction formatting
// --------------------------------------------------------------------------- //
function matchFractionExact(frac: number): string | null {
  if (Math.abs(frac) < EPS) return '';
  for (const [val, str] of ALLOWED_FRACTIONS) {
    if (Math.abs(frac - val) < EPS) return str;
  }
  return null;
}

/** Nearest allowed fraction with a loose tolerance (for formatting stored/original values). */
function matchFractionLoose(frac: number): string | null {
  if (Math.abs(frac) < 0.02) return '';
  let best: string | null = null;
  let bestDelta = 0.05; // only snap if reasonably close
  for (const [val, str] of ALLOWED_FRACTIONS) {
    const d = Math.abs(frac - val);
    if (d < bestDelta) {
      bestDelta = d;
      best = str;
    }
  }
  return best;
}

function trimDecimal(value: number): string {
  return parseFloat(value.toFixed(2)).toString();
}

/** Format an already-snapped value using unicode fractions (e.g. 1.5 → "1½"). */
function formatSnapped(value: number): string {
  const whole = Math.floor(value + EPS);
  const fracStr = matchFractionExact(value - whole);
  if (fracStr === null) return trimDecimal(value); // safety net; shouldn't happen post-snap
  if (fracStr === '') return String(whole);
  return whole > 0 ? `${whole}${fracStr}` : fracStr;
}

/** Format an arbitrary (unscaled/original) value, snapping loosely to nice fractions. */
function formatLoose(value: number): string {
  const whole = Math.floor(value + EPS);
  const fracStr = matchFractionLoose(value - whole);
  if (fracStr === null) return trimDecimal(value);
  if (fracStr === '') return String(whole);
  return whole > 0 ? `${whole}${fracStr}` : fracStr;
}

function unitLabel(unit: string, numeric: number): string {
  const u = unit.toLowerCase();
  if (INVARIABLE_UNITS.has(u)) return unit;
  // Kitchen convention: fractions of one stay singular ("¼ cup"), plural only above 1.
  if (numeric <= 1 + EPS) return unit;
  return unit.endsWith('s') ? unit : `${unit}s`;
}

// --------------------------------------------------------------------------- //
// Volume rendering (the heart of the snapping logic)
// --------------------------------------------------------------------------- //
function cupLabel(numeric: number): string {
  return numeric > 1 + EPS ? 'cups' : 'cup';
}

/** If `cups` is exactly a clean single cup value (≥ ¼ cup), render it as one term. */
function tryExactCup(cups: number): string | null {
  if (cups < 0.25 - EPS) return null;
  const whole = Math.floor(cups + EPS);
  const frac = cups - whole;
  if (Math.abs(frac) < EPS) {
    return `${whole} ${cupLabel(cups)}`;
  }
  for (const [val, str] of CUP_SINGLE_FRACTIONS) {
    if (Math.abs(frac - val) < EPS) {
      const num = whole > 0 ? `${whole}${str}` : str;
      return `${num} ${cupLabel(cups)}`;
    }
  }
  return null;
}

/** Render N quarter-cups (integer) as "1¼ cups", "¾ cup", etc. */
function renderQuarterCups(quarters: number): string {
  const whole = Math.floor(quarters / 4);
  const q = quarters % 4;
  const fracStr = ['', '¼', '½', '¾'][q];
  const numeric = quarters / 4;
  const num = whole > 0 ? `${whole}${fracStr}` : fracStr;
  return `${num} ${cupLabel(numeric)}`;
}

/**
 * Snap a sub-tablespoon teaspoon remainder (0 ≤ rem < 3) to the nearest allowed value so
 * we only ever print kitchen fractions. Candidates are whole + {⅛,¼,⅓,½,⅔,¾}.
 */
function snapTspRemainder(rem: number): number {
  let best = 0;
  let bestDelta = Infinity;
  for (let whole = 0; whole <= 3; whole++) {
    for (const [frac] of [[0], ...ALLOWED_FRACTIONS] as [number, string?][]) {
      const cand = whole + frac;
      const d = Math.abs(rem - cand);
      if (d < bestDelta) {
        bestDelta = d;
        best = cand;
      }
    }
  }
  return best;
}

/** Render a positive volume given as total teaspoons, kitchen-friendly. */
export function renderVolume(totalTsp: number): string {
  if (totalTsp < EPS) return '0';

  // 1) A clean single cup value wins (e.g. ¾ cup, ⅓ cup, 1¼ cups).
  const exact = tryExactCup(totalTsp / CUP);
  if (exact) return exact;

  // 2) Otherwise decompose into ¼-cups + whole tbsp + tsp remainder — the fewest ops.
  //    Using ¼-cup granularity (each = 4 tbsp) keeps the tbsp remainder whole, which is
  //    why dijon 18 tsp → "¼ cup + 2 tbsp" rather than "⅓ cup + 2 tsp".
  const parts: string[] = [];
  let rem = totalTsp;

  const quarterCups = Math.floor(rem / (CUP / 4) + EPS); // CUP/4 = 12 tsp
  if (quarterCups >= 1) {
    rem -= quarterCups * (CUP / 4);
    parts.push(renderQuarterCups(quarterCups));
  }

  const wholeTbsp = Math.floor(rem / TBSP + EPS);
  if (wholeTbsp >= 1) {
    rem -= wholeTbsp * TBSP;
    parts.push(`${wholeTbsp} tbsp`);
  }

  const tsp = snapTspRemainder(rem);
  if (tsp > EPS) {
    parts.push(`${formatSnapped(tsp)} tsp`);
  }

  return parts.length ? parts.join(' + ') : '0';
}

// --------------------------------------------------------------------------- //
// Weight & count rendering
// --------------------------------------------------------------------------- //
function renderWeight(grams: number, originalUnit: string): string {
  const metric = ['g', 'gram', 'grams', 'gm', 'kg', 'kilogram', 'kilograms'].includes(originalUnit);
  if (metric) {
    if (grams >= 1000 - EPS) return `${trimDecimal(grams / 1000)} kg`;
    return `${Math.round(grams)} g`;
  }
  // Imperial: promote oz → lb at 16 oz.
  const oz = grams / 28.35;
  if (oz >= 16 - EPS) return `${trimDecimal(oz / 16)} lb`;
  return `${trimDecimal(oz)} oz`;
}

function renderCount(quantity: number, unit: string | null, factor: number): ScaledQuantity {
  const raw = quantity * factor;
  const rounded = Math.round(raw);
  const significant = Math.abs(raw - rounded) > EPS;
  if (!unit) return { display: String(rounded), rounded: significant };
  return { display: `${rounded} ${unitLabel(unit, rounded)}`, rounded: significant };
}

// --------------------------------------------------------------------------- //
// Public entry points
// --------------------------------------------------------------------------- //
/** Format an original (1x) or non-scalable quantity as stored, prettifying fractions. */
export function formatOriginal(quantity: number, unit: string | null): string {
  const num = formatLoose(quantity);
  if (!unit) return num;
  return `${num} ${unitLabel(unit, quantity)}`;
}

/**
 * Scale one ingredient by `factor` and return its display string.
 * - no quantity           → assembly item, never scaled (display: null)
 * - scalable = 0          → shown unchanged
 * - factor = 1            → original, prettified (no surprising re-expression)
 * - volume / weight / count → scaled and snapped to kitchen-friendly output
 */
export function scaleQuantity(ing: Ingredient, factor: number): ScaledQuantity {
  const scalable = ing.scalable === undefined ? 1 : ing.scalable;

  if (ing.quantity === null || ing.quantity === undefined) {
    return { display: null };
  }
  if (!scalable || Math.abs(factor - 1) < EPS) {
    return { display: formatOriginal(ing.quantity, ing.unit) };
  }

  const unit = (ing.unit || '').toLowerCase().trim();

  if (unit in VOLUME_TO_TSP) {
    const tsp = ing.quantity * VOLUME_TO_TSP[unit] * factor;
    return { display: renderVolume(tsp) };
  }
  if (unit in WEIGHT_TO_G) {
    const grams = ing.quantity * WEIGHT_TO_G[unit] * factor;
    return { display: renderWeight(grams, unit) };
  }
  // Everything else (clove, slice, egg, whole, can, or no unit) is a count → round whole.
  return renderCount(ing.quantity, ing.unit, factor);
}
