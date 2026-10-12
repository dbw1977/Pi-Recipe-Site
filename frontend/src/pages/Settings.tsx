import { useEffect, useState } from 'react';
import { api, BackupEntry, BackupSettings, BackupStatus, GoogleStatus, TagCategory } from '../api';

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

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    weekday: 'long', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  });
}

function hourLabel(h: number): string {
  const ampm = h < 12 ? 'AM' : 'PM';
  return `${h % 12 === 0 ? 12 : h % 12}:00 ${ampm}`;
}

/** One destination's latest result. `staleDays` = how old counts as "needs attention" (null = never, e.g. weekly is off). */
function BackupRow({ label, entry, staleDays }: { label: string; entry: BackupEntry | null; staleDays: number | null }) {
  const age = daysSince(entry?.created_at);
  const failed = entry != null && entry.ok !== 1;
  const stale = staleDays != null && entry != null && entry.ok === 1 && age != null && age > staleDays;
  const bad = failed || stale;
  return (
    <div className="flex items-start justify-between gap-3 border-t border-black/5 py-3 first:border-t-0">
      <div className="min-w-0">
        <div className="font-medium">{label}</div>
        {entry ? (
          <div className="text-sm text-muted">
            {entry.ok === 1 ? (
              <>
                {new Date((entry.created_at || '') + 'Z').toLocaleString()} · {fmtSize(entry.size_bytes)}
                {age != null && <> · {age === 0 ? 'today' : `${age}d ago`}</>}
                {entry.message && entry.message !== 'ok' && <div>{entry.message}</div>}
              </>
            ) : (
              <span className="text-emberDark">Last try failed: {entry.message}</span>
            )}
          </div>
        ) : (
          <div className="text-sm text-muted">No backup yet.</div>
        )}
      </div>
      <span className={`chip shrink-0 ${bad ? 'bg-ember/10 text-emberDark' : entry ? 'bg-herb/15 text-herb' : 'bg-cream text-muted'}`}>
        {bad ? '⚠ needs attention' : entry ? '✓ healthy' : '—'}
      </span>
    </div>
  );
}

const inputCls =
  'w-full rounded-lg border-0 bg-white px-3 py-2 text-sm shadow-sm ring-1 ring-black/10 focus:outline-none focus:ring-2 focus:ring-ember/40';
const selectCls =
  'rounded-lg border-0 bg-white py-1.5 pl-2.5 pr-7 text-sm text-bark shadow-sm ring-1 ring-black/10 focus:outline-none focus:ring-2 focus:ring-ember/40';

function Check({ checked, onChange, children }: { checked: boolean; onChange: (v: boolean) => void; children: React.ReactNode }) {
  return (
    <label className="flex cursor-pointer items-start gap-2.5">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="mt-1 h-4 w-4 shrink-0 accent-ember" />
      <span className="text-[15px] leading-snug">{children}</span>
    </label>
  );
}

