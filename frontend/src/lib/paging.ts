// Library paging + sort helpers (pure, so they're unit-tested).
import type { ListSort } from '../api';

export const PAGE_SIZES = [20, 50, 100] as const;
export type PageSize = (typeof PAGE_SIZES)[number];
export const DEFAULT_PAGE_SIZE: PageSize = 20;

/** The sorts a person can choose. 'relevance' ("Best match") is added only while searching. */
export const SORT_OPTIONS: { value: Exclude<ListSort, 'relevance'>; label: string }[] = [
  { value: 'newest', label: 'Newest added' },
  { value: 'oldest', label: 'Oldest added' },
  { value: 'title_asc', label: 'A → Z' },
  { value: 'title_desc', label: 'Z → A' },
  { value: 'rating_desc', label: 'Highest rated' },
  { value: 'rating_asc', label: 'Lowest rated' },
];
export const DEFAULT_SORT = 'newest' as const;

export function parsePageSize(raw: unknown): PageSize {
  const n = Number(raw);
  return (PAGE_SIZES as readonly number[]).includes(n) ? (n as PageSize) : DEFAULT_PAGE_SIZE;
}

export function parseSort(raw: unknown): Exclude<ListSort, 'relevance'> {
  return SORT_OPTIONS.some((o) => o.value === raw)
    ? (raw as Exclude<ListSort, 'relevance'>)
    : DEFAULT_SORT;
}

export function pageCount(total: number, size: number): number {
  return Math.max(1, Math.ceil(total / size));
}

/** Keep a 0-based page index inside 0..lastPage (e.g. after a delete shrinks the list). */
export function clampPage(page: number, total: number, size: number): number {
  return Math.min(Math.max(0, page), pageCount(total, size) - 1);
}

/** "21–40 of 87" — the range this page covers. `noun` is only used for the empty case. */
export function rangeText(total: number, page: number, size: number, noun = 'recipe'): string {
  if (total === 0) return `0 ${noun}s`;
  const from = page * size + 1;
  const to = Math.min(total, (page + 1) * size);
  return `${from}–${to} of ${total}`;
}
