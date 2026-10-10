"""Hologram route — serves the 3D Holographic web interface."""

from __future__ import annotations

import pathlib

from fastapi import APIRouter, Request
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


@hologram_router.get("/api/tts")
async def get_speech_audio(text: str = ""):
    """Stream synthesized WAV speech audio directly to the browser."""
    import asyncio

    from fastapi import HTTPException
    from fastapi.responses import Response

    query_text = (text or "").strip()
    if not query_text:
        raise HTTPException(status_code=400, detail="Query text required")

    from openjarvis.server.tts_engine import synthesize_wav

    wav_bytes = await asyncio.to_thread(synthesize_wav, query_text)
    if not wav_bytes:
        raise HTTPException(status_code=500, detail="TTS synthesis unavailable")

    return Response(
        content=wav_bytes,
        media_type="audio/wav",
        headers={
            "Cache-Control": "public, max-age=3600",
            "Content-Length": str(len(wav_bytes)),
        },
    )


@hologram_router.post("/api/hologram/directive")
async def handle_directive(request: Request, payload: dict) -> dict:
    """Process user voice or text directive and return articulate reply.

    Wires directly into the full JarvisSystem runtime (tools, skills, memory,
    workflows, and inference engines) if available on app.state.system,
    falling back to standalone autonomous intelligence.
    """
    import asyncio
    import logging

    logger = logging.getLogger("openjarvis.server.hologram")
    directive = str(payload.get("directive") or payload.get("query") or "").strip()
    if not directive:
        return {"reply": "Yes, sir? I am listening."}

    # 1. Full Backend Execution: route through running JarvisSystem if wired
    system = getattr(request.app.state, "system", None)
    if system is not None and hasattr(system, "ask"):
        try:
            result = await asyncio.to_thread(system.ask, directive)
            if isinstance(result, dict) and result.get("content"):
                return {
                    "reply": result["content"],
                    "actions": result.get("tool_calls", []),
                    "status": "executed",
                }
        except Exception as exc:
            logger.warning("JarvisSystem execution failed in hologram directive: %s", exc)

    # 2. Standalone / Autonomous intelligence fallback
    from openjarvis.server.autonomous_intelligence import generate_autonomous_response

    reply = await asyncio.to_thread(generate_autonomous_response, directive)
    return {"reply": reply, "status": "autonomous_fallback"}
