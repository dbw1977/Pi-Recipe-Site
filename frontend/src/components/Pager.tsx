import { PAGE_SIZES, PageSize, pageCount, parsePageSize, rangeText } from '../lib/paging';
import { selectCls } from './SortSelect';

/** Prev/Next with a "21–40 of 87" range, plus the per-page picker. Hidden until there is
 *  more than the smallest page size to page through. */
export default function Pager({
  total,
  page,
  pageSize,
  noun,
  onPage,
  onSize,
}: {
  total: number;
  page: number;
  pageSize: PageSize;
  noun: string; // singular: "recipe" | "place"
  onPage: (page: number) => void;
  onSize: (size: PageSize) => void;
}) {
  if (total <= PAGE_SIZES[0]) return null;
  const pages = pageCount(total, pageSize);
  return (
    <nav className="mt-6 flex flex-col items-center gap-3" aria-label="Pages">
      <div className="flex items-center gap-3">
        <button
          onClick={() => onPage(page - 1)}
          disabled={page === 0}
          className="btn-ghost !py-2 disabled:opacity-40"
        >
          ‹ Prev
        </button>
        <span className="min-w-[7.5rem] text-center text-sm tabular-nums text-muted">
          {rangeText(total, page, pageSize, noun)}
        </span>
        <button
          onClick={() => onPage(page + 1)}
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
          onChange={(e) => onSize(parsePageSize(e.target.value))}
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
  );
}
