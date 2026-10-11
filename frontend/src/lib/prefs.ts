// Per-device conveniences (sort, page size) live in localStorage. Every access is guarded:
// private windows / blocked storage must never break a page — the choice just isn't remembered.
export function loadPref(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function savePref(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* not persisted — the choice still applies for this visit */
  }
}
