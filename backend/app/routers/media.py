"""Media upload endpoint (Chunk F) — device camera/library photo → local store."""
from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from .. import photo_upload

router = APIRouter(prefix="/api/media", tags=["media"])


@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    """Accept an image (camera or library), fix orientation, downscale, and store it.
    Returns the DB-relative path to use as a hero_image or gallery item."""
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="Please choose an image file.")
    data = await file.read()
    rel = photo_upload.process_and_store(data, file.content_type)
    return {"path": rel}
