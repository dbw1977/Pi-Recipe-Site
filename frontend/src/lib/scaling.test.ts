import { describe, it, expect } from 'vitest';
import { scaleQuantity, renderVolume, formatOriginal, Ingredient } from './scaling';

const disp = (ing: Partial<Ingredient>, factor: number) =>
  scaleQuantity({ name: 'x', quantity: null, unit: null, scalable: 1, ...ing }, factor).display;

describe('spec §7 worked dressing at 3x', () => {
  it('olive oil ¼ cup ×3 → ¾ cup (clean)', () => {
    expect(disp({ quantity: 0.25, unit: 'cup' }, 3)).toBe('¾ cup');
  });
  it('apple cider vinegar 1 tbsp ×3 → 3 tbsp', () => {
    expect(disp({ quantity: 1, unit: 'tbsp' }, 3)).toBe('3 tbsp');
  });
  it('dijon 2 tbsp ×3 → ¼ cup + 2 tbsp (sum of parts)', () => {
    expect(disp({ quantity: 2, unit: 'tbsp' }, 3)).toBe('¼ cup + 2 tbsp');
  });
  it('honey 1½ tbsp ×3 → ¼ cup + 1½ tsp (sum of parts)', () => {
    expect(disp({ quantity: 1.5, unit: 'tbsp' }, 3)).toBe('¼ cup + 1½ tsp');
  });
  it('garlic 2 cloves ×3 → 6 cloves (whole count)', () => {
    expect(disp({ quantity: 2, unit: 'clove' }, 3)).toBe('6 cloves');
  });
  it('fresh dill 1 tbsp ×3 → 3 tbsp', () => {
    expect(disp({ quantity: 1, unit: 'tbsp' }, 3)).toBe('3 tbsp');
  });
  it('fresh chives 1 tbsp ×3 → 3 tbsp', () => {
    expect(disp({ quantity: 1, unit: 'tbsp' }, 3)).toBe('3 tbsp');
  });
  it('salt & pepper (scalable=0) → unchanged', () => {
    expect(disp({ quantity: null, unit: null, name: 'salt and pepper', scalable: 0 }, 3)).toBe(null);
  });
});

describe('dressing at 2x', () => {
  it('olive oil ¼ cup ×2 → ½ cup', () => {
    expect(disp({ quantity: 0.25, unit: 'cup' }, 2)).toBe('½ cup');
  });
  it('dijon 2 tbsp ×2 → ¼ cup', () => {
    expect(disp({ quantity: 2, unit: 'tbsp' }, 2)).toBe('¼ cup');
  });
  it('honey 1½ tbsp ×2 → 3 tbsp', () => {
    expect(disp({ quantity: 1.5, unit: 'tbsp' }, 2)).toBe('3 tbsp');
  });
  it('acv 1 tbsp ×2 → 2 tbsp', () => {
    expect(disp({ quantity: 1, unit: 'tbsp' }, 2)).toBe('2 tbsp');
  });
  it('garlic 2 cloves ×2 → 4 cloves', () => {
    expect(disp({ quantity: 2, unit: 'clove' }, 2)).toBe('4 cloves');
  });
});

describe('ladder promotion & snapping', () => {
  it('¼ cup ×3 → ¾ cup', () => {
    expect(renderVolume(12 * 3)).toBe('¾ cup');
  });
  it('⅓ cup ×2 → ⅔ cup', () => {
    expect(renderVolume(16 * 2)).toBe('⅔ cup');
  });
  it('½ cup renders as a single term', () => {
    expect(renderVolume(24)).toBe('½ cup');
  });
  it('1 cup', () => {
    expect(renderVolume(48)).toBe('1 cup');
  });
  it('1¼ cups (plural)', () => {
    expect(renderVolume(60)).toBe('1¼ cups');
  });
  it('6 tsp renders as 2 tbsp, never ⅛ cup', () => {
    expect(renderVolume(6)).toBe('2 tbsp');
  });
  it('3 tbsp stays 3 tbsp (not a cup fraction)', () => {
    expect(renderVolume(9)).toBe('3 tbsp');
  });
  it('never renders a disallowed fraction (⅜ cup as 18 tsp)', () => {
    const out = renderVolume(18);
    expect(out).toBe('¼ cup + 2 tbsp');
    expect(out).not.toMatch(/[⅜⅝⅞]/);
  });
  it('1 tbsp + 1 tsp for 4 tsp', () => {
    expect(renderVolume(4)).toBe('1 tbsp + 1 tsp');
  });
});

describe('count rounding (spec §7.5)', () => {
  it('eggs stay whole when scaled cleanly', () => {
    expect(disp({ quantity: 1, unit: 'egg' }, 3)).toBe('3 eggs');
  });
  it('eggs with no unit render just the number', () => {
    expect(disp({ quantity: 2, unit: null, name: 'eggs' }, 2)).toBe('4');
  });
  it('a fractional count rounds to whole and flags it', () => {
    const r = scaleQuantity({ name: 'egg', quantity: 3, unit: 'egg', scalable: 1 }, 1.5);
    expect(r.display).toBe('5 eggs'); // 4.5 → 5
    expect(r.rounded).toBe(true);
  });
});

describe('non-scaling & 1x behaviour', () => {
  it('no-quantity assembly item is null', () => {
    expect(disp({ quantity: null, unit: null, name: 'sliced steak', scalable: 0 }, 3)).toBe(null);
  });
  it('scalable=0 with a quantity is shown unchanged even at 3x', () => {
    expect(disp({ quantity: 1, unit: 'tsp', scalable: 0 }, 3)).toBe('1 tsp');
  });
  it('1x shows the original, prettified', () => {
    expect(disp({ quantity: 1.5, unit: 'tbsp' }, 1)).toBe('1½ tbsp');
    expect(disp({ quantity: 0.25, unit: 'cup' }, 1)).toBe('¼ cup');
  });
  it('formatOriginal prettifies fractions', () => {
    expect(formatOriginal(0.5, 'cup')).toBe('½ cup');
    expect(formatOriginal(2, 'clove')).toBe('2 cloves');
    expect(formatOriginal(3, 'tbsp')).toBe('3 tbsp');
  });
});

describe('weight scaling', () => {
  it('grams stay metric', () => {
    expect(disp({ quantity: 100, unit: 'g' }, 2)).toBe('200 g');
  });
  it('ounces promote to pounds past 16 oz', () => {
    expect(disp({ quantity: 8, unit: 'oz' }, 3)).toBe('1.5 lb');
  });
});
