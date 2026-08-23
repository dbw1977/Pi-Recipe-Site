import { useEffect, useState } from 'react';
import { api, BackupEntry, BackupStatus, GoogleStatus, TagCategory } from '../api';

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

      <GoogleCard />

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

function GoogleCard() {
  const [status, setStatus] = useState<GoogleStatus | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [authUrl, setAuthUrl] = useState<string | null>(null);
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () => api.googleStatus().then(setStatus).catch(() => setStatus(null));
  useEffect(() => {
    load();
  }, []);

  const startConnect = async () => {
    setError(null);
    try {
      const { url } = await api.googleAuthUrl();
      setAuthUrl(url);
      setConnecting(true);
      window.open(url, '_blank', 'noopener');
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const finish = async () => {
    if (!code.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.googleConnect(code.trim());
      setConnecting(false);
      setCode('');
      setAuthUrl(null);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const disconnect = async () => {
    if (!confirm('Disconnect Google? Drive import and Drive backup will stop until you reconnect.')) return;
    await api.googleDisconnect();
    await load();
  };

  return (
    <section className="card p-4">
      <h2 className="text-lg font-semibold">Google account</h2>
      <p className="mb-2 mt-1 text-sm text-muted">
        Connect once to enable <strong>Google Drive import</strong> (bulk-load a recipes folder) and
        the <strong>weekly Drive backup</strong> of your library. One sign-in covers both.
      </p>
      {error && <div className="mb-2 rounded-lg bg-ember/10 px-3 py-2 text-sm text-emberDark">{error}</div>}

      {!status ? (
        <p className="py-2 text-muted">Loading…</p>
      ) : !status.configured ? (
        <div className="rounded-lg bg-cream px-3 py-2 text-sm text-muted">
          🔒 Not set up yet. Add <code>GOOGLE_CLIENT_SECRETS</code> (a Desktop-app OAuth
          <code> client_secret.json</code>) to your <code>.env</code> on the Pi, then restart. See the runbook.
        </div>
      ) : status.authorized ? (
        <>
          <div className="flex items-center justify-between gap-3 border-t border-black/5 py-3 first:border-t-0">
            <div className="font-medium text-herb">✓ Connected</div>
            <button onClick={disconnect} className="btn-ghost !py-2 text-sm !text-ember">Disconnect</button>
          </div>
          <ul className="space-y-1 text-sm">
            <li className={status.drive_import_ready ? 'text-herb' : 'text-muted'}>
              {status.drive_import_ready ? '✓' : '•'} Drive import{' '}
              {status.drive_import_ready ? 'ready' : status.drive_import_folder ? '' : '— set DRIVE_FOLDER_ID in .env'}
            </li>
            <li className={status.drive_backup_ready ? 'text-herb' : 'text-muted'}>
              {status.drive_backup_ready ? '✓' : '•'} Drive backup{' '}
              {status.drive_backup_ready ? 'ready' : status.drive_backup_folder ? '' : '— set DRIVE_BACKUP_FOLDER_ID in .env'}
            </li>
          </ul>
        </>
      ) : !connecting ? (
        <button onClick={startConnect} className="btn-primary">Connect Google</button>
      ) : (
        <div className="space-y-2">
          <p className="text-sm text-muted">
            A Google sign-in opened in a new tab. Approve access — your browser will land on a{' '}
            <code>localhost</code> page that won't load (that's expected). Copy the <strong>code</strong> from
            that page's address bar (or paste the whole URL) here:
          </p>
          {authUrl && (
            <a href={authUrl} target="_blank" rel="noreferrer" className="block text-sm text-ember underline">
              Re-open the Google sign-in →
            </a>
          )}
          <div className="flex gap-2">
            <input
              className="w-full rounded-lg border-0 bg-white px-3 py-2.5 text-[15px] shadow-sm ring-1 ring-black/10 focus:outline-none focus:ring-2 focus:ring-ember/40"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="paste the code or the localhost URL"
            />
            <button onClick={finish} disabled={busy} className="btn-primary whitespace-nowrap">
              {busy ? 'Connecting…' : 'Connect'}
            </button>
          </div>
          <button onClick={() => { setConnecting(false); setCode(''); }} className="text-sm text-muted underline">
            Cancel
          </button>
        </div>
      )}
    </section>
  );
}

function TagManager() {
  const [cats, setCats] = useState<TagCategory[]>([]);
  const [adding, setAdding] = useState<Record<number, string>>({});
  const [error, setError] = useState<string | null>(null);

  // 'all' so the manager covers recipe AND place dimensions (City/Area, Place Type, Price).
  const load = () => api.listTags('all').then(setCats).catch(() => setCats([]));
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
