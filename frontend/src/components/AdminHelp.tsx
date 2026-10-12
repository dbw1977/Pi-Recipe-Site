import { ReactNode, useEffect, useState } from 'react';
import { api, BackupStatus, GoogleStatus, ImportStatus } from '../api';
import { backupHealth } from '../lib/backupHealth';

/** A command the admin pastes into the Pi's terminal, with a one-tap copy. */
function Code({ children }: { children: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(children);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* plain HTTP on the LAN can block the clipboard — the text is selectable instead */
    }
  };
  return (
    <div className="my-2">
      <pre className="whitespace-pre-wrap rounded-lg bg-cream p-3 text-xs text-bark [overflow-wrap:anywhere]">{children}</pre>
      <div className="mt-1 text-right">
        <button onClick={copy} className="rounded-md bg-white px-2.5 py-1 text-xs text-muted shadow-sm ring-1 ring-black/10">
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
    </div>
  );
}

function Row({ ok, label, detail, onMore }: { ok: boolean | null; label: string; detail: string; onMore?: () => void }) {
  return (
    <li className="flex items-start gap-2 py-1.5 text-sm">
      <span className={`mt-0.5 w-4 shrink-0 text-center ${ok === true ? 'text-herb' : ok === false ? 'text-emberDark' : 'text-muted'}`}>
        {ok === true ? '✓' : ok === false ? '⚠' : '•'}
      </span>
      <span className="min-w-0">
        <span className="font-medium">{label}</span>
        <span className="text-muted"> — {detail}</span>
        {onMore && ok === false && (
          <>
            {' '}
            <button onClick={onMore} className="text-ember underline">What to do</button>
          </>
        )}
      </span>
    </li>
  );
}

interface Topic {
  id: string;
  title: string;
  body: ReactNode;
}

const TOPICS: Topic[] = [
  {
    id: 'update',
    title: 'Updating the app',
    body: (
      <>
        <p>On the Pi:</p>
        <Code>{'~/pi-recipe-site/scripts/update.sh'}</Code>
        <p>
          It pulls the latest version, installs any new Python packages, rebuilds the screens, restarts the app and checks it’s
          healthy. Database changes apply automatically on restart. Add <code>--apt</code> to update the Pi’s system packages first:
        </p>
        <Code>{'~/pi-recipe-site/scripts/update.sh --apt'}</Code>
        <p>
          Running <code>sudo apt upgrade</code> on its own only updates the Pi’s system software — it never updates this app.
        </p>
      </>
    ),
  },
  {
    id: 'backups',
    title: 'Backups and restoring',
    body: (
      <>
        <ul className="list-disc space-y-1.5 pl-5">
          <li>A backup is <strong>one file</strong>, <code>recipes-backup.zip</code>: recipes, places, meal plans, settings and (if ticked) photos. It’s replaced each time.</li>
          <li>Weekly backups run <strong>inside the app</strong> at the day and time you choose. If the Pi was off then, it backs up as soon as it’s running again.</li>
          <li>Save it somewhere that survives the Pi — a NAS, a USB drive, or Google Drive. A folder on the Pi’s own SD card is lost with the Pi.</li>
          <li>Google Drive keeps older versions of the file, so you can roll back from drive.google.com.</li>
        </ul>
        <p className="mt-2 font-medium text-bark">Getting the library back (new Pi, or an earlier backup)</p>
        <ol className="list-decimal space-y-1.5 pl-5">
          <li>On a new Pi: install the app (README), then open Settings.</li>
          <li>Use <strong>Restore from a backup</strong>: choose the file, or pick it from the saved folder or Google Drive (connect Google first for Drive).</li>
          <li>Check the preview, then confirm. Nothing is replaced until you do.</li>
        </ol>
        <p className="mt-2">
          Before replacing anything, the app saves your current library next to the database as <code>before-restore-….db</code> (the newest 3 are kept).
          To undo a restore, stop the app and restore that file:
        </p>
        <Code>{`sudo systemctl stop recipes
cd ~/pi-recipe-site/backend && . .venv/bin/activate
python -m app.backup restore /path/to/before-restore-XXXX.db --yes
sudo systemctl start recipes`}</Code>
        <p>
          Not in a backup (they’re secrets): the <code>.env</code> file and your Google connection. After restoring on a new Pi, reconnect Google and
          re-enter your keys. Test a restore once — a backup you’ve never restored is only a hope.
        </p>
      </>
    ),
  },
  {
    id: 'importing',
    title: 'Importing recipes — what works',
    body: (
      <ul className="list-disc space-y-1.5 pl-5">
        <li><strong>From a link</strong> works offline for many recipe sites. With the AI key it also reads other pages, Reddit posts and Substack newsletters.</li>
        <li>Some sites refuse automated readers (Food &amp; Wine, for example). Open the page on your phone, screenshot the recipe, and use <strong>From a screenshot</strong> — that always works.</li>
        <li>A paid-subscribers-only Substack post only shares a preview, so use a screenshot there too.</li>
        <li>Screenshots, videos, voice notes and Drive import need the AI key. Video needs <code>ffmpeg</code>; spoken narration also needs the transcription tool.</li>
        <li>Everything imported lands in <strong>Drafts</strong> (the badge in the header). Nothing is published until you approve it.</li>
      </ul>
    ),
  },
  {
    id: 'google',
    title: 'Google account',
    body: (
      <ul className="list-disc space-y-1.5 pl-5">
        <li>One connection covers Drive import and Drive backup. Use <strong>Connect Google</strong> in the Google card above.</li>
        <li>After you approve, your browser lands on a <code>localhost</code> page that won’t load — that’s expected. Copy the code from the address bar (or paste the whole address) back into the app.</li>
        <li>If the card says it isn’t set up, the <code>GOOGLE_CLIENT_SECRETS</code> setting is missing from <code>.env</code> (a Desktop-app OAuth client file from Google Cloud).</li>
        <li>The connection isn’t part of backups. After restoring on a new Pi, connect again.</li>
      </ul>
    ),
  },
  {
    id: 'greyed',
    title: 'Something is greyed out or failing',
    body: (
      <>
        <ul className="list-disc space-y-1.5 pl-5">
          <li>
            <strong>Import options greyed out</strong> — the app can’t see an Anthropic key. Check, on the Pi:
          </li>
        </ul>
        <Code>{'curl localhost/api/imports/status'}</Code>
        <ul className="list-disc space-y-1.5 pl-5">
          <li>If it says <code>"claude": false</code>, put <code>ANTHROPIC_API_KEY=…</code> in <code>~/pi-recipe-site/.env</code> and restart (command below).</li>
          <li>A message saying the key is <em>invalid</em> means it’s wrong or was revoked — make a new one at console.anthropic.com and replace it.</li>
          <li><strong>A backup shows ⚠</strong> — the reason is shown under it. Usual causes: the NAS or USB drive isn’t mounted, the folder isn’t writable, or Google is disconnected.</li>
          <li>Anything else: look at the log (below). The last lines usually say what happened.</li>
        </ul>
      </>
    ),
  },
  {
    id: 'where',
    title: 'Where everything lives',
    body: (
      <ul className="list-disc space-y-1.5 pl-5">
        <li><code>~/pi-recipe-site/.env</code> — keys and paths. Restart the app after editing it.</li>
        <li><strong>Library database</strong> — at <code>RECIPE_DB_PATH</code>. Always on the Pi’s local disk, never on a NAS.</li>
        <li><strong>Photos</strong> — in <code>MEDIA_ROOT</code> (can be on a NAS). <strong>Thumbnails</strong> — a cache in <code>THUMBS_DIR</code>; safe to delete, it rebuilds itself.</li>
        <li><strong>Backups</strong> — wherever you chose in the Backups card.</li>
        <li>The app runs as the <code>recipes</code> service.</li>
      </ul>
    ),
  },
  {
    id: 'commands',
    title: 'Handy commands',
    body: (
      <>
        <p>Run these on the Pi (they assume the app is on the usual port 80).</p>
        <p className="font-medium text-bark">Is it running?</p>
        <Code>{'systemctl status recipes'}</Code>
        <p className="font-medium text-bark">Recent log (what went wrong)</p>
        <Code>{'sudo journalctl -u recipes -n 50 --no-pager'}</Code>
        <p className="font-medium text-bark">Restart (after editing .env)</p>
        <Code>{'sudo systemctl restart recipes'}</Code>
        <p className="font-medium text-bark">Health check (should answer status ok)</p>
        <Code>{'curl localhost/api/health'}</Code>
      </>
    ),
  },
];

