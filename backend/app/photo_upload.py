"""Device photo upload processing (Chunk F, spec §18 / CLAUDE.md rule 3).

Phone photos are often EXIF-rotated and huge. We fix orientation, downscale oversized
images, and re-encode to JPEG before storing in the local media store (originals on the
NAS). Pillow is imported lazily; if it's missing we store the bytes unprocessed rather
than fail (rule 8). Thumbnails are produced on demand by the /thumb route (Chunk C).
"""
from __future__ import annotations

import io

from .extraction import media

_MAX_EDGE = 2000  # longest side; keeps the Pi and the grid fast


def process_and_store(data: bytes, content_type: str | None) -> str:
    """Return the DB-relative media path for a processed (or, as a fallback, raw) image."""
    try:
        from PIL import Image, ImageOps  # lazy
    except ImportError:
        return media.save_bytes(data, content_type=content_type, filename="upload")

    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)          # honor the camera's rotation flag
        img = img.convert("RGB")
        w, h = img.size
        if max(w, h) > _MAX_EDGE:
            scale = _MAX_EDGE / max(w, h)
            img = img.resize((round(w * scale), round(h * scale)))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85, optimize=True)
        return media.save_bytes(buf.getvalue(), content_type="image/jpeg", filename="upload.jpg")
    except Exception:
        # Corrupt/unsupported image — keep the original rather than losing the upload.
        return media.save_bytes(data, content_type=content_type, filename="upload")
