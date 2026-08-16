import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, RecipeCard, TagCategory } from '../api';

// A small hero color rotation so image-less cards still look intentional, not broken.
const PLACEHOLDER_TONES = ['#e9ddcb', '#e6d3c4', '#dfe3d3', '#ead9d4', '#e2ddd0'];

export default function Library() {
  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');
  const [activeTags, setActiveTags] = useState<number[]>([]);
  const [cards, setCards] = useState<RecipeCard[]>([]);
  const [categories, setCategories] = useState<TagCategory[]>([]);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [loading, setLoading] = useState(true);

  // Debounce the search box (spec §9: live, debounced).
  useEffect(() => {
    const t = setTimeout(() => setDebounced(query.trim()), 220);
    return () => clearTimeout(t);
  }, [query]);

  useEffect(() => {
    api.listTags().then(setCategories).catch(() => setCategories([]));
  }, []);

  useEffect(() => {
    setLoading(true);
    api
      .listRecipes(debounced || undefined, activeTags)
      .then(setCards)
      .catch(() => setCards([]))
      .finally(() => setLoading(false));
  }, [debounced, activeTags]);

  const toggleTag = (id: number) =>
    setActiveTags((prev) => (prev.includes(id) ? prev.filter((t) => t !== id) : [...prev, id]));

  const activeTagCount = activeTags.length;
  const nonEmptyCategories = useMemo(
    () => categories.filter((c) => c.tags.length > 0),
    [categories],
  );

  return (
    <div>
      {/* Search */}
      <div className="mb-3 flex gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search recipes, ingredients, @source…"
          className="w-full rounded-xl border-0 bg-paper px-4 py-3 text-base shadow-sm ring-1 ring-black/5 focus:outline-none focus:ring-2 focus:ring-ember/40"
          inputMode="search"
        />
        <button
          onClick={() => setFiltersOpen((o) => !o)}
          className="btn-ghost whitespace-nowrap"
          aria-expanded={filtersOpen}
        >
          Filters{activeTagCount ? ` · ${activeTagCount}` : ''}
        </button>
      </div>

      {/* Tag filters */}
      {filtersOpen && (
        <div className="card mb-4 p-4">
          {activeTagCount > 0 && (
            <button
              onClick={() => setActiveTags([])}
              className="mb-3 text-sm font-medium text-ember underline"
            >
              Clear {activeTagCount} filter{activeTagCount > 1 ? 's' : ''}
            </button>
          )}
          <div className="space-y-3">
            {nonEmptyCategories.map((cat) => (
              <div key={cat.id}>
                <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">
                  {cat.name}
                </div>
                <div className="flex flex-wrap gap-2">
                  {cat.tags.map((tag) => {
                    const on = activeTags.includes(tag.id);
                    return (
                      <button
                        key={tag.id}
                        onClick={() => toggleTag(tag.id)}
                        className={`chip ${
                          on ? 'bg-ember text-white ring-ember' : 'bg-white text-bark'
                        }`}
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

      {/* Grid */}
      {loading ? (
        <p className="py-16 text-center text-muted">Loading…</p>
      ) : cards.length === 0 ? (
        <EmptyState searching={!!debounced || activeTagCount > 0} />
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {cards.map((card, i) => (
            <CardTile key={card.id} card={card} tone={PLACEHOLDER_TONES[i % PLACEHOLDER_TONES.length]} />
          ))}
        </div>
      )}
    </div>
  );
}

function CardTile({ card, tone }: { card: RecipeCard; tone: string }) {
  const keyTags = card.tags.slice(0, 2);
  return (
    <Link to={`/recipe/${card.id}`} className="card group overflow-hidden">
      <div className="aspect-[4/3] w-full overflow-hidden" style={{ background: tone }}>
        {card.hero_image ? (
          <img
            src={mediaUrl(card.hero_image)}
            alt={card.title}
            loading="lazy"
            className="h-full w-full object-cover transition group-active:scale-[1.02]"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-3xl opacity-40">
            🍽️
          </div>
        )}
      </div>
      <div className="p-3">
        <h3 className="line-clamp-2 text-[15px] font-semibold leading-snug">{card.title}</h3>
        {card.source_handle || card.source_name ? (
          <p className="mt-0.5 truncate text-xs text-muted">
            {card.source_handle || card.source_name}
          </p>
        ) : null}
        {keyTags.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {keyTags.map((t) => (
              <span key={t.id} className="chip !px-2 !py-0.5 !text-[11px] bg-cream">
                {t.name}
              </span>
            ))}
          </div>
        )}
      </div>
    </Link>
  );
}

function EmptyState({ searching }: { searching: boolean }) {
  return (
    <div className="card mt-6 p-10 text-center">
      <div className="text-4xl">🥗</div>
      <p className="mt-3 font-display text-lg">
        {searching ? 'No recipes match that.' : 'Your cookbook is empty.'}
      </p>
      {!searching && (
        <Link to="/new" className="btn-primary mt-4">
          Add your first recipe
        </Link>
      )}
    </div>
  );
}

// Media originals live on the NAS (Chunk C); for now, serve relative paths under /media.
export function mediaUrl(path: string): string {
  if (/^https?:\/\//.test(path)) return path;
  return `/media/${path.replace(/^\/+/, '')}`;
}