export default function AdminHelp({ backup }: { backup: BackupStatus | null }) {
  const [imp, setImp] = useState<ImportStatus | null>(null);
  const [google, setGoogle] = useState<GoogleStatus | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    api.importStatus().then(setImp).catch(() => setImp(null));
    api.googleStatus().then(setGoogle).catch(() => setGoogle(null));
  }, []);

  const show = (id: string) => {
    setOpen(id);
    setTimeout(() => document.getElementById(`help-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50);
  };
  const health = backup ? backupHealth(backup) : null;

  return (
    <section className="card p-4">
      <h2 className="text-lg font-semibold">Admin help</h2>
      <p className="mb-2 mt-1 text-sm text-muted">What’s working, and answers to the things you’d otherwise have to remember.</p>

      <ul className="divide-y divide-black/5">
        {imp && (
          <Row ok={imp.claude} label="AI features"
            detail={imp.claude ? 'on (screenshots, videos, Reddit, Substack, variations)' : 'off: no Anthropic key found'}
            onMore={() => show('greyed')} />
        )}
        {imp && (
          <Row ok={null} label="Videos and voice"
            detail={`video ${imp.video ? 'ready' : 'not ready'} · narration transcription ${imp.voice_transcription ? 'ready' : 'not installed (optional)'}`} />
        )}
        {google && (
          <Row ok={google.authorized} label="Google account"
            detail={google.authorized ? 'connected' : google.configured ? 'not connected' : 'not set up'}
            onMore={() => show('google')} />
        )}
        {health && <Row ok={health.ok} label="Backups" detail={health.text} onMore={() => show('backups')} />}
      </ul>

      <div className="mt-3 border-t border-black/5">
        {TOPICS.map((t) => (
          <details
            key={t.id}
            id={`help-${t.id}`}
            open={open === t.id}
            onToggle={(e) => {
              const isOpen = (e.currentTarget as HTMLDetailsElement).open;
              setOpen((cur) => (isOpen ? t.id : cur === t.id ? null : cur));
            }}
            className="border-b border-black/5 py-2"
          >
            <summary className="cursor-pointer py-1 text-[15px] font-medium text-bark">{t.title}</summary>
            <div className="space-y-2 pb-2 pt-1 text-sm leading-relaxed text-bark/85">{t.body}</div>
          </details>
        ))}
      </div>
    </section>
  );
}
