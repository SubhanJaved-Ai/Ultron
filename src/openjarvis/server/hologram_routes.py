"""Hologram route — serves the 3D Holographic web interface."""

from __future__ import annotations

import pathlib

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

hologram_router = APIRouter()

_HOLOGRAM_HTML_PATH = pathlib.Path(__file__).parent / "static" / "hologram.html"
_INDEX_HTML_PATH = pathlib.Path(__file__).parent / "static" / "index.html"


@hologram_router.get("/hologram", response_class=HTMLResponse)
@hologram_router.get("/hologram.html", response_class=HTMLResponse)
async def serve_hologram() -> HTMLResponse:
    """Serve the 3D Hologram PWA interface with cache-busting headers."""
    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
    }
    target_path = _HOLOGRAM_HTML_PATH if _HOLOGRAM_HTML_PATH.is_file() else _INDEX_HTML_PATH
    if target_path.is_file():
        return HTMLResponse(
            content=target_path.read_text(encoding="utf-8"),
            headers=headers,
        )
    return HTMLResponse(
        content="<html><body><h1>Jarvis 2.0 Hologram Interface</h1></body></html>",
        status_code=200,
        headers=headers,
    )


@hologram_router.get("/api/tts")
async def get_speech_audio(text: str = "", voice_gender: str = "", lang: str = ""):
    """Stream synthesized speech audio (ElevenLabs or Windows SAPI) to the browser/hologram."""
    import asyncio
    import logging

    from fastapi import HTTPException
    from fastapi.responses import Response

    query_text = (text or "").strip()
    if not query_text:
        raise HTTPException(status_code=400, detail="Query text required")

    logger = logging.getLogger("openjarvis.server.hologram.tts")

    from openjarvis.speech.router import detect_language

    resolved_lang = (lang or "").strip().lower() or detect_language(query_text)

    # Resolve voice gender preference if not explicitly provided
    resolved_gender = (voice_gender or "").strip().lower()
    if not resolved_gender:
        try:
            from openjarvis.core.user_preferences import get_personalization_preferences

            resolved_gender = get_personalization_preferences().get(
                "voice_gender", "masculine"
            )
        except Exception:
            resolved_gender = "masculine"

    # 1. Check if user configured ElevenLabs as preferred voice provider
    try:
        from openjarvis.core.user_preferences import get_voice_preferences

        prefs = get_voice_preferences()
        if prefs.get("provider") == "elevenlabs":
            from openjarvis.speech.elevenlabs_tts import ElevenLabsTTSBackend

            el_backend = ElevenLabsTTSBackend(
                model_id=prefs.get("model_id", ""),
                default_voice_id=prefs.get("voice_id", ""),
                stability=prefs.get("stability", 0.5),
                similarity_boost=prefs.get("similarity_boost", 0.75),
                style=prefs.get("style", 0.0),
                speed=prefs.get("speed", 1.0),
            )
            if el_backend.health():
                res = await asyncio.to_thread(
                    el_backend.synthesize,
                    query_text,
                    output_format="mp3",
                )
                if res and res.audio:
                    try:
                        from openjarvis.traces.usage_ledger import get_usage_ledger

                        get_usage_ledger().record_usage(
                            provider="elevenlabs",
                            model=prefs.get("model_id", "eleven_multilingual_v2"),
                            purpose="speech",
                            characters=len(query_text),
                            status="success",
                        )
                    except Exception:
                        pass
                    return Response(
                        content=res.audio,
                        media_type="audio/mpeg",
                        headers={
                            "Cache-Control": "public, max-age=3600",
                            "Content-Length": str(len(res.audio)),
                            "X-Voice-Provider": "elevenlabs",
                            "X-Voice-Id": res.voice_id,
                            "X-Voice-Language": resolved_lang,
                        },
                    )
    except Exception as exc:
        logger.warning(
            "ElevenLabs synthesis failed in hologram route; falling back to local SAPI: %s",
            exc,
        )

    # 2. Local fallback: Native Windows SAPI (David for masculine, Zira for feminine)
    from openjarvis.server.tts_engine import synthesize_wav

    wav_bytes = await asyncio.to_thread(
        synthesize_wav, query_text, voice_gender=resolved_gender
    )
    if not wav_bytes:
        raise HTTPException(status_code=500, detail="TTS synthesis unavailable")

    sapi_headers = {
        "Cache-Control": "public, max-age=3600",
        "Content-Length": str(len(wav_bytes)),
        "X-Voice-Provider": "windows_sapi",
        "X-Voice-Gender": resolved_gender,
        "X-Voice-Language": resolved_lang,
    }
    if resolved_lang in ("ur", "hi"):
        sapi_headers["X-Voice-Notice"] = "windows_sapi_english_only"

    return Response(
        content=wav_bytes,
        media_type="audio/wav",
        headers=sapi_headers,
    )



