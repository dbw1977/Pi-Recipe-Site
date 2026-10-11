const STARS = [1, 2, 3, 4, 5];

interface Props {
  value: number | null | undefined; // 1-5, or null/undefined = not rated
  /** Omit for a read-only display (cards). With it, each star is a tap target. */
  onChange?: (next: number | null) => void;
  size?: 'sm' | 'lg';
}

/**
 * Our 1-5 star rating. Interactive mode: tap a star to rate; tap the star you already chose
 * to clear it — no separate "clear" control to crowd the screen.
 */
export default function StarRating({ value, onChange, size = 'sm' }: Props) {
  const current = value ?? 0;
  const text = size === 'lg' ? 'text-2xl' : 'text-[13px]';

  if (!onChange) {
    // Cards: render nothing for unrated recipes so the grid stays quiet.
    if (!current) return null;
    return (
      <span className={`inline-flex ${text} leading-none`} role="img" aria-label={`Rated ${current} out of 5`}>
        {STARS.map((n) => (
          <span key={n} className={n <= current ? 'text-ember' : 'text-bark/20'} aria-hidden>
            ★
          </span>
        ))}
      </span>
    );
  }

  return (
    <div className="flex items-center gap-1" role="group" aria-label="Your rating">
      <div className="-ml-1.5 flex">
        {STARS.map((n) => (
          <button
            key={n}
            type="button"
            onClick={() => onChange(n === current ? null : n)}
            aria-label={n === current ? `${n} stars (tap to clear)` : `${n} star${n > 1 ? 's' : ''}`}
            aria-pressed={n === current}
            className={`${text} px-1.5 py-1 leading-none transition active:scale-110 ${
              n <= current ? 'text-ember' : 'text-bark/20'
            }`}
          >
            ★
          </button>
        ))}
      </div>
      <span className="no-print text-sm text-muted">{current ? `${current}/5` : 'Not rated'}</span>
    </div>
  );
}
