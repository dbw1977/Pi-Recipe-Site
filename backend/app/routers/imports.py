"""Import endpoints — the four ingestion paths, all landing as drafts (spec §5, §6).

Missing credentials disable only the affected path with a clear 503 message; nothing
crashes and nothing auto-publishes (CLAUDE.md rules 8 & 10).
"""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from .. import crud, crud_places
from ..db import get_connection, transaction
from ..extraction import claude, drive, url_import, video, voice
from ..extraction.errors import ExtractionError, FeatureUnavailable
from ..extraction.screenshot import import_screenshots
from ..extraction.place_import import import_place_screenshots
from ..extraction.duplicates import find_duplicate
from ..schemas import RecipeIn

router = APIRouter(prefix="/api/imports", tags=["imports"])


# --------------------------------------------------------------------------- #
# Shared persistence
# --------------------------------------------------------------------------- #
def _persist(result: url_import.ImportResult) -> dict:
    with transaction() as conn:
        dup = find_duplicate(
            conn, title=result.recipe.title, source_url=result.recipe.source_url,
            statuses=("published", "draft"),
        )
        rid = crud.create_draft(conn, result.recipe, result.media)
        draft = crud.get_recipe(conn, rid)
    return {"draft": draft.model_dump(), "duplicate": dup}


def _persist_stub(err: ExtractionError, *, source_type: str, source_url: str | None = None) -> dict:
    """Claude returned unparseable output — still open a review draft with what we have
    so the user can finish it (spec §10)."""
    stub = RecipeIn(
        title="Imported draft — needs review",
        description=(err.partial.get("raw") or "")[:2000] or None,
        source_type=source_type,
        source_url=source_url,
        status="draft",
    )
    with transaction() as conn:
        rid = crud.create_draft(conn, stub, [])
        draft = crud.get_recipe(conn, rid)
    return {"draft": draft.model_dump(), "duplicate": None, "warning": err.message}


# --------------------------------------------------------------------------- #
# Status — which paths are enabled (drives the Import UI)
# --------------------------------------------------------------------------- #
@router.get("/status")
def status() -> dict:
    return {
        "url": True,  # offline scraper always works; AI fallback if Claude is on
        "claude": claude.available(),
        "screenshot": claude.available(),
        "video": claude.available() and video.frames_available(),
        "voice_transcription": voice.transcription_available(),
        "voice": voice.transcription_available() and claude.available(),
        "drive_configured": drive.available(),
        "drive_authorized": drive.available() and drive.authorized(),
    }


# --------------------------------------------------------------------------- #
# URL
# --------------------------------------------------------------------------- #
class UrlIn(BaseModel):
    url: str


@router.post("/url")
def import_url_endpoint(payload: UrlIn):
    conn = get_connection()
    try:
        result = url_import.import_url(conn, payload.url)
    except FeatureUnavailable as e:
        raise HTTPException(status_code=503, detail=e.message)
    except ExtractionError as e:
        return _persist_stub(e, source_type="url", source_url=payload.url)
    finally:
        conn.close()
    return _persist(result)


# --------------------------------------------------------------------------- #
# Screenshot(s) OR video (multipart: one or more `file` parts + optional `extra` cover)
#   - files are images -> Claude vision reads them all together as one recipe
#   - first file is a video -> ffmpeg samples frames, Claude vision reads them
# An optional `extra` image is used as the recipe's cover (hero) photo.
# --------------------------------------------------------------------------- #
@router.post("/screenshot")
async def import_screenshot_endpoint(
    file: list[UploadFile] = File(...),
    extra: list[UploadFile] | None = File(default=None),
):
    primaries = [(await uf.read(), uf.content_type) for uf in file]

    # First supplied image among `extra` is the cover/hero photo.
    cover: tuple[bytes, str | None] | None = None
    for uf in extra or []:
        data = await uf.read()
        ctype = uf.content_type or ""
        if ctype.startswith("image/") and cover is None:
            cover = (data, ctype)

    is_video = (file[0].content_type or "").startswith("video/")
    conn = get_connection()
    try:
        if is_video:
            vbytes, vct = primaries[0]
            extra_media = [(cover[0], cover[1], "image")] if cover else None
            result = video.import_video(conn, vbytes, vct, extra_media=extra_media)
        else:
            images = [(b, ct) for b, ct in primaries if (ct or "").startswith("image/")]
            result = import_screenshots(conn, images, cover=cover)
    except FeatureUnavailable as e:
        raise HTTPException(status_code=503, detail=e.message)
    except ExtractionError as e:
        return _persist_stub(e, source_type="video" if is_video else "instagram")
    finally:
        conn.close()
    return _persist(result)


