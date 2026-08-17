// Small date helpers for the meal planner (Chunk E). Local-time, no dependencies.

export function toISODate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

/** The upcoming Saturday (today if it's already Saturday). */
export function upcomingSaturday(from = new Date()): string {
  const d = new Date(from);
  const delta = (6 - d.getDay() + 7) % 7; // 6 = Saturday
  d.setDate(d.getDate() + delta);
  return toISODate(d);
}

const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

/** Label for day N of a window starting at startISO, e.g. "Sat Aug 22". */
export function dayLabel(startISO: string, offset: number): { dow: string; date: string } {
  const d = new Date(startISO + 'T00:00:00');
  d.setDate(d.getDate() + offset);
  return {
    dow: DAY_NAMES[d.getDay()],
    date: d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
  };
}

export function rangeLabel(startISO: string, days = 7): string {
  const start = new Date(startISO + 'T00:00:00');
  const end = new Date(start);
  end.setDate(end.getDate() + days - 1);
  const fmt = (d: Date) => d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  return `${fmt(start)} – ${fmt(end)}`;
}
