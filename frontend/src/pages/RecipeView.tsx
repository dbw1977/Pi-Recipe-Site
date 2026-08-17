import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api, FeaturedResponse, Recipe } from '../api';
import { scaleQuantity } from '../lib/scaling';
import { mediaUrl } from './Library';

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

  useEffect(() => {
    if (!id) return;
    api.getRecipe(Number(id)).then(setRecipe).catch((e) => setError(e.message));
    api.getFeatured().then(setFeatured).catch(() => setFeatured(null));
  }, [id]);

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

      {/* Actions */}
      <div className="no-print">
        <button onClick={toggleFeature} className="btn-ghost mb-2 w-full">
          {isPinned ? '★ Unpin from Recipe of the Week' : '☆ Feature as Recipe of the Week'}
        </button>
        <button onClick={() => window.print()} className="btn-ghost mb-2 w-full">
          ⤓ Save as PDF
        </button>
        <div className="flex gap-2">
          <Link to={`/recipe/${recipe.id}/edit`} className="btn-ghost flex-1">
            Edit
          </Link>
          <button onClick={onDelete} className="btn-ghost flex-1 !text-ember">
            Delete
          </button>
        </div>
      </div>
    </article>
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