# --------------------------------------------------------------------------- #
# Place from screenshot(s) (Chunk D) — one or more images + optional cover photo
# --------------------------------------------------------------------------- #
def _persist_place(result) -> dict:
    with transaction() as conn:
        pid = crud_places.create_draft(conn, result.place, result.media)
        draft = crud_places.get_place(conn, pid)
    return {"draft": draft.model_dump(), "duplicate": None}


@router.post("/place/screenshot")
async def import_place_screenshot_endpoint(
    file: list[UploadFile] = File(...),
    extra: list[UploadFile] | None = File(default=None),
):
    images = [(await uf.read(), uf.content_type) for uf in file if (uf.content_type or "").startswith("image/")]
    cover: tuple[bytes, str | None] | None = None
    for uf in extra or []:
        data = await uf.read()
        ctype = uf.content_type or ""
        if ctype.startswith("image/") and cover is None:
            cover = (data, ctype)

    conn = get_connection()
    try:
        result = import_place_screenshots(conn, images, cover=cover)
    except FeatureUnavailable as e:
        raise HTTPException(status_code=503, detail=e.message)
    except ExtractionError as e:
        # Open a place draft with whatever we have so the user can finish it (spec §10).
        from ..schemas import PlaceIn
        stub = PlaceIn(name="Imported place — needs review", our_notes=(e.partial.get("raw") or "")[:2000] or None, status="draft")
        with transaction() as conn2:
            pid = crud_places.create_draft(conn2, stub, [])
            draft = crud_places.get_place(conn2, pid)
        return {"draft": draft.model_dump(), "duplicate": None, "warning": e.message}
    finally:
        conn.close()
    return _persist_place(result)


# --------------------------------------------------------------------------- #
# Voice (multipart: audio + optional photos)
# --------------------------------------------------------------------------- #
@router.post("/voice")
async def import_voice_endpoint(
    file: UploadFile = File(...),
    photos: list[UploadFile] | None = File(default=None),
):
    audio_bytes = await file.read()
    photo_data = [(await p.read(), p.content_type) for p in (photos or [])]

    conn = get_connection()
    try:
        result = voice.import_voice(conn, audio_bytes, file.content_type, photos=photo_data)
    except FeatureUnavailable as e:
        raise HTTPException(status_code=503, detail=e.message)
    except ExtractionError as e:
        return _persist_stub(e, source_type="voice")
    finally:
        conn.close()
    return _persist(result)


# --------------------------------------------------------------------------- #
# Google Drive
# --------------------------------------------------------------------------- #
@router.post("/drive/scan")
def drive_scan_endpoint():
    try:
        with transaction() as conn:
            def persist(recipe: RecipeIn, media_rows: list[dict]) -> int:
                return crud.create_draft(conn, recipe, media_rows)

            summary = drive.scan(conn, persist)
    except FeatureUnavailable as e:
        raise HTTPException(status_code=503, detail=e.message)
    return summary


@router.get("/drive/auth-url")
def drive_auth_url_endpoint(request: Request):
    redirect_uri = str(request.url_for("drive_callback"))
    try:
        return {"url": drive.auth_url(redirect_uri), "redirect_uri": redirect_uri}
    except FeatureUnavailable as e:
        raise HTTPException(status_code=503, detail=e.message)


@router.get("/drive/callback", name="drive_callback")
def drive_callback(request: Request, code: str | None = None, error: str | None = None):
    if error or not code:
        return RedirectResponse("/import?drive=error")
    redirect_uri = str(request.url_for("drive_callback"))
    try:
        drive.finish_auth(code, redirect_uri)
    except FeatureUnavailable as e:
        raise HTTPException(status_code=503, detail=e.message)
    return RedirectResponse("/import?drive=connected")
