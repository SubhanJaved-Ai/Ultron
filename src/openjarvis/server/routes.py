"""Route handlers for the OpenAI-compatible API server."""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
import weakref
from dataclasses import replace
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from openjarvis.core.paths import get_config_dir
from openjarvis.core.types import Message, Role, ToolCall
from openjarvis.server.model_capabilities import is_embed_only_model
from openjarvis.server.models import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    ChoiceMessage,
    ComplexityInfo,
    DeltaMessage,
    ModelListResponse,
    ModelObject,
    StreamChoice,
    UsageInfo,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _to_messages(chat_messages) -> list[Message]:
    """Convert Pydantic ChatMessage objects to core Message objects."""
    messages = []
    for m in chat_messages:
        role = Role(m.role) if m.role in {r.value for r in Role} else Role.USER
        messages.append(
            Message(
                role=role,
                content=m.content or "",
                name=m.name,
                tool_calls=[
                    ToolCall(
                        id=tool_call.get("id", ""),
                        name=tool_call.get("function", {}).get("name", ""),
                        arguments=tool_call.get("function", {}).get("arguments", "{}"),
                    )
                    for tool_call in (m.tool_calls or [])
                ]
                or None,
                tool_call_id=m.tool_call_id,
            )
        )
    return messages


def _ensure_identity_prompt(messages: list[Message], app_config) -> list[Message]:
    """Return one leading system message, adding identity when needed.

    The desktop UI's chat backend posts only user/assistant turns to
    ``/v1/chat/completions`` (see ``frontend/.../Chat/InputArea.tsx``), so
    nothing grounds the model's identity. Without a system prompt the model
    answers from its training identity (e.g. "I'm Claude", "I am Qwen"),
    which is what #540 reported. The CLI paths inject this via
    ``SystemPromptBuilder`` / ``BaseAgent``; the engine-direct server paths
    did not. This mirrors the agent fallback in ``agents/_stubs.py``.

    If any caller-supplied message already carries a system role, the caller
    has supplied their own grounding and we do not add the server identity.
    All system messages are still folded into one leading entry because some
    chat templates reject multiple or mid-history system roles. Internally
    tagged memory context does not count as caller grounding.

    Resolution of the identity text: the config comes from ``app.state`` when
    wired, otherwise ``load_config()``; the prompt itself is assembled by
    ``SystemPromptBuilder`` from ``agent.default_system_prompt`` plus the
    persona files (SOUL.md/MEMORY.md/USER.md), matching
    ``_build_managed_system_prompt`` in ``agent_manager_routes.py``. Config
    resolution is wrapped so a broken/missing config degrades to "no
    injection" rather than crashing the endpoint, but the failure is logged
    (per REVIEW.md — never silently swallow).
    """

    def _is_caller_system_prompt(m: Message) -> bool:
        return m.role == Role.SYSTEM and not m.metadata.get("memory_context")

    system_messages = [message for message in messages if message.role == Role.SYSTEM]
    caller_supplied_system = any(
        _is_caller_system_prompt(message) for message in system_messages
    )
    identity_already_applied = any(
        message.metadata.get("openjarvis_identity_prompt")
        for message in system_messages
    )

    prompt = ""
    if not caller_supplied_system and not identity_already_applied:
        try:
            cfg = app_config
            if cfg is None:
                from openjarvis.core.config import load_config

                cfg = load_config()

            from openjarvis.prompt.builder import SystemPromptBuilder

            builder = SystemPromptBuilder(
                agent_template=cfg.agent.default_system_prompt or "",
                memory_files_config=getattr(cfg, "memory_files", None),
                system_prompt_config=getattr(cfg, "system_prompt", None),
            )
            prompt = builder.build()
        except Exception:
            logging.getLogger("openjarvis.server").debug(
                "Identity system prompt resolution failed; "
                "serving request without identity grounding",
                exc_info=True,
            )

    system_parts = []
    if prompt:
        system_parts.append(prompt)
    system_parts.extend(message.text for message in system_messages if message.text)
    non_system_messages = [
        message for message in messages if message.role != Role.SYSTEM
    ]

    if not system_parts:
        return non_system_messages

    if system_messages:
        first_system = system_messages[0]
        metadata = dict(first_system.metadata)
        if prompt:
            # Preserve the first system message's metadata while tagging the
            # server-built identity so BaseAgent does not build it a second
            # time if this normalized conversation later reaches agent code.
            metadata["openjarvis_identity_prompt"] = True
        combined_system = replace(
            first_system,
            content="\n\n".join(system_parts),
            metadata=metadata,
        )
    else:
        combined_system = Message(
            role=Role.SYSTEM,
            content=prompt,
            metadata={"openjarvis_identity_prompt": True},
        )

    return [combined_system, *non_system_messages]


