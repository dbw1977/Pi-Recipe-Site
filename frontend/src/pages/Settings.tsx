import { useEffect, useState } from 'react';
import { api, BackupEntry, BackupStatus } from '../api';

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
    </div>
  );
}
