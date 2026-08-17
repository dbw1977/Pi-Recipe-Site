import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import {
  api,
  Equipment,
  Group,
  Ingredient,
  RecipeInput,
  Step,
  TagCategory,
} from '../api';
import { scaleQuantity } from '../lib/scaling';

const COMMON_UNITS = [
  'tsp', 'tbsp', 'cup', 'fl oz', 'pint', 'quart',
  'g', 'kg', 'oz', 'lb',
  'clove', 'slice', 'egg', 'whole', 'piece', 'can', 'pinch',
];

const emptyIngredient = (): Ingredient => ({
  quantity: null, unit: null, name: '', note: '', scalable: 1,
});
const emptyGroup = (name = ''): Group => ({ name: name || null, ingredients: [emptyIngredient()] });

interface ReviewState {
  review?: boolean;
  duplicate?: { id: number; title: string; reason: string } | null;
  warning?: string;
}

export default function RecipeEdit() {
  const { id } = useParams();
  const editing = Boolean(id);
  const navigate = useNavigate();
  const location = useLocation();
  const reviewState = (location.state || {}) as ReviewState;

  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [sourceName, setSourceName] = useState('');
  const [sourceHandle, setSourceHandle] = useState('');
  const [sourceUrl, setSourceUrl] = useState('');
  const [heroImage, setHeroImage] = useState('');
  const [servingsBase, setServingsBase] = useState<string>('');
  const [servingsUnit, setServingsUnit] = useState('');
  const [totalTime, setTotalTime] = useState<string>('');
  const [groups, setGroups] = useState<Group[]>([emptyGroup()]);
  const [steps, setSteps] = useState<Step[]>([]);
  const [equipment, setEquipment] = useState<Equipment[]>([]);
  const [tagIds, setTagIds] = useState<number[]>([]);
  const [categories, setCategories] = useState<TagCategory[]>([]);
  const [status, setStatus] = useState('published');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [previewFactor, setPreviewFactor] = useState(0); // 0 = preview off

  const isDraft = status === 'draft';
  const reviewing = isDraft || reviewState.review;

  useEffect(() => {
    api.listTags().then(setCategories).catch(() => setCategories([]));
  }, []);

  useEffect(() => {
    if (!editing || !id) return;
    api.getRecipe(Number(id)).then((r) => {
      setTitle(r.title);
      setDescription(r.description || '');
      setSourceName(r.source_name || '');
      setSourceHandle(r.source_handle || '');
      setSourceUrl(r.source_url || '');
      setHeroImage(r.hero_image || '');
      setServingsBase(r.servings_base?.toString() || '');
      setServingsUnit(r.servings_unit || '');
      setTotalTime(r.total_time?.toString() || '');
      setGroups(r.groups.length ? r.groups : [emptyGroup()]);
      setSteps(r.steps);
      setEquipment(r.equipment);
      setTagIds(r.tags.map((t) => t.id));
      setStatus(r.status);
    });
  }, [editing, id]);

  // -- mutations --------------------------------------------------------------------
  const updateGroup = (gi: number, patch: Partial<Group>) =>
    setGroups((gs) => gs.map((g, i) => (i === gi ? { ...g, ...patch } : g)));
  const addGroup = () => setGroups((gs) => [...gs, emptyGroup()]);
  const removeGroup = (gi: number) => setGroups((gs) => gs.filter((_, i) => i !== gi));
  const updateIngredient = (gi: number, ii: number, patch: Partial<Ingredient>) =>
    setGroups((gs) =>
      gs.map((g, i) =>
        i === gi
          ? { ...g, ingredients: g.ingredients.map((ing, j) => (j === ii ? { ...ing, ...patch } : ing)) }
          : g,
      ),
    );
  const addIngredient = (gi: number) =>
    setGroups((gs) => gs.map((g, i) => (i === gi ? { ...g, ingredients: [...g.ingredients, emptyIngredient()] } : g)));
  const removeIngredient = (gi: number, ii: number) =>
    setGroups((gs) => gs.map((g, i) => (i === gi ? { ...g, ingredients: g.ingredients.filter((_, j) => j !== ii) } : g)));
  const toggleTag = (tid: number) =>
    setTagIds((prev) => (prev.includes(tid) ? prev.filter((t) => t !== tid) : [...prev, tid]));

  const buildPayload = (targetStatus: string): RecipeInput => ({
    title: title.trim(),
    description: description.trim() || null,
    source_type: 'manual',
    source_name: sourceName.trim() || null,
    source_handle: sourceHandle.trim() || null,
    source_url: sourceUrl.trim() || null,
    hero_image: heroImage.trim() || null,
    servings_base: servingsBase ? Number(servingsBase) : null,
    servings_unit: servingsUnit.trim() || null,
    total_time: totalTime ? Number(totalTime) : null,
    status: targetStatus,
    groups: groups
      .map((g, gi) => ({
        name: g.name?.trim() ? g.name.trim() : null,
        sort_order: gi,
        ingredients: g.ingredients
          .filter((ing) => ing.name.trim())
          .map((ing, ii) => ({
            quantity: ing.quantity === null || (ing.quantity as unknown) === '' ? null : Number(ing.quantity),
            unit: ing.unit?.trim() ? ing.unit.trim() : null,
            name: ing.name.trim(),
            note: ing.note?.trim() ? ing.note.trim() : null,
            scalable: ing.scalable ? 1 : 0,
            sort_order: ii,
          })),
      }))
      .filter((g) => g.ingredients.length > 0 || g.name),
    steps: steps.filter((s) => s.text.trim()).map((s, i) => ({ text: s.text.trim(), sort_order: i })),
    equipment: equipment
      .filter((e) => e.name.trim())
      .map((e, i) => ({ name: e.name.trim(), inferred: e.inferred ? 1 : 0, sort_order: i })),
    tag_ids: tagIds,
  });

  const save = async (targetStatus: string) => {
    setError(null);
    if (!title.trim()) {
      setError('A title is required.');
      return;
    }
    setSaving(true);
    try {
      const payload = buildPayload(targetStatus);
      const saved = editing ? await api.updateRecipe(Number(id), payload) : await api.createRecipe(payload);
      // Published → view it; kept as draft → back to the queue.
      navigate(targetStatus === 'published' ? `/recipe/${saved.id}` : '/drafts');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const discard = async () => {
    if (!id || !confirm('Discard this draft? It will not be saved.')) return;
    await api.discardDraft(Number(id));
    navigate('/drafts');
  };

  return (
    <div className="space-y-4">
      <h1 className="font-display text-2xl font-semibold">
        {reviewing ? 'Review import' : editing ? 'Edit recipe' : 'New recipe'}
      </h1>

      {!editing && !reviewing && (
        <Link
          to="/import"
          className="block rounded-xl bg-ember/5 px-4 py-3 text-sm text-emberDark ring-1 ring-ember/15"
        >
          ✨ Rather not type it all?{' '}
          <span className="font-semibold underline">
            Import from a link, screenshot, voice, or Drive →
          </span>
        </Link>
      )}

      {reviewing && (
        <div className="rounded-xl bg-herb/10 px-4 py-3 text-sm text-herb">
          Check everything below, fix anything the importer got wrong, then <strong>Approve</strong> to
          publish. Nothing is saved to the library until you do.
        </div>
      )}
      {reviewState.warning && (
        <div className="rounded-xl bg-ember/10 px-4 py-3 text-sm text-emberDark">
          {reviewState.warning}
        </div>
      )}
      {reviewState.duplicate && (
        <div className="rounded-xl bg-ember/10 px-4 py-3 text-sm text-emberDark">
          ⚠ Possible duplicate ({reviewState.duplicate.reason}) of “{reviewState.duplicate.title}”.
        </div>
      )}
      {error && <div className="rounded-xl bg-ember/10 px-4 py-3 text-sm text-emberDark">{error}</div>}

      {/* Basics */}
      <section className="card space-y-3 p-4">
        <Field label="Title">
          <input className={inputCls} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Apple Cheddar Steak Salad" />
        </Field>
        <Field label="Description">
          <textarea className={inputCls} rows={2} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="A short line — not the blog story." />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Source name">
            <input className={inputCls} value={sourceName} onChange={(e) => setSourceName(e.target.value)} placeholder="chacekitchen" />
          </Field>
          <Field label="@handle">
            <input className={inputCls} value={sourceHandle} onChange={(e) => setSourceHandle(e.target.value)} placeholder="@chacekitchen" />
          </Field>
        </div>
        <Field label="Source URL">
          <input className={inputCls} value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} placeholder="https://…" inputMode="url" />
        </Field>
        <Field label="Hero image path">
          <input className={inputCls} value={heroImage} onChange={(e) => setHeroImage(e.target.value)} placeholder="relative/media/path.jpg (optional)" />
        </Field>
        <div className="grid grid-cols-3 gap-3">
          <Field label="Makes">
            <input className={inputCls} value={servingsBase} onChange={(e) => setServingsBase(e.target.value)} inputMode="numeric" placeholder="2" />
          </Field>
          <Field label="Unit">
            <input className={inputCls} value={servingsUnit} onChange={(e) => setServingsUnit(e.target.value)} placeholder="salads" />
          </Field>
          <Field label="Time (min)">
            <input className={inputCls} value={totalTime} onChange={(e) => setTotalTime(e.target.value)} inputMode="numeric" placeholder="25" />
          </Field>
        </div>
      </section>

      {/* Ingredient groups */}
      <section className="card space-y-4 p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Ingredients</h2>
          <button onClick={addGroup} className="text-sm font-medium text-ember">+ group</button>
        </div>
        <datalist id="units">
          {COMMON_UNITS.map((u) => <option key={u} value={u} />)}
        </datalist>

        {groups.map((group, gi) => (
          <div key={gi} className="rounded-xl bg-cream/60 p-3">
            <div className="mb-2 flex items-center gap-2">
              <input
                className={`${inputCls} !bg-white`}
                value={group.name ?? ''}
                onChange={(e) => updateGroup(gi, { name: e.target.value })}
                placeholder={`Group name (e.g. "For the dressing") — optional`}
              />
              {groups.length > 1 && (
                <button onClick={() => removeGroup(gi)} className="text-muted" aria-label="Remove group">✕</button>
              )}
            </div>
            <div className="space-y-2">
              {group.ingredients.map((ing, ii) => (
                <div key={ii} className="rounded-lg bg-white p-2 ring-1 ring-black/5">
                  <div className="flex gap-2">
                    <input
                      className={`${inputCls} w-16 text-center`}
                      value={ing.quantity ?? ''}
                      onChange={(e) => updateIngredient(gi, ii, { quantity: e.target.value === '' ? null : Number(e.target.value) })}
                      inputMode="decimal"
                      placeholder="qty"
                    />
                    <input
                      className={`${inputCls} w-20`}
                      list="units"
                      value={ing.unit ?? ''}
                      onChange={(e) => updateIngredient(gi, ii, { unit: e.target.value || null })}
                      placeholder="unit"
                    />
                    <input
                      className={`${inputCls} flex-1`}
                      value={ing.name}
                      onChange={(e) => updateIngredient(gi, ii, { name: e.target.value })}
                      placeholder="ingredient"
                    />
                    <button onClick={() => removeIngredient(gi, ii)} className="px-1 text-muted" aria-label="Remove">✕</button>
                  </div>
                  <div className="mt-2 flex items-center gap-3">
                    <input
                      className={`${inputCls} flex-1 !py-2 text-sm`}
                      value={ing.note ?? ''}
                      onChange={(e) => updateIngredient(gi, ii, { note: e.target.value })}
                      placeholder="note (minced, to taste…)"
                    />
                    <label className="flex shrink-0 items-center gap-1.5 text-sm text-muted">
                      <input
                        type="checkbox"
                        checked={!!ing.scalable}
                        onChange={(e) => updateIngredient(gi, ii, { scalable: e.target.checked ? 1 : 0 })}
                        className="h-4 w-4 accent-ember"
                      />
                      scales
                    </label>
                  </div>
                </div>
              ))}
            </div>
            <button onClick={() => addIngredient(gi)} className="mt-2 text-sm font-medium text-ember">+ ingredient</button>
          </div>
        ))}
      </section>

      {/* Scaled preview (spec §6) */}
      <section className="card p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Preview scaling</h2>
          <div className="flex gap-1 rounded-xl bg-cream p-1">
            {[0, 2, 3].map((f) => (
              <button
                key={f}
                onClick={() => setPreviewFactor(f)}
                className={`rounded-lg px-3 py-1.5 text-sm font-semibold ${previewFactor === f ? 'bg-ember text-white' : 'text-bark'}`}
              >
                {f === 0 ? 'Off' : `${f}×`}
              </button>
            ))}
          </div>
        </div>
        {previewFactor > 0 && (
          <div className="mt-3 space-y-3">
            {groups.map((g, gi) => (
              <div key={gi}>
                {g.name && <div className="text-sm font-semibold text-herb">{g.name}</div>}
                <ul className="text-[15px]">
                  {g.ingredients.filter((i) => i.name.trim()).map((ing, ii) => {
                    const s = scaleQuantity(
                      { ...ing, quantity: ing.quantity === null || (ing.quantity as unknown) === '' ? null : Number(ing.quantity) },
                      previewFactor,
                    );
                    return (
                      <li key={ii} className="py-0.5">
                        {s.display && <span className="font-semibold">{s.display} </span>}
                        {ing.name}
                        {s.rounded && <span className="ml-1 text-xs text-ember">(rounded)</span>}
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Equipment with inferred markers */}
      <section className="card space-y-2 p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Equipment / utensils</h2>
          <button onClick={() => setEquipment((eq) => [...eq, { name: '', inferred: 0 }])} className="text-sm font-medium text-ember">+ add</button>
        </div>
        {equipment.length === 0 && <p className="text-sm text-muted">None yet.</p>}
        {equipment.map((e, i) => (
          <div key={i} className="flex items-center gap-2">
            <input
              className={inputCls}
              value={e.name}
              onChange={(ev) => setEquipment((eq) => eq.map((x, j) => (j === i ? { ...x, name: ev.target.value } : x)))}
              placeholder="whisk, grill, mixing bowl…"
            />
            {e.inferred ? (
              <button
                onClick={() => setEquipment((eq) => eq.map((x, j) => (j === i ? { ...x, inferred: 0 } : x)))}
                className="chip shrink-0 bg-cream !text-[11px] text-muted"
                title="AI-guessed — tap to confirm"
              >
                guessed ✓
              </button>
            ) : null}
            <button onClick={() => setEquipment((eq) => eq.filter((_, j) => j !== i))} className="px-1 text-muted" aria-label="Remove">✕</button>
          </div>
        ))}
      </section>

      {/* Steps */}
      <ListEditor
        title="Steps"
        items={steps.map((s) => s.text)}
        onAdd={() => setSteps((s) => [...s, { text: '' }])}
        onChange={(i, val) => setSteps((s) => s.map((st, j) => (j === i ? { ...st, text: val } : st)))}
        onRemove={(i) => setSteps((s) => s.filter((_, j) => j !== i))}
        placeholder="Describe the step…"
        numbered
        multiline
      />

      {/* Tags */}
      <section className="card space-y-3 p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Tags</h2>
          {reviewing && tagIds.length > 0 && (
            <button onClick={() => setTagIds([])} className="text-sm font-medium text-ember">
              Clear all
            </button>
          )}
        </div>
        {reviewing && (
          <p className="-mt-1 text-sm text-muted">
            Auto-selected from the recipe. The <span className="font-medium text-herb">highlighted</span>{' '}
            ones ({tagIds.length}) are what get saved when you <strong>Approve</strong> — tap any to
            remove it, tap a plain one to add it, or Clear all to start over.
          </p>
        )}
        {categories.filter((c) => c.tags.length).map((cat) => (
          <div key={cat.id}>
            <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">{cat.name}</div>
            <div className="flex flex-wrap gap-2">
              {cat.tags.map((tag) => {
                const on = tagIds.includes(tag.id);
                return (
                  <button key={tag.id} onClick={() => toggleTag(tag.id)} className={`chip ${on ? 'bg-herb text-white ring-herb' : 'bg-white'}`}>
                    {on && reviewing ? '✓ ' : ''}{tag.name}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </section>

      {/* Actions */}
      <div className="sticky bottom-4 flex gap-2">
        {reviewing ? (
          <>
            <button onClick={() => save('published')} disabled={saving} className="btn-primary flex-1 shadow-lg">
              {saving ? 'Saving…' : 'Approve & publish'}
            </button>
            {editing && (
              <button onClick={() => save('draft')} disabled={saving} className="btn-ghost shadow-lg">
                Save draft
              </button>
            )}
            {editing && (
              <button onClick={discard} disabled={saving} className="btn-ghost !text-ember shadow-lg">
                Discard
              </button>
            )}
          </>
        ) : (
          <button onClick={() => save('published')} disabled={saving} className="btn-primary flex-1 shadow-lg">
            {saving ? 'Saving…' : editing ? 'Save changes' : 'Save recipe'}
          </button>
        )}
      </div>
    </div>
  );
}

const inputCls =
  'w-full rounded-lg border-0 bg-white px-3 py-2.5 text-[15px] shadow-sm ring-1 ring-black/10 focus:outline-none focus:ring-2 focus:ring-ember/40';

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-muted">{label}</span>
      {children}
    </label>
  );
}

function ListEditor({
  title, items, onAdd, onChange, onRemove, placeholder, numbered, multiline,
}: {
  title: string; items: string[]; onAdd: () => void; onChange: (i: number, val: string) => void;
  onRemove: (i: number) => void; placeholder: string; numbered?: boolean; multiline?: boolean;
}) {
  return (
    <section className="card space-y-2 p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">{title}</h2>
        <button onClick={onAdd} className="text-sm font-medium text-ember">+ add</button>
      </div>
      {items.length === 0 && <p className="text-sm text-muted">None yet.</p>}
      {items.map((val, i) => (
        <div key={i} className="flex items-start gap-2">
          {numbered && <span className="mt-2.5 w-5 shrink-0 text-right text-sm font-semibold text-muted">{i + 1}.</span>}
          {multiline ? (
            <textarea className={inputCls} rows={2} value={val} onChange={(e) => onChange(i, e.target.value)} placeholder={placeholder} />
          ) : (
            <input className={inputCls} value={val} onChange={(e) => onChange(i, e.target.value)} placeholder={placeholder} />
          )}
          <button onClick={() => onRemove(i)} className="px-1 pt-2 text-muted" aria-label="Remove">✕</button>
        </div>
      ))}
    </section>
  );
}