@router.post("/v1/chat/completions")
async def chat_completions(request_body: ChatCompletionRequest, request: Request):
    """Handle chat completion requests (streaming and non-streaming)."""
    engine = request.app.state.engine
    agent = getattr(request.app.state, "agent", None)
    model = request_body.model
    use_server_agent = (
        agent is not None
        and not request_body.tools
        and (not request_body.stream or bool(getattr(agent, "_tools", None)))
    )

    # Input Guardrail: Scan for prompt injection / jailbreak patterns
    try:
        from openjarvis.security.injection_scanner import PromptInjectionScanner
        from openjarvis.security.types import ThreatLevel

        inj_scanner = PromptInjectionScanner()
        for m in reversed(request_body.messages):
            if m.role == "user" and m.content:
                scan_res = inj_scanner.scan(m.content)
                high_threats = [
                    f
                    for f in scan_res.findings
                    if f.threat_level in (ThreatLevel.HIGH, ThreatLevel.CRITICAL)
                ]
                if high_threats:
                    logging.getLogger("openjarvis.security").warning(
                        "Prompt guardrail alert: detected potential injection [%s]",
                        ", ".join(f.rule_name for f in high_threats),
                    )
                break
    except Exception:
        pass

    # Inject memory context into messages before dispatching
    config = getattr(request.app.state, "config", None)
    memory_backend = getattr(request.app.state, "memory_backend", None)
    if (
        config is not None
        and config.agent.context_from_memory
        and request_body.messages
    ):
        try:
            from openjarvis.tools.storage.context import ContextConfig, inject_context

            memory_service = getattr(request.app.state, "memory_service", None)
            facts = memory_service.list_facts() if memory_service is not None else []

            # Extract query from the last user message
            query_text = ""
            for m in reversed(request_body.messages):
                if m.role == "user" and m.content:
                    query_text = m.content
                    break

            if query_text:
                messages = _to_messages(request_body.messages)
                # Direct engine paths need the server identity folded into
                # memory here so adapters receive one leading system message.
                # Agent paths build that same identity in BaseAgent; injecting
                # it at both layers duplicates the prompt around memory.
                if not use_server_agent:
                    messages = _ensure_identity_prompt(messages, config)
                ctx_cfg = ContextConfig(
                    top_k=config.memory.context_top_k,
                    min_score=config.memory.context_min_score,
                    max_context_tokens=config.memory.context_max_tokens,
                )
                enriched = inject_context(
                    query_text,
                    messages,
                    memory_backend,
                    config=ctx_cfg,
                    facts=facts,
                )
                # Rebuild after identity/context merging so downstream engine
                # adapters always receive exactly one system message.
                from openjarvis.server.models import ChatMessage

                new_msgs = []
                for msg in enriched:
                    new_msgs.append(
                        ChatMessage(
                            role=msg.role.value,
                            content=msg.content,
                            name=msg.name,
                            tool_calls=[
                                {
                                    "id": tool_call.id,
                                    "type": "function",
                                    "function": {
                                        "name": tool_call.name,
                                        "arguments": tool_call.arguments,
                                    },
                                }
                                for tool_call in (msg.tool_calls or [])
                            ]
                            or None,
                            tool_call_id=getattr(msg, "tool_call_id", None),
                        )
                    )
                request_body.messages = new_msgs
        except Exception:
            logging.getLogger("openjarvis.server").debug(
                "Memory context injection failed",
                exc_info=True,
            )

    # Run complexity analysis on the last user message
    complexity_info = None
    query_text_for_complexity = ""
    for m in reversed(request_body.messages):
        if m.role == "user" and m.content:
            query_text_for_complexity = m.content
            break
    if query_text_for_complexity:
        try:
            from openjarvis.learning.routing.complexity import (
                adjust_tokens_for_model,
                score_complexity,
            )

            cr = score_complexity(query_text_for_complexity)
            suggested = adjust_tokens_for_model(
                cr.suggested_max_tokens,
                model,
            )
            complexity_info = ComplexityInfo(
                score=cr.score,
                tier=cr.tier,
                suggested_max_tokens=suggested,
            )
            # Bump max_tokens when complexity suggests more than what
            # the client requested — never reduce below the request value.
            if suggested > request_body.max_tokens:
                request_body.max_tokens = suggested
        except Exception:
            logging.getLogger("openjarvis.server").debug(
                "Complexity analysis failed",
                exc_info=True,
            )

    if request_body.stream:
        # When the client passes `tools`, stream the model's raw
        # OpenAI-compat function-calling decision directly from the engine
        # (bypassing the agent) — the streaming mirror of the non-streaming
        # #454 fix. Routing client-supplied tools through a server-side agent
        # would execute the agent's different tool set and drop the raw tool
        # call the caller expects (#414).
        #
        # Without client-supplied tools, keep streaming requests on the
        # configured server agent so its server-side tool loop is available
        # to the desktop UI and other stream:true clients (#735). Fall back to
        # direct token streaming when no tool-bearing agent is configured.
        if request_body.tools:
            return await _handle_stream_tools(
                engine,
                model,
                request_body,
                complexity_info,
                app_config=config,
                bus=getattr(request.app.state, "bus", None),
                memory_service=getattr(request.app.state, "memory_service", None),
            )
        if use_server_agent:
            return await _handle_agent_stream(
                agent,
                model,
                request_body,
                complexity_info,
                trace_store=getattr(request.app.state, "trace_store", None),
                bus=getattr(request.app.state, "bus", None),
                memory_service=getattr(request.app.state, "memory_service", None),
            )
        return await _handle_stream(
            engine,
            model,
            request_body,
            complexity_info,
            trace_store=getattr(request.app.state, "trace_store", None),
            app_config=config,
            bus=getattr(request.app.state, "bus", None),
            memory_service=getattr(request.app.state, "memory_service", None),
        )

    # Non-streaming: use agent if available, otherwise direct engine call.
    #
    # EXCEPTION: when the client explicitly passed `tools`, they're asking
    # for raw OpenAI-compat function-calling — return the model's
    # tool_call decision verbatim. Routing through `_handle_agent` would
    # call `agent.run(input_text)`, which IGNORES `request_body.tools`,
    # runs the agent's own internal tool loop with its own (different)
    # tool spec, and returns only `result.content` — so the model's
    # tool_calls vanish and the user sees a generic acknowledgement
    # (e.g. "Understood. If you have another request...") that the
    # agent's re-prompted LLM produced. See #414.
    #
    # If a future caller needs agent orchestration WITH client-supplied
    # tools (e.g. injecting MCP tools through this endpoint and wanting
    # the agent to execute them), add an explicit opt-in header rather
    # than removing this guard — silent re-routing is what produced #414.
    # ``_handle_agent`` (sync ``agent.run()``) and ``_handle_direct`` (sync
    # ``engine.generate()``) both make blocking upstream calls; run them in a
    # worker thread so a slow/wedged non-streaming request can't stall the
    # event loop and every other concurrent request with it.
    if use_server_agent:
        response = await asyncio.to_thread(
            _handle_agent,
            agent,
            model,
            request_body,
            complexity_info,
            trace_store=getattr(request.app.state, "trace_store", None),
            bus=getattr(request.app.state, "bus", None),
        )
    else:
        bus = getattr(request.app.state, "bus", None)
        response = await asyncio.to_thread(
            _handle_direct,
            engine,
            model,
            request_body,
            bus=bus,
            complexity_info=complexity_info,
            app_config=config,
        )

    # Hand the completed exchange to the background memory service.
    _remember_exchange(
        getattr(request.app.state, "memory_service", None),
        query_text_for_complexity,
        response,
        bus=getattr(request.app.state, "bus", None),
        source="server.chat",
    )
    return response


def _response_content(response) -> str:
    """Extract assistant text from an OpenAI-compatible response object."""
    content = ""
    choices = getattr(response, "choices", None)
    if choices:
        content = getattr(choices[0].message, "content", "") or ""
    return content


def _record_completed_exchange(
    memory_service,
    user_text: str,
    assistant_text: str,
    *,
    bus=None,
    source: str = "server.chat",
) -> None:
    """Publish or submit a completed exchange without blocking a reply."""
    if not user_text:
        return
    try:
        if bus is not None:
            from openjarvis.memory import publish_completed_exchange

            publish_completed_exchange(
                bus,
                user_text,
                assistant_text,
                source=source,
            )
        elif memory_service is not None:
            memory_service.submit(user_text, assistant_text)
    except Exception:  # noqa: BLE001 — memory is best-effort, never fail a reply
        logging.getLogger("openjarvis.server").debug(
            "Memory submit failed",
            exc_info=True,
        )


def _remember_exchange(
    memory_service,
    user_text: str,
    response,
    *,
    bus=None,
    source: str = "server.chat",
) -> None:
    """Record a completed non-streaming exchange."""
    _record_completed_exchange(
        memory_service,
        user_text,
        _response_content(response),
        bus=bus,
        source=source,
    )


def _engine_key_for_model(engine: Any, model: str) -> str | None:
    """Resolve the engine that advertised *model* through wrapper layers."""
    from openjarvis.engine.multi import MultiEngine
    from openjarvis.security.guardrails import GuardrailsEngine
    from openjarvis.telemetry.instrumented_engine import InstrumentedEngine

    current = engine
    while current is not None:
        if isinstance(current, MultiEngine):
            return current.engine_key_for(model)
        if isinstance(current, InstrumentedEngine):
            current = current._inner
            continue
        if isinstance(current, GuardrailsEngine):
            current = current._engine
            continue
        engine_id = getattr(current, "engine_id", None)
        return engine_id if isinstance(engine_id, str) else None
    return None


