import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api, FeaturedResponse, MealPlanCard, Recipe } from '../api';
import { scaleQuantity } from '../lib/scaling';
import { dayLabel, rangeLabel, upcomingSaturday } from '../lib/dates';
import { mediaUrl } from './Library';
import OverflowMenu from '../components/OverflowMenu';

const FACTORS = [1, 2, 3];

export default function RecipeView() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [recipe, setRecipe] = useState<Recipe | null>(null);
  const [factor, setFactor] = useState(1);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [notesOpen, setNotesOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [featured, setFeatured] = useState<FeaturedResponse | null>(null);
  const [aiAvailable, setAiAvailable] = useState(false);
  const [panel, setPanel] = useState<'plan' | 'variation' | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const photoRef = useRef<HTMLInputElement>(null);

  const reload = () => api.getRecipe(Number(id)).then(setRecipe).catch((e) => setError(e.message));

  useEffect(() => {
    if (!id) return;
    reload();
    api.getFeatured().then(setFeatured).catch(() => setFeatured(null));
    api.importStatus().then((s) => setAiAvailable(!!s.claude)).catch(() => setAiAvailable(false));
  }, [id]);

  const onPhoto = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !recipe) return;
    setNotice('Uploading photo…');
    try {
      const { path } = await api.uploadPhoto(file);
      await api.setRecipeHero(recipe.id, path);
      await reload();
      setNotice('Photo set.');
    } catch (er) {
      setNotice((er as Error).message);
    } finally {
      if (photoRef.current) photoRef.current.value = '';
    }
  };

  // The browser's "Save as PDF" uses document.title as the default filename,
  // so name the tab after the recipe while it's open, then restore on leave.
  useEffect(() => {
    if (!recipe) return;
    const prev = document.title;
    document.title = recipe.title;
    return () => {
      document.title = prev;
    };
  }, [recipe]);

  const isPinned =
    !!recipe && featured?.pinned === true && featured?.recipe?.id === recipe.id;

  const toggleFeature = async () => {
    if (!recipe) return;
    const next = isPinned ? await api.unpinFeatured() : await api.pinFeatured(recipe.id);
    setFeatured(next);
  };

  const noteItems = useMemo(
    () =>
      recipe
        ? recipe.groups
            .flatMap((g) => g.ingredients)
            .filter((i) => i.note && i.note.trim() && i.note.trim().toLowerCase() !== 'to taste')
            .map((i) => ({ name: i.name, note: i.note as string }))
        : [],
    [recipe],
  );

  if (error) return <p className="py-16 text-center text-muted">{error}</p>;
  if (!recipe) return <p className="py-16 text-center text-muted">Loading…</p>;

  const toggleCheck = (key: string) =>
    setChecked((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });

  const onDelete = async () => {
    if (!confirm(`Delete “${recipe.title}”? This cannot be undone.`)) return;
    await api.deleteRecipe(recipe.id);
    navigate('/');
  };

  // Middle ground: a generated/imported draft is cookable right here; "Save to library"
  // publishes it into the grid only when it's a keeper.
  const saveToLibrary = async () => {
    await api.approveDraft(recipe.id);
    await reload();
    setNotice('Saved to your library.');
  };

  return (
    <article>
      {/* Hero */}
      <div className="card mb-4 overflow-hidden">
        <div className="no-print aspect-[16/10] w-full bg-[#e9ddcb]">
          {recipe.hero_image ? (
            <img
              src={mediaUrl(recipe.hero_image)}
              alt={recipe.title}
              className="h-full w-full object-cover"
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center text-5xl opacity-40">
              🍽️
            </div>
          )}
        </div>
        <div className="p-4">
          <h1 className="font-display text-2xl font-semibold leading-tight">{recipe.title}</h1>
          {recipe.generated ? (
            <div className="no-print mt-2 rounded-lg bg-ember/8 px-3 py-2 text-sm text-emberDark ring-1 ring-ember/15">
              ✨ <strong>AI variation</strong>
              {recipe.derived_from_title ? (
                <>
                  {' '}of{' '}
                  <Link to={`/recipe/${recipe.derived_from_recipe_id}`} className="underline">
                    {recipe.derived_from_title}
                  </Link>
                </>
              ) : null}
              {' '}· untested — review before cooking.
            </div>
          ) : null}
          <SourceLine recipe={recipe} />
          {recipe.description && (
            <p className="mt-2 text-[15px] text-bark/80">{recipe.description}</p>
          )}
          <div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-muted">
            {recipe.servings_base ? (
              <span>
                Makes {recipe.servings_base} {recipe.servings_unit || 'servings'}
                {factor > 1 ? ` · scaled ×${factor} → ${recipe.servings_base * factor}` : ''}
              </span>
            ) : null}
            {recipe.total_time ? <span>· {recipe.total_time} min</span> : null}
          </div>
          {recipe.tags.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {recipe.tags.map((t) => (
                <span key={t.id} className="chip bg-cream !text-[13px]">
                  {t.name}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Draft "middle ground": cook from it here; save to the library only when it's a keeper */}
      {recipe.status === 'draft' && (
        <div className="no-print mb-4 rounded-xl bg-herb/10 p-3 ring-1 ring-herb/20">
          <p className="text-sm text-herb">
            <strong>{recipe.generated ? 'AI draft' : 'Draft'} — not in your library yet.</strong>{' '}
            Cook from it right here. Save it when it's a keeper, or discard it.
          </p>
          <div className="mt-2 flex gap-2">
            <button onClick={saveToLibrary} className="btn-primary flex-1 !py-2 text-sm">
              ✓ Save to library
            </button>
            <button onClick={onDelete} className="btn-ghost !py-2 text-sm !text-ember">
              Discard
            </button>
          </div>
        </div>
      )}

      {/* Actions — AI variation is promoted to a prominent button; the rest live in a
          scrollable ⋮ menu rendered OUTSIDE the clipped hero card so every item is reachable. */}
      <div className="no-print mb-4 flex items-center gap-2">
        {aiAvailable && (
          <button
            onClick={() => setPanel(panel === 'variation' ? null : 'variation')}
            className="btn-primary flex-1"
          >
            ✨ Create AI variation
          </button>
        )}
        <div className="ml-auto">
          <OverflowMenu
            items={[
              { label: '✎ Edit', onClick: () => navigate(`/recipe/${recipe.id}/edit`) },
              { label: '📅 Add to meal plan', onClick: () => setPanel(panel === 'plan' ? null : 'plan') },
              { label: '📷 Add / take photo', onClick: () => photoRef.current?.click() },
              { label: isPinned ? '★ Unpin from Recipe of the Week' : '☆ Feature as Recipe of the Week', onClick: toggleFeature },
              { label: '⤓ Save as PDF', onClick: () => window.print() },
              { label: '🗑 Delete', onClick: onDelete, danger: true },
            ]}
          />
        </div>
      </div>
      <input ref={photoRef} type="file" accept="image/*" capture="environment" className="hidden" onChange={onPhoto} />
      {notice && <div className="no-print mb-3 text-sm text-herb">{notice}</div>}
      {panel === 'plan' && <div className="no-print mb-4"><AddToPlan recipeId={recipe.id} /></div>}
      {panel === 'variation' && <div className="no-print mb-4"><AiVariation recipe={recipe} onClose={() => setPanel(null)} /></div>}

      {/* Scale toggle — sticky so it's reachable while scrolling ingredients */}
      <div className="no-print sticky top-[60px] z-[5] mb-4">
        <div className="card flex items-center justify-between p-2">
          <span className="pl-2 text-sm font-medium text-muted">Scale</span>
          <div className="flex gap-1 rounded-xl bg-cream p-1">
            {FACTORS.map((f) => (
              <button
                key={f}
                onClick={() => setFactor(f)}
                className={`min-w-[56px] rounded-lg px-4 py-2 text-base font-semibold transition ${
                  factor === f ? 'bg-ember text-white shadow-sm' : 'text-bark'
                }`}
                aria-pressed={factor === f}
              >
                {f}×
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Ingredients */}
      <section className="card mb-4 p-4">
        <h2 className="mb-3 text-lg font-semibold">Ingredients</h2>
        <div className="space-y-4">
          {recipe.groups.map((group, gi) => (
            <div key={group.id ?? gi}>
              {group.name && (
                <div className="mb-1.5 text-sm font-semibold uppercase tracking-wide text-herb">
                  {group.name}
                </div>
              )}
              <ul className="space-y-1">
                {group.ingredients.map((ing, ii) => {
                  const key = `${gi}-${ii}`;
                  const scaled = scaleQuantity(ing, factor);
                  const isChecked = checked.has(key);
                  return (
                    <li key={ing.id ?? ii}>
                      <label className="flex cursor-pointer items-start gap-3 rounded-lg px-1 py-1.5 active:bg-cream">
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={() => toggleCheck(key)}
                          className="mt-1 h-5 w-5 shrink-0 accent-ember"
                        />
                        <span
                          className={`text-[15px] leading-snug ${
                            isChecked ? 'text-muted line-through' : ''
                          }`}
                        >
                          {scaled.display && (
                            <span className="font-semibold">{scaled.display} </span>
                          )}
                          {ing.name}
                          {ing.note && ing.note.trim() ? (
                            <span className="text-muted"> — {ing.note}</span>
                          ) : null}
                          {scaled.rounded && (
                            <span className="ml-1 text-xs text-ember">(rounded)</span>
                          )}
                        </span>
                      </label>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
      </section>

      {/* Equipment */}
      {recipe.equipment.length > 0 && (
        <section className="card mb-4 p-4">
          <h2 className="mb-3 text-lg font-semibold">Equipment</h2>
          <ul className="flex flex-wrap gap-2">
            {recipe.equipment.map((eq, i) => (
              <li key={eq.id ?? i} className="chip bg-cream">
                {eq.name}
                {eq.inferred ? <span className="ml-1 text-xs text-muted">·guessed</span> : null}
              </li>
            ))}
          </ul>
          {factor > 1 && (
            <p className="mt-3 text-sm text-muted">
              Scaling ×{factor}: you may need a larger or extra vessel (bigger bowl, a second
              pan). Equipment itself isn’t scaled.
            </p>
          )}
        </section>
      )}

      {/* Steps */}
      <section className="card mb-4 p-4">
        <h2 className="mb-3 text-lg font-semibold">Steps</h2>
        {recipe.steps.length === 0 ? (
          <p className="text-muted">No steps recorded for this one.</p>
        ) : (
          <ol className="space-y-4">
            {recipe.steps.map((step, i) => (
              <li key={step.id ?? i} className="flex gap-3">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-ember/10 font-semibold text-ember">
                  {i + 1}
                </span>
                <p className="pt-1 text-[17px] leading-relaxed">{step.text}</p>
              </li>
            ))}
          </ol>
        )}
      </section>

      {/* Notes (collapsible) */}
      {noteItems.length > 0 && (
        <section className="card mb-4 p-4">
          <button
            onClick={() => setNotesOpen((o) => !o)}
            className="flex w-full items-center justify-between text-lg font-semibold"
          >
            Notes <span className="text-muted">{notesOpen ? '–' : '+'}</span>
          </button>
          {notesOpen && (
            <ul className="mt-3 space-y-1.5 text-[15px]">
              {noteItems.map((n, i) => (
                <li key={i}>
                  <span className="font-medium">{n.name}:</span>{' '}
                  <span className="text-bark/80">{n.note}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

    </article>
  );
}

// The AI-variation panel: an instruction box + quick presets. On success the generated
// draft is opened in the review screen (it's already saved to the Drafts queue).
const PRESETS: [string, string][] = [
  ['Vegetarian', 'make a vegetarian version'],
  ['Spicier', 'make it spicier'],
  ['Healthier', 'make it healthier / lighter'],
  ['Kid-friendly', 'make a kid-friendly version'],
  ['Air fryer', 'convert it for the air fryer'],
  ['For a crowd', 'scale it up for a crowd'],
];

function AiVariation({ recipe, onClose }: { recipe: Recipe; onClose: () => void }) {
  const navigate = useNavigate();
  const [instruction, setInstruction] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const go = async () => {
    const text = instruction.trim();
    if (!text) return;
    setBusy(true);
    setErr(null);
    try {
      const res = await api.createVariation(recipe.id, text);
      onClose();
      // Land in the cook view (a draft): cook from it now, save to library if it's a keeper.
      navigate(`/recipe/${res.draft.id}`);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-3 rounded-xl bg-ember/5 p-3 ring-1 ring-ember/15">
      <div className="mb-1 text-sm font-semibold text-emberDark">✨ Create an AI variation</div>
      <p className="mb-2 text-xs text-muted">
        Describe a change — you'll get an editable draft to review. It's AI-written and untested.
      </p>
      <div className="mb-2 flex flex-wrap gap-1.5">
        {PRESETS.map(([label, text]) => (
          <button
            key={label}
            onClick={() => setInstruction(text)}
            className="chip bg-white !py-1 !text-[12px] hover:ring-ember"
          >
            {label}
          </button>
        ))}
      </div>
      <textarea
        className="w-full rounded-lg border-0 bg-white px-3 py-2 text-[15px] shadow-sm ring-1 ring-black/10 focus:outline-none focus:ring-2 focus:ring-ember/40"
        rows={2}
        value={instruction}
        onChange={(e) => setInstruction(e.target.value)}
        placeholder="e.g. make me a patty melt version"
      />
      {err && <div className="mt-2 rounded-lg bg-ember/10 px-3 py-2 text-sm text-emberDark">{err}</div>}
      <div className="mt-2 flex gap-2">
        <button onClick={go} disabled={busy} className="btn-primary flex-1 !py-2 text-sm">
          {busy ? 'Generating…' : 'Generate variation'}
        </button>
        <button onClick={onClose} className="btn-ghost !py-2 text-sm">Cancel</button>
      </div>
    </div>
  );
}

function AddToPlan({ recipeId }: { recipeId: number }) {
  const [open, setOpen] = useState(true);
  const [plans, setPlans] = useState<MealPlanCard[]>([]);
  const [planId, setPlanId] = useState<string>('new');
  const [day, setDay] = useState(0);
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) api.listMealPlans().then((p) => { setPlans(p); if (p.length) setPlanId(String(p[0].id)); }).catch(() => setPlans([]));
  }, [open]);

  const start = planId === 'new' ? upcomingSaturday() : plans.find((p) => String(p.id) === planId)!.start_date;

  const add = async () => {
    setBusy(true);
    try {
      let pid: number;
      if (planId === 'new') pid = (await api.createMealPlan(upcomingSaturday())).id;
      else pid = Number(planId);
      await api.addPlanEntry(pid, { day_index: day, recipe_id: recipeId });
      const d = dayLabel(start, day);
      setDone(`Added to ${d.dow} ${d.date}.`);
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} className="btn-ghost mb-2 w-full">
        📅 Add to meal plan
      </button>
    );
  }

  return (
    <div className="mb-2 rounded-xl bg-white p-3 ring-1 ring-black/10">
      {done ? (
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm text-herb">{done}</span>
          <Link to="/plan" className="text-sm font-medium text-ember underline">Open planner →</Link>
        </div>
      ) : (
        <>
          <div className="mb-2 grid grid-cols-2 gap-2">
            <select value={planId} onChange={(e) => setPlanId(e.target.value)} className="rounded-lg bg-cream px-2 py-2 text-sm ring-1 ring-black/10">
              <option value="new">New week (this Sat)</option>
              {plans.map((p) => (
                <option key={p.id} value={p.id}>{p.title || rangeLabel(p.start_date)}</option>
              ))}
            </select>
            <select value={day} onChange={(e) => setDay(Number(e.target.value))} className="rounded-lg bg-cream px-2 py-2 text-sm ring-1 ring-black/10">
              {Array.from({ length: 7 }, (_, i) => {
                const d = dayLabel(start, i);
                return <option key={i} value={i}>{d.dow} {d.date}</option>;
              })}
            </select>
          </div>
          <div className="flex gap-2">
            <button onClick={add} disabled={busy} className="btn-primary flex-1 !py-2 text-sm">
              {busy ? 'Adding…' : 'Add'}
            </button>
            <button onClick={() => setOpen(false)} className="btn-ghost !py-2 text-sm">Cancel</button>
          </div>
        </>
      )}
    </div>
  );
}

function SourceLine({ recipe }: { recipe: Recipe }) {
  const label = recipe.source_handle || recipe.source_name;
  if (!label) return null;
  return (
    <p className="mt-1 text-sm text-muted">
      {recipe.source_url ? (
        <a
          href={recipe.source_url}
          target="_blank"
          rel="noreferrer"
          className="underline decoration-dotted"
        >
          {label}
        </a>
      ) : (
        label
      )}
    </p>
  );
}
