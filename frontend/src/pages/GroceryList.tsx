import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api, GroceryItem, GroceryLineInput, MealPlan } from '../api';
import { aggregateGroceries, PlanRecipe } from '../lib/grocery';
import { rangeLabel } from '../lib/dates';

const AISLE_ORDER = [
  'Produce', 'Meat & Seafood', 'Dairy & Eggs', 'Bakery', 'Pantry', 'Condiments',
  'Spices', 'Frozen', 'Beverages', 'Other',
];

export default function GroceryList() {
  const { id } = useParams();
  const planId = Number(id);
  const [plan, setPlan] = useState<MealPlan | null>(null);
  const [items, setItems] = useState<GroceryItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [manual, setManual] = useState('');

  useEffect(() => {
    api.getMealPlan(planId).then(setPlan).catch(() => setPlan(null));
    api.getGrocery(planId).then(setItems).catch(() => setItems([]));
  }, [planId]);

  useEffect(() => {
    const prev = document.title;
    if (plan) document.title = `Grocery — ${rangeLabel(plan.start_date)}`;
    return () => {
      document.title = prev;
    };
  }, [plan]);

  const generate = async () => {
    if (!plan) return;
    setBusy(true);
    setNote(null);
    try {
      // Pull the full recipe for every recipe entry, keeping its per-entry scale.
      const recipeEntries = plan.entries.filter((e) => e.kind === 'recipe' && e.recipe_id);
      const recipes = await Promise.all(
        recipeEntries.map(async (e) => {
          const r = await api.getRecipe(e.recipe_id!);
          return {
            title: r.title,
            scale: e.scale,
            ingredients: r.groups.flatMap((g) => g.ingredients),
          } as PlanRecipe;
        }),
      );
      const lines = aggregateGroceries(recipes);

      // Optional AI: tidy items the built-in lookup left in "Other". Skipped without a key.
      const unknown = lines.filter((l) => l.aisle === 'Other').map((l) => l.name);
      if (unknown.length) {
        try {
          const { aisles } = await api.categorizeAisles(unknown);
          for (const l of lines) if (aisles[l.name]) l.aisle = aisles[l.name];
        } catch {
          /* no key / offline — deterministic aisles stand */
        }
      }

      const payload: GroceryLineInput[] = lines.map((l) => ({
        name: l.name, unit: l.unit, display: l.display, base: l.base,
        family: l.family, aisle: l.aisle, recipes: l.recipes,
      }));
      setItems(await api.generateGrocery(planId, payload));
      if (recipes.length === 0) setNote('No recipes on this plan yet — add some on the board, then generate.');
    } finally {
      setBusy(false);
    }
  };

  const toggle = async (it: GroceryItem) => {
    setItems((prev) => prev.map((x) => (x.id === it.id ? { ...x, checked: x.checked ? 0 : 1 } : x)));
    await api.setGroceryChecked(planId, it.id, !it.checked).catch(() => {});
  };
  const addManual = async () => {
    if (!manual.trim()) return;
    const created = await api.addGroceryItem(planId, manual.trim());
    setItems((prev) => [...prev, created]);
    setManual('');
  };
  const remove = async (it: GroceryItem) => {
    setItems((prev) => prev.filter((x) => x.id !== it.id));
    await api.deleteGroceryItem(planId, it.id).catch(() => {});
  };

  const grouped = useMemo(() => {
    const by: Record<string, GroceryItem[]> = {};
    for (const it of items) (by[it.aisle] || (by[it.aisle] = [])).push(it);
    const order = [...AISLE_ORDER, ...Object.keys(by).filter((a) => !AISLE_ORDER.includes(a))];
    return order.filter((a) => by[a]?.length).map((a) => [a, by[a]] as const);
  }, [items]);

  const copyText = async () => {
    const lines: string[] = [];
    for (const [aisle, list] of grouped) {
      lines.push(`== ${aisle} ==`);
      for (const it of list) lines.push(`- ${it.display ? it.display + ' ' : ''}${it.name}`);
      lines.push('');
    }
    try {
      await navigator.clipboard.writeText(lines.join('\n').trim());
      setNote('Copied the list to your clipboard.');
    } catch {
      setNote('Could not copy automatically — select and copy manually.');
    }
  };

  if (!plan) return <p className="py-16 text-center text-muted">Loading…</p>;

  const remaining = items.filter((i) => !i.checked).length;

  return (
    <div className="space-y-4">
      <div className="no-print space-y-3">
        <div className="flex items-center justify-between gap-2">
          <div>
            <h1 className="font-display text-2xl font-semibold">Grocery list</h1>
            <Link to={`/plan/${planId}`} className="text-sm text-ember underline">← back to the week</Link>
          </div>
          <button onClick={generate} disabled={busy} className="btn-primary !py-2 whitespace-nowrap">
            {busy ? 'Building…' : items.length ? '↻ Regenerate' : 'Generate list'}
          </button>
        </div>
        <p className="text-sm text-muted">
          Sums everything across your planned recipes into kitchen-friendly amounts. Regenerating
          keeps your checkmarks and any items you added by hand.
        </p>
        {note && <div className="rounded-lg bg-herb/10 px-3 py-2 text-sm text-herb">{note}</div>}
        {items.length > 0 && (
          <div className="flex flex-wrap gap-2">
            <button onClick={copyText} className="btn-ghost !py-2 text-sm">📋 Copy as text</button>
            <button onClick={() => window.print()} className="btn-ghost !py-2 text-sm">⤓ Save as PDF</button>
            <span className="ml-auto self-center text-sm text-muted">{remaining} left</span>
          </div>
        )}
        <div className="flex gap-2">
          <input
            value={manual}
            onChange={(e) => setManual(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && addManual()}
            placeholder="Add an item (paper towels…)"
            className="w-full rounded-lg border-0 bg-white px-3 py-2.5 text-[15px] shadow-sm ring-1 ring-black/10 focus:outline-none focus:ring-2 focus:ring-ember/40"
          />
          <button onClick={addManual} className="btn-ghost">Add</button>
        </div>
      </div>

      {/* Printable heading */}
      <h2 className="hidden font-display text-2xl font-semibold print:block">
        Grocery list · {rangeLabel(plan.start_date)}
      </h2>

      {items.length === 0 ? (
        <div className="card p-10 text-center text-muted">
          <div className="text-4xl">🛒</div>
          <p className="mt-3">No list yet. Tap <b>Generate list</b> to build it from your week.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {grouped.map(([aisle, list]) => (
            <section key={aisle} className="card p-4">
              <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-herb">{aisle}</h3>
              <ul className="space-y-1">
                {list.map((it) => (
                  <li key={it.id}>
                    <label className="flex cursor-pointer items-start gap-3 rounded-lg px-1 py-1.5 active:bg-cream">
                      <input type="checkbox" checked={!!it.checked} onChange={() => toggle(it)} className="mt-1 h-5 w-5 shrink-0 accent-ember" />
                      <span className={`flex-1 text-[15px] leading-snug ${it.checked ? 'text-muted line-through' : ''}`}>
                        {it.display && <span className="font-semibold">{it.display} </span>}
                        {it.name}
                        {it.manual ? <span className="ml-1 text-xs text-muted">(added)</span> : null}
                        {it.recipes.length > 0 && (
                          <span className="no-print block text-xs text-muted">for {it.recipes.join(', ')}</span>
                        )}
                      </span>
                      <button onClick={(e) => { e.preventDefault(); remove(it); }} className="no-print px-1 text-muted" aria-label="Remove">✕</button>
                    </label>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