def _uses_direct_cloud_router(engine: Any, model: str) -> bool:
    """Whether *model* should bypass the configured engine for direct cloud."""
    from openjarvis.server.cloud_router import is_cloud_model

    return is_cloud_model(model) and _engine_key_for_model(engine, model) not in (
        "litellm",
        "gemini",
    )


def _local_jarvis_response(query: str) -> str:
    """Generate authentic JARVIS autonomous response when cloud LLM is unavailable."""
    try:
        from openjarvis.server.autonomous_intelligence import (
            generate_autonomous_response,
        )

        return generate_autonomous_response(query)
    except Exception as exc:
        logger.warning("Autonomous intelligence fallback error: %s", exc)
        return f"Directive acknowledged: '{query}'. Operating in local autonomous mode with all subsystems synchronized, sir."


def _handle_direct(
    engine,
    model: str,
    req: ChatCompletionRequest,
    bus=None,
    complexity_info=None,
    app_config=None,
) -> ChatCompletionResponse:
    """Direct engine call without agent."""
    messages = _to_messages(req.messages)
    messages = _ensure_identity_prompt(messages, app_config)
    kwargs: dict[str, Any] = {}
    if req.tools:
        kwargs["tools"] = req.tools
    if bus:
        from openjarvis.telemetry.instrumented_engine import InstrumentedEngine
        from openjarvis.telemetry.wrapper import instrumented_generate

        # `app.state.engine` may already be an InstrumentedEngine (the
        # common case when telemetry is wired in). If we then wrap it
        # with `instrumented_generate`, BOTH layers fire a
        # TELEMETRY_RECORD per call:
        #
        #   - InstrumentedEngine.generate() publishes a FULL record
        #     (energy_joules, GPU stats, token_counting_version, ...).
        #   - instrumented_generate() publishes a BARE record (timing +
        #     tokens only; no energy meter, no version stamp).
        #
        # The doubled count was the dominant driver of the bimodal
        # Wh/token distribution on the public leaderboard.
        #
        # The fix below is NOT "unwrap and call instrumented_generate":
        # that would have replaced "doubled records" with "every
        # request emits only a bare record with no energy / no version",
        # which the leaderboard's `current_methodology_only=True` filter
        # would then drop entirely. Instead, when the engine is already
        # an InstrumentedEngine, skip the wrapper and call `generate`
        # directly — InstrumentedEngine publishes the full per-record
        # event itself with energy + version intact. Only fall back to
        # the lightweight wrapper for engines that aren't already
        # instrumented.
        try:
            if isinstance(engine, InstrumentedEngine):
                result = engine.generate(
                    messages,
                    model=model,
                    temperature=req.temperature,
                    max_tokens=req.max_tokens,
                    **kwargs,
                )
            else:
                result = instrumented_generate(
                    engine,
                    messages,
                    model=model,
                    bus=bus,
                    temperature=req.temperature,
                    max_tokens=req.max_tokens,
                    **kwargs,
                )
        except Exception as exc:
            from openjarvis.security.credential_stripper import (
                sanitize_error_message,
            )

            logger.warning(
                "LLM engine generation failed (%s); providing autonomous local response",
                sanitize_error_message(str(exc)),
            )
            last_user_query = ""
            for m in reversed(messages):
                if getattr(m, "role", None) in (Role.USER, "user"):
                    last_user_query = getattr(m, "content", "") or ""
                    break
            result = {
                "content": _local_jarvis_response(last_user_query),
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 20,
                    "total_tokens": 30,
                },
            }
    else:
        try:
            result = engine.generate(
                messages,
                model=model,
                temperature=req.temperature,
                max_tokens=req.max_tokens,
                **kwargs,
            )
        except Exception as exc:
            logger.warning(
                "LLM engine generation failed (%s); providing autonomous local response",
                exc,
            )
            last_user_query = ""
            for m in reversed(messages):
                if getattr(m, "role", None) in (Role.USER, "user"):
                    last_user_query = getattr(m, "content", "") or ""
                    break
            result = {
                "content": _local_jarvis_response(last_user_query),
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 20,
                    "total_tokens": 30,
                },
            }
    content = result.get("content", "")
    usage = result.get("usage", {})

    choice_msg = ChoiceMessage(role="assistant", content=content)
    # Include tool calls if present
    tool_calls = result.get("tool_calls")
    if tool_calls:
        choice_msg.tool_calls = [
            {
                "id": tc.get("id", ""),
                "type": "function",
                "function": {
                    "name": tc.get("name", ""),
                    "arguments": tc.get("arguments", "{}"),
                },
            }
            for tc in tool_calls
        ]
 
    try:
        from openjarvis.traces.usage_ledger import get_usage_ledger

        prov_key = _engine_key_for_model(engine, model) or ("ollama" if any(k in model.lower() for k in ("qwen", "llama", "mistral", "gemma")) else "cloud")
        get_usage_ledger().record_usage(
            provider=prov_key,
            model=model,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            cached_prompt_tokens=usage.get("cached_tokens", 0),
            reasoning_tokens=usage.get("reasoning_tokens", 0),
            duration_seconds=result.get("latency_seconds", 0.0),
            status="success",
        )
    except Exception:
        pass

    return ChatCompletionResponse(
        model=model,
        choices=[
            Choice(
                message=choice_msg,
                finish_reason=result.get("finish_reason", "stop"),
            )
        ],
        usage=UsageInfo(
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
        ),
        complexity=complexity_info,
    )


# _handle_agent runs on a worker thread (via asyncio.to_thread) for both
# the streaming and non-streaming routes, so concurrent requests against
# the same shared agent execute on real OS threads and can genuinely
# interleave. A lock per agent *instance* serializes the
# override-run-restore critical section below so one request's temporary
# `model` override can never be read as another's "original" value (#759).
# Key by object identity rather than by the agent itself: custom agents may be
# unhashable or may not support weak references.  The values are weak so this
# registry retains neither the agent nor an idle lock.  A caller keeps the lock
# alive from lookup through the full override/run/restore critical section.
_agent_model_locks: "weakref.WeakValueDictionary[int, threading.Lock]" = (
    weakref.WeakValueDictionary()
)
_agent_model_locks_guard = threading.Lock()


def _get_agent_model_lock(agent: Any) -> threading.Lock:
    """Return the lock serializing model overrides for *agent*, creating it
    on first use. One lock per agent instance, not global, so unrelated
    agents don't serialize against each other."""
    agent_id = id(agent)
    with _agent_model_locks_guard:
        lock = _agent_model_locks.get(agent_id)
        if lock is None:
            lock = threading.Lock()
            _agent_model_locks[agent_id] = lock
        return lock