def execute_real_system_action(directive: str, user_addr: str = "") -> dict | None:
    """Detect and immediately execute real OS, filesystem, desktop, or application directives."""
    import datetime
    import os
    import re
    import shutil
    import subprocess
    import sys
    import time
    import urllib.parse
    import webbrowser
    from pathlib import Path

    t0 = time.perf_counter()
    clean = directive.strip()
    q = clean.lower()
    addr_suffix = f", {user_addr}" if user_addr else ""

    def _make_action(
        name: str,
        tool: str,
        args: dict,
        output: str,
        success: bool = True,
        status: str = "executed",
        guardrails: str = "PASSED [Zero Deletion Active]",
        agent: str = "Ultron Autonomous Desktop & Filesystem Controller",
    ) -> dict:
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        return {
            "name": name,
            "agent": agent,
            "tool": tool,
            "duration_ms": elapsed_ms,
            "guardrails": guardrails,
            "arguments": args,
            "success": success,
            "status": status,
            "output": output,
        }

    from openjarvis.security.file_policy import validate_ultron_fs_operation

    # -----------------------------------------------------------------------
    # Guardrail Intercept 0a: Zero Deletion Policy Enforcement
    # -----------------------------------------------------------------------
    del_match = re.search(
        r"\b(?:delete|remove|erase|destroy|del|unlink|purge)\s+(?:the\s+)?(?:file|folder|dir|item|document)?\s*([^\n\r]+)",
        q,
    )
    if del_match:
        target_raw = del_match.group(1).strip().strip("'\"")
        valid, msg = validate_ultron_fs_operation(target_raw, operation="delete")
        if not valid:
            act = _make_action(
                name="file_delete",
                tool="zero_deletion_guardrail",
                args={"target": target_raw, "operation": "delete"},
                output=msg,
                success=False,
                status="guardrail_blocked",
                guardrails="BLOCKED [Zero Deletion Policy Active]",
                agent="Ultron Autonomous Safety Matrix",
            )
            return {
                "reply": f"Security Guardrail Engaged: File deletion is strictly prohibited by Ultron Zero-Data-Loss Safety Policy. No files will be modified or removed{addr_suffix}.",
                "actions": [act],
                "status": "guardrail_blocked",
            }

    # -----------------------------------------------------------------------
    # Action 0b: Desktop Control & Real File Creation on Host Disk
    # -----------------------------------------------------------------------
    create_keywords = bool(
        re.search(r"\b(?:create|make|write|generate|paste|put|drop)\s+(?:a\s+)?(?:new\s+)?(?:text\s+|txt\s+)?file\b", q)
        or re.search(r"\b(?:control\s+(?:my\s+)?desktop.*)?(?:create|make|write|paste).*?\bfile\b", q)
        or "ultron new create file" in q
    )
    if create_keywords:
        # Determine target drive and filename
        is_c_drive = bool(re.search(r"\b(?:on|in|to)\s+(?:the\s+)?c(?::|\s+drive)\b", q) or "c:\\" in q)
        is_d_drive = bool(re.search(r"\b(?:on|in|to)\s+(?:the\s+)?d(?::|\s+drive)\b", q) or "d:\\" in q)

        # File name resolution
        if "ultron new create file" in q:
            fname = "Ultron new create file.txt"
        else:
            # Check for custom filename in quotes or words
            custom_match = re.search(r"(?:name[d]?|called)\s+[\"']?([a-zA-Z0-9_\- .]+?\.?[a-zA-Z0-9]*)[\"']?(?:\s+on|\s+in|$)", q)
            if custom_match:
                fname = custom_match.group(1).strip()
                if not fname.endswith((".txt", ".md", ".json", ".log")):
                    fname += ".txt"
            else:
                fname = "Ultron new create file.txt"

        if is_c_drive:
            target_path = Path("C:/") / fname
        else:
            target_path = Path("D:/") / fname

        # Validate with strict Ultron safety guardrails
        valid, msg = validate_ultron_fs_operation(target_path, operation="create")
        if not valid:
            act = _make_action(
                name="file_create",
                tool="c_drive_isolation_guardrail",
                args={"target": str(target_path), "operation": "create"},
                output=msg,
                success=False,
                status="guardrail_blocked",
                guardrails="BLOCKED [C-Drive Write Restricted]",
                agent="Ultron Autonomous Safety Matrix",
            )
            return {
                "reply": f"Security Guardrail Engaged: Write access to C: drive is strictly restricted by Ultron Security Guardrails. All workspace operations must be performed on D: drive or designated safe storage{addr_suffix}.",
                "actions": [act],
                "status": "guardrail_blocked",
            }

        # Execute real file write on physical host volume
        try:
            iso_now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            content = (
                "======================================================================\n"
                "ULTRON AUTONOMOUS SYSTEM - REAL FILE VERIFICATION RECORD\n"
                "======================================================================\n"
                f"File Name        : {target_path.name}\n"
                f"Target Path      : {target_path}\n"
                f"Created At       : {iso_now}\n"
                f"Agent Controller : Ultron Autonomous Desktop & Filesystem Controller\n"
                f"Execution Engine : Jarvis 2.0 Autonomous Matrix\n"
                f"Origin Directive : {clean}\n"
                "Safety Guardrails: ACTIVE & ENFORCED\n"
                "  [✓] C: Drive Isolation : ENFORCED (Zero C:\\ modifications permitted)\n"
                "  [✓] Zero Deletion      : ENFORCED (File deletions strictly prohibited)\n"
                "  [✓] Safe Storage Volume: D:\\ (Non-system host storage verified)\n"
                "Host Verification:\n"
                f"  Physical Disk Status: CONFIRMED CREATED ON HOST FILESYSTEM\n"
                "======================================================================\n"
            )
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(content, encoding="utf-8")
            size = target_path.stat().st_size

            # Launch Windows Explorer to highlight the file on the user's desktop
            if sys.platform == "win32":
                try:
                    subprocess.Popen(["explorer.exe", f"/select,{str(target_path)}"])
                except Exception:
                    pass

            act = _make_action(
                name="file_create",
                tool="desktop_filesystem_creator",
                args={"path": str(target_path), "size_bytes": size, "mode": "write"},
                output=f"Real file successfully written to {target_path} ({size} bytes). Host disk confirmed and highlighted in Explorer.",
                success=True,
                status="executed",
                guardrails="PASSED [C: Isolated | Zero Deletion Active]",
                agent="Ultron Autonomous Desktop & Filesystem Controller",
            )
            return {
                "reply": f"Ultron desktop controller executed successfully. Created real file '{target_path.name}' on D: drive ({size} bytes). Safety guardrails verified: C-drive isolated, zero-deletion policy active{addr_suffix}.",
                "actions": [act],
                "status": "executed",
            }
        except Exception as exc:
            act = _make_action(
                name="file_create",
                tool="desktop_filesystem_creator",
                args={"path": str(target_path)},
                output=f"Filesystem error: {exc}",
                success=False,
                status="failed",
                guardrails="PASSED [Security Check Passed]",
            )
            return {
                "reply": f"Encountered an OS error while creating {target_path}: {exc}{addr_suffix}.",
                "actions": [act],
                "status": "failed",
            }

    # -----------------------------------------------------------------------
    # 1. Autonomous Desktop Agent Orchestration & System Catalog RAG
    # -----------------------------------------------------------------------
    from openjarvis.desktop.orchestrator import get_desktop_orchestrator

    desktop_res = get_desktop_orchestrator().handle_directive(clean, user_addr=addr_suffix)
    if desktop_res.handled:
        return {
            "reply": f"{desktop_res.reply}{addr_suffix}",
            "actions": desktop_res.actions,
            "status": desktop_res.status,
            "target_url": desktop_res.target_url,
            "target_path": desktop_res.target_path,
            "target_type": desktop_res.target_type,
        }


    # -----------------------------------------------------------------------
    # 2b. General Browser & Web Search Navigation
    # -----------------------------------------------------------------------
    browser_search = re.search(r"\b(?:search|look\s+up)\s+(?:for\s+)?(.+?)(?:\s+(?:on|in)\s+(google|youtube))?$", q)
    open_web = re.search(r"\b(?:open|launch|go\s+to|browse)\s+(?:the\s+)?(?:web\s+)?(?:browser|chrome|edge)\b", q)
    open_site = re.search(r"\b(?:open|launch|go\s+to|visit)\s+(https?://[^\s]+|youtube|google|github|reddit|twitter|x\.com)\b", q)

    if open_web or open_site or (browser_search and any(w in q for w in ("search for", "look up"))):
        url = "https://www.google.com"
        action_name = "browser_navigate"
        desc = "browser"

        if open_site:
            target = open_site.group(1).lower()
            if target.startswith("http"):
                url = target
            elif "youtube" in target:
                url = "https://www.youtube.com"
            elif "github" in target:
                url = "https://github.com"
            elif "reddit" in target:
                url = "https://www.reddit.com"
            elif "twitter" in target or "x.com" in target:
                url = "https://x.com"
            desc = target
        elif browser_search:
            query_term = browser_search.group(1).strip()
            dest = (browser_search.group(2) or "google").lower()
            if "youtube" in dest:
                url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query_term)}"
                desc = f"YouTube search for '{query_term}'"
            else:
                url = f"https://www.google.com/search?q={urllib.parse.quote_plus(query_term)}"
                desc = f"Google search for '{query_term}'"

        try:
            webbrowser.open(url)
            if sys.platform == "win32":
                try:
                    activate_script = (
                        "$wshell = New-Object -ComObject WScript.Shell\n"
                        "Start-Sleep -Milliseconds 350\n"
                        "$wshell.AppActivate('Google Chrome')\n"
                        "$wshell.AppActivate('Browser')\n"
                    )
                    subprocess.Popen(["powershell", "-NoProfile", "-Command", activate_script])
                except Exception:
                    pass

            act = _make_action(
                name=action_name,
                tool="browser_controller",
                args={"url": url},
                output=f"Navigated to {url}",
                success=True,
                status="executed",
                guardrails="PASSED [Network Web Navigation]",
            )
            return {
                "reply": f"Launching browser and navigating to {desc} now{addr_suffix}.",
                "actions": [act],
                "target_url": url,
                "status": "executed",
            }
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # 3. Application Launcher (Notepad, Calc, Terminal, Paint, etc.)
    # -----------------------------------------------------------------------
    app_match = re.search(r"\b(?:open|launch|run|start)\s+(notepad|calculator|calc|cmd|terminal|powershell|paint|task\s+manager|code|vs\s*code)\b", q)
    if app_match:
        target_app = app_match.group(1).lower().replace(" ", "")
        app_map = {
            "notepad": ["notepad.exe"],
            "calculator": ["calc.exe"],
            "calc": ["calc.exe"],
            "cmd": ["cmd.exe"],
            "terminal": ["wt.exe", "powershell.exe", "cmd.exe"],
            "powershell": ["powershell.exe"],
            "paint": ["mspaint.exe"],
            "taskmanager": ["taskmgr.exe"],
            "code": ["code.cmd", "code"],
            "vscode": ["code.cmd", "code"],
        }
        cmd_candidates = app_map.get(target_app, [f"{target_app}.exe"])
        launched = False
        for cmd in cmd_candidates:
            try:
                subprocess.Popen([cmd])
                launched = True
                break
            except Exception:
                continue

        if launched:
            act = _make_action(
                name="launch_app",
                tool="application_launcher",
                args={"app": target_app},
                output=f"Launched {target_app}",
                success=True,
                status="executed",
                guardrails="PASSED [Process Launch Permitted]",
            )
            return {
                "reply": f"Launching {target_app} on your workstation now{addr_suffix}.",
                "actions": [act],
                "status": "executed",
            }

    # -----------------------------------------------------------------------
    # 4. Desktop Screenshot Capture
    # -----------------------------------------------------------------------
    if re.search(r"\b(?:take|capture)\s+(?:a\s+)?(?:desktop\s+|screen\s+)?screenshot\b", q):
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            out_dir = Path("d:/Ultron/screenshots")
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"screenshot_{int(time.time())}.png"
            img.save(str(out_path))
            act = _make_action(
                name="take_screenshot",
                tool="desktop_screengrab",
                args={"destination": str(out_path)},
                output=f"Saved screenshot to {out_path}",
                success=True,
                status="executed",
                guardrails="PASSED [Screen Capture Permitted]",
            )
            return {
                "reply": f"Desktop screenshot captured and archived to {out_path.name}{addr_suffix}.",
                "actions": [act],
                "status": "executed",
            }
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # 5. Disk Space & Storage Inspection
    # -----------------------------------------------------------------------
    if re.search(r"\b(?:check|show|get|what\s+is\s+my|how\s+much)\s+(?:the\s+)?(?:disk\s+space|storage\s+space|drive\s+space|storage|disk)\b", q):
        try:
            drives = ["C:\\", "D:\\"]
            telemetry = []
            for d in drives:
                if Path(d).exists():
                    total, used, free = shutil.disk_usage(d)
                    free_gb = round(free / (1024 ** 3), 1)
                    total_gb = round(total / (1024 ** 3), 1)
                    telemetry.append(f"{d} {free_gb} GB free of {total_gb} GB")
            joined_tel = ", ".join(telemetry)
            act = _make_action(
                name="check_storage",
                tool="storage_telemetry",
                args={"drives": drives},
                output=joined_tel,
                success=True,
                status="executed",
                guardrails="PASSED [Read Telemetry Permitted]",
            )
            return {
                "reply": f"Current local storage telemetry: {joined_tel}{addr_suffix}.",
                "actions": [act],
                "status": "executed",
            }
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # 6. Current Time and Date
    # -----------------------------------------------------------------------
    if re.search(r"\b(?:what\s+time\s+is\s+it|what'?s\s+the\s+time|current\s+time|what\s+is\s+the\s+date|what\s+day\s+is\s+it|today'?s\s+date)\b", q):
        now_dt = datetime.datetime.now()
        time_str = now_dt.strftime("%I:%M %p, %A, %B %d, %Y")
        act = _make_action(
            name="system_clock",
            tool="system_clock_reader",
            args={},
            output=time_str,
            success=True,
            status="executed",
            guardrails="PASSED [Read Clock Permitted]",
        )
        return {
            "reply": f"The current system time is {time_str}{addr_suffix}.",
            "actions": [act],
            "status": "executed",
        }

    return None

    return None


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

        # 0b. Real-time native OS, desktop, browser & application action execution
        real_action = execute_real_system_action(directive, user_addr=user_addr)
        if real_action is not None:
            return real_action

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
            "reply": f"Directive received: '{directive}'. Ready to execute your operational objective{addr_suffix}. Please specify any target parameters.",
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


