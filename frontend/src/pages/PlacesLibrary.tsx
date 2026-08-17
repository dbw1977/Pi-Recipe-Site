import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, PlaceCard, TagCategory } from '../api';
import { thumbUrl } from './Library';

const TONES = ['#e9ddcb', '#e6d3c4', '#dfe3d3', '#ead9d4', '#e2ddd0'];

export function priceLabel(level: number | null): string {
  return level && level >= 1 && level <= 4 ? '$'.repeat(level) : '';
}
export function ratingStars(rating: number | null): string {
  return rating && rating >= 1 && rating <= 5 ? '★'.repeat(rating) : '';
}

export default function PlacesLibrary() {
  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');
  const [activeTags, setActiveTags] = useState<number[]>([]);
  const [cards, setCards] = useState<PlaceCard[]>([]);
  const [categories, setCategories] = useState<TagCategory[]>([]);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(query.trim()), 220);
    return () => clearTimeout(t);
  }, [query]);

  useEffect(() => {
    api.listTags('place').then(setCategories).catch(() => setCategories([]));
  }, []);

  useEffect(() => {
    setLoading(true);
    api
      .listPlaces(debounced || undefined, activeTags)
      .then(setCards)
      .catch(() => setCards([]))
      .finally(() => setLoading(false));
  }, [debounced, activeTags]);

  const toggleTag = (id: number) =>
    setActiveTags((prev) => (prev.includes(id) ? prev.filter((t) => t !== id) : [...prev, id]));

  const nonEmpty = useMemo(() => categories.filter((c) => c.tags.length > 0), [categories]);

  return (
    <div>
      <div className="mb-3 flex gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search places, dishes, cities…"
          className="w-full rounded-xl border-0 bg-paper px-4 py-3 text-base shadow-sm ring-1 ring-black/5 focus:outline-none focus:ring-2 focus:ring-ember/40"
          inputMode="search"
        />
        <button onClick={() => setFiltersOpen((o) => !o)} className="btn-ghost whitespace-nowrap" aria-expanded={filtersOpen}>
          Filters{activeTags.length ? ` · ${activeTags.length}` : ''}
        </button>
      </div>

      <div className="mb-4 flex items-center justify-between">
        <p className="text-sm text-muted">Where to eat & what to order.</p>
        <Link to="/eat/export" className="text-sm font-medium text-ember underline">
          Export a list →
        </Link>
      </div>

      {filtersOpen && (
        <div className="card mb-4 p-4">
          {activeTags.length > 0 && (
            <button onClick={() => setActiveTags([])} className="mb-3 text-sm font-medium text-ember underline">
              Clear {activeTags.length} filter{activeTags.length > 1 ? 's' : ''}
            </button>
          )}
          <div className="space-y-3">
            {nonEmpty.map((cat) => (
              <div key={cat.id}>
                <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">{cat.name}</div>
                <div className="flex flex-wrap gap-2">
                  {cat.tags.map((tag) => {
                    const on = activeTags.includes(tag.id);
                    return (
                      <button
                        key={tag.id}
                        onClick={() => toggleTag(tag.id)}
                        className={`chip ${on ? 'bg-ember text-white ring-ember' : 'bg-white text-bark'}`}
                      >
                        {tag.name}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {loading ? (
        <p className="py-16 text-center text-muted">Loading…</p>
      ) : cards.length === 0 ? (
        <EmptyState searching={!!debounced || activeTags.length > 0} />
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {cards.map((card, i) => (
            <PlaceTile key={card.id} card={card} tone={TONES[i % TONES.length]} />
          ))}
        </div>
      )}
    </div>
  );
}

function PlaceTile({ card, tone }: { card: PlaceCard; tone: string }) {
  return (
    <Link to={`/eat/place/${card.id}`} className="card group overflow-hidden">
      <div className="relative aspect-[4/3] w-full overflow-hidden" style={{ background: tone }}>
        {card.hero_image ? (
          <img
            src={thumbUrl(card.hero_image)}
            alt={card.name}
            loading="lazy"
            className="h-full w-full object-cover transition group-active:scale-[1.02]"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-3xl opacity-40">🍴</div>
        )}
        {!card.visited && (
          <span className="absolute left-2 top-2 chip bg-white/90 !px-2 !py-0.5 !text-[11px] font-semibold text-ember">
            Want to try
          </span>
        )}
      </div>
      <div className="p-3">
        <h3 className="line-clamp-2 text-[15px] font-semibold leading-snug">{card.name}</h3>
        <p className="mt-0.5 truncate text-xs text-muted">
          {[card.city, priceLabel(card.price_level)].filter(Boolean).join(' · ')}
          {card.our_rating ? <span className="ml-1 text-ember">{ratingStars(card.our_rating)}</span> : null}
        </p>
      </div>
    </Link>
  );
}

function EmptyState({ searching }: { searching: boolean }) {
  return (
    <div className="card mt-6 p-10 text-center">
      <div className="text-4xl">🍴</div>
      <p className="mt-3 font-display text-lg">
        {searching ? 'No places match that.' : 'No places saved yet.'}
      </p>
      {!searching && (
        <Link to="/eat/new" className="btn-primary mt-4">
          Add your first place
        </Link>
      )}
    </div>
  );
}