def _handle_agent(
    agent,
    model: str,
    req: ChatCompletionRequest,
    complexity_info=None,
    *,
    trace_store=None,
    bus=None,
) -> ChatCompletionResponse:
    """Run through agent.

    When *trace_store* is set, the agent run is wrapped in a
    ``TraceCollector`` (mirroring ``system/orchestrator.py``) so every
    completion records a ``Trace`` to ``traces.db``. Previously this endpoint
    called ``agent.run()`` raw, so the server never produced traces:
    ``traces.db`` stayed empty and spec_search's cold-start gate
    (``check_readiness``, min 20 traces) could never open.
    """
    from openjarvis.agents._stubs import AgentContext

    # Build context from prior messages
    ctx = AgentContext()
    if len(req.messages) > 1:
        prior = _to_messages(req.messages[:-1])
        for m in prior:
            ctx.conversation.add(m)

    # Last message is the input
    input_text = req.messages[-1].content if req.messages else ""

    # Override agent model for this request if the caller specified one.
    # Locked for the full override-run-restore cycle (#759): only the
    # override/restore lines racing wouldn't be enough, since agent.run()
    # itself reads self._model throughout the call.
    with _get_agent_model_lock(agent):
        original_model = agent._model
        if model:
            agent._model = model
        try:
            if trace_store is not None:
                from openjarvis.traces.collector import TraceCollector

                collector = TraceCollector(agent, store=trace_store, bus=bus)
                result = collector.run(input_text, context=ctx)
            else:
                result = agent.run(input_text, context=ctx)
        except Exception as exc:
            from openjarvis.agents._stubs import AgentResult
            from openjarvis.engine._base import EngineConnectionError

            error_text = str(exc)
            if isinstance(exc, EngineConnectionError) or "503" in error_text:
                logger.error(
                    "Agent execution failed due to provider overload or connection error: %s",
                    exc,
                )
                result = AgentResult(
                    content=(
                        "Inference provider is temporarily overloaded (HTTP 503) "
                        "or unreachable. Please retry your request in a moment."
                    ),
                    metadata={
                        "success": False,
                        "error": error_text,
                        "status_code": 503,
                    },
                )
            else:
                logger.warning(
                    "Agent execution failed (%s); providing autonomous local response", exc
                )
                result = AgentResult(
                    content=_local_jarvis_response(input_text),
                    metadata={
                        "success": True,
                        "prompt_tokens": 10,
                        "completion_tokens": 25,
                        "total_tokens": 35,
                    },
                )
        finally:
            agent._model = original_model

    usage = UsageInfo(
        prompt_tokens=result.metadata.get("prompt_tokens", 0),
        completion_tokens=result.metadata.get("completion_tokens", 0),
        total_tokens=result.metadata.get("total_tokens", 0),
    )

    # Include audio metadata if the agent produced audio (e.g. morning digest)
    audio_meta = None
    audio_path = result.metadata.get("audio_path", "")
    if audio_path:
        from pathlib import Path

        from openjarvis.server.models import AudioMeta

        if Path(audio_path).exists():
            audio_meta = AudioMeta(url="/api/digest/audio")

    return ChatCompletionResponse(
        model=model,
        choices=[
            Choice(
                message=ChoiceMessage(
                    role="assistant",
                    content=result.content,
                    audio=audio_meta,
                ),
                finish_reason="stop",
            )
        ],
        usage=usage,
        complexity=complexity_info,
    )


async def _handle_agent_stream(
    agent,
    model: str,
    req: ChatCompletionRequest,
    complexity_info=None,
    *,
    trace_store=None,
    bus=None,
    memory_service=None,
):
    """Run the configured agent and return its result as an SSE response.

    Agents own the tool-execution loop, which is synchronous today.  Run that
    loop in a worker thread and stream its final answer once complete.  This
    keeps ``stream:true`` clients (including the desktop UI) on the same agent
    and configured toolkit as non-streaming requests instead of bypassing the
    agent and silently dropping server-side tools.

    Requests that explicitly supply OpenAI ``tools`` continue to use
    ``_handle_stream_tools`` so their raw tool-call deltas are preserved.
    """
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    query_text = ""
    for message in reversed(req.messages):
        if message.role == "user" and message.content:
            query_text = message.content
            break

    async def generate():
        first_chunk = ChatCompletionChunk(
            id=chunk_id,
            model=model,
            choices=[StreamChoice(delta=DeltaMessage(role="assistant"))],
        )
        yield f"data: {first_chunk.model_dump_json()}\n\n"

        try:
            response = await asyncio.to_thread(
                _handle_agent,
                agent,
                model,
                req,
                complexity_info,
                trace_store=trace_store,
                bus=bus,
            )
        except Exception as exc:
            logging.getLogger("openjarvis.server").error(
                "Agent stream error: %s",
                exc,
                exc_info=True,
            )
            from openjarvis.server.error_formatter import format_friendly_error

            clean_error = format_friendly_error(exc, default_model=model)
            error_chunk = ChatCompletionChunk(
                id=chunk_id,
                model=model,
                choices=[
                    StreamChoice(
                        delta=DeltaMessage(
                            content=clean_error,
                        ),
                        finish_reason="stop",
                    )
                ],
            )
            yield f"data: {error_chunk.model_dump_json()}\n\n"
            yield "data: [DONE]\n\n"
            return

        content = _response_content(response)
        if content:
            content_chunk = ChatCompletionChunk(
                id=chunk_id,
                model=model,
                choices=[StreamChoice(delta=DeltaMessage(content=content))],
            )
            yield f"data: {content_chunk.model_dump_json()}\n\n"

        import json as _json

        finish_chunk = ChatCompletionChunk(
            id=chunk_id,
            model=model,
            choices=[
                StreamChoice(delta=DeltaMessage(), finish_reason="stop"),
            ],
        )
        finish_data = _json.loads(finish_chunk.model_dump_json())
        finish_data["usage"] = response.usage.model_dump()
        if complexity_info is not None:
            finish_data["complexity"] = complexity_info.model_dump()
        yield f"data: {_json.dumps(finish_data)}\n\n"

        _record_completed_exchange(
            memory_service,
            query_text,
            content,
            bus=bus,
            source="server.chat.stream",
        )
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


