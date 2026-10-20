"""Shared base for OpenAI-compatible ``/v1/`` engines."""

from __future__ import annotations

import asyncio
import datetime
import email.utils
import json
import logging
import random
from collections.abc import AsyncIterator, Sequence
from typing import Any, Dict, List

import httpx

from openjarvis.core.types import Message
from openjarvis.engine._base import (
    EngineConnectionError,
    EngineContextLengthError,
    InferenceEngine,
    estimate_prompt_tokens,
    messages_to_dicts,
)
from openjarvis.engine._http_async import (
    STREAM_TRANSPORT_ERRORS,
    AsyncHTTPEngineMixin,
)
from openjarvis.engine._stubs import StreamChunk
from openjarvis.intelligence.model_catalog import resolve_model_id_for_engine

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = (429, 502, 503, 504)


def _parse_retry_after(header_val: str | None) -> float | None:
    """Parse a Retry-After header as either seconds or an HTTP date."""
    if not header_val:
        return None
    val = header_val.strip()
    try:
        sec = float(val)
        if sec >= 0:
            return sec
    except ValueError:
        pass
    try:
        dt = email.utils.parsedate_to_datetime(val)
        now = datetime.datetime.now(datetime.timezone.utc)
        return max(0.0, (dt - now).total_seconds())
    except Exception:
        pass
    return None


def _compute_retry_delay(
    attempt: int,
    retry_after: float | None = None,
    base_delay: float = 1.0,
    max_delay: float = 8.0,
) -> float:
    """Compute exponential backoff delay with jitter, respecting Retry-After."""
    backoff = min(max_delay, base_delay * (2**attempt))
    jitter = backoff * random.uniform(-0.25, 0.25)
    delay = max(0.1, backoff + jitter)
    if retry_after is not None:
        delay = max(delay, retry_after)
    return min(delay, 15.0)


