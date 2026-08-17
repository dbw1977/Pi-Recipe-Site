import { describe, expect, it } from 'vitest';
import { aggregateGroceries, aisleFor, normalizeName, PlanRecipe } from './grocery';

describe('normalizeName', () => {
  it('folds prep words, unit-nouns, and plurals to a base name', () => {
    expect(normalizeName('minced garlic')).toBe('garlic');
    expect(normalizeName('3 Garlic Cloves')).toBe('garlic');
    expect(normalizeName('garlic cloves')).toBe('garlic');
    expect(normalizeName('fresh cilantro (chopped)')).toBe('cilantro');
    expect(normalizeName('boneless skinless chicken thighs')).toBe('chicken thigh');
    expect(normalizeName('Ripe Tomatoes')).toBe('tomato');
  });
});

describe('aggregateGroceries', () => {
  it('sums the same count ingredient across recipes (the garlic case)', () => {
    const recipes: PlanRecipe[] = [
      { title: 'Stir Fry', scale: 1, ingredients: [{ quantity: 3, unit: 'clove', name: 'garlic' }] },
      { title: 'Marinade', scale: 1, ingredients: [{ quantity: 3, unit: 'clove', name: 'garlic cloves' }] },
    ];
    const lines = aggregateGroceries(recipes);
    const garlic = lines.find((l) => l.name === 'garlic')!;
    expect(garlic.display).toBe('6 cloves');
    expect(garlic.aisle).toBe('Produce');
    expect(garlic.recipes.sort()).toEqual(['Marinade', 'Stir Fry']);
  });

  it('scales counts by the entry factor before summing', () => {
    const recipes: PlanRecipe[] = [
      { title: 'A', scale: 2, ingredients: [{ quantity: 2, unit: 'clove', name: 'garlic' }] }, // 4
      { title: 'B', scale: 1, ingredients: [{ quantity: 2, unit: 'clove', name: 'garlic' }] }, // 2
    ];
    expect(aggregateGroceries(recipes).find((l) => l.name === 'garlic')!.display).toBe('6 cloves');
  });

  it('merges compatible volumes and snaps to kitchen-friendly units', () => {
    const recipes: PlanRecipe[] = [
      { title: 'A', scale: 1, ingredients: [{ quantity: 0.25, unit: 'cup', name: 'olive oil' }] }, // 12 tsp
      { title: 'B', scale: 1, ingredients: [{ quantity: 2, unit: 'tbsp', name: 'olive oil' }] }, // 6 tsp
    ];
    // 18 tsp -> "¼ cup + 2 tbsp"
    expect(aggregateGroceries(recipes).find((l) => l.name === 'olive oil')!.display).toBe('¼ cup + 2 tbsp');
  });

  it('sums weights and promotes oz → lb', () => {
    const recipes: PlanRecipe[] = [
      { title: 'A', scale: 1, ingredients: [{ quantity: 10, unit: 'oz', name: 'ground beef' }] },
      { title: 'B', scale: 1, ingredients: [{ quantity: 8, unit: 'oz', name: 'ground beef' }] },
    ];
    // 18 oz -> 1.13 lb
    const line = aggregateGroceries(recipes).find((l) => l.name === 'beef')!;
    expect(line.display).toMatch(/lb$/);
  });

  it('keeps incompatible units for the same name as separate lines', () => {
    const recipes: PlanRecipe[] = [
      { title: 'A', scale: 1, ingredients: [{ quantity: 2, unit: 'clove', name: 'garlic' }] },
      { title: 'B', scale: 1, ingredients: [{ quantity: 30, unit: 'g', name: 'garlic' }] },
    ];
    const garlic = aggregateGroceries(recipes).filter((l) => l.name === 'garlic');
    expect(garlic.length).toBe(2); // cloves and grams don't merge
  });

  it('lists quantity-less items once, without an amount', () => {
    const recipes: PlanRecipe[] = [
      { title: 'A', scale: 1, ingredients: [{ quantity: null, unit: null, name: 'salt', note: 'to taste' }] },
      { title: 'B', scale: 1, ingredients: [{ quantity: null, unit: null, name: 'salt' }] },
    ];
    const salt = aggregateGroceries(recipes).filter((l) => l.name === 'salt');
    expect(salt.length).toBe(1);
    expect(salt[0].display).toBeNull();
  });

  it('routes common items to sensible aisles', () => {
    expect(aisleFor('chicken thigh')).toBe('Meat & Seafood');
    expect(aisleFor('cheddar')).toBe('Dairy & Eggs');
    expect(aisleFor('quinoa')).toBe('Pantry');
    expect(aisleFor('unicorn dust')).toBe('Other');
  });
});