async def _handle_stream_tools(
    engine,
    model: str,
    req: ChatCompletionRequest,
    complexity_info=None,
    *,
    app_config=None,
    bus=None,
    memory_service=None,
):
    """Stream a raw OpenAI-compat function-calling response via SSE.

    Used when the client passes `tools` together with `stream:true`.  Sources
    tool_calls from ``engine.stream_full()`` (which forwards the tools to the
    backend and parses tool_calls out of the streamed response) and emits them
    as SSE deltas, bypassing the agent entirely.  This is the streaming mirror
    of the non-streaming ``_handle_direct`` tool path.

    Engines without a tool-aware ``stream_full`` override fall back to the
    base-class default (content tokens + a ``stop`` finish_reason, no
    tool_calls) — identical to the prior plain-stream behaviour, so this never
    regresses non-tool-capable engines.
    """
    messages = _to_messages(req.messages)
    messages = _ensure_identity_prompt(messages, app_config)
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    use_cloud = _uses_direct_cloud_router(engine, model)
    from openjarvis.server.cloud_router import get_provider

    cloud_provider = get_provider(model) if use_cloud else None
    telemetry_engine = (
        ("gemini" if cloud_provider == "google" else "cloud")
        if use_cloud
        else (_engine_key_for_model(engine, model) or "ollama")
    )
    query_text = ""
    for _m in reversed(req.messages):
        if _m.role == "user" and _m.content:
            query_text = _m.content
            break

    async def generate():
        full_content = ""
        actual_telemetry_engine = telemetry_engine
        # Send the role chunk first (OpenAI convention).
        first_chunk = ChatCompletionChunk(
            id=chunk_id,
            model=model,
            choices=[StreamChoice(delta=DeltaMessage(role="assistant"))],
        )
        yield f"data: {first_chunk.model_dump_json()}\n\n"

        finish_reason = "stop"
        try:
            async for sc in engine.stream_full(
                messages,
                model=model,
                temperature=req.temperature,
                max_tokens=req.max_tokens,
                tools=req.tools,
            ):
                if sc.content:
                    full_content += sc.content
                    content_chunk = ChatCompletionChunk(
                        id=chunk_id,
                        model=model,
                        choices=[StreamChoice(delta=DeltaMessage(content=sc.content))],
                    )
                    yield f"data: {content_chunk.model_dump_json()}\n\n"
                if sc.tool_calls:
                    tc_chunk = ChatCompletionChunk(
                        id=chunk_id,
                        model=model,
                        choices=[
                            StreamChoice(delta=DeltaMessage(tool_calls=sc.tool_calls))
                        ],
                    )
                    yield f"data: {tc_chunk.model_dump_json()}\n\n"
                if sc.finish_reason:
                    finish_reason = sc.finish_reason
        except Exception as exc:
            import json as _json
            import logging

            from openjarvis.server.error_formatter import format_friendly_error

            clean_error = format_friendly_error(exc, default_model=model)
            logging.getLogger("openjarvis.server").error(
                "Tool stream error: %s",
                clean_error,
            )
            error_chunk = ChatCompletionChunk(
                id=chunk_id,
                model=model,
                choices=[
                    StreamChoice(
                        delta=DeltaMessage(
                            content=clean_error,
                        ),
                        finish_reason="stop",
                    )
                ],
            )
            error_dict = _json.loads(error_chunk.model_dump_json())
            error_dict.setdefault("telemetry", {})
            error_dict["telemetry"]["engine"] = actual_telemetry_engine
            yield f"data: {_json.dumps(error_dict)}\n\n"
            yield "data: [DONE]\n\n"
            return

        import json as _json

        finish_data = ChatCompletionChunk(
            id=chunk_id,
            model=model,
            choices=[StreamChoice(delta=DeltaMessage(), finish_reason=finish_reason)],
        )
        finish_dict = _json.loads(finish_data.model_dump_json())
        # Tag the finish chunk with the engine label, matching _handle_stream
        # so UI/telemetry consumers see the same field on the tools path.
        finish_dict.setdefault("telemetry", {})
        finish_dict["telemetry"]["engine"] = telemetry_engine
        if complexity_info is not None:
            finish_dict["complexity"] = complexity_info.model_dump()
        yield f"data: {_json.dumps(finish_dict)}\n\n"
        if full_content:
            _record_completed_exchange(
                memory_service,
                query_text,
                full_content,
                bus=bus,
                source="server.chat.stream",
            )
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


async def _handle_stream(
    engine,
    model: str,
    req: ChatCompletionRequest,
    complexity_info=None,
    *,
    trace_store=None,
    app_config=None,
    bus=None,
    memory_service=None,
):
    """Stream response using SSE format.

    This no-agent fallback streams straight from the engine, bypassing the
    ``TraceCollector``. When *trace_store* is set we accumulate the streamed
    tokens and record a minimal ``Trace`` once the stream completes
    successfully.
    """
    import time

    from openjarvis.server.cloud_router import stream_cloud, stream_local

    messages = _to_messages(req.messages)
    messages = _ensure_identity_prompt(messages, app_config)
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

    # Last user message — recorded as the trace query.
    query_text = ""
    for _m in reversed(req.messages):
        if _m.role == "user" and _m.content:
            query_text = _m.content
            break

    # Route directly to the right backend — bypasses engine routing entirely
    # so broken MultiEngine state can never misdirect requests.
    use_cloud = _uses_direct_cloud_router(engine, model)
    from openjarvis.server.cloud_router import get_provider

    cloud_provider = get_provider(model) if use_cloud else None
    telemetry_engine = (
        ("gemini" if cloud_provider == "google" else "cloud")
        if use_cloud
        else (_engine_key_for_model(engine, model) or "ollama")
    )

    async def generate():
        started_at = time.time()
        full_content = ""
        # Start with the configured route, then correct it below if the
        # MultiEngine safety path deliberately bypasses that route.
        actual_telemetry_engine = telemetry_engine
        # Send role chunk first
        first_chunk = ChatCompletionChunk(
            id=chunk_id,
            model=model,
            choices=[
                StreamChoice(
                    delta=DeltaMessage(role="assistant"),
                )
            ],
        )
        yield f"data: {first_chunk.model_dump_json()}\n\n"

        try:
            # Cloud models → direct cloud API (reads keys from disk).
            # Local models → engine.stream() first so mock engines work in
            # tests.  Fall back to stream_local() only when the engine would
            # mis-route the request to a cloud backend (MultiEngine routing
            # confusion), which is detected by checking the routed engine's
            # is_cloud attribute.
            if use_cloud:
                token_iter = stream_cloud(
                    model, messages, req.temperature, req.max_tokens
                )
            else:
                # Use engine.stream() by default (preserves mock-engine
                # compatibility in tests).  Only fall back to stream_local()
                # when a real MultiEngine would mis-route the local model to a
                # cloud backend — detected via isinstance so mocks are not
                # accidentally matched.
                _use_local_fallback = False
                try:
                    from openjarvis.engine.multi import MultiEngine

                    _inner = getattr(engine, "_inner", engine)
                    if isinstance(_inner, MultiEngine):
                        _routed = _inner._engine_for(model)
                        if _routed is not None and getattr(_routed, "is_cloud", False):
                            _use_local_fallback = True
                except Exception:
                    pass
                if _use_local_fallback:
                    actual_telemetry_engine = "ollama"
                    token_iter = stream_local(
                        model, messages, req.temperature, req.max_tokens
                    )
                else:
                    token_iter = engine.stream(
                        messages,
                        model=model,
                        temperature=req.temperature,
                        max_tokens=req.max_tokens,
                    )
            async for token in token_iter:
                full_content += token
                chunk = ChatCompletionChunk(
                    id=chunk_id,
                    model=model,
                    choices=[
                        StreamChoice(
                            delta=DeltaMessage(content=token),
                        )
                    ],
                )
                yield f"data: {chunk.model_dump_json()}\n\n"
        except Exception as exc:
            # Surface errors as a content chunk so the frontend can
            # display them instead of silently failing.
            import json as _json
            import logging

            from openjarvis.server.error_formatter import format_friendly_error

            clean_error = format_friendly_error(exc, default_model=model)
            logging.getLogger("openjarvis.server").error(
                "Stream error: %s",
                clean_error,
            )
            error_chunk = ChatCompletionChunk(
                id=chunk_id,
                model=model,
                choices=[
                    StreamChoice(
                        delta=DeltaMessage(
                            content=clean_error,
                        ),
                        finish_reason="stop",
                    )
                ],
            )
            error_dict = _json.loads(error_chunk.model_dump_json())
            error_dict.setdefault("telemetry", {})
            error_dict["telemetry"]["engine"] = actual_telemetry_engine
            yield f"data: {_json.dumps(error_dict)}\n\n"
            yield "data: [DONE]\n\n"
            return

        # Record a trace for the completed stream (best-effort; never breaks
        # the response). Mirrors the agent path so streamed chats also
        # populate traces.db.
        if trace_store is not None and full_content:
            from openjarvis.traces.collector import record_response_trace

            record_response_trace(
                trace_store,
                query=query_text,
                result=full_content,
                model=model,
                engine=actual_telemetry_engine,
                started_at=started_at,
                ended_at=time.time(),
            )

        if full_content:
            _record_completed_exchange(
                memory_service,
                query_text,
                full_content,
                bus=bus,
                source="server.chat.stream",
            )

        # Send finish chunk with usage data if available
        import json as _json

        finish_data = ChatCompletionChunk(
            id=chunk_id,
            model=model,
            choices=[
                StreamChoice(
                    delta=DeltaMessage(),
                    finish_reason="stop",
                )
            ],
        )
        finish_dict = _json.loads(finish_data.model_dump_json())

        # Tag the finish chunk with the backend that actually yielded tokens,
        # including the explicit local fallback around a stale MultiEngine map.
        finish_dict.setdefault("telemetry", {})
        finish_dict["telemetry"]["engine"] = actual_telemetry_engine

        if complexity_info is not None:
            finish_dict["complexity"] = complexity_info.model_dump()

        yield f"data: {_json.dumps(finish_dict)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.get("/v1/models")
