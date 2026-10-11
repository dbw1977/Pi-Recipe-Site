import type { ListSort } from '../api';
import { SORT_OPTIONS } from '../lib/paging';

export const selectCls =
  'rounded-lg border-0 bg-white py-1.5 pl-2.5 pr-7 text-sm text-bark shadow-sm ring-1 ring-black/10 focus:outline-none focus:ring-2 focus:ring-ember/40';

/** The "Sort" dropdown. "Best match" is offered only while searching. */
export default function SortSelect({
  value,
  onChange,
  searching,
}: {
  value: ListSort;
  onChange: (v: ListSort) => void;
  searching: boolean;
}) {
  return (
    <label className="flex items-center gap-2 text-sm text-muted">
      Sort
      <select value={value} onChange={(e) => onChange(e.target.value as ListSort)} className={selectCls}>
        {searching && <option value="relevance">Best match</option>}
        {SORT_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}
