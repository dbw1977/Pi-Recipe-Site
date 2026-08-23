import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api, DriveScanSummary, GoogleStatus, ImportResponse, ImportStatus } from '../api';

export default function Import() {
  const [status, setStatus] = useState<ImportStatus | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    api.importStatus().then(setStatus).catch(() => setStatus(null));
    // Surface Drive OAuth round-trip result (?drive=connected|error).
  }, []);

  // After any successful import, go straight to the draft's review screen.
  const onImported = (res: ImportResponse) => {
    navigate(`/recipe/${res.draft.id}/edit`, {
      state: { review: true, duplicate: res.duplicate, warning: res.warning },
    });
  };

  return (
    <div className="space-y-4">
      <h1 className="font-display text-2xl font-semibold">New recipe</h1>
      <p className="text-sm text-muted">
        Type it in by hand, or bring one in from a link, a photo/video, a voice note, or Google
        Drive. Anything you bring in lands as a <strong>draft</strong> to review — nothing
        publishes automatically.
      </p>

      {/* Primary: enter it by hand */}
      <Link
        to="/new"
        className="card flex items-center justify-between p-4 ring-1 ring-ember/15 hover:ring-ember/40"
      >
        <span>
          <span className="text-lg font-semibold">✎ Enter it by hand</span>
          <span className="mt-0.5 block text-sm text-muted">Full control — type the ingredients and steps.</span>
        </span>
        <span className="text-ember">→</span>
      </Link>

      <div className="pt-1 text-xs font-semibold uppercase tracking-wide text-muted">or bring one in</div>

      <UrlCard onImported={onImported} />
      <ScreenshotCard status={status} onImported={onImported} />
      <VoiceCard status={status} onImported={onImported} />
      <DriveCard />
    </div>
  );
}

function Card({
  title, subtitle, children, disabled, disabledHint,
}: {
  title: string; subtitle: string; children: React.ReactNode;
  disabled?: boolean; disabledHint?: string;
}) {
  return (
    <section className={`card p-4 ${disabled ? 'opacity-70' : ''}`}>
      <h2 className="text-lg font-semibold">{title}</h2>
      <p className="mb-3 text-sm text-muted">{subtitle}</p>
      {disabled ? (
        <div className="rounded-lg bg-cream px-3 py-2 text-sm text-muted">🔒 {disabledHint}</div>
      ) : (
        children
      )}
    </section>
  );
}

function ErrorLine({ msg }: { msg: string | null }) {
  if (!msg) return null;
  return <div className="mt-2 rounded-lg bg-ember/10 px-3 py-2 text-sm text-emberDark">{msg}</div>;
}