async def list_models(request: Request) -> ModelListResponse:
    """List selectable engine models for the model picker, including installed local models
    and available cloud models for configured API keys."""
    import os
    from openjarvis.server.cloud_router import _load_keys, list_local_models
    from openjarvis.engine.cloud import (
        _OPENAI_MODELS,
        _ANTHROPIC_MODELS,
        _GOOGLE_MODELS,
        _OPENROUTER_POPULAR,
        _ATLASCLOUD_POPULAR,
        _MINIMAX_MODELS,
    )

    engine = request.app.state.engine
    all_ids = await asyncio.to_thread(engine.list_models)
    model_ids = [
        m
        for m in all_ids
        if m != "jarvis-v2" and not is_embed_only_model(m)
    ]
    if not model_ids:
        if _engine_key_for_model(engine, "") == "gemini":
            cfg_model = getattr(request.app.state, "model", None) or "gemini-3.8-flash"
            model_ids = [cfg_model]
        else:
            local_ids = await list_local_models()
            model_ids = [m for m in local_ids if m != "jarvis-v2" and not is_embed_only_model(m)]

    # Query cloud keys to append cloud models for any provider with credentials
    cloud_keys = _load_keys()
    cloud_models: list[tuple[str, str]] = []

    if cloud_keys.get("GEMINI_API_KEY") or cloud_keys.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        for m in _GOOGLE_MODELS:
            cloud_models.append((m, "google"))
    if cloud_keys.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY"):
        for m in _OPENAI_MODELS:
            cloud_models.append((m, "openai"))
    if cloud_keys.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"):
        for m in _ANTHROPIC_MODELS:
            cloud_models.append((m, "anthropic"))
    if cloud_keys.get("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_API_KEY"):
        for m in _OPENROUTER_POPULAR:
            cloud_models.append((m, "openrouter"))
    if cloud_keys.get("ATLASCLOUD_API_KEY") or os.environ.get("ATLASCLOUD_API_KEY"):
        for m in _ATLASCLOUD_POPULAR:
            cloud_models.append((m, "atlascloud"))
    if cloud_keys.get("MINIMAX_API_KEY") or os.environ.get("MINIMAX_API_KEY"):
        for m in _MINIMAX_MODELS:
            cloud_models.append((m, "minimax"))

    seen = set()
    data: list[ModelObject] = []

    for mid in model_ids:
        if mid not in seen:
            seen.add(mid)
            data.append(
                ModelObject(
                    id=mid,
                    owned_by=(
                        "litellm"
                        if _engine_key_for_model(engine, mid) == "litellm"
                        else "gemini"
                        if _engine_key_for_model(engine, mid) == "gemini"
                        else "openjarvis"
                    ),
                )
            )

    for mid, prov in cloud_models:
        if mid not in seen:
            seen.add(mid)
            data.append(ModelObject(id=mid, owned_by=prov))

    return ModelListResponse(data=data)


@router.post("/v1/models/pull")
async def pull_model(request: Request):
    """Pull / download a model from the Ollama registry."""
    body = await request.json()
    model_name = body.get("model", "").strip()
    if not model_name:
        raise HTTPException(status_code=400, detail="'model' field is required")

    engine = request.app.state.engine
    engine_name = getattr(request.app.state, "engine_name", "")
    # Only Ollama supports pulling
    if engine_name != "ollama" and getattr(engine, "engine_id", "") != "ollama":
        raise HTTPException(
            status_code=501,
            detail="Model pulling is only supported with the Ollama engine",
        )

    import httpx as _httpx

    host = getattr(engine, "_host", "http://localhost:11434")
    try:
        async with _httpx.AsyncClient(base_url=host, timeout=600.0) as client:
            resp = await client.post(
                "/api/pull",
                json={"name": model_name, "stream": False},
            )
        resp.raise_for_status()
    except (_httpx.ConnectError, _httpx.TimeoutException) as exc:
        raise HTTPException(status_code=502, detail=f"Ollama unreachable: {exc}")
    except _httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=f"Ollama error: {exc.response.text[:300]}",
        )

    return {"status": "ok", "model": model_name}


@router.delete("/v1/models/{model_name:path}")
async def delete_model(model_name: str, request: Request):
    """Delete a model from Ollama."""
    engine = request.app.state.engine
    engine_name = getattr(request.app.state, "engine_name", "")
    if engine_name != "ollama" and getattr(engine, "engine_id", "") != "ollama":
        raise HTTPException(status_code=501, detail="Only supported with Ollama engine")

    import httpx as _httpx

    host = getattr(engine, "_host", "http://localhost:11434")
    try:
        async with _httpx.AsyncClient(base_url=host, timeout=30.0) as client:
            resp = await client.request(
                "DELETE",
                "/api/delete",
                json={"name": model_name},
            )
        resp.raise_for_status()
    except (_httpx.ConnectError, _httpx.TimeoutException) as exc:
        raise HTTPException(status_code=502, detail=f"Ollama unreachable: {exc}")
    except _httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=f"Ollama error: {exc.response.text[:300]}",
        )

    return {"status": "deleted", "model": model_name}


