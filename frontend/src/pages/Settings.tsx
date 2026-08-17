import { useEffect, useState } from 'react';
import { api, BackupEntry, BackupStatus, TagCategory } from '../api';

function daysSince(iso: string | undefined): number | null {
  if (!iso) return null;
  const t = Date.parse(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z');
  if (Number.isNaN(t)) return null;
  return Math.floor((Date.now() - t) / 86_400_000);
}

function fmtSize(n: number | null): string {
  if (!n) return '';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function BackupRow({ label, entry, staleDays }: { label: string; entry: BackupEntry | null; staleDays: number }) {
  const age = daysSince(entry?.created_at);
  const stale = entry == null || age == null || age > staleDays || entry.ok !== 1;
  return (
    <div className="flex items-start justify-between gap-3 border-t border-black/5 py-3 first:border-t-0">
      <div>
        <div className="font-medium">{label}</div>
        {entry ? (
          <div className="text-sm text-muted">
            {entry.ok === 1 ? (
              <>
                {new Date((entry.created_at || '') + 'Z').toLocaleString()} · {fmtSize(entry.size_bytes)}
                {age != null && <> · {age === 0 ? 'today' : `${age}d ago`}</>}
              </>
            ) : (
              <span className="text-emberDark">Last run failed: {entry.message}</span>
            )}
          </div>
        ) : (
          <div className="text-sm text-muted">No backup recorded yet.</div>
        )}
      </div>
      <span
        className={`chip shrink-0 ${stale ? 'bg-ember/10 text-emberDark' : 'bg-herb/15 text-herb'}`}
      >
        {stale ? '⚠ needs attention' : '✓ healthy'}
      </span>
    </div>
  );
}

export default function Settings() {
  const [status, setStatus] = useState<BackupStatus | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => api.backupStatus().then(setStatus).catch(() => setStatus(null));
  useEffect(() => {
    load();
  }, []);

  const run = async (kind: 'local' | 'drive') => {
    setBusy(kind);
    setError(null);
    try {
      setStatus(await api.runBackup(kind));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-4">
      <h1 className="font-display text-2xl font-semibold">Settings</h1>

      <section className="card p-4">
        <h2 className="text-lg font-semibold">Backups</h2>
        <p className="mb-2 mt-1 text-sm text-muted">
          Your whole library is one small database file. A nightly copy is kept locally and a
          weekly copy goes to Google Drive. Green means recent and healthy.
        </p>
        {status ? (
          <>
            <BackupRow label="Local snapshot (nightly)" entry={status.local} staleDays={2} />
            <BackupRow
              label={`Google Drive (weekly)${status.drive_configured ? '' : ' — not configured'}`}
              entry={status.drive}
              staleDays={10}
            />
          </>
        ) : (
          <p className="py-2 text-muted">Loading…</p>
        )}

        <div className="mt-3 flex flex-wrap gap-2">
          <button onClick={() => run('local')} disabled={busy !== null} className="btn-primary">
            {busy === 'local' ? 'Backing up…' : 'Back up now (local)'}
          </button>
          {status?.drive_configured && (
            <button onClick={() => run('drive')} disabled={busy !== null} className="btn-ghost">
              {busy === 'drive' ? 'Uploading…' : 'Back up to Drive now'}
            </button>
          )}
        </div>
        {error && <div className="mt-2 rounded-lg bg-ember/10 px-3 py-2 text-sm text-emberDark">{error}</div>}

        <p className="mt-3 text-xs text-muted">
          Automatic backups are scheduled on the Pi (systemd timers). Restore steps are in the
          project README (§ Restore). Test a restore at least once — a backup you've never
          restored is only a hope.
        </p>
      </section>

      <TagManager />
    </div>
  );
}

function TagManager() {
  const [cats, setCats] = useState<TagCategory[]>([]);
  const [adding, setAdding] = useState<Record<number, string>>({});
  const [error, setError] = useState<string | null>(null);

  const load = () => api.listTags().then(setCats).catch(() => setCats([]));
  useEffect(() => {
    load();
  }, []);

  const add = async (catId: number) => {
    const name = (adding[catId] || '').trim();
    if (!name) return;
    setError(null);
    try {
      await api.createTag(catId, name);
      setAdding((a) => ({ ...a, [catId]: '' }));
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const del = async (id: number, name: string) => {
    if (!confirm(`Delete the tag “${name}”? It’s removed from any recipes using it.`)) return;
    setError(null);
    try {
      await api.deleteTag(id);
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <section className="card p-4">
      <h2 className="text-lg font-semibold">Tags</h2>
      <p className="mb-2 mt-1 text-sm text-muted">
        The controlled list the app tags recipes from — used by auto-tagging on import and by the
        recipe editor. Add ones you use; delete ones you don’t. Changes apply right away.
      </p>
      {error && (
        <div className="mb-2 rounded-lg bg-ember/10 px-3 py-2 text-sm text-emberDark">{error}</div>
      )}
      <div className="space-y-3">
        {cats.map((cat) => (
          <div key={cat.id} className="border-t border-black/5 pt-3 first:border-t-0">
            <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted">
              {cat.name}
            </div>
            <div className="flex flex-wrap gap-2">
              {cat.tags.map((t) => (
                <span key={t.id} className="chip bg-white">
                  {t.name}
                  <button
                    onClick={() => del(t.id, t.name)}
                    className="ml-1.5 text-muted hover:text-ember"
                    aria-label={`Delete ${t.name}`}
                  >
                    ✕
                  </button>
                </span>
              ))}
              {cat.tags.length === 0 && <span className="text-sm text-muted">None yet.</span>}
            </div>
            <div className="mt-2 flex gap-2">
              <input
                className="w-full rounded-lg border-0 bg-white px-3 py-2 text-sm shadow-sm ring-1 ring-black/10 focus:outline-none focus:ring-2 focus:ring-ember/40"
                value={adding[cat.id] || ''}
                onChange={(e) => setAdding((a) => ({ ...a, [cat.id]: e.target.value }))}
                onKeyDown={(e) => e.key === 'Enter' && add(cat.id)}
                placeholder={`Add a ${cat.name} tag…`}
              />
              <button onClick={() => add(cat.id)} className="btn-ghost !py-2 text-sm">
                Add
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
