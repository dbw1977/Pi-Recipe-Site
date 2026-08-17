import { useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { api, Dish, PlaceInput, Tag, TagCategory } from '../api';

const PLACE_TYPES = [
  'restaurant', 'takeout', 'cafe', 'coffee', 'bar', 'brewery', 'food truck',
  'bakery', 'dessert', 'deli', 'fast food', 'fine dining',
];

const inputCls =
  'w-full rounded-lg border-0 bg-white px-3 py-2.5 text-[15px] shadow-sm ring-1 ring-black/10 focus:outline-none focus:ring-2 focus:ring-ember/40';

const emptyDish = (): Dish => ({ name: '', note: '', must_order: 0 });

interface ReviewState {
  review?: boolean;
  warning?: string;
}

export default function PlaceEdit() {
  const { id } = useParams();
  const editing = Boolean(id);
  const navigate = useNavigate();
  const location = useLocation();
  const reviewState = (location.state || {}) as ReviewState;

  const [name, setName] = useState('');
  const [placeType, setPlaceType] = useState('');
  const [city, setCity] = useState('');
  const [address, setAddress] = useState('');
  const [mapsUrl, setMapsUrl] = useState('');
  const [website, setWebsite] = useState('');
  const [phone, setPhone] = useState('');
  const [priceLevel, setPriceLevel] = useState<number | null>(null);
  const [rating, setRating] = useState<number | null>(null);
  const [visited, setVisited] = useState(1);
  const [sourceName, setSourceName] = useState('');
  const [notes, setNotes] = useState('');
  const [dishes, setDishes] = useState<Dish[]>([emptyDish()]);
  const [cuisineTags, setCuisineTags] = useState<Tag[]>([]);
  const [tagIds, setTagIds] = useState<number[]>([]);
  const [cities, setCities] = useState<string[]>([]);
  const [status, setStatus] = useState('published');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reviewing = status === 'draft' || reviewState.review;

  // Cuisine chips (the only tags chosen by hand; city/type/price mirror from the fields).
  useEffect(() => {
    api
      .listTags('place')
      .then((cats: TagCategory[]) => {
        const cuisine = cats.find((c) => c.name === 'Cuisine');
        setCuisineTags(cuisine?.tags ?? []);
      })
      .catch(() => setCuisineTags([]));
    api.placesMeta().then((m) => {
      setCities(m.cities);
      if (!editing && m.home_city) setCity((c) => c || m.home_city!);
    });
  }, [editing]);

  useEffect(() => {
    if (!editing || !id) return;
    api.getPlace(Number(id)).then((p) => {
      setName(p.name);
      setPlaceType(p.place_type || '');
      setCity(p.city || '');
      setAddress(p.address || '');
      setMapsUrl(p.maps_url || '');
      setWebsite(p.website || '');
      setPhone(p.phone || '');
      setPriceLevel(p.price_level);
      setRating(p.our_rating);
      setVisited(p.visited);
      setSourceName(p.source_name || '');
      setNotes(p.our_notes || '');
      setDishes(p.dishes.length ? p.dishes : [emptyDish()]);
      setTagIds(p.tags.filter((t) => t.category === 'Cuisine').map((t) => t.id));
      setStatus(p.status);
    });
  }, [editing, id]);

  const toggleTag = (tid: number) =>
    setTagIds((prev) => (prev.includes(tid) ? prev.filter((t) => t !== tid) : [...prev, tid]));
  const updateDish = (i: number, patch: Partial<Dish>) =>
    setDishes((ds) => ds.map((d, j) => (j === i ? { ...d, ...patch } : d)));

  const buildPayload = (targetStatus: string): PlaceInput => ({
    name: name.trim(),
    place_type: placeType.trim() || null,
    city: city.trim() || null,
    address: address.trim() || null,
    maps_url: mapsUrl.trim() || null,
    website: website.trim() || null,
    phone: phone.trim() || null,
    price_level: priceLevel,
    our_rating: rating,
    our_notes: notes.trim() || null,
    source_name: sourceName.trim() || null,
    visited,
    status: targetStatus,
    dishes: dishes
      .filter((d) => d.name.trim())
      .map((d, i) => ({ name: d.name.trim(), note: d.note?.trim() || null, must_order: d.must_order ? 1 : 0, sort_order: i })),
    tag_ids: tagIds,
  });

  const save = async (targetStatus: string) => {
    setError(null);
    if (!name.trim()) {
      setError('A name is required.');
      return;
    }
    setSaving(true);
    try {
      const payload = buildPayload(targetStatus);
      const saved = editing ? await api.updatePlace(Number(id), payload) : await api.createPlace(payload);
      navigate(targetStatus === 'published' ? `/eat/place/${saved.id}` : '/eat/drafts');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const discard = async () => {
    if (!id || !confirm('Discard this draft? It will not be saved.')) return;
    await api.deletePlace(Number(id));
    navigate('/eat/drafts');
  };

  const citiesId = useMemo(() => 'city-list', []);

  return (
    <div className="space-y-4">
      <h1 className="font-display text-2xl font-semibold">
        {reviewing ? 'Review place' : editing ? 'Edit place' : 'New place'}
      </h1>

      {!editing && !reviewing && (
        <Link to="/eat/import" className="block rounded-xl bg-ember/5 px-4 py-3 text-sm text-emberDark ring-1 ring-ember/15">
          ✨ Got a screenshot of a rec?{' '}
          <span className="font-semibold underline">Import it from a screenshot →</span>
        </Link>
      )}
      {reviewing && (
        <div className="rounded-xl bg-herb/10 px-4 py-3 text-sm text-herb">
          Check everything below, fix anything the importer got wrong, then <strong>Approve</strong> to
          publish. Nothing is saved to Eat Out until you do.
        </div>
      )}
      {reviewState.warning && (
        <div className="rounded-xl bg-ember/10 px-4 py-3 text-sm text-emberDark">{reviewState.warning}</div>
      )}
      {error && <div className="rounded-xl bg-ember/10 px-4 py-3 text-sm text-emberDark">{error}</div>}

      {/* Basics */}
      <section className="card space-y-3 p-4">
        <Field label="Name">
          <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="Birrieria La Plaza" />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Type">
            <input className={inputCls} list="place-types" value={placeType} onChange={(e) => setPlaceType(e.target.value)} placeholder="restaurant" />
            <datalist id="place-types">
              {PLACE_TYPES.map((t) => <option key={t} value={t} />)}
            </datalist>
          </Field>
          <Field label="City / Area">
            <input className={inputCls} list={citiesId} value={city} onChange={(e) => setCity(e.target.value)} placeholder="Gainesville" />
            <datalist id={citiesId}>
              {cities.map((c) => <option key={c} value={c} />)}
            </datalist>
          </Field>
        </div>

        {/* Visited / want-to-try */}
        <div className="flex gap-1 rounded-xl bg-cream p-1">
          {[{ v: 1, label: '✓ Been there' }, { v: 0, label: '☆ Want to try' }].map((o) => (
            <button
              key={o.v}
              onClick={() => setVisited(o.v)}
              className={`flex-1 rounded-lg px-3 py-2 text-sm font-semibold transition ${
                visited === o.v ? 'bg-ember text-white shadow-sm' : 'text-bark'
              }`}
            >
              {o.label}
            </button>
          ))}
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Price">
            <div className="flex gap-1 rounded-xl bg-cream p-1">
              {[1, 2, 3, 4].map((n) => (
                <button
                  key={n}
                  onClick={() => setPriceLevel(priceLevel === n ? null : n)}
                  className={`flex-1 rounded-lg py-2 text-sm font-semibold transition ${
                    priceLevel === n ? 'bg-ember text-white' : 'text-bark'
                  }`}
                >
                  {'$'.repeat(n)}
                </button>
              ))}
            </div>
          </Field>
          <Field label="Our rating">
            <div className="flex gap-1 pt-1.5 text-2xl">
              {[1, 2, 3, 4, 5].map((n) => (
                <button
                  key={n}
                  onClick={() => setRating(rating === n ? null : n)}
                  className={rating && n <= rating ? 'text-ember' : 'text-black/15'}
                  aria-label={`${n} star${n > 1 ? 's' : ''}`}
                >
                  ★
                </button>
              ))}
            </div>
          </Field>
        </div>

        <Field label="Google Maps link">
          <input className={inputCls} value={mapsUrl} onChange={(e) => setMapsUrl(e.target.value)} placeholder="Paste a Google Maps link" inputMode="url" />
        </Field>
        <Field label="Address">
          <input className={inputCls} value={address} onChange={(e) => setAddress(e.target.value)} placeholder="123 Main St (optional)" />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Website">
            <input className={inputCls} value={website} onChange={(e) => setWebsite(e.target.value)} placeholder="optional" inputMode="url" />
          </Field>
          <Field label="Recommended by">
            <input className={inputCls} value={sourceName} onChange={(e) => setSourceName(e.target.value)} placeholder="a friend, @account…" />
          </Field>
        </div>
      </section>

      {/* Dishes */}
      <section className="card space-y-2 p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">What to order</h2>
          <button onClick={() => setDishes((ds) => [...ds, emptyDish()])} className="text-sm font-medium text-ember">
            + dish
          </button>
        </div>
        {dishes.map((d, i) => (
          <div key={i} className="rounded-lg bg-cream/60 p-2">
            <div className="flex gap-2">
              <input
                className={`${inputCls} !bg-white flex-1`}
                value={d.name}
                onChange={(e) => updateDish(i, { name: e.target.value })}
                placeholder="birria tacos"
              />
              <button onClick={() => setDishes((ds) => ds.filter((_, j) => j !== i))} className="px-1 text-muted" aria-label="Remove">✕</button>
            </div>
            <div className="mt-2 flex items-center gap-3">
              <input
                className={`${inputCls} !bg-white flex-1 !py-2 text-sm`}
                value={d.note ?? ''}
                onChange={(e) => updateDish(i, { note: e.target.value })}
                placeholder="note (get the extra consommé…)"
              />
              <label className="flex shrink-0 items-center gap-1.5 text-sm text-muted">
                <input
                  type="checkbox"
                  checked={!!d.must_order}
                  onChange={(e) => updateDish(i, { must_order: e.target.checked ? 1 : 0 })}
                  className="h-4 w-4 accent-ember"
                />
                must-order
              </label>
            </div>
          </div>
        ))}
      </section>

      {/* Notes */}
      <section className="card p-4">
        <label className="block">
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-muted">Our notes</span>
          <textarea className={inputCls} rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Why we like it, tips, what to avoid…" />
        </label>
      </section>

      {/* Cuisine tags */}
      <section className="card space-y-2 p-4">
        <h2 className="text-lg font-semibold">Cuisine</h2>
        <div className="flex flex-wrap gap-2">
          {cuisineTags.map((tag) => {
            const on = tagIds.includes(tag.id);
            return (
              <button key={tag.id} onClick={() => toggleTag(tag.id)} className={`chip ${on ? 'bg-herb text-white ring-herb' : 'bg-white'}`}>
                {on ? '✓ ' : ''}{tag.name}
              </button>
            );
          })}
        </div>
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
            {saving ? 'Saving…' : editing ? 'Save changes' : 'Save place'}
          </button>
        )}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-muted">{label}</span>
      {children}
    </label>
  );
}