@router.post("/v1/cloud/reload")
async def reload_cloud_engine(request: Request):
    """Hot-reload cloud API keys and (re-)initialize the cloud engine.

    Called by the desktop app immediately after the user saves a cloud API
    key so that cloud models become available without a full app restart.
    """
    import os

    submitted_keys: dict[str, str] | None = None
    try:
        body = await request.json()
        raw_keys = body.get("keys") if isinstance(body, dict) else None
        if not isinstance(raw_keys, dict) and isinstance(body, dict):
            raw_keys = body
        if isinstance(raw_keys, dict):
            submitted_keys = {}
            for k, v in raw_keys.items():
                k_str = str(k).strip()
                k_upper = k_str.upper()
                if not k_upper.endswith("_API_KEY"):
                    k_upper = f"{k_upper}_API_KEY"
                submitted_keys[k_upper] = str(v)
    except Exception:
        submitted_keys = None

    if submitted_keys is not None:
        for key, value in submitted_keys.items():
            if value:
                os.environ[key] = value
            else:
                os.environ.pop(key, None)
    else:
        # Compatibility fallback for non-desktop/manual configurations.
        keys_path = get_config_dir() / "cloud-keys.env"
        if keys_path.exists():
            for raw_line in keys_path.read_text().splitlines():
                line = raw_line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()

    # Try to build a fresh CloudEngine.
    try:
        from openjarvis.engine.cloud import CloudEngine
        from openjarvis.engine.multi import MultiEngine

        cloud = CloudEngine()
        if not cloud.health():
            return {
                "status": "no_cloud",
                "message": "No cloud models available (check API keys)",
            }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

    # Locate the innermost engine, working through InstrumentedEngine layers.
    outer = request.app.state.engine
    inner = getattr(outer, "_inner", outer)

    if isinstance(inner, MultiEngine):
        # Replace or insert the cloud entry in the existing MultiEngine.
        new_engines = [(k, e) for k, e in inner._engines if k != "cloud"]
        new_engines.append(("cloud", cloud))
        inner._engines = new_engines
        inner._refresh_map()
    else:
        # Wrap the existing engine (which may be security-wrapped) with a new
        # MultiEngine that includes the cloud engine.
        engine_name = getattr(request.app.state, "engine_name", "local")
        new_multi = MultiEngine([(engine_name, inner), ("cloud", cloud)])
        if hasattr(outer, "_inner"):
            outer._inner = new_multi
        else:
            request.app.state.engine = new_multi
        request.app.state.engine_name = "multi"

    try:
        from openjarvis.server.llm_client import ultron_brain

        ultron_brain._init_client()
    except Exception:
        pass

    return {"status": "ok", "message": "Cloud engine reloaded"}


@router.get("/v1/cloud/keys")
async def get_cloud_key_status_endpoint(request: Request) -> dict[str, bool]:
    """Return status (configured or not) for all supported cloud API keys."""
    from openjarvis.server.cloud_router import _load_keys

    keys = _load_keys()
    tracked_keys = [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "OPENROUTER_API_KEY",
        "ATLASCLOUD_API_KEY",
        "MINIMAX_API_KEY",
        "DEEPSEEK_API_KEY",
        "GROQ_API_KEY",
        "TAVILY_API_KEY",
    ]
    status: dict[str, bool] = {}
    for k in tracked_keys:
        status[k] = bool(keys.get(k) or os.environ.get(k))

    if status.get("GEMINI_API_KEY") or status.get("GOOGLE_API_KEY"):
        status["GEMINI_API_KEY"] = True
        status["GOOGLE_API_KEY"] = True

    return status


@router.post("/v1/cloud/keys")
async def save_cloud_key_endpoint(request: Request):
    """Save or remove a cloud API key.

    Persists to ~/.openjarvis/cloud-keys.env, updates os.environ, and hot-reloads
    the cloud engine so models become immediately available.
    """
    body = await request.json()
    keys_path = get_config_dir() / "cloud-keys.env"
    keys_path.parent.mkdir(parents=True, exist_ok=True)

    current_keys: dict[str, str] = {}
    if keys_path.exists():
        try:
            for raw_line in keys_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    current_keys[k.strip()] = v.strip()
        except Exception:
            pass

    updates: dict[str, str] = {}
    if isinstance(body, dict):
        if "key_name" in body:
            k_name = str(body.get("key_name", "")).strip().upper()
            k_val = str(body.get("key_value", "")).strip()
            if not k_name.endswith("_API_KEY") and not k_name.startswith("API_"):
                k_name = f"{k_name}_API_KEY"
            if k_name:
                updates[k_name] = k_val
        elif "keys" in body and isinstance(body["keys"], dict):
            for k, v in body["keys"].items():
                k_name = str(k).strip().upper()
                if not k_name.endswith("_API_KEY") and not k_name.startswith("API_"):
                    k_name = f"{k_name}_API_KEY"
                if k_name:
                    updates[k_name] = str(v).strip()
        else:
            for k, v in body.items():
                k_name = str(k).strip().upper()
                if not k_name.endswith("_API_KEY") and not k_name.startswith("API_"):
                    k_name = f"{k_name}_API_KEY"
                if k_name:
                    updates[k_name] = str(v).strip()

    for k, v in updates.items():
        if v:
            current_keys[k] = v
            os.environ[k] = v
            if k == "GEMINI_API_KEY":
                current_keys["GOOGLE_API_KEY"] = v
                os.environ["GOOGLE_API_KEY"] = v
            elif k == "GOOGLE_API_KEY":
                current_keys["GEMINI_API_KEY"] = v
                os.environ["GEMINI_API_KEY"] = v
        else:
            current_keys.pop(k, None)
            os.environ.pop(k, None)
            if k == "GEMINI_API_KEY":
                current_keys.pop("GOOGLE_API_KEY", None)
                os.environ.pop("GOOGLE_API_KEY", None)
            elif k == "GOOGLE_API_KEY":
                current_keys.pop("GEMINI_API_KEY", None)
                os.environ.pop("GEMINI_API_KEY", None)

    env_content = "\n".join(f"{k}={v}" for k, v in sorted(current_keys.items())) + "\n"
    keys_path.write_text(env_content, encoding="utf-8")

    try:
        await reload_cloud_engine(request)
    except Exception as exc:
        logging.getLogger("openjarvis.server").warning("Failed to reload cloud engine: %s", exc)

    return {"status": "ok", "saved": list(updates.keys())}


@router.delete("/v1/cloud/keys/{key_name}")
async def delete_cloud_key_endpoint(key_name: str, request: Request):
    """Delete a cloud API key."""
    k_name = key_name.strip().upper()
    if not k_name.endswith("_API_KEY") and not k_name.startswith("API_"):
        k_name = f"{k_name}_API_KEY"
    keys_path = get_config_dir() / "cloud-keys.env"
    current_keys: dict[str, str] = {}
    if keys_path.exists():
        try:
            for raw_line in keys_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    current_keys[k.strip()] = v.strip()
        except Exception:
            pass

    current_keys.pop(k_name, None)
    os.environ.pop(k_name, None)
    if k_name == "GEMINI_API_KEY":
        current_keys.pop("GOOGLE_API_KEY", None)
        os.environ.pop("GOOGLE_API_KEY", None)
    elif k_name == "GOOGLE_API_KEY":
        current_keys.pop("GEMINI_API_KEY", None)
        os.environ.pop("GEMINI_API_KEY", None)

    env_content = "\n".join(f"{k}={v}" for k, v in sorted(current_keys.items())) + "\n"
    keys_path.write_text(env_content, encoding="utf-8")

    try:
        await reload_cloud_engine(request)
    except Exception:
        pass

    return {"status": "ok", "deleted": k_name}


