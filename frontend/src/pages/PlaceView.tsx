import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { api, Place } from '../api';
import { mediaUrl } from './Library';
import { priceLabel, ratingStars } from './PlacesLibrary';
import OverflowMenu from '../components/OverflowMenu';

export function mapsHref(place: Place): string {
  if (place.maps_url) return place.maps_url;
  const q = encodeURIComponent([place.name, place.address, place.city].filter(Boolean).join(' '));
  return `https://www.google.com/maps/search/?api=1&query=${q}`;
}

export default function PlaceView() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [place, setPlace] = useState<Place | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    api.getPlace(Number(id)).then(setPlace).catch((e) => setError(e.message));
  }, [id]);

  if (error) return <p className="py-16 text-center text-muted">{error}</p>;
  if (!place) return <p className="py-16 text-center text-muted">Loading…</p>;

  const onDelete = async () => {
    if (!confirm(`Delete “${place.name}”? This cannot be undone.`)) return;
    await api.deletePlace(place.id);
    navigate('/eat');
  };

  const meta = [
    place.place_type,
    place.city,
    priceLabel(place.price_level),
  ].filter(Boolean);

  return (
    <article>
      {/* Hero */}
      <div className="card mb-4 overflow-hidden">
        <div className="aspect-[16/10] w-full bg-[#e9ddcb]">
          {place.hero_image ? (
            <img src={mediaUrl(place.hero_image)} alt={place.name} className="h-full w-full object-cover" />
          ) : (
            <div className="flex h-full w-full items-center justify-center text-5xl opacity-40">🍴</div>
          )}
        </div>
        <div className="p-4">
          <div className="flex items-start justify-between gap-2">
            <h1 className="font-display text-2xl font-semibold leading-tight">{place.name}</h1>
            <div className="flex shrink-0 items-center gap-1.5">
              {!place.visited && (
                <span className="chip bg-ember/10 !text-[12px] font-semibold text-emberDark">Want to try</span>
              )}
              <OverflowMenu
                items={[
                  { label: '✎ Edit', onClick: () => navigate(`/eat/place/${place.id}/edit`) },
                  { label: '🗑 Delete', onClick: onDelete, danger: true },
                ]}
              />
            </div>
          </div>
          <p className="mt-1 text-sm text-muted">
            {meta.join(' · ')}
            {place.our_rating ? <span className="ml-1 text-ember">{ratingStars(place.our_rating)}</span> : null}
          </p>
          {place.source_name && (
            <p className="mt-1 text-sm text-muted">Recommended by {place.source_name}</p>
          )}
          <a href={mapsHref(place)} target="_blank" rel="noreferrer" className="btn-primary mt-3 w-full">
            📍 Open in Maps / Directions
          </a>
          {place.address && <p className="mt-2 text-sm text-muted">{place.address}</p>}
        </div>
      </div>

      {/* Dishes — the eat-out parallel to a recipe's ingredients; make it prominent */}
      <section className="card mb-4 p-4">
        <h2 className="mb-3 text-lg font-semibold">What to order</h2>
        {place.dishes.length === 0 ? (
          <p className="text-muted">No dishes noted yet.</p>
        ) : (
          <ul className="space-y-2">
            {place.dishes.map((d, i) => (
              <li key={d.id ?? i} className="flex items-start gap-2.5">
                <span className={`mt-0.5 text-lg ${d.must_order ? 'text-ember' : 'opacity-30'}`}>
                  {d.must_order ? '★' : '•'}
                </span>
                <span className="text-[15px] leading-snug">
                  <span className="font-semibold">{d.name}</span>
                  {d.must_order ? <span className="ml-1 text-xs font-semibold text-ember">must-order</span> : null}
                  {d.note ? <span className="text-muted"> — {d.note}</span> : null}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Notes */}
      {place.our_notes && (
        <section className="card mb-4 p-4">
          <h2 className="mb-2 text-lg font-semibold">Our notes</h2>
          <p className="whitespace-pre-line text-[15px] leading-relaxed text-bark/90">{place.our_notes}</p>
        </section>
      )}

      {/* Tags */}
      {place.tags.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-1.5">
          {place.tags.map((t) => (
            <span key={t.id} className="chip bg-cream !text-[13px]">
              {t.name}
            </span>
          ))}
        </div>
      )}

    </article>
  );
}
