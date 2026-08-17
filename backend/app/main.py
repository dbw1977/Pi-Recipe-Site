"""FastAPI application entry point.

Runs migrations at startup, exposes the JSON API under /api, and serves the built
React app as static files (SPA fallback) so the whole thing is one process on the Pi.
Binds 0.0.0.0 for LAN access (CLAUDE.md rule 9); reach it at http://recipes.local.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, thumbnails
from .migrations_runner import run_migrations
from .routers import backups, drafts, featured, imports, meals, places, recipes, tags


@asynccontextmanager
async def _lifespan(app: FastAPI):
    run_migrations()  # apply numbered SQL + seed taxonomy at startup
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Pi Recipe Site", version="0.5.0 (Chunk E)", lifespan=_lifespan)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "chunk": "E"}

    app.include_router(recipes.router)
    app.include_router(places.router)
    app.include_router(meals.router)
    app.include_router(tags.router)
    app.include_router(imports.router)
    app.include_router(drafts.router)
    app.include_router(featured.router)
    app.include_router(backups.router)

    _mount_thumbs(app)
    _mount_media(app)
    _mount_frontend(app)
    return app


def _mount_thumbs(app: FastAPI) -> None:
    """Serve small derived thumbnails for the grid, generating + caching on first hit.
    Falls back to the original image if a thumbnail can't be produced (e.g. no Pillow)."""

    @app.get("/thumb/{rel_path:path}")
    def thumb(rel_path: str):
        cached = thumbnails.get_or_create(rel_path)
        if cached is not None:
            return FileResponse(str(cached), media_type="image/webp")
        original = (config.media_root() / rel_path).resolve()
        if original.is_file() and str(original).startswith(str(config.media_root().resolve())):
            return FileResponse(str(original))
        return JSONResponse({"detail": "Not found"}, status_code=404)


def _mount_media(app: FastAPI) -> None:
    """Serve imported/downloaded media (originals may live on the NAS in production)."""
    root = config.media_root()
    app.mount("/media", StaticFiles(directory=str(root)), name="media")


def _mount_frontend(app: FastAPI) -> None:
    """Serve the Vite build if present. In dev the frontend runs on its own port,
    so a missing build is fine — the API still works."""
    dist = config.FRONTEND_DIST
    assets = dist / "assets"
    index = dist / "index.html"

    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        # Never shadow the API namespace.
        if full_path.startswith("api/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        # Serve a real static file if it exists (favicon, manifest, etc.).
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and str(candidate).startswith(str(dist.resolve())):
            return FileResponse(str(candidate))
        if index.is_file():
            return FileResponse(str(index))
        return JSONResponse(
            {"detail": "Frontend not built. Run `npm run build` in ./frontend."},
            status_code=200,
        )


app = create_app()
