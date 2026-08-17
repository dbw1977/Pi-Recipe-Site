import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api, MealPlan, PlaceCard, PlanEntry, RecipeCard } from '../api';
import { dayLabel, rangeLabel } from '../lib/dates';

const SCALES = [0.5, 1, 1.5, 2, 3];

export default function PlanBoard() {
  const { id } = useParams();
  const planId = Number(id);
  const navigate = useNavigate();
  const [plan, setPlan] = useState<MealPlan | null>(null);
  const [pickerDay, setPickerDay] = useState<number | null>(null);

  const load = () => api.getMealPlan(planId).then(setPlan).catch(() => setPlan(null));
  useEffect(() => {
    load();
  }, [planId]);

  if (!plan) return <p className="py-16 text-center text-muted">Loading…</p>;

  const entriesFor = (day: number) => plan.entries.filter((e) => e.day_index === day);

  const addEntry = async (day: number, opts: { recipe_id?: number; place_id?: number }) => {
    await api.addPlanEntry(planId, { day_index: day, ...opts });
    setPickerDay(null);
    load();
  };
  const removeEntry = async (e: PlanEntry) => {
    await api.deletePlanEntry(planId, e.id);
    load();
  };
  const setScale = async (e: PlanEntry, scale: number) => {
    await api.updatePlanEntry(planId, e.id, { scale });
    load();
  };
  const deletePlan = async () => {
    if (!confirm('Delete this whole week plan?')) return;
    await api.deleteMealPlan(planId);
    navigate('/plan');
  };

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h1 className="font-display text-2xl font-semibold">
            {plan.title || 'This week'}
          </h1>
          <p className="text-sm text-muted">{rangeLabel(plan.start_date)}</p>
        </div>
        <Link to={`/plan/${planId}/grocery`} className="btn-primary !py-2 whitespace-nowrap">
          🛒 Grocery list
        </Link>
      </div>

      <div className="space-y-3">
        {Array.from({ length: 7 }, (_, day) => {
          const { dow, date } = dayLabel(plan.start_date, day);
          const entries = entriesFor(day);
          return (
            <section key={day} className="card p-3">
              <div className="mb-2 flex items-center justify-between">
                <div className="font-semibold">
                  {dow} <span className="text-sm font-normal text-muted">{date}</span>
                </div>
                <button onClick={() => setPickerDay(pickerDay === day ? null : day)} className="text-sm font-medium text-ember">
                  {pickerDay === day ? 'Close' : '+ Add'}
                </button>
              </div>

              {entries.length === 0 && pickerDay !== day && (
                <p className="text-sm text-muted">Nothing planned.</p>
              )}

              <div className="space-y-2">
                {entries.map((e) => (
                  <div key={e.id} className="flex items-center gap-2 rounded-lg bg-cream/60 p-2">
                    <span className="text-lg">{e.kind === 'place' ? '🍴' : '🍳'}</span>
                    <div className="min-w-0 flex-1">
                      <Link
                        to={e.kind === 'place' ? `/eat/place/${e.place_id}` : `/recipe/${e.recipe_id}`}
                        className="block truncate text-[15px] font-medium"
                      >
                        {e.title}
                      </Link>
                      {e.kind === 'place' && <div className="text-xs text-muted">Eating out</div>}
                    </div>
                    {e.kind === 'recipe' && (
                      <select
                        value={e.scale}
                        onChange={(ev) => setScale(e, Number(ev.target.value))}
                        className="rounded-lg bg-white px-2 py-1 text-sm shadow-sm ring-1 ring-black/10"
                        title="Scale"
                      >
                        {SCALES.map((s) => (
                          <option key={s} value={s}>{s}×</option>
                        ))}
                      </select>
                    )}
                    <button onClick={() => removeEntry(e)} className="px-1 text-muted" aria-label="Remove">✕</button>
                  </div>
                ))}
              </div>

              {pickerDay === day && <Picker onAddRecipe={(rid) => addEntry(day, { recipe_id: rid })} onAddPlace={(pid) => addEntry(day, { place_id: pid })} />}
            </section>
          );
        })}
      </div>

      <button onClick={deletePlan} className="btn-ghost w-full !text-ember">
        Delete this plan
      </button>
    </div>
  );
}

function Picker({ onAddRecipe, onAddPlace }: { onAddRecipe: (id: number) => void; onAddPlace: (id: number) => void }) {
  const [mode, setMode] = useState<'cook' | 'eat'>('cook');
  const [q, setQ] = useState('');
  const [recipes, setRecipes] = useState<RecipeCard[]>([]);
  const [places, setPlaces] = useState<PlaceCard[]>([]);

  useEffect(() => {
    const t = setTimeout(() => {
      if (mode === 'cook') api.listRecipes(q || undefined).then((r) => setRecipes(r.slice(0, 8))).catch(() => setRecipes([]));
      else api.listPlaces(q || undefined).then((p) => setPlaces(p.slice(0, 8))).catch(() => setPlaces([]));
    }, 200);
    return () => clearTimeout(t);
  }, [q, mode]);

  return (
    <div className="mt-2 rounded-lg bg-white p-2 ring-1 ring-black/10">
      <div className="mb-2 flex gap-1 rounded-lg bg-cream p-0.5">
        {(['cook', 'eat'] as const).map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={`flex-1 rounded-md px-2 py-1 text-sm font-semibold ${mode === m ? 'bg-ember text-white' : 'text-bark'}`}
          >
            {m === 'cook' ? '🍳 Cook' : '🍴 Eat out'}
          </button>
        ))}
      </div>
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder={mode === 'cook' ? 'Search recipes…' : 'Search places…'}
        className="mb-2 w-full rounded-lg bg-cream px-3 py-2 text-sm ring-1 ring-black/10 focus:outline-none focus:ring-2 focus:ring-ember/40"
        autoFocus
      />
      <div className="max-h-56 space-y-1 overflow-y-auto">
        {mode === 'cook'
          ? recipes.map((r) => (
              <button key={r.id} onClick={() => onAddRecipe(r.id)} className="block w-full truncate rounded-md px-2 py-1.5 text-left text-sm hover:bg-cream">
                {r.title}
              </button>
            ))
          : places.map((p) => (
              <button key={p.id} onClick={() => onAddPlace(p.id)} className="block w-full truncate rounded-md px-2 py-1.5 text-left text-sm hover:bg-cream">
                {p.name} {p.city ? <span className="text-muted">· {p.city}</span> : null}
              </button>
            ))}
        {mode === 'cook' && recipes.length === 0 && <p className="px-2 py-1 text-sm text-muted">No recipes found.</p>}
        {mode === 'eat' && places.length === 0 && <p className="px-2 py-1 text-sm text-muted">No places found.</p>}
      </div>
    </div>
  );
}