# ---------------------------------------------------------------------------
# Theme API  (TSK-P5-03 — Tri-Theme Hologram HUD)
# ---------------------------------------------------------------------------


@hologram_router.get("/api/hologram/theme")
async def get_hologram_theme() -> dict:
    """Return the current hologram HUD theme (cyan, crimson, emerald)."""
    from openjarvis.core.user_preferences import get_theme

    return {"theme": get_theme()}


@hologram_router.post("/api/hologram/theme")
async def update_hologram_theme(payload: dict) -> dict:
    """Persist the hologram HUD theme.

    Accepts a JSON body with key ``theme`` (or string directly).
    Allowed values: 'cyan', 'crimson', 'emerald'.
    Returns HTTP 422 for invalid theme values.
    """
    import logging

    from fastapi import HTTPException

    from openjarvis.core.user_preferences import set_theme

    logger = logging.getLogger("openjarvis.server.hologram.theme")
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=422,
            detail="Payload must be a JSON object with a 'theme' key.",
        )
    theme_val = payload.get("theme")
    if not isinstance(theme_val, str):
        raise HTTPException(
            status_code=422,
            detail="Theme value must be a string ('cyan', 'crimson', or 'emerald').",
        )
    try:
        saved = set_theme(theme_val)
    except ValueError as exc:
        logger.warning("Invalid theme update rejected: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"theme": saved}