function BackupCard() {
  const [status, setStatus] = useState<BackupStatus | null>(null);
  const [form, setForm] = useState<BackupSettings | null>(null);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    api
      .backupStatus()
      .then((st) => {
        setStatus(st);
        setForm((f) => f ?? st.settings); // never overwrite what's being typed
      })
      .catch(() => setStatus(null));

  useEffect(() => {
    load();
  }, []);

  // While a backup runs, follow its progress.
  useEffect(() => {
    if (!status?.running) return;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [status?.running]);

  if (!status || !form) return (
    <section className="card p-4">
      <h2 className="text-lg font-semibold">Backups</h2>
      <p className="py-2 text-muted">Loading…</p>
    </section>
  );

  const dirty = JSON.stringify(form) !== JSON.stringify(status.settings);
  const set = (patch: Partial<BackupSettings>) => {
    setForm({ ...form, ...patch });
    setNotice(null);
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const st = await api.saveBackupSettings(form);
      setStatus(st);
      setForm(st.settings);
      setNotice('Saved.');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const backUpNow = async () => {
    setError(null);
    setNotice(null);
    try {
      setStatus(await api.runBackup());
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const s = status.settings;
  const anyDestination = s.local_enabled || s.drive_enabled;
  const neverBackedUp = !status.local && !status.drive;
  const driveNeedsGoogle = form.drive_enabled && !status.google.authorized;

  return (
    <section className="card p-4">
      <h2 className="text-lg font-semibold">Backups</h2>
      <p className="mb-3 mt-1 text-sm text-muted">
        One file with your whole library — recipes, places, meal plans
        {form.include_media ? ' and photos' : ''}. It’s replaced each time, so there’s always
        exactly one, and it’s all you need to rebuild on a new Pi.
      </p>

      {neverBackedUp && (
        <div className="mb-3 rounded-lg bg-ember/10 px-3 py-2 text-sm text-emberDark">
          No backup has been made yet — right now your library exists only on this Pi.
        </div>
      )}

      {/* Where */}
      <div className="space-y-3">
        <div className="space-y-2">
          <Check checked={form.local_enabled} onChange={(v) => set({ local_enabled: v })}>
            <strong>A folder</strong> on this Pi, a NAS, or a USB drive
          </Check>
          {form.local_enabled && (
            <div className="ml-6 space-y-1.5">
              <input className={inputCls} value={form.local_dir} onChange={(e) => set({ local_dir: e.target.value })}
                placeholder="/mnt/nas/recipes-backup" inputMode="url" autoCapitalize="none" spellCheck={false} />
              {status.local_same_disk && !dirty && (
                <p className="rounded-lg bg-ember/10 px-3 py-2 text-xs text-emberDark">
                  ⚠ That folder is on the Pi’s own disk, so the backup would be lost along with the Pi.
                  Pick a NAS or USB path — or also turn on Google Drive.
                </p>
              )}
            </div>
          )}
        </div>

        <div className="space-y-2">
          <Check checked={form.drive_enabled} onChange={(v) => set({ drive_enabled: v })}>
            <strong>Google Drive</strong>
          </Check>
          {form.drive_enabled && (
            <div className="ml-6 space-y-1.5">
              <label className="block text-xs text-muted">Folder name (created in your Drive if it doesn’t exist)</label>
              <input className={inputCls} value={form.drive_folder_name} onChange={(e) => set({ drive_folder_name: e.target.value })} />
              {driveNeedsGoogle && (
                <p className="text-xs text-emberDark">Connect your Google account in the card above first.</p>
              )}
            </div>
          )}
        </div>
      </div>

      {/* When */}
      <div className="mt-4 space-y-2 border-t border-black/5 pt-4">
        <Check checked={form.enabled} onChange={(v) => set({ enabled: v })}>
          Back up automatically every week
        </Check>
        {form.enabled && (
          <div className="ml-6 flex flex-wrap items-center gap-2 text-sm text-muted">
            on
            <select className={selectCls} value={form.day} onChange={(e) => set({ day: Number(e.target.value) })} aria-label="Day of the week">
              {status.day_names.map((d, i) => (
                <option key={d} value={i}>{d}</option>
              ))}
            </select>
            at
            <select className={selectCls} value={form.hour} onChange={(e) => set({ hour: Number(e.target.value) })} aria-label="Time of day">
              {Array.from({ length: 24 }, (_, h) => (
                <option key={h} value={h}>{hourLabel(h)}</option>
              ))}
            </select>
          </div>
        )}
        {s.enabled && anyDestination && status.next_run && !dirty && (
          <p className="ml-6 text-xs text-muted">Next automatic backup: {fmtTime(status.next_run)}</p>
        )}
      </div>

      {/* What */}
      <div className="mt-4 space-y-1 border-t border-black/5 pt-4">
        <Check checked={form.include_media} onChange={(v) => set({ include_media: v })}>
          Include photos
          {status.media && status.media.files > 0 && (
            <span className="text-muted"> — {status.media.files} photos, {fmtSize(status.media.bytes)}</span>
          )}
        </Check>
        <p className="ml-6 text-xs text-muted">
          Needed to rebuild everything on a new Pi. Skip only if your photos already live on a NAS that’s backed up separately.
        </p>
      </div>

      {/* Actions */}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <button onClick={save} disabled={!dirty || saving} className="btn-primary disabled:opacity-40">
          {saving ? 'Saving…' : 'Save settings'}
        </button>
        <button onClick={backUpNow} disabled={dirty || status.running || !anyDestination} className="btn-ghost disabled:opacity-40"
          title={dirty ? 'Save your changes first' : undefined}>
          {status.running ? 'Backing up…' : 'Back up now'}
        </button>
        {dirty && <span className="text-xs text-muted">Save to apply your changes.</span>}
        {notice && !dirty && <span className="text-sm text-herb">{notice}</span>}
      </div>
      {status.running && (
        <p className="mt-2 text-sm text-muted" role="status" aria-live="polite">⏳ {status.step || 'Working…'}</p>
      )}
      {error && <div className="mt-2 rounded-lg bg-ember/10 px-3 py-2 text-sm text-emberDark">{error}</div>}

      {/* Latest results */}
      {(s.local_enabled || status.local) && (
        <div className="mt-4">
          <BackupRow label="Folder (Pi / NAS / USB)" entry={status.local} staleDays={s.enabled ? 9 : null} />
        </div>
      )}
      {(s.drive_enabled || status.drive) && (
        <BackupRow label="Google Drive" entry={status.drive} staleDays={s.enabled ? 9 : null} />
      )}

      <details className="mt-4 text-sm">
        <summary className="cursor-pointer font-medium text-ember">Restoring after a hardware failure</summary>
        <div className="mt-2 space-y-2 text-muted">
          <p>On the new Pi, install the app (README), then stop it and restore. Test this once — a backup you’ve never restored is only a hope.</p>
          <pre className="overflow-x-auto rounded-lg bg-cream p-3 text-xs text-bark">{`sudo systemctl stop recipes
cd ~/pi-recipe-site/backend && . .venv/bin/activate
# from a folder / NAS / USB:
python -m app.backup restore /path/to/recipes-backup.zip --yes
# or from Google Drive (connect Google in Settings first):
python -m app.backup restore-drive --yes
sudo systemctl start recipes`}</pre>
          <p>Your Google connection and <code>.env</code> keys aren’t in the backup (they’re secrets) — reconnect Google and re-enter the keys afterwards.</p>
        </div>
      </details>
    </section>
  );
}

export default function Settings() {
  return (
    <div className="space-y-4">
      <h1 className="font-display text-2xl font-semibold">Settings</h1>

      <GoogleCard />
      <BackupCard />
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
        <strong>backing up to Google Drive</strong> (choose it in Backups below). One sign-in covers both.
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
              {status.drive_backup_ready ? '✓' : '•'} Drive backup {status.drive_backup_ready ? 'ready — pick it under Backups' : ''}
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
