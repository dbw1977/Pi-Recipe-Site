import { useEffect, useState } from 'react';
import { api, Place } from '../api';
import { priceLabel, ratingStars } from './PlacesLibrary';
import { mapsHref } from './PlaceView';

export default function PlacesExport() {
  const [cities, setCities] = useState<string[]>([]);
  const [city, setCity] = useState<string>('');
  const [places, setPlaces] = useState<Place[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.placesMeta().then((m) => {
      setCities(m.cities);
      const first = m.home_city && m.cities.includes(m.home_city) ? m.home_city : m.cities[0] || '';
      setCity(first);
    });
  }, []);

  useEffect(() => {
    if (!city) return;
    setLoading(true);
    api
      .listPlaces(undefined, [], city)
      .then((cards) => Promise.all(cards.map((c) => api.getPlace(c.id))))
      .then(setPlaces)
      .catch(() => setPlaces([]))
      .finally(() => setLoading(false));
  }, [city]);

  // Name the tab so the saved PDF gets a sensible filename.
  useEffect(() => {
    const prev = document.title;
    if (city) document.title = `Our ${city} Picks`;
    return () => {
      document.title = prev;
    };
  }, [city]);

  return (
    <div className="space-y-4">
      {/* Controls — hidden when printing */}
      <div className="no-print space-y-3">
        <h1 className="font-display text-2xl font-semibold">Export a list</h1>
        <p className="text-sm text-muted">
          Pick a city and save a clean, one-page list of your picks — perfect to text or email a
          visitor (the site itself stays on your home network).
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={city}
            onChange={(e) => setCity(e.target.value)}
            className="rounded-lg border-0 bg-white px-3 py-2.5 text-[15px] shadow-sm ring-1 ring-black/10 focus:outline-none focus:ring-2 focus:ring-ember/40"
          >
            {cities.length === 0 && <option value="">No cities yet</option>}
            {cities.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <button onClick={() => window.print()} disabled={!places.length} className="btn-primary">
            ⤓ Save as PDF
          </button>
        </div>
      </div>

      {/* The printable card */}
      {loading ? (
        <p className="py-16 text-center text-muted">Loading…</p>
      ) : !city ? (
        <p className="py-16 text-center text-muted">Add a place with a city first.</p>
      ) : (
        <article className="card p-6">
          <header className="mb-4 border-b border-black/10 pb-3">
            <h2 className="font-display text-3xl font-semibold">Our {city} Picks</h2>
            <p className="mt-1 text-sm text-muted">
              {places.length} spot{places.length === 1 ? '' : 's'} we love
            </p>
          </header>

          {places.length === 0 ? (
            <p className="text-muted">No places saved in {city} yet.</p>
          ) : (
            <ol className="space-y-4">
              {places.map((p) => {
                const meta = [p.place_type, priceLabel(p.price_level)].filter(Boolean);
                const musts = p.dishes.filter((d) => d.must_order);
                const dishes = (musts.length ? musts : p.dishes).slice(0, 4);
                return (
                  <li key={p.id} className="break-inside-avoid">
                    <div className="flex items-baseline justify-between gap-2">
                      <h3 className="text-lg font-semibold">{p.name}</h3>
                      {p.our_rating ? <span className="text-sm text-ember">{ratingStars(p.our_rating)}</span> : null}
                    </div>
                    {meta.length > 0 && <p className="text-sm text-muted">{meta.join(' · ')}</p>}
                    {dishes.length > 0 && (
                      <p className="mt-1 text-[15px]">
                        <span className="font-medium">Order:</span>{' '}
                        {dishes.map((d) => d.name).join(', ')}
                      </p>
                    )}
                    {p.our_notes && <p className="mt-1 text-sm text-bark/80">{p.our_notes}</p>}
                    <a href={mapsHref(p)} className="mt-1 inline-block text-sm text-ember underline">
                      {p.maps_url || p.address ? 'Map / directions' : 'Find on Maps'}
                    </a>
                  </li>
                );
              })}
            </ol>
          )}
        </article>
      )}
    </div>
  );
}
