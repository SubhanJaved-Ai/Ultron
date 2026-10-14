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

    Wires directly into Ultron's Frontier LLM Brain with dynamic address preferences
    and execution runtime.
    """
    import asyncio
    import logging
    import re

    from openjarvis.core.user_preferences import get_user_address, set_user_address
    from openjarvis.server.llm_client import ultron_brain

    logger = logging.getLogger("openjarvis.server.hologram")
    current_user = getattr(request.state, "user", None)
    user_id = current_user.id if current_user else None
    directive = str(payload.get("directive") or payload.get("query") or "").strip()
    history = payload.get("history") or []
    user_addr = get_user_address(user_id=user_id)

    if not directive:
        greeting = (
            f"Yes, {user_addr}? I am listening."
            if user_addr
            else "I am listening. Ready for your directive."
        )
        return {"reply": greeting}

    # 0. Prompt Injection & Attack Safeguard
    try:
        from openjarvis.security.injection_scanner import InjectionScanner
        from openjarvis.security.types import ThreatLevel

        scanner = InjectionScanner()
        scan_res = scanner.scan(directive)
        if not scan_res.is_clean and scan_res.threat_level in (
            ThreatLevel.MEDIUM,
            ThreatLevel.HIGH,
            ThreatLevel.CRITICAL,
        ):
            logger.warning(
                "Injection pattern blocked in hologram directive: threat=%s findings=%s",
                scan_res.threat_level,
                scan_res.findings,
            )
            addr_suffix = f", {user_addr}" if user_addr else ""
            return {
                "reply": f"Security protocol engaged: Malicious directive pattern or instruction override rejected{addr_suffix}.",
                "status": "security_blocked",
                "actions": [],
            }
    except Exception as exc:
        logger.debug("Injection scanner execution skipped: %s", exc)

    # Intercept "Call me ..." or "My name is ..." to persist user preference instantly
    call_me_match = re.search(
        r"(?:call me|my name is|address me as|refer to me as)\s+(.+)",
        directive,
        re.IGNORECASE,
    )
    if call_me_match:
        target_name = call_me_match.group(1).strip()
        saved = set_user_address(target_name, user_id=user_id)
        if saved:
            return {
                "reply": f"Understood, {saved}. I have saved your preference and will address you as {saved}.",
                "status": "preference_saved",
            }

    # Intercept memory backend and storage location queries
    if re.search(
        r"where is (?:my )?(?:memory|data|database) saved|memory (?:status|backend)|what database",
        directive,
        re.IGNORECASE,
    ):
        from openjarvis.storage.memory_backend import MemoryBackendManager

        mem_status = MemoryBackendManager.get_status()
        return {
            "reply": mem_status.get("message", "Local memory active."),
            "status": "memory_status",
            "actions": [],
        }

    # Intercept identity queries to accurately reflect current address preference
    if re.search(
        r"^(?:who am i|what is my name|what's my name)\??$",
        directive.strip(),
        re.IGNORECASE,
    ):
        if not user_addr:
            return {
                "reply": "You haven't specified your preferred name or title yet. You can tell me by saying 'Call me [name]' or 'My name is [name]'.",
                "status": "identity_query",
                "actions": [],
            }
        else:
            return {
                "reply": f"You are {user_addr}. All systems and operational parameters are aligned under your profile.",
                "status": "identity_query",
                "actions": [],
            }

    # Execution registration in ActiveExecutionContextStore (TSK-P5-01 / GAP-01)
    import uuid

    from openjarvis.server.cancellation import get_execution_store

    store = get_execution_store()
    effective_session_id = user_id or "default"
    ctx_id = f"ctx-holo-{uuid.uuid4().hex[:8]}"
    token = store.register(ctx_id, owner_session_id=effective_session_id)
    active_token = store.register("active", owner_session_id=effective_session_id)

    try:
        if token.is_cancelled or active_token.is_cancelled:
            return {
                "reply": "Directive execution was cancelled by operator.",
                "status": "cancelled",
                "actions": [],
            }

        # 1. Full Backend Execution: route through running JarvisSystem if wired
        system = getattr(request.app.state, "system", None)
        if system is not None and hasattr(system, "ask"):
            try:
                ask_kwargs = {"operator_id": user_id} if user_id else {}
                result = await asyncio.to_thread(
                    system.ask,
                    directive,
                    **ask_kwargs,
                )
                if token.is_cancelled or active_token.is_cancelled:
                    return {
                        "reply": "Directive aborted cleanly by operator.",
                        "status": "cancelled",
                        "actions": [],
                    }
                if isinstance(result, dict) and result.get("content"):
                    raw_actions = (
                        result.get("tool_results") or result.get("tool_calls") or []
                    )
                    normalized_actions = []
                    for act in raw_actions:
                        if isinstance(act, dict):
                            act_name = act.get("tool_name") or act.get("name") or "action"
                            act_args = act.get("arguments") or act.get("args") or {}
                            act_success = act.get("success") is not False
                            act_content = act.get("content") or act.get("output") or ""
                            normalized_actions.append(
                                {
                                    "name": act_name,
                                    "arguments": act_args,
                                    "success": act_success,
                                    "status": "executed" if act_success else "failed",
                                    "output": (
                                        str(act_content)[:300] if act_content else ""
                                    ),
                                }
                            )
                    return {
                        "reply": result["content"],
                        "actions": normalized_actions,
                        "status": "executed",
                    }
            except Exception as exc:
                logger.warning(
                    "JarvisSystem execution failed in hologram directive: %s", exc
                )

        # 2. Frontier LLM Brain Execution (Gemini / Smart Reasoning)
        try:
            if token.is_cancelled or active_token.is_cancelled:
                return {
                    "reply": "Directive aborted cleanly by operator.",
                    "status": "cancelled",
                    "actions": [],
                }
            reply = await asyncio.to_thread(
                ultron_brain.generate_response, directive, history=history
            )
            if token.is_cancelled or active_token.is_cancelled:
                return {
                    "reply": "Directive aborted cleanly by operator.",
                    "status": "cancelled",
                    "actions": [],
                }
            return {"reply": reply, "status": "brain_executed"}
        except Exception as exc:
            logger.error("UltronBrain generation failed: %s", exc)

        # 3. Final safe fallback
        addr_suffix = f", {user_addr}" if user_addr else ""
        return {
            "reply": f"Standing by to execute your objective{addr_suffix}.",
            "status": "fallback",
        }
    finally:
        store.unregister(ctx_id)
        store.unregister("active")


# ---------------------------------------------------------------------------
# Personality API  (TSK-P5-02 — Soul Circuit)
# ---------------------------------------------------------------------------


@hologram_router.get("/api/hologram/personality")
async def get_personality_settings() -> dict:
    """Return the current personality dimension settings.

    Returns a JSON object with keys ``formality``, ``verbosity``, and
    ``warmth``, each a float in ``[0.0, 1.0]``.
    """
    from openjarvis.core.user_preferences import get_personality

    return {"personality": get_personality()}


@hologram_router.post("/api/hologram/personality")
async def update_personality_settings(payload: dict) -> dict:
    """Persist personality dimension updates.

    Accepts a JSON body with any subset of ``formality``, ``verbosity``,
    ``warmth`` as floats in ``[0.0, 1.0]``.  Unknown keys are ignored.
    Values outside the valid range return HTTP 422.

    Returns the full merged personality dict after saving.
    """
    import logging

    from fastapi import HTTPException

    from openjarvis.core.user_preferences import set_personality

    logger = logging.getLogger("openjarvis.server.hologram.personality")
    updates = payload.get("personality") or payload
    if not isinstance(updates, dict):
        raise HTTPException(
            status_code=422,
            detail="Payload must be a JSON object with personality dimension keys.",
        )
    try:
        merged = set_personality(updates)
    except ValueError as exc:
        logger.warning("Invalid personality update rejected: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"personality": merged}
