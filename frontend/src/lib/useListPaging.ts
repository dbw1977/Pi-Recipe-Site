import { useEffect, useState } from 'react';
import type { ListSort } from '../api';
import { PageSize, parsePageSize, parseSort } from './paging';
import { loadPref, savePref } from './prefs';

/**
 * Page / page-size / sort state shared by the Cook and Eat Out libraries. `prefix` namespaces
 * the remembered choices ("lib" = recipes, "places" = Eat Out) so each collection keeps its own.
 *
 * - While `searching`, "Best match" leads until the person picks a sort *during* the search;
 *   a sort picked while merely browsing becomes the new default without pre-empting relevance.
 * - Anything that changes what is listed should call `resetPage()` (back to page 1).
 */
export function useListPaging(prefix: string, searching: boolean) {
  const [page, setPage] = useState(0); // 0-based
  const [pageSize, setPageSize] = useState<PageSize>(() => parsePageSize(loadPref(`${prefix}.pageSize`)));
  const [sortChoice, setSortChoice] = useState(() => parseSort(loadPref(`${prefix}.sort`)));
  const [pickedSort, setPickedSort] = useState(false);

  useEffect(() => {
    if (!searching) setPickedSort(false);
  }, [searching]);

  const sort: ListSort = searching && !pickedSort ? 'relevance' : sortChoice;

  const resetPage = () => setPage(0);
  const changeSort = (v: ListSort) => {
    setPage(0);
    if (v === 'relevance') {
      setPickedSort(false);
      return;
    }
    setSortChoice(v);
    setPickedSort(searching);
    savePref(`${prefix}.sort`, v);
  };
  const changeSize = (n: PageSize) => {
    setPage(0);
    setPageSize(n);
    savePref(`${prefix}.pageSize`, String(n));
  };
  const goToPage = (p: number) => {
    setPage(p);
    window.scrollTo({ top: 0 });
  };

  return { page, setPage, pageSize, sort, resetPage, changeSort, changeSize, goToPage };
}
