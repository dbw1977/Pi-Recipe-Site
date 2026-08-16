import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api, DraftCard } from '../api';
import { mediaUrl } from './Library';

export default function Drafts() {
  const [drafts, setDrafts] = useState<DraftCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  const load = () => {
    setLoading(true);
    api
      .listDrafts()
      .then(setDrafts)
      .catch(() => setDrafts([]))
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  const approve = async (id: number) => {
    setDrafts((d) => d.filter((x) => x.id !== id));
    await api.approveDraft(id).catch(load);
  };
  const discard = async (id: number) => {
    if (!confirm('Discard this draft? It will not be saved.')) return;
    setDrafts((d) => d.filter((x) => x.id !== id));
    await api.discardDraft(id).catch(load);
  };
  const approveAll = async () => {
    if (!confirm(`Publish all ${drafts.length} drafts?`)) return;
    setBusy(true);
    try {
      await api.approveAll();
      setDrafts([]);
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <p className="py-16 text-center text-muted">Loading…</p>;

  if (drafts.length === 0) {
    return (
      <div className="card mt-6 p-10 text-center">
        <div className="text-4xl">✅</div>
        <p className="mt-3 font-display text-lg">No drafts to review.</p>
        <Link to="/import" className="btn-primary mt-4">
          Import recipes
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-2xl font-semibold">
          Drafts <span className="text-muted">({drafts.length})</span>
        </h1>
        <button onClick={approveAll} disabled={busy} className="btn-primary !py-2">
          Approve all
        </button>
      </div>
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
                <div className="flex h-full w-full items-center justify-center text-2xl opacity-40">
                  🍽️
                </div>
              )}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-start justify-between gap-2">
                <h3 className="truncate font-semibold">{d.title}</h3>
              </div>
              {(d.source_handle || d.source_name) && (
                <p className="truncate text-xs text-muted">{d.source_handle || d.source_name}</p>
              )}
              {d.duplicate && (
                <p className="mt-1 text-xs font-medium text-emberDark">
                  ⚠ Possible duplicate ({d.duplicate.reason}) of “{d.duplicate.title}”
                </p>
              )}
              {d.tags.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1">
                  {d.tags.slice(0, 3).map((t) => (
                    <span key={t.id} className="chip bg-cream !px-2 !py-0.5 !text-[11px]">
                      {t.name}
                    </span>
                  ))}
                </div>
              )}
              <div className="mt-2 flex gap-2">
                <button onClick={() => approve(d.id)} className="btn-primary !px-3 !py-1.5 text-sm">
                  Approve
                </button>
                <button
                  onClick={() => navigate(`/recipe/${d.id}/edit`, { state: { review: true } })}
                  className="btn-ghost !px-3 !py-1.5 text-sm"
                >
                  Edit
                </button>
                <button
                  onClick={() => discard(d.id)}
                  className="btn-ghost !px-3 !py-1.5 text-sm !text-ember"
                >
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