class _OpenAICompatibleEngine(AsyncHTTPEngineMixin, InferenceEngine):
    """Base for engines that serve the OpenAI ``/v1/chat/completions`` API."""

    # vLLM/SGLang report context-window overflows in 400 bodies; the shared
    # ``_raise_stream_http_error`` types those as ``EngineContextLengthError``.
    _stream_400_signals_context_length = True

    engine_id: str = ""
    _default_host: str = "http://localhost:8000"
    _api_prefix: str = "/v1"

    def __init__(
        self,
        host: str | None = None,
        *,
        api_key: str | None = None,
        timeout: float = 600.0,
    ) -> None:
        import os

        # Sanitize the engine id for env-var lookup ("openai-compat" ->
        # "OPENAI_COMPAT_..."); shells cannot set hyphenated variable names.
        env_prefix = self.engine_id.upper().replace("-", "_")
        self._host = (
            host or os.environ.get(f"{env_prefix}_HOST") or self._default_host
        ).rstrip("/")
        # Bearer auth for endpoints started with e.g. ``vllm serve --api-key``.
        # Setting it on the client covers generate/stream/stream_full/
        # list_models/health alike; ``None`` keeps requests header-free.
        resolved_key = api_key or os.environ.get(f"{env_prefix}_API_KEY")
        if not resolved_key and env_prefix == "GEMINI":
            resolved_key = os.environ.get("GOOGLE_API_KEY")
        if resolved_key:
            resolved_key = resolved_key.strip().strip("'\"").strip()
        self._api_key = resolved_key or None
        headers = (
            {"Authorization": f"Bearer {self._api_key}"} if self._api_key else None
        )
        # Used by the shared async streaming plumbing (AsyncHTTPEngineMixin) so
        # the bounded request timeout is applied to streaming reads, not just
        # the synchronous methods (a wedged token read fails at ``timeout``
        # rather than hanging the caller for the httpx default).
        self._timeout = timeout
        self._headers = headers
        # Injection seam for tests: an ``httpx.MockTransport`` swapped in here lets
        # the async stream path be exercised with a mocked transport and no real
        # server. ``None`` in production so httpx uses its default networking.
        self._async_transport: httpx.AsyncBaseTransport | None = None
        self._client = httpx.Client(
            base_url=self._host, timeout=timeout, headers=headers
        )
        self.last_health_status: int | None = None
        self.last_health_error: str | None = None
        self._extra_contents: Dict[str, Any] = {}

    # -- InferenceEngine interface ------------------------------------------

    def _resolve_model_id(self, model: str) -> str:
        resolved = resolve_model_id_for_engine(model, self.engine_id)
        if self.engine_id == "gemini" and not resolved.startswith("models/"):
            return f"models/{resolved}"
        return resolved

    def generate(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        payload_messages = messages_to_dicts(messages)
        # Ensure engine-tracked extra_content (such as Google Gemini thought_signatures)
        # is preserved on tool calls in conversation history
        for msg in payload_messages:
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    call_id = tc.get("id")
                    if not tc.get("extra_content") and call_id in self._extra_contents:
                        tc["extra_content"] = self._extra_contents[call_id]

        payload: Dict[str, Any] = {
            "model": self._resolve_model_id(model),
            "messages": payload_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
            **kwargs,
        }
        # Default to tool_choice=auto when tools are provided
        if "tools" in payload and "tool_choice" not in payload:
            payload["tool_choice"] = "auto"
        url = f"{self._api_prefix}/chat/completions"
        attempt = 0
        max_retries = 3
        while True:
            try:
                resp = self._client.post(url, json=payload)
                if resp.status_code == 400 and "tools" in payload:
                    payload.pop("tools", None)
                    payload.pop("tool_choice", None)
                    resp = self._client.post(url, json=payload)
                if resp.status_code in RETRYABLE_STATUS_CODES and attempt < max_retries:
                    err_txt = resp.text.lower()
                    if resp.status_code == 429 and ("quota" in err_txt or "resource_exhausted" in err_txt):
                        resp.raise_for_status()
                    retry_after = _parse_retry_after(resp.headers.get("retry-after"))
                    if retry_after is not None and retry_after > 30:
                        resp.raise_for_status()
                    delay = _compute_retry_delay(attempt, retry_after)
                    logger.warning(
                        "%s engine busy (HTTP %d); retrying in %.2fs (attempt %d/%d)",
                        self.engine_id,
                        resp.status_code,
                        delay,
                        attempt + 1,
                        max_retries,
                    )
                    attempt += 1
                    import time

                    time.sleep(delay)
                    continue
                resp.raise_for_status()
                break
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                if attempt < max_retries:
                    delay = _compute_retry_delay(attempt)
                    logger.warning(
                        "%s engine connection error; retrying in %.2fs (attempt %d/%d)",
                        self.engine_id,
                        delay,
                        attempt + 1,
                        max_retries,
                    )
                    attempt += 1
                    import time

                    time.sleep(delay)
                    continue
                raise EngineConnectionError(
                    f"{self.engine_id} engine not reachable at {self._host}"
                ) from exc
            except httpx.HTTPStatusError as exc:
                error_detail = exc.response.text.strip()
                if exc.response.status_code == 404:
                    detail_suffix = (
                        f" Response body: {error_detail}" if error_detail else ""
                    )
                    raise EngineConnectionError(
                        f"{self.engine_id} engine at {self._host} returned 404 for "
                        f"{self._api_prefix}/chat/completions. Make sure this port "
                        "is running an OpenAI-compatible chat server, not another "
                        f"local web service.{detail_suffix}"
                    ) from exc
                detail_suffix = f": {error_detail}" if error_detail else ""
                raise EngineConnectionError(
                    f"{self.engine_id} engine at {self._host} returned HTTP "
                    f"{exc.response.status_code}{detail_suffix}"
                ) from exc
        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            return {
                "content": "",
                "usage": data.get("usage", {}),
                "model": data.get("model", model),
                "finish_reason": "error",
            }
        choice = choices[0]
        usage = data.get("usage", {})
        # Ensure prompt_tokens reflects the full prompt size (including
        # system prompt and all conversation history).
        # OpenAI-compat APIs (vLLM, SGLang) report full counts — KV
        # caching is transparent, so evaluated == full.
        reported_prompt = usage.get("prompt_tokens", 0)
        estimated_prompt = estimate_prompt_tokens(messages)
        prompt_tokens = max(reported_prompt, estimated_prompt)
        completion_tokens = usage.get("completion_tokens", 0)
        result: Dict[str, Any] = {
            "content": choice["message"].get("content") or "",
            "usage": {
                "prompt_tokens": prompt_tokens,
                "prompt_tokens_evaluated": reported_prompt or prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
            "model": data.get("model", model),
            "finish_reason": choice.get("finish_reason", "stop"),
        }
        # Extract tool calls if present
        raw_tool_calls = choice["message"].get("tool_calls", [])
        if raw_tool_calls:
            extracted_tcs = []
            for tc in raw_tool_calls:
                call_id = tc.get("id", "")
                extra_content = tc.get("extra_content")
                if extra_content and call_id:
                    self._extra_contents[call_id] = extra_content
                tc_dict = {
                    "id": call_id,
                    "name": tc.get("function", {}).get("name", ""),
                    "arguments": tc.get("function", {}).get("arguments", "{}"),
                }
                if extra_content:
                    tc_dict["extra_content"] = extra_content
                extracted_tcs.append(tc_dict)
            result["tool_calls"] = extracted_tcs
        return result

    async def stream(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        payload: Dict[str, Any] = {
            "model": self._resolve_model_id(model),
            "messages": messages_to_dicts(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            **kwargs,
        }
        # Default to tool_choice=auto when tools are provided
        if "tools" in payload and "tool_choice" not in payload:
            payload["tool_choice"] = "auto"
        url = f"{self._api_prefix}/chat/completions"
        attempt = 0
        max_retries = 3
        yielded_any_token = False

        while True:
            try:
                # ASYNC streaming: ``httpx.AsyncClient`` + ``aiter_lines`` never
                # blocks the event loop between tokens (the previous SYNC
                # ``httpx.Client`` + ``iter_lines`` inside this ``async def`` blocked
                # the single uvicorn worker on every inter-token wait, serializing all
                # concurrent chats and letting one wedged read freeze the whole API).
                # The shared client keeps pooled connections across turns.
                client = self._get_async_client()
                async with client.stream("POST", url, json=payload) as resp:
                    # ``not is_success`` covers 3xx as well as 4xx/5xx. With
                    # ``follow_redirects`` off (the default) an unexpected redirect
                    # would otherwise fall through to ``aiter_lines`` and surface as
                    # a silent EMPTY stream instead of a clean engine error.
                    if not resp.is_success:
                        # Load the (short) error body before touching ``.text``:
                        # a streaming response is otherwise unread.
                        await resp.aread()
                        if (
                            not yielded_any_token
                            and attempt < max_retries
                            and resp.status_code in RETRYABLE_STATUS_CODES
                        ):
                            err_txt = resp.text.lower()
                            if resp.status_code == 429 and ("quota" in err_txt or "resource_exhausted" in err_txt):
                                self._raise_stream_http_error(resp.status_code, resp.text)
                            retry_after = _parse_retry_after(resp.headers.get("retry-after"))
                            if retry_after is not None and retry_after > 30:
                                self._raise_stream_http_error(resp.status_code, resp.text)
                            delay = _compute_retry_delay(attempt, retry_after)
                            logger.warning(
                                "%s engine busy (HTTP %d); retrying in %.2fs (attempt %d/%d)",
                                self.engine_id,
                                resp.status_code,
                                delay,
                                attempt + 1,
                                max_retries,
                            )
                            attempt += 1
                            await asyncio.sleep(delay)
                            continue
                        self._raise_stream_http_error(resp.status_code, resp.text)
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data_str = line[len("data:") :].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content")
                        if content:
                            yielded_any_token = True
                            yield content
                break
            except STREAM_TRANSPORT_ERRORS as exc:
                # A wedged upstream read trips ``timeout`` (ReadTimeout) and is mapped
                # here, so the request fails cleanly at the configured bound instead
                # of hanging indefinitely (see STREAM_TRANSPORT_ERRORS for why the
                # set is exactly this narrow).
                if not yielded_any_token and attempt < max_retries:
                    delay = _compute_retry_delay(attempt)
                    logger.warning(
                        "%s engine connection error; retrying in %.2fs (attempt %d/%d)",
                        self.engine_id,
                        delay,
                        attempt + 1,
                        max_retries,
                    )
                    attempt += 1
                    await asyncio.sleep(delay)
                    continue
                raise EngineConnectionError(
                    f"{self.engine_id} engine not reachable at {self._host}"
                ) from exc

    async def stream_full(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> AsyncIterator["StreamChunk"]:
        """Yield StreamChunks with content, tool_calls, and finish_reason."""
        msg_dicts = messages_to_dicts(messages)
        payload: Dict[str, Any] = {
            "model": self._resolve_model_id(model),
            "messages": msg_dicts,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            **kwargs,
        }
        if "tools" in payload and "tool_choice" not in payload:
            payload["tool_choice"] = "auto"
        url = f"{self._api_prefix}/chat/completions"
        attempt = 0
        max_retries = 3
        yielded_any = False

        while True:
            try:
                # ASYNC streaming (see ``stream``): non-blocking shared client so
                # rich streaming never stalls the event loop and honours ``timeout``.
                client = self._get_async_client()
                async with client.stream("POST", url, json=payload) as resp:
                    # ``not is_success`` covers 3xx as well as 4xx/5xx. With
                    # ``follow_redirects`` off (the default) an unexpected redirect
                    # would otherwise fall through to ``aiter_lines`` and surface as
                    # a silent EMPTY stream instead of a clean engine error.
                    if not resp.is_success:
                        await resp.aread()
                        if (
                            not yielded_any
                            and attempt < max_retries
                            and resp.status_code in RETRYABLE_STATUS_CODES
                        ):
                            retry_after = _parse_retry_after(resp.headers.get("retry-after"))
                            delay = _compute_retry_delay(attempt, retry_after)
                            logger.warning(
                                "%s engine busy (HTTP %d); retrying in %.2fs (attempt %d/%d)",
                                self.engine_id,
                                resp.status_code,
                                delay,
                                attempt + 1,
                                max_retries,
                            )
                            attempt += 1
                            await asyncio.sleep(delay)
                            continue
                        self._raise_stream_http_error(resp.status_code, resp.text)
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data_str = line[len("data:") :].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        choice = chunk.get("choices", [{}])[0]
                        delta = choice.get("delta", {})
                        finish = choice.get("finish_reason")
                        content = delta.get("content")
                        tool_calls = delta.get("tool_calls")
                        usage = chunk.get("usage")

                        if content or tool_calls or finish or usage:
                            yielded_any = True
                            yield StreamChunk(
                                content=content,
                                tool_calls=tool_calls,
                                finish_reason=finish,
                                usage=usage,
                            )
                break
            except STREAM_TRANSPORT_ERRORS as exc:
                # See ``stream``: transport failures (incl. a mid-stream server
                # disconnect) map to a clean error; the set is kept narrow so
                # cancellation still propagates.
                if not yielded_any and attempt < max_retries:
                    delay = _compute_retry_delay(attempt)
                    logger.warning(
                        "%s engine connection error; retrying in %.2fs (attempt %d/%d)",
                        self.engine_id,
                        delay,
                        attempt + 1,
                        max_retries,
                    )
                    attempt += 1
                    await asyncio.sleep(delay)
                    continue
                raise EngineConnectionError(
                    f"{self.engine_id} engine not reachable at {self._host}"
                ) from exc

    def list_models(self) -> List[str]:
        try:
            resp = self._client.get(f"{self._api_prefix}/models")
            resp.raise_for_status()
        except (
            httpx.ConnectError,
            httpx.TimeoutException,
            httpx.HTTPStatusError,
        ) as exc:
            logger.warning(
                "Failed to list models from %s at %s: %s",
                self.engine_id,
                self._host,
                exc,
            )
            return []
        data = resp.json()
        models = [m["id"] for m in data.get("data", [])]
        normalized: list[str] = []
        for m in models:
            normalized.append(m)
            if m.startswith("models/"):
                short = m[len("models/") :]
                if short not in normalized:
                    normalized.append(short)
        return normalized

    def health(self) -> bool:
        try:
            resp = self._client.get(f"{self._api_prefix}/models", timeout=3.0)
            self.last_health_status = resp.status_code
            if resp.status_code == 200:
                self.last_health_error = None
                return True
            if resp.status_code in (401, 403) or (
                resp.status_code == 400
                and any(w in resp.text.lower() for w in ("api_key", "api key", "invalid key"))
            ):
                self.last_health_error = f"Authentication failed: API key rejected or revoked (HTTP {resp.status_code})"
                logger.error(
                    "%s health check failed (HTTP %d): %s",
                    self.engine_id,
                    resp.status_code,
                    self.last_health_error,
                )
            elif resp.status_code in (429, 502, 503, 504):
                self.last_health_error = f"Provider temporarily unavailable (HTTP {resp.status_code})"
                logger.warning(
                    "%s health check failed (HTTP %d): %s",
                    self.engine_id,
                    resp.status_code,
                    self.last_health_error,
                )
            else:
                self.last_health_error = f"Health check returned HTTP {resp.status_code}"
                logger.debug(
                    "%s health check failed (HTTP %d): %s",
                    self.engine_id,
                    resp.status_code,
                    resp.text,
                )
            return False
        except Exception as exc:
            self.last_health_status = None
            self.last_health_error = str(exc)
            logger.debug(
                "%s health check failed at %s: %s",
                self.engine_id,
                self._host,
                exc,
            )
            return False

    def close(self) -> None:
        self._client.close()
        self._close_async_client()


# ``EngineContextLengthError`` moved to ``openjarvis.engine._base``; re-exported
# here for callers/tests that import it from this module.
__all__ = ["_OpenAICompatibleEngine", "EngineContextLengthError"]
