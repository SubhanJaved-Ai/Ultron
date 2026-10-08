"""Hologram route — serves the 3D Holographic web interface."""

from __future__ import annotations

import pathlib

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

hologram_router = APIRouter()

_INDEX_HTML_PATH = pathlib.Path(__file__).parent / "static" / "index.html"


@hologram_router.get("/hologram", response_class=HTMLResponse)
async def serve_hologram() -> HTMLResponse:
    """Serve the 3D Hologram PWA interface with cache-busting headers."""
    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
    }
    if _INDEX_HTML_PATH.is_file():
        return HTMLResponse(
            content=_INDEX_HTML_PATH.read_text(encoding="utf-8"),
            headers=headers,
        )
    return HTMLResponse(
        content="<html><body><h1>Jarvis 2.0 Hologram Interface</h1></body></html>",
        status_code=200,
        headers=headers,
    )
