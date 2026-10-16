"""Tests for Gemini OpenAI-compatible routing, error sanitization, and regression prevention.

Validates:
1. Google streaming in cloud_router uses the official OpenAI-compatible endpoint
   (https://generativelanguage.googleapis.com/v1beta/openai/chat/completions).
2. API keys are sent ONLY via the Authorization: Bearer header.
3. Keys are NEVER placed in URL query strings.
4. Error messages (upstream errors, connection errors, HTTP errors) sanitize
   and redact secrets before bubbling to logs or client SSE streams.
5. GET /v1/models retains gemini engine models and attributes ownership correctly.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from openjarvis.core.types import Message, Role
from openjarvis.engine.openai_compat_engines import GeminiOpenAIEngine
from openjarvis.security.credential_stripper import (
    sanitize_error_message,
    sanitize_url,
)
from openjarvis.server.app import create_app
from openjarvis.server.cloud_router import stream_cloud


class TestCredentialStripperSanitization:
    def test_sanitize_url_redacts_sensitive_query_parameters(self) -> None:
        synthetic_key = "".join(["AQ.", "mock_exposed_key_123456789012345678901234567890"])
        raw_url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.5-pro:streamGenerateContent?alt=sse&key={synthetic_key}"
        )
        cleaned = sanitize_url(raw_url)
        assert synthetic_key not in cleaned
        assert "key=%5BREDACTED%5D" in cleaned or "key=[REDACTED]" in cleaned

    def test_sanitize_error_message_redacts_keys_and_bearer_tokens(self) -> None:
        synthetic_key = "".join(["AQ.", "mock_exposed_key_123456789012345678901234567890"])
        raw_error = (
            "Client error '404 Not Found' for url "
            f"'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:streamGenerateContent?alt=sse&key={synthetic_key}' "
            f"with Bearer {synthetic_key}"
        )
        cleaned = sanitize_error_message(raw_error)
        assert synthetic_key not in cleaned
        assert "[REDACTED" in cleaned


class TestCloudRouterGemini:
    @pytest.mark.asyncio
    async def test_google_streaming_uses_openai_compatible_endpoint(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        secret_key = "AQ.TestSecretGeminiKey1234567890abcdef"
        monkeypatch.setenv("GEMINI_API_KEY", secret_key)

        expected_url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

        with respx.mock:
            route = respx.post(expected_url).mock(
                return_value=httpx.Response(
                    200,
                    text=(
                        'data: {"choices": [{"delta": {"content": "Hello world!"}}]}\n\n'
                        "data: [DONE]\n\n"
                    ),
                    headers={"content-type": "text/event-stream"},
                )
            )

            tokens = []
            async for token in stream_cloud(
                "gemini-3.8-flash",
                [Message(role=Role.USER, content="Introduce yourself")],
            ):
                tokens.append(token)

        assert "".join(tokens) == "Hello world!"
        assert route.called
        last_request = route.calls.last.request

        # 1. Endpoint matches OpenAI-compatible path
        assert str(last_request.url) == expected_url

        # 2. Key is NEVER in URL or query params
        assert "key=" not in str(last_request.url)
        assert last_request.url.query == b""

        # 3. Key is sent ONLY via Bearer header
        assert last_request.headers["Authorization"] == f"Bearer {secret_key}"

        # 4. Request payload is OpenAI-compatible format
        body = json.loads(last_request.content.decode("utf-8"))
        assert body["model"] == "gemini-3.8-flash"
        assert body["messages"] == [{"role": "user", "content": "Introduce yourself"}]
        assert body["stream"] is True

    @pytest.mark.asyncio
    async def test_regression_key_never_in_url_or_raised_error_on_failure(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        secret_key = "AQ.TestSecretGeminiKey1234567890abcdef"
        monkeypatch.setenv("GEMINI_API_KEY", secret_key)

        with respx.mock:
            respx.post(
                "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
            ).mock(
                return_value=httpx.Response(
                    404,
                    json={
                        "error": {
                            "code": 404,
                            "message": f"Model gemini-3.8-flash not found with key {secret_key}",
                            "status": "NOT_FOUND",
                        }
                    },
                )
            )

            with pytest.raises(RuntimeError) as exc_info:
                async for _ in stream_cloud(
                    "gemini-3.8-flash",
                    [Message(role=Role.USER, content="Hi")],
                ):
                    pass

            error_msg = str(exc_info.value)
            # Secret key must NEVER appear in the error message
            assert secret_key not in error_msg
            assert "[REDACTED" in error_msg

    @pytest.mark.asyncio
    async def test_google_key_fallback_to_google_api_key(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setenv("GOOGLE_API_KEY", "AQ.FallbackGoogleApiKey1234567890")

        with respx.mock:
            route = respx.post(
                "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
            ).mock(
                return_value=httpx.Response(
                    200,
                    text='data: {"choices": [{"delta": {"content": "ok"}}]}\n\ndata: [DONE]\n\n',
                    headers={"content-type": "text/event-stream"},
                )
            )

            tokens = [
                t
                async for t in stream_cloud(
                    "gemini-3.8-flash",
                    [Message(role=Role.USER, content="ping")],
                )
            ]

        assert "".join(tokens) == "ok"
        assert (
            route.calls.last.request.headers["Authorization"]
            == "Bearer AQ.FallbackGoogleApiKey1234567890"
        )

    @pytest.mark.asyncio
    async def test_gemini_retries_transient_503_and_succeeds(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "AQ.GeminiKey12345678901234567890")
        monkeypatch.setattr("openjarvis.server.cloud_router._compute_retry_delay", lambda *a, **k: 0.01)

        expected_url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

        with respx.mock:
            route = respx.post(expected_url)
            # 1st call fails with 503 (high demand), 2nd call succeeds
            route.side_effect = [
                httpx.Response(
                    503,
                    json={"error": {"code": 503, "message": "The model is overloaded. Please try again later."}},
                ),
                httpx.Response(
                    200,
                    text='data: {"choices": [{"delta": {"content": "Recovered response"}}]}\n\ndata: [DONE]\n\n',
                    headers={"content-type": "text/event-stream"},
                ),
            ]

            tokens = [
                t
                async for t in stream_cloud(
                    "gemini-3.8-flash",
                    [Message(role=Role.USER, content="hello")],
                )
            ]

        assert "".join(tokens) == "Recovered response"
        assert route.call_count == 2

    @pytest.mark.asyncio
    async def test_gemini_retries_transient_429_respecting_retry_after(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "AQ.GeminiKey12345678901234567890")
        delays_computed = []

        def recording_compute(attempt, retry_after=None, **kwargs):
            delays_computed.append((attempt, retry_after))
            return 0.01

        monkeypatch.setattr("openjarvis.server.cloud_router._compute_retry_delay", recording_compute)

        expected_url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

        with respx.mock:
            route = respx.post(expected_url)
            route.side_effect = [
                httpx.Response(
                    429,
                    json={"error": {"code": 429, "message": "Rate limit exceeded"}},
                    headers={"Retry-After": "3"},
                ),
                httpx.Response(
                    200,
                    text='data: {"choices": [{"delta": {"content": "After 429"}}]}\n\ndata: [DONE]\n\n',
                    headers={"content-type": "text/event-stream"},
                ),
            ]

            tokens = [
                t
                async for t in stream_cloud(
                    "gemini-3.8-flash",
                    [Message(role=Role.USER, content="rate check")],
                )
            ]

        assert "".join(tokens) == "After 429"
        assert route.call_count == 2
        assert len(delays_computed) == 1
        assert delays_computed[0][1] == 3.0

    @pytest.mark.asyncio
    async def test_gemini_does_not_retry_non_retryable_401(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "AQ.GeminiKey12345678901234567890")

        expected_url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

        with respx.mock:
            route = respx.post(expected_url).mock(
                return_value=httpx.Response(
                    401,
                    json={"error": {"code": 401, "message": "Invalid API key"}},
                )
            )

            with pytest.raises(RuntimeError) as exc_info:
                async for _ in stream_cloud(
                    "gemini-3.8-flash",
                    [Message(role=Role.USER, content="auth check")],
                ):
                    pass

        assert "401" in str(exc_info.value)
        assert route.call_count == 1  # Exactly 1 call, zero retries


class TestServerRoutesGemini:
    def test_list_models_includes_gemini_model_when_engine_is_gemini(self) -> None:
        mock_engine = MagicMock(spec=GeminiOpenAIEngine)
        mock_engine.engine_id = "gemini"
        mock_engine.list_models.return_value = ["gemini-3.8-flash", "gemini-3.5-flash"]

        app = create_app(engine=mock_engine, model="gemini-3.8-flash")
        client = TestClient(app)

        resp = client.get("/v1/models")
        assert resp.status_code == 200
        data = resp.json()["data"]
        model_ids = [m["id"] for m in data]
        assert "gemini-3.8-flash" in model_ids
        gemini_obj = next(m for m in data if m["id"] == "gemini-3.8-flash")
        assert gemini_obj["owned_by"] == "gemini"

    def test_chat_stream_sse_scrubs_secrets_on_generation_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        mock_engine = MagicMock(spec=GeminiOpenAIEngine)
        mock_engine.engine_id = "gemini"
        leaked_secret = "".join(["AQ.", "synthetic_leaked_key_12345678901234567890"])

        async def failing_stream(*args, **kwargs):
            raise RuntimeError(
                f"Client error '404 Not Found' for url 'https://google.example/stream?key={leaked_secret}'"
            )
            yield ""  # generator

        mock_engine.stream = failing_stream

        app = create_app(engine=mock_engine, model="gemini-3.8-flash")
        client = TestClient(app)

        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "gemini-3.8-flash",
                "messages": [{"role": "user", "content": "Hi"}],
                "stream": True,
            },
        )
        assert resp.status_code == 200
        content = resp.text

        # The leaked secret MUST be redacted in the SSE chunk stream
        assert leaked_secret not in content
        assert "[REDACTED" in content
        assert "Error during generation" in content or "Generation Error" in content
        # Ensure telemetry with engine is included even on error chunk
        assert '"telemetry"' in content
        assert '"gemini"' in content
