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

from . import config
from .migrations_runner import run_migrations
from .routers import recipes, tags


@asynccontextmanager
async def _lifespan(app: FastAPI):
    run_migrations()  # apply numbered SQL + seed taxonomy at startup
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Pi Recipe Site", version="0.1.0 (Chunk A)", lifespan=_lifespan)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "chunk": "A"}

    app.include_router(recipes.router)
    app.include_router(tags.router)

    _mount_frontend(app)
    return app


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