// --- URL --------------------------------------------------------------------
function UrlCard({ onImported }: { onImported: (r: ImportResponse) => void }) {
  const [url, setUrl] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const go = async () => {
    if (!url.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      onImported(await api.importUrl(url.trim()));
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card
      title="From a link"
      subtitle="Paste a recipe URL. Recipe sites work with no setup; Reddit posts use the AI key."
    >
      <div className="flex gap-2">
        <input
          className="w-full rounded-lg border-0 bg-white px-3 py-2.5 shadow-sm ring-1 ring-black/10 focus:outline-none focus:ring-2 focus:ring-ember/40"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://…"
          inputMode="url"
        />
        <button onClick={go} disabled={busy} className="btn-primary whitespace-nowrap">
          {busy ? '…' : 'Import'}
        </button>
      </div>
      <ErrorLine msg={err} />
    </Card>
  );
}

// --- Screenshot / video -----------------------------------------------------
function ScreenshotCard({
  status, onImported,
}: {
  status: ImportStatus | null; onImported: (r: ImportResponse) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [cover, setCover] = useState<File | null>(null);
  const sourceRef = useRef<HTMLInputElement>(null);
  const coverRef = useRef<HTMLInputElement>(null);

  // Video needs ffmpeg on the Pi; only hide it when the server explicitly reports false.
  const videoReady = !status || status.video !== false;

  const pick = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    setBusy(true);
    setErr(null);
    try {
      onImported(await api.importScreenshot(files, cover ?? undefined));
    } catch (er) {
      setErr((er as Error).message);
    } finally {
      setBusy(false);
      if (sourceRef.current) sourceRef.current.value = '';
    }
  };

  const clearCover = () => {
    setCover(null);
    if (coverRef.current) coverRef.current.value = '';
  };

  return (
    <Card
      title="From a screenshot or video"
      subtitle="A recipe screenshot (Instagram, a photo) or a recipe video you've downloaded. Claude reads it and structures the recipe."
      disabled={!!status && !status.screenshot}
      disabledHint="Needs an Anthropic API key (ANTHROPIC_API_KEY) in your .env."
    >
      {/* Optional cover photo — becomes the recipe's picture. Documented so anyone knows. */}
      <div className="mb-3 rounded-lg bg-cream/70 p-3">
        <div className="text-sm font-medium">
          Cover photo <span className="font-normal text-muted">(optional)</span>
        </div>
        <p className="mt-0.5 text-xs text-muted">
          Want a nice picture on the recipe? Add a photo of the finished dish and it becomes the
          recipe's cover image. Skip it and we'll use the screenshot — or, for a video, a frame
          from the clip.
        </p>
        <input
          ref={coverRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => setCover(e.target.files?.[0] || null)}
        />
        <div className="mt-2 flex items-center gap-2">
          <button onClick={() => coverRef.current?.click()} className="btn-ghost !py-2 text-sm">
            {cover ? `✓ ${cover.name}` : '🖼 Choose cover photo'}
          </button>
          {cover && (
            <button onClick={clearCover} className="text-xs text-ember">
              remove
            </button>
          )}
        </div>
      </div>

      <input
        ref={sourceRef}
        type="file"
        accept="image/*,video/*"
        multiple
        className="hidden"
        onChange={pick}
      />
      <button onClick={() => sourceRef.current?.click()} disabled={busy} className="btn-primary w-full">
        {busy ? 'Reading…' : '📷 Choose screenshots or a video'}
      </button>
      <p className="mt-2 text-xs text-muted">
        Pick <strong>several screenshots</strong> of the same recipe (e.g. a caption split across
        images, or ingredients and steps on separate screens) and they're combined into one
        recipe — or pick a single video.
      </p>
      {!videoReady && (
        <p className="mt-2 text-xs text-muted">
          Videos need <code>ffmpeg</code> installed on the Pi; screenshots work now.
        </p>
      )}
      <p className="mt-2 text-xs text-muted">
        A video takes a little longer — the Pi samples frames from it, then Claude reads them.
      </p>
      <ErrorLine msg={err} />
    </Card>
  );
}

// --- Voice ------------------------------------------------------------------
function VoiceCard({
  status, onImported,
}: {
  status: ImportStatus | null; onImported: (r: ImportResponse) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);

  const send = async (file: File) => {
    setBusy(true);
    setErr(null);
    try {
      onImported(await api.importVoice(file));
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const startRec = async () => {
    setErr(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream);
      chunksRef.current = [];
      rec.ondataavailable = (e) => e.data.size && chunksRef.current.push(e.data);
      rec.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
        send(new File([blob], 'note.webm', { type: 'audio/webm' }));
      };
      rec.start();
      recorderRef.current = rec;
      setRecording(true);
    } catch {
      setErr('Could not access the microphone. You can upload an audio file instead.');
    }
  };

  const stopRec = () => {
    recorderRef.current?.stop();
    setRecording(false);
  };

  return (
    <Card
      title="From a voice note"
      subtitle="Record or upload audio; transcribed locally, then structured."
      disabled={!!status && !status.voice}
      disabledHint="Needs whisper.cpp (WHISPER_BIN + WHISPER_MODEL) and an Anthropic key."
    >
      <div className="flex gap-2">
        {recording ? (
          <button onClick={stopRec} className="btn-primary flex-1 !bg-emberDark">
            ⏺ Stop &amp; import
          </button>
        ) : (
          <button onClick={startRec} disabled={busy} className="btn-primary flex-1">
            🎙 Record
          </button>
        )}
        <input
          ref={fileRef}
          type="file"
          accept="audio/*"
          className="hidden"
          onChange={(e) => e.target.files?.[0] && send(e.target.files[0])}
        />
        <button onClick={() => fileRef.current?.click()} disabled={busy} className="btn-ghost">
          Upload
        </button>
      </div>
      {busy && <p className="mt-2 text-sm text-muted">Transcribing… this can take a bit on a Pi.</p>}
      <ErrorLine msg={err} />
    </Card>
  );
}

// --- Drive ------------------------------------------------------------------
function DriveCard() {
  const [gs, setGs] = useState<GoogleStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [summary, setSummary] = useState<DriveScanSummary | null>(null);

  useEffect(() => {
    api.googleStatus().then(setGs).catch(() => setGs(null));
  }, []);

  const scan = async () => {
    setBusy(true);
    setErr(null);
    setSummary(null);
    try {
      setSummary(await api.driveScan());
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card
      title="From Google Drive"
      subtitle="Scan a Drive folder of saved recipes (bulk load)."
      disabled={!!gs && !gs.configured}
      disabledHint="Needs a Google Desktop-app OAuth client (GOOGLE_CLIENT_SECRETS) + DRIVE_FOLDER_ID in your .env."
    >
      {gs && !gs.authorized ? (
        <Link to="/settings" className="btn-primary block w-full text-center">
          Connect your Google account in Settings →
        </Link>
      ) : gs && !gs.drive_import_folder ? (
        <div className="rounded-lg bg-cream px-3 py-2 text-sm text-muted">
          Connected — set <code>DRIVE_FOLDER_ID</code> in your .env to your Recipes folder, then restart.
        </div>
      ) : (
        <button onClick={scan} disabled={busy} className="btn-primary w-full">
          {busy ? 'Scanning…' : '🔍 Scan Drive folder'}
        </button>
      )}
      {summary && (
        <div className="mt-3 space-y-1 text-sm">
          <p className="font-medium text-herb">
            {summary.created.length} new draft{summary.created.length === 1 ? '' : 's'} from{' '}
            {summary.total_seen} file{summary.total_seen === 1 ? '' : 's'}.
          </p>
          {summary.skipped.length > 0 && (
            <p className="text-muted">{summary.skipped.length} skipped (unsupported types).</p>
          )}
          {summary.errors.length > 0 && (
            <p className="text-emberDark">{summary.errors.length} had errors.</p>
          )}
          {summary.created.length > 0 && (
            <Link to="/drafts" className="inline-block pt-1 font-medium text-ember underline">
              Review {summary.created.length} in Drafts →
            </Link>
          )}
        </div>
      )}
      <ErrorLine msg={err} />
    </Card>
  );
}
