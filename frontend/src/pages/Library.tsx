import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, FeaturedResponse, RecipeCard, RecipeSort, TagCategory } from '../api';
import StarRating from '../components/StarRating';
import {
  clampPage,
  PAGE_SIZES,
  PageSize,
  pageCount,
  parsePageSize,
  parseSort,
  rangeText,
  SORT_OPTIONS,
} from '../lib/paging';

// A small hero color rotation so image-less cards still look intentional, not broken.
const PLACEHOLDER_TONES = ['#e9ddcb', '#e6d3c4', '#dfe3d3', '#ead9d4', '#e2ddd0'];

// Sort + page size are per-device conveniences, so they live in localStorage. Every access is
// guarded: private windows / blocked storage must never break the library.
function loadPref(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}
function savePref(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* not persisted — the choice still applies for this visit */
  }
}

const selectCls =
  'rounded-lg border-0 bg-white py-1.5 pl-2.5 pr-7 text-sm text-bark shadow-sm ring-1 ring-black/10 focus:outline-none focus:ring-2 focus:ring-ember/40';

export default function Library() {
  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');
  const [activeTags, setActiveTags] = useState<number[]>([]);
  const [cards, setCards] = useState<RecipeCard[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0); // 0-based
  const [pageSize, setPageSize] = useState<PageSize>(() => parsePageSize(loadPref('lib.pageSize')));
  const [sortChoice, setSortChoice] = useState(() => parseSort(loadPref('lib.sort')));
  // While searching, "Best match" leads until the person picks a sort of their own.
  const [pickedSort, setPickedSort] = useState(false);
  const [categories, setCategories] = useState<TagCategory[]>([]);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [featured, setFeatured] = useState<FeaturedResponse | null>(null);

  const searching = !!debounced;
  const sort: RecipeSort = searching && !pickedSort ? 'relevance' : sortChoice;

  // Debounce the search box (spec §9: live, debounced).
  useEffect(() => {
    const t = setTimeout(() => setDebounced(query.trim()), 220);
    return () => clearTimeout(t);
  }, [query]);

  useEffect(() => {
    if (!debounced) setPickedSort(false);
  }, [debounced]);

  useEffect(() => {
    api.listTags().then(setCategories).catch(() => setCategories([]));
    api.getFeatured().then(setFeatured).catch(() => setFeatured(null));
  }, []);

  useEffect(() => {
    let stale = false; // ignore a slow response that a newer request has overtaken
    setLoading(true);
    api
      .listRecipesPage({
        q: debounced || undefined,
        tagIds: activeTags,
        sort,
        limit: pageSize,
        offset: page * pageSize,
      })
      .then(({ items, total: t }) => {
        if (stale) return;
        // The list shrank under us (recipe deleted elsewhere) — step back to a real page.
        if (items.length === 0 && t > 0 && page > 0) {
          setPage(clampPage(page, t, pageSize));
          return;
        }
        setCards(items);
        setTotal(t);
      })
      .catch(() => {
        if (stale) return;
        setCards([]);
        setTotal(0);
      })
      .finally(() => {
        if (!stale) setLoading(false);
      });
    return () => {
      stale = true;
    };
  }, [debounced, activeTags, sort, pageSize, page]);

  // Any change to what's being listed starts again from the first page.
  const toggleTag = (id: number) => {
    setPage(0);
    setActiveTags((prev) => (prev.includes(id) ? prev.filter((t) => t !== id) : [...prev, id]));
  };
  const clearTags = () => {
    setPage(0);
    setActiveTags([]);
  };
  const changeQuery = (v: string) => {
    setPage(0);
    setQuery(v);
  };
  const changeSort = (v: RecipeSort) => {
    setPage(0);
    if (v === 'relevance') {
      setPickedSort(false);
      return;
    }
    setSortChoice(v);
    // Only a sort chosen *during* a search overrides "Best match"; picking one while browsing
    // is just the new default and must not pre-empt relevance on the next search.
    setPickedSort(searching);
    savePref('lib.sort', v);
  };
  const changeSize = (n: PageSize) => {
    setPage(0);
    setPageSize(n);
    savePref('lib.pageSize', String(n));
  };
  const goToPage = (p: number) => {
    setPage(p);
    window.scrollTo({ top: 0 });
  };

  const activeTagCount = activeTags.length;
  const nonEmptyCategories = useMemo(
    () => categories.filter((c) => c.tags.length > 0),
    [categories],
  );

  const pages = pageCount(total, pageSize);
  const showHero = !debounced && activeTagCount === 0 && page === 0 && featured?.recipe;

  return (
    <div>
      {/* Recipe of the Week — pinned at the very top when browsing the full library */}
      {showHero && featured?.recipe && (
        <FeaturedHero card={featured.recipe} pinned={featured.pinned} />
      )}

      {/* Search */}
      <div className="mb-3 flex gap-2">
        <input
          value={query}
          onChange={(e) => changeQuery(e.target.value)}
          placeholder="Search name, ingredient, tag…"
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

      {/* Sort + result count */}
      <div className="mb-4 flex items-center justify-between gap-3">
        <label className="flex items-center gap-2 text-sm text-muted">
          Sort
          <select
            value={sort}
            onChange={(e) => changeSort(e.target.value as RecipeSort)}
            className={selectCls}
          >
            {searching && <option value="relevance">Best match</option>}
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        {!loading && total > 0 && (
          <span className="text-sm tabular-nums text-muted">
            {total} recipe{total === 1 ? '' : 's'}
          </span>
        )}
      </div>

      {/* Tag filters */}
      {filtersOpen && (
        <div className="card mb-4 p-4">
          {activeTagCount > 0 && (
            <button
              onClick={clearTags}
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

      {/* Pager — only once there's more than the smallest page size to page through */}
      {!loading && total > PAGE_SIZES[0] && (
        <nav className="mt-6 flex flex-col items-center gap-3" aria-label="Pages">
          <div className="flex items-center gap-3">
            <button
              onClick={() => goToPage(page - 1)}
              disabled={page === 0}
              className="btn-ghost !py-2 disabled:opacity-40"
            >
              ‹ Prev
            </button>
            <span className="min-w-[7.5rem] text-center text-sm tabular-nums text-muted">
              {rangeText(total, page, pageSize)}
            </span>
            <button
              onClick={() => goToPage(page + 1)}
              disabled={page >= pages - 1}
              className="btn-ghost !py-2 disabled:opacity-40"
            >
              Next ›
            </button>
          </div>
          <label className="flex items-center gap-2 text-sm text-muted">
            Per page
            <select
              value={pageSize}
              onChange={(e) => changeSize(parsePageSize(e.target.value))}
              className={selectCls}
            >
              {PAGE_SIZES.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
        </nav>
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
            src={thumbUrl(card.hero_image)}
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
        {card.rating ? (
          <div className="mt-1">
            <StarRating value={card.rating} />
          </div>
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

function FeaturedHero({ card, pinned }: { card: RecipeCard; pinned: boolean }) {
  return (
    <Link to={`/recipe/${card.id}`} className="card mb-5 block overflow-hidden">
      <div className="relative aspect-[16/9] w-full bg-[#e9ddcb] sm:aspect-[21/9]">
        {card.hero_image ? (
          <img src={mediaUrl(card.hero_image)} alt={card.title} className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-5xl opacity-40">🍽️</div>
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/10 to-transparent" />
        <span className="absolute left-3 top-3 chip bg-white/90 !text-[12px] font-semibold text-ember">
          ⭐ {pinned ? 'Pinned this week' : 'Recipe of the Week'}
        </span>
        <div className="absolute inset-x-0 bottom-0 p-4 text-white">
          <h2 className="font-display text-2xl font-semibold leading-tight drop-shadow">{card.title}</h2>
          {(card.source_handle || card.source_name) && (
            <p className="mt-0.5 text-sm text-white/85">{card.source_handle || card.source_name}</p>
          )}
          <span className="mt-2 inline-block rounded-lg bg-white/95 px-3 py-1.5 text-sm font-semibold text-bark">
            View recipe →
          </span>
        </div>
      </div>
    </Link>
  );
}

// Media originals live on the NAS (Chunk C); serve relative paths under /media.
export function mediaUrl(path: string): string {
  if (/^https?:\/\//.test(path)) return path;
  return `/media/${path.replace(/^\/+/, '')}`;
}

// Grid images use the on-disk thumbnail cache (generated on first hit).
export function thumbUrl(path: string): string {
  if (/^https?:\/\//.test(path)) return path;
  return `/thumb/${path.replace(/^\/+/, '')}`;
}