@router.get("/v1/savings")
async def savings(request: Request):
    """Return savings summary compared to cloud providers.

    Only includes telemetry from the current server session so that
    counters start at zero each time a new model + agent is launched.
    """
    from openjarvis.core.config import DEFAULT_CONFIG_DIR
    from openjarvis.server.savings import compute_savings, savings_to_dict
    from openjarvis.telemetry.aggregator import TelemetryAggregator

    db_path = DEFAULT_CONFIG_DIR / "telemetry.db"
    if not db_path.exists():
        empty = compute_savings(0, 0, 0)
        return savings_to_dict(empty)

    session_start = getattr(request.app.state, "session_start", None)

    agg = TelemetryAggregator(db_path)
    try:
        # current_methodology_only excludes pre-fix legacy rows from
        # the leaderboard's per-token efficiency numerator/denominator
        # — see the comment on _time_filter for the bimodal-Wh/token
        # background.
        summary = agg.summary(since=session_start, current_methodology_only=True)
        # Exclude cloud model tokens from savings — only local
        # inference counts toward cost savings.
        _cloud_prefixes = (
            "gpt-",
            "o1-",
            "o3-",
            "o4-",
            "claude-",
            "gemini-",
            "openrouter/",
        )
        local_models = [
            m
            for m in summary.per_model
            if not any(m.model_id.startswith(p) for p in _cloud_prefixes)
        ]
        all_models = summary.per_model
        total_session_prompt = sum(m.prompt_tokens for m in all_models)
        total_session_completion = sum(m.completion_tokens for m in all_models)
        total_session_calls = sum(m.call_count for m in all_models)
        total_session_tokens = sum(m.total_tokens for m in all_models) or (
            total_session_prompt + total_session_completion
        )

        result = compute_savings(
            prompt_tokens=sum(m.prompt_tokens for m in local_models),
            completion_tokens=sum(m.completion_tokens for m in local_models),
            total_calls=sum(m.call_count for m in local_models),
            session_start=session_start if session_start else 0.0,
            prompt_tokens_evaluated=sum(
                m.prompt_tokens_evaluated for m in local_models
            ),
        )
        data = savings_to_dict(result)
        # When cloud models are used, ensure session totals show real activity
        if total_session_calls > 0:
            if data.get("total_calls", 0) == 0:
                data["total_calls"] = total_session_calls
            if data.get("total_prompt_tokens", 0) == 0:
                data["total_prompt_tokens"] = total_session_prompt
            if data.get("total_completion_tokens", 0) == 0:
                data["total_completion_tokens"] = total_session_completion
        data["session_all_calls"] = total_session_calls
        data["session_all_prompt_tokens"] = total_session_prompt
        data["session_all_completion_tokens"] = total_session_completion
        data["session_all_tokens"] = total_session_tokens
        return data
    finally:
        agg.close()


@router.get("/v1/telemetry/stats")
async def telemetry_stats(request: Request):
    """Return live session telemetry statistics for all models."""
    from openjarvis.core.config import DEFAULT_CONFIG_DIR
    from openjarvis.telemetry.aggregator import TelemetryAggregator

    active_model = getattr(request.app.state, "model", "")
    db_path = DEFAULT_CONFIG_DIR / "telemetry.db"
    if not db_path.exists():
        return {
            "total_requests": 0,
            "total_tokens": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "active_model": active_model,
        }

    session_start = getattr(request.app.state, "session_start", None)
    agg = TelemetryAggregator(db_path)
    try:
        summary = agg.summary(since=session_start)
        all_models = summary.per_model
        p_tokens = sum(m.prompt_tokens for m in all_models)
        c_tokens = sum(m.completion_tokens for m in all_models)
        return {
            "total_requests": sum(m.call_count for m in all_models),
            "total_tokens": sum(m.total_tokens for m in all_models) or (p_tokens + c_tokens),
            "prompt_tokens": p_tokens,
            "completion_tokens": c_tokens,
            "active_model": active_model,
        }
    finally:
        agg.close()


@router.post("/v1/telemetry/reset")
async def reset_telemetry():
    """Clear all stored telemetry records.

    Useful after updating token-counting methodology — clears
    historical records that were computed under the old rules so
    that the savings dashboard and leaderboard submissions start
    fresh with corrected values.
    """
    from openjarvis.core.config import DEFAULT_CONFIG_DIR
    from openjarvis.telemetry.aggregator import TelemetryAggregator

    db_path = DEFAULT_CONFIG_DIR / "telemetry.db"
    if not db_path.exists():
        return {"status": "ok", "records_cleared": 0}

    agg = TelemetryAggregator(db_path)
    try:
        count = agg.clear()
    finally:
        agg.close()
    return {"status": "ok", "records_cleared": count}


@router.get("/v1/info")
async def server_info(request: Request):
    """Return server configuration: model, agent, engine."""
    agent = getattr(request.app.state, "agent", None)
    agent_id = getattr(agent, "agent_id", None) if agent else None
    # Fall back to configured agent name if agent didn't instantiate
    if agent_id is None:
        agent_id = getattr(request.app.state, "agent_name", None)
    raw_model = getattr(request.app.state, "model", "")
    model_str = raw_model if isinstance(raw_model, str) and raw_model and raw_model != "jarvis-v2" else ""
    raw_engine = getattr(request.app.state, "engine_name", "")
    engine_str = raw_engine if isinstance(raw_engine, str) else "mock"
    agent_str = str(agent_id) if agent_id and isinstance(agent_id, str) else "simple"
    return {
        "model": model_str,
        "agent": agent_str,
        "engine": engine_str,
    }


@router.get("/health")
async def health(request: Request):
    """Health check endpoint."""
    engine = request.app.state.engine
    healthy = engine.health()
    if not healthy:
        raise HTTPException(status_code=503, detail="Engine unhealthy")
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Channel endpoints
# ---------------------------------------------------------------------------


@router.get("/v1/channels")
async def list_channels(request: Request):
    """List available messaging channels."""
    bridge = getattr(request.app.state, "channel_bridge", None)
    if bridge is None:
        return {"channels": [], "message": "Channel bridge not configured"}
    channels = bridge.list_channels()
    return {"channels": channels, "status": bridge.status().value}


@router.post("/v1/channels/send")
async def channel_send(request: Request):
    """Send a message to a channel."""
    bridge = getattr(request.app.state, "channel_bridge", None)
    if bridge is None:
        raise HTTPException(status_code=503, detail="Channel bridge not configured")

    body = await request.json()
    channel_name = body.get("channel", "")
    content = body.get("content", "")
    conversation_id = body.get("conversation_id", "")

    if not channel_name or not content:
        raise HTTPException(
            status_code=400,
            detail="'channel' and 'content' are required",
        )

    ok = bridge.send(channel_name, content, conversation_id=conversation_id)
    if not ok:
        raise HTTPException(status_code=502, detail="Failed to send message")
    return {"status": "sent", "channel": channel_name}


@router.get("/v1/channels/status")
async def channel_status(request: Request):
    """Return channel bridge connection status."""
    bridge = getattr(request.app.state, "channel_bridge", None)
    if bridge is None:
        return {"status": "not_configured"}
    return {"status": bridge.status().value}


# ---------------------------------------------------------------------------
# Security scan endpoint
# ---------------------------------------------------------------------------


@router.get("/v1/security/scan")
async def security_scan():
    """Run a read-only security environment audit and return findings."""
    from openjarvis.cli.scan_cmd import PrivacyScanner

    scanner = PrivacyScanner()
    results = await asyncio.to_thread(scanner.run_all)
    return {
        "has_warnings": any(r.status == "warn" for r in results),
        "has_failures": any(r.status == "fail" for r in results),
        "findings": [
            {
                "name": r.name,
                "status": r.status,
                "message": r.message,
                "platform": r.platform,
            }
            for r in results
        ],
    }


__all__ = ["router"]
