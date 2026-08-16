"""Voice-note import (spec §5d): whisper.cpp (local) → transcript → Claude structuring.

Audio never leaves the Pi for transcription (Anthropic's API doesn't transcribe audio).
Both the whisper binary/model and the Anthropic key are optional; a missing one disables
only this path with a clear message.
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
from .errors import ExtractionError, FeatureUnavailable
from .tags import load_tag_index
from .url_import import ImportResult


def transcription_available() -> bool:
    return bool(config.WHISPER_BIN and config.WHISPER_MODEL)


def _require_whisper() -> None:
    if not config.WHISPER_BIN or not config.WHISPER_MODEL:
        raise FeatureUnavailable(
            "Voice import needs whisper.cpp. Set WHISPER_BIN (the binary, e.g. whisper-cli) "
            "and WHISPER_MODEL (a .bin model) in your .env.",
            needs="WHISPER_BIN + WHISPER_MODEL",
        )
    if not Path(config.WHISPER_BIN).exists():
        raise FeatureUnavailable(
            f"WHISPER_BIN path does not exist: {config.WHISPER_BIN}", needs="WHISPER_BIN"
        )
    if not Path(config.WHISPER_MODEL).exists():
        raise FeatureUnavailable(
            f"WHISPER_MODEL path does not exist: {config.WHISPER_MODEL}", needs="WHISPER_MODEL"
        )


def _to_wav16k(src: Path) -> Path:
    """whisper.cpp wants 16 kHz mono WAV. Convert with ffmpeg if available; otherwise pass
    the file through (works if the user already uploaded a 16 kHz WAV)."""
    if shutil.which("ffmpeg") is None:
        return src
    dst = src.with_suffix(".16k.wav")
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), "-ar", "16000", "-ac", "1", str(dst)],
        check=True, capture_output=True,
    )
    return dst


def transcribe(audio_bytes: bytes, content_type: str | None) -> str:
    _require_whisper()
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        suffix = ".wav"
        if content_type and "webm" in content_type:
            suffix = ".webm"
        elif content_type and ("mp4" in content_type or "m4a" in content_type):
            suffix = ".m4a"
        elif content_type and "mpeg" in content_type:
            suffix = ".mp3"
        src = tmp / f"audio{suffix}"
        src.write_bytes(audio_bytes)
        try:
            wav = _to_wav16k(src)
        except subprocess.CalledProcessError as e:  # pragma: no cover
            raise ExtractionError(f"Audio conversion failed: {e.stderr.decode()[:400]}")

        out_base = tmp / "out"
        try:
            subprocess.run(
                [config.WHISPER_BIN, "-m", config.WHISPER_MODEL, "-f", str(wav),
                 "-otxt", "-of", str(out_base), "-nt"],
                check=True, capture_output=True, timeout=1800,
            )
        except subprocess.CalledProcessError as e:  # pragma: no cover
            raise ExtractionError(f"whisper.cpp failed: {e.stderr.decode()[:400]}")
        txt = out_base.with_suffix(".txt")
        if not txt.exists():
            raise ExtractionError("whisper.cpp produced no transcript.")
        return txt.read_text().strip()


def import_voice(
    conn: sqlite3.Connection,
    audio_bytes: bytes,
    content_type: str | None,
    *,
    photos: list[tuple[bytes, str | None]] | None = None,
) -> ImportResult:
    transcript = transcribe(audio_bytes, content_type)
    if not transcript:
        raise ExtractionError("The audio transcribed to an empty transcript.")
    if not claude.available():
        raise FeatureUnavailable(
            "Voice transcription succeeded, but structuring the transcript into a recipe "
            "needs the Anthropic API. Add ANTHROPIC_API_KEY to your .env.",
            needs="ANTHROPIC_API_KEY",
        )
    tag_index = load_tag_index(conn)
    extracted = claude.structure_text(
        transcript, tag_index.allowed_by_category, kind="voice transcript"
    )

    audio_rel = media.save_bytes(audio_bytes, content_type=content_type, filename="voice")
    media_rows = [{"kind": "audio", "path": audio_rel, "caption": "voice note"}]
    hero = None
    for data, ctype in photos or []:
        rel = media.save_bytes(data, content_type=ctype)
        media_rows.append({"kind": "image", "path": rel, "caption": None})
        hero = hero or rel

    recipe = to_recipe_input(
        extracted, source_type="voice", tag_index=tag_index, hero_image=hero
    )
    return ImportResult(recipe=recipe, media=media_rows)
