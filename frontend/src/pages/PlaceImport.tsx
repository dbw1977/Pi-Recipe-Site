import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api, ImportStatus, PlaceImportResponse } from '../api';

export default function PlaceImport() {
  const [status, setStatus] = useState<ImportStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [cover, setCover] = useState<File | null>(null);
  const sourceRef = useRef<HTMLInputElement>(null);
  const coverRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    api.importStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  const onImported = (res: PlaceImportResponse) => {
    navigate(`/eat/place/${res.draft.id}/edit`, { state: { review: true, warning: res.warning } });
  };

  const pick = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    setBusy(true);
    setErr(null);
    try {
      onImported(await api.importPlaceScreenshot(files, cover ?? undefined));
    } catch (er) {
      setErr((er as Error).message);
    } finally {
      setBusy(false);
      if (sourceRef.current) sourceRef.current.value = '';
    }
  };

  const disabled = !!status && !status.screenshot;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-2xl font-semibold">Import a place</h1>
        <Link to="/eat/new" className="btn-ghost !py-2">
          ✎ By hand
        </Link>
      </div>
      <p className="text-sm text-muted">
        Screenshot a friend's text or an Instagram post about a spot — Claude pulls out the name,
        city, and the dishes they raved about. It lands as a <strong>draft</strong> for you to
        review; nothing publishes automatically.
      </p>

      <section className={`card p-4 ${disabled ? 'opacity-70' : ''}`}>
        <h2 className="text-lg font-semibold">From a screenshot</h2>
        <p className="mb-3 text-sm text-muted">One or more screenshots of the same recommendation.</p>
        {disabled ? (
          <div className="rounded-lg bg-cream px-3 py-2 text-sm text-muted">
            🔒 Needs an Anthropic API key (ANTHROPIC_API_KEY) in your .env.
          </div>
        ) : (
          <>
            <div className="mb-3 rounded-lg bg-cream/70 p-3">
              <div className="text-sm font-medium">
                Cover photo <span className="font-normal text-muted">(optional)</span>
              </div>
              <p className="mt-0.5 text-xs text-muted">
                Add a photo of the place or a dish and it becomes the card image. Otherwise the
                screenshot is used.
              </p>
              <input ref={coverRef} type="file" accept="image/*" className="hidden" onChange={(e) => setCover(e.target.files?.[0] || null)} />
              <div className="mt-2 flex items-center gap-2">
                <button onClick={() => coverRef.current?.click()} className="btn-ghost !py-2 text-sm">
                  {cover ? `✓ ${cover.name}` : '🖼 Choose cover photo'}
                </button>
                {cover && (
                  <button onClick={() => { setCover(null); if (coverRef.current) coverRef.current.value = ''; }} className="text-xs text-ember">
                    remove
                  </button>
                )}
              </div>
            </div>
            <input ref={sourceRef} type="file" accept="image/*" multiple className="hidden" onChange={pick} />
            <button onClick={() => sourceRef.current?.click()} disabled={busy} className="btn-primary w-full">
              {busy ? 'Reading…' : '📷 Choose screenshot(s)'}
            </button>
            {err && <div className="mt-2 rounded-lg bg-ember/10 px-3 py-2 text-sm text-emberDark">{err}</div>}
          </>
        )}
      </section>
    </div>
  );
}
