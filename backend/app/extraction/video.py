"""Video import: sample frames with ffmpeg, read them with Claude vision (spec §5b).

Claude can't watch a video, so we pull a handful of frames spread across the clip — enough
to catch on-screen ingredient overlays and the finished dish — and hand those to the vision
model. ffmpeg is optional: without it this path disables gracefully (CLAUDE.md rule 8),
never crashing the app or the other importers. The original video is kept in the media
store alongside a chosen frame used as the hero (unless the user supplies a cover photo).
"""
from __future__ import annotations

import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path

from .. import config
from . import claude, media
from .draft import to_recipe_input
from .errors import FeatureUnavailable
from .tags import load_tag_index
from .url_import import ImportResult

_SRC_EXT = {
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/webm": ".webm",
    "video/x-matroska": ".mkv",
    "video/x-msvideo": ".avi",
}


def frames_available() -> bool:
    """True when ffmpeg is on PATH (or configured) — required to sample frames."""
    return shutil.which(config.FFMPEG_BIN) is not None


def _src_ext(content_type: str | None) -> str:
    ct = (content_type or "").split(";")[0].strip().lower()
    return _SRC_EXT.get(ct, ".mp4")


def _duration_seconds(path: Path) -> float | None:
    """Best-effort clip length via ffprobe (if installed) so frames spread evenly."""
    probe = shutil.which("ffprobe")
    if not probe:
        return None
    try:
        out = subprocess.run(
            [probe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=20,
        )
        return float(out.stdout.strip())
    except (ValueError, subprocess.SubprocessError, OSError):
        return None


def extract_frames(
    video_bytes: bytes, content_type: str | None, count: int | None = None
) -> list[bytes]:
    """Sample up to `count` JPEG frames spread across the video, downscaled for vision."""
    count = count or config.VIDEO_FRAME_COUNT
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        src = tmp / f"input{_src_ext(content_type)}"
        src.write_bytes(video_bytes)

        dur = _duration_seconds(src)
        # Even spacing when we know the duration; otherwise a frame every 2s, capped by count.
        rate = f"{count}/{dur:.3f}" if dur and dur > 0 else "1/2"
        pattern = str(tmp / "f_%03d.jpg")
        cmd = [
            config.FFMPEG_BIN, "-hide_banner", "-loglevel", "error", "-i", str(src),
            "-vf", f"fps={rate},scale='min(768,iw)':-2",
            "-frames:v", str(count), "-q:v", "3", pattern,
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=180, check=True)
        except (subprocess.SubprocessError, OSError) as e:
            raise FeatureUnavailable(
                "Couldn't read that video — ffmpeg failed to open it. Try a different file, "
                "or grab a screenshot of the recipe instead."
            ) from e
        return [f.read_bytes() for f in sorted(tmp.glob("f_*.jpg"))]


def import_video(
    conn: sqlite3.Connection,
    video_bytes: bytes,
    content_type: str | None,
    *,
    extra_media: list[tuple[bytes, str | None, str]] | None = None,
) -> ImportResult:
    """extra_media: optional (bytes, content_type, kind) — a supplied cover photo wins as hero."""
    if not claude.available():
        raise FeatureUnavailable(
            "Video import reads the clip's frames with Claude vision, so it needs the "
            "Anthropic key. Add ANTHROPIC_API_KEY to your .env to enable it.",
            needs="ANTHROPIC_API_KEY",
        )
    if not frames_available():
        raise FeatureUnavailable(
            "Video import needs ffmpeg on the Pi to sample frames from the clip. Install it "
            "with: sudo apt install ffmpeg — then it works automatically. (Screenshots don't "
            "need it.)",
            needs="ffmpeg",
        )

    tag_index = load_tag_index(conn)
    frames = extract_frames(video_bytes, content_type)
    if not frames:
        raise FeatureUnavailable(
            "That video produced no readable frames. Try a screenshot of the recipe instead."
        )
    extracted = claude.extract_from_images(frames, "image/jpeg", tag_index.allowed_by_category)

    # Keep the original video in the media store.
    video_rel = media.save_bytes(video_bytes, content_type=content_type, filename="video")
    media_rows = [{"kind": "video", "path": video_rel, "caption": "source video"}]

    # Hero: a supplied cover photo wins; otherwise a frame from later in the clip, where the
    # finished dish usually appears.
    hero: str | None = None
    for data, ctype, kind in extra_media or []:
        rel = media.save_bytes(data, content_type=ctype)
        media_rows.append({"kind": kind, "path": rel, "caption": None})
        if kind == "image" and hero is None:
            hero = rel
    if hero is None:
        idx = min(len(frames) - 1, int(len(frames) * 0.6))
        hero = media.save_bytes(frames[idx], content_type="image/jpeg", filename="frame.jpg")
        media_rows.append({"kind": "image", "path": hero, "caption": "video frame"})

    recipe = to_recipe_input(
        extracted, source_type="video", tag_index=tag_index, hero_image=hero
    )
    return ImportResult(recipe=recipe, media=media_rows)
