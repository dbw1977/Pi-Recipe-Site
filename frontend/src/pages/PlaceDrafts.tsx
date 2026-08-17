import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api, PlaceCard } from '../api';
import { mediaUrl } from './Library';
import { priceLabel } from './PlacesLibrary';

export default function PlaceDrafts() {
  const [drafts, setDrafts] = useState<PlaceCard[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const load = () => {
    setLoading(true);
    api
      .listPlaceDrafts()
      .then(setDrafts)
      .catch(() => setDrafts([]))
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  const approve = async (id: number) => {
    setDrafts((d) => d.filter((x) => x.id !== id));
    await api.approvePlace(id).catch(load);
  };
  const discard = async (id: number) => {
    if (!confirm('Discard this draft? It will not be saved.')) return;
    setDrafts((d) => d.filter((x) => x.id !== id));
    await api.deletePlace(id).catch(load);
  };

  if (loading) return <p className="py-16 text-center text-muted">Loading…</p>;

  if (drafts.length === 0) {
    return (
      <div className="card mt-6 p-10 text-center">
        <div className="text-4xl">✅</div>
        <p className="mt-3 font-display text-lg">No place drafts to review.</p>
        <Link to="/eat/import" className="btn-primary mt-4">
          Import a place
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h1 className="font-display text-2xl font-semibold">
        Place drafts <span className="text-muted">({drafts.length})</span>
      </h1>
      <p className="text-sm text-muted">
        Review each import. <strong>Approve</strong> publishes as-is; <strong>Edit</strong> opens
        the full review screen; <strong>Discard</strong> throws it away.
      </p>

      <div className="space-y-3">
        {drafts.map((d) => (
          <div key={d.id} className="card flex gap-3 p-3">
            <div className="h-20 w-20 shrink-0 overflow-hidden rounded-xl bg-[#e9ddcb]">
              {d.hero_image ? (
                <img src={mediaUrl(d.hero_image)} alt="" className="h-full w-full object-cover" />
              ) : (
                <div className="flex h-full w-full items-center justify-center text-2xl opacity-40">🍴</div>
              )}
            </div>
            <div className="min-w-0 flex-1">
              <h3 className="truncate font-semibold">{d.name}</h3>
              <p className="truncate text-xs text-muted">
                {[d.city, priceLabel(d.price_level)].filter(Boolean).join(' · ')}
              </p>
              <div className="mt-2 flex gap-2">
                <button onClick={() => approve(d.id)} className="btn-primary !px-3 !py-1.5 text-sm">
                  Approve
                </button>
                <button
                  onClick={() => navigate(`/eat/place/${d.id}/edit`, { state: { review: true } })}
                  className="btn-ghost !px-3 !py-1.5 text-sm"
                >
                  Edit
                </button>
                <button onClick={() => discard(d.id)} className="btn-ghost !px-3 !py-1.5 text-sm !text-ember">
                  Discard
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
