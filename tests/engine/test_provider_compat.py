"""Tests for model provider configuration, compatibility, and security.

Covers:
1. Valid configuration across provider matrix (Gemini, OpenAI, Anthropic, Ollama, custom OpenAI-compatible).
2. Missing or invalid configuration detection.
3. Authentication error handling (401 / 403).
4. Timeout and connection error resilience.
5. API key masking and credential sanitization (zero plaintext secrets in responses/errors).
6. OpenAI-compatible endpoint request formatting and URL normalization.
"""

from __future__ import annotations

import json
from typing import Any, Dict

import httpx
import pytest
import respx

from openjarvis.core.types import Message, Role
from openjarvis.engine._base import EngineConnectionError
from openjarvis.engine.cloud import CloudEngine
from openjarvis.engine.ollama import OllamaEngine
from openjarvis.engine.openai_compat_engines import (
    OpenAICompatEngine,
    normalize_openai_base_url,
)
from openjarvis.security.credential_stripper import (
    CredentialStripper,
    sanitize_error_message,
    sanitize_url,
)
from openjarvis.server.cloud_router import stream_cloud, stream_local

_MOCK_CHAT_RESPONSE: Dict[str, Any] = {
    "choices": [
        {
            "message": {"role": "assistant", "content": "Confirmed operational."},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16},
    "model": "test-model",
}


# ===========================================================================
# 1. Valid Configuration Across Provider Matrix
# ===========================================================================


class TestValidConfiguration:
    def test_openai_compatible_valid_config(self) -> None:
        """OpenAI-compatible engine correctly constructs request with Bearer auth and parses response."""
        engine = OpenAICompatEngine(
            host="http://custom-ai.internal:8000",
            api_key="sk-test-valid-key-1234567890",
        )
        with respx.mock:
            route = respx.post("http://custom-ai.internal:8000/v1/chat/completions").mock(
                return_value=httpx.Response(200, json=_MOCK_CHAT_RESPONSE)
            )
            result = engine.generate(
                [Message(role=Role.USER, content="System check")],
                model="custom-model",
            )

        assert route.called
        sent_request = route.calls.last.request
        assert sent_request.headers["Authorization"] == "Bearer sk-test-valid-key-1234567890"
        assert result["content"] == "Confirmed operational."
        assert result["usage"]["prompt_tokens"] >= 12
        assert result["usage"]["completion_tokens"] == 4

    def test_ollama_valid_config(self) -> None:
        """Ollama engine communicates with /api/chat and maps response."""
        engine = OllamaEngine(host="http://localhost:11434")
        ollama_response = {
            "model": "qwen2.5:7b",
            "message": {"role": "assistant", "content": "Ultron online."},
            "done": True,
            "prompt_eval_count": 10,
            "eval_count": 5,
        }
        with respx.mock:
            route = respx.post("http://localhost:11434/api/chat").mock(
                return_value=httpx.Response(200, json=ollama_response)
            )
            result = engine.generate(
                [Message(role=Role.USER, content="Status")],
                model="qwen2.5:7b",
            )

        assert route.called
        assert result["content"] == "Ultron online."
        assert result["model"] == "qwen2.5:7b"
        assert result["usage"]["completion_tokens"] == 5

    @pytest.mark.asyncio
    async def test_gemini_cloud_router_streaming(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Gemini stream routes through official OpenAI-compatible endpoint with GEMINI_API_KEY."""
        monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyTestValidGeminiKeyABC12345678")
        # Ensure fast-path greeting is bypassed by using a task prompt
        messages = [Message(role=Role.USER, content="Calculate quantum hash matrix")]

        stream_body = (
            'data: {"choices":[{"delta":{"content":"Quantum "}}]}\n\n'
            'data: {"choices":[{"delta":{"content":"coherent."}}]}\n\n'
            "data: [DONE]\n\n"
        )

        with respx.mock:
            route = respx.post(
                "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
            ).mock(
                return_value=httpx.Response(
                    200,
                    text=stream_body,
                    headers={"Content-Type": "text/event-stream"},
                )
            )
            tokens = []
            async for token in stream_cloud("gemini-3.8-flash", messages):
                tokens.append(token)

        assert route.called
        sent_request = route.calls.last.request
        assert "Authorization" in sent_request.headers
        assert "".join(tokens) == "Quantum coherent."

    @pytest.mark.asyncio
    async def test_anthropic_cloud_router_streaming(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Anthropic stream routes to api.anthropic.com with x-api-key header."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-anthropic-key-1234567890")
        messages = [Message(role=Role.USER, content="Execute neural synthesis")]

        stream_body = (
            'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Synthesizing "}}\n\n'
            'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"matrix."}}\n\n'
        )

        with respx.mock:
            route = respx.post("https://api.anthropic.com/v1/messages").mock(
                return_value=httpx.Response(
                    200,
                    text=stream_body,
                    headers={"Content-Type": "text/event-stream"},
                )
            )
            tokens = []
            async for token in stream_cloud("claude-sonnet-4-6", messages):
                tokens.append(token)

        assert route.called
        sent_request = route.calls.last.request
        assert sent_request.headers["x-api-key"] == "sk-ant-test-anthropic-key-1234567890"
        assert "".join(tokens) == "Synthesizing matrix."


# ===========================================================================
# 2. Missing or Invalid Configuration Detection
# ===========================================================================


class TestMissingOrInvalidConfiguration:
    @pytest.mark.asyncio
    async def test_missing_openai_key_in_cloud_router(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Invoking OpenAI model without OPENAI_API_KEY raises actionable ValueError."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        messages = [Message(role=Role.USER, content="Initialize core")]
        with pytest.raises(ValueError, match="OPENAI_API_KEY not set"):
            async for _ in stream_cloud("gpt-4o", messages):
                pass

    @pytest.mark.asyncio
    async def test_missing_gemini_key_in_cloud_router(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Invoking Gemini model without GEMINI_API_KEY or GOOGLE_API_KEY raises ValueError."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        messages = [Message(role=Role.USER, content="Initialize core")]
        with pytest.raises(ValueError, match="GEMINI_API_KEY not set"):
            async for _ in stream_cloud("gemini-3.8-flash", messages):
                pass

    @pytest.mark.asyncio
    async def test_missing_anthropic_key_in_cloud_router(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Invoking Anthropic model without ANTHROPIC_API_KEY raises ValueError."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        messages = [Message(role=Role.USER, content="Initialize core")]
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY not set"):
            async for _ in stream_cloud("claude-sonnet-4-6", messages):
                pass

    @pytest.mark.asyncio
    async def test_unsupported_cloud_provider_model(self) -> None:
        """Attempting to stream an unknown model raises ValueError."""
        messages = [Message(role=Role.USER, content="Initialize core")]
        with pytest.raises(ValueError, match="Unknown cloud provider for model"):
            async for _ in stream_cloud("unknown-proprietary-model-x9", messages):
                pass

    def test_cloud_engine_missing_clients_raise_connection_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CloudEngine without SDK clients raises EngineConnectionError when called."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

        engine = CloudEngine()
        messages = [Message(role=Role.USER, content="Check diagnostics")]

        with pytest.raises(EngineConnectionError, match="OpenAI client not available"):
            engine._generate_openai(messages, model="gpt-4o", temperature=0.7, max_tokens=100)

        with pytest.raises(EngineConnectionError, match="Anthropic client not available"):
            engine._generate_anthropic(messages, model="claude-sonnet-4-6", temperature=0.7, max_tokens=100)

        with pytest.raises(EngineConnectionError, match="Google client not available"):
            engine._generate_google(messages, model="gemini-3.8-flash", temperature=0.7, max_tokens=100)


# ===========================================================================
# 3. Authentication Errors (401 / 403)
# ===========================================================================


class TestAuthenticationErrors:
    def test_openai_compat_handles_401_unauthorized(self) -> None:
        """401 Unauthorized returns structured EngineConnectionError with status code."""
        engine = OpenAICompatEngine(
            host="http://custom-ai.internal:8000",
            api_key="sk-invalid-key-attempt",
        )
        with respx.mock:
            respx.post("http://custom-ai.internal:8000/v1/chat/completions").mock(
                return_value=httpx.Response(
                    401,
                    json={"error": {"message": "Incorrect API key provided"}},
                )
            )
            with pytest.raises(EngineConnectionError) as exc_info:
                engine.generate(
                    [Message(role=Role.USER, content="Test auth")],
                    model="test-model",
                )

        assert "HTTP 401" in str(exc_info.value)
        assert "Incorrect API key" in str(exc_info.value)

    def test_openai_compat_handles_403_forbidden(self) -> None:
        """403 Forbidden raises EngineConnectionError."""
        engine = OpenAICompatEngine(host="http://custom-ai.internal:8000")
        with respx.mock:
            respx.post("http://custom-ai.internal:8000/v1/chat/completions").mock(
                return_value=httpx.Response(
                    403,
                    text="Access forbidden: project quota or IP restriction",
                )
            )
            with pytest.raises(EngineConnectionError) as exc_info:
                engine.generate(
                    [Message(role=Role.USER, content="Test auth")],
                    model="test-model",
                )

        assert "HTTP 403" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_cloud_router_handles_401_with_sanitized_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Cloud router surfaces 401 cleanly with sanitized error message."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai-key-sample")
        messages = [Message(role=Role.USER, content="Deploy shields")]

        with respx.mock:
            respx.post("https://api.openai.com/v1/chat/completions").mock(
                return_value=httpx.Response(
                    401,
                    json={"error": {"message": "Invalid authentication token: Bearer sk-test-openai-key-sample"}},
                )
            )
            with pytest.raises(RuntimeError) as exc_info:
                async for _ in stream_cloud("gpt-4o", messages):
                    pass

        err_text = str(exc_info.value)
        assert "Cloud provider error (401)" in err_text
        # Ensure the secret token itself was scrubbed
        assert "sk-test-openai-key-sample" not in err_text
        assert "[REDACTED" in err_text


# ===========================================================================
# 4. Timeout and Connection Errors
# ===========================================================================


class TestTimeoutAndConnectionErrors:
    def test_ollama_engine_handles_connection_failure(self) -> None:
        """When Ollama is not running, EngineConnectionError is raised."""
        engine = OllamaEngine(host="http://127.0.0.1:19999", timeout=1.0)
        with pytest.raises(EngineConnectionError, match="Ollama not reachable"):
            engine.generate([Message(role=Role.USER, content="Ping")], model="llama3")

    def test_openai_compat_handles_connection_failure_after_retries(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OpenAI-compat engine raises EngineConnectionError when host is unreachable."""
        # Speed up retry delay for deterministic test speed
        monkeypatch.setattr(
            "openjarvis.engine._openai_compat._compute_retry_delay",
            lambda attempt, retry_after=None: 0.01,
        )
        engine = OpenAICompatEngine(host="http://127.0.0.1:19998", timeout=0.5)
        with pytest.raises(EngineConnectionError, match="not reachable"):
            engine.generate([Message(role=Role.USER, content="Ping")], model="vllm-model")

    @pytest.mark.asyncio
    async def test_cloud_router_handles_connection_timeout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Cloud router raises RuntimeError on connection timeout after retries."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-timeout")
        monkeypatch.setattr(
            "openjarvis.server.cloud_router._compute_retry_delay",
            lambda attempt, retry_after=None: 0.01,
        )
        messages = [Message(role=Role.USER, content="Deploy drone")]

        with respx.mock:
            respx.post("https://api.openai.com/v1/chat/completions").mock(
                side_effect=httpx.ConnectTimeout("Connection timed out")
            )
            with pytest.raises(RuntimeError, match="Cloud provider connection error"):
                async for _ in stream_cloud("gpt-4o", messages):
                    pass


# ===========================================================================
# 5. API Key Masking and Security
# ===========================================================================


class TestApiKeyMaskingAndSanitization:
    def test_sanitize_error_message_redacts_keys(self) -> None:
        """CredentialStripper scrubs OpenAI, Gemini, and Bearer tokens from errors."""
        raw_error = (
            "API failed with sk-proj-1234567890abcdefghijklmnopqrstuvwxyz "
            "and Gemini key AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q "
            "using header Bearer secret-bearer-token-1234567890"
        )
        sanitized = sanitize_error_message(raw_error)

        assert "sk-proj-1234567890abcdefghijklmnopqrstuvwxyz" not in sanitized
        assert "AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q" not in sanitized
        assert "secret-bearer-token-1234567890" not in sanitized
        assert "[REDACTED:api_key]" in sanitized
        assert "[REDACTED:google_gemini_key]" in sanitized
        assert "Bearer [REDACTED" in sanitized

    def test_sanitize_url_redacts_query_parameters(self) -> None:
        """Sensitive URL query parameters like ?key=... are scrubbed."""
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro?key=AIzaSySecretApiKey1234567890"
        sanitized = sanitize_url(url)

        assert "AIzaSySecretApiKey1234567890" not in sanitized
        assert "key=%5BREDACTED%5D" in sanitized or "key=[REDACTED]" in sanitized

    def test_credential_stripper_class_instance(self) -> None:
        """CredentialStripper.strip works identically."""
        stripper = CredentialStripper()
        text = "Failed on key sk-live-secret-test-key-1234567890"
        stripped = stripper.strip(text)
        assert "sk-live-secret-test-key-1234567890" not in stripped
        assert "[REDACTED:api_key]" in stripped


# ===========================================================================
# 6. OpenAI-Compatible Endpoint URL Normalization & Request Formatting
# ===========================================================================


class TestNormalizeOpenAIBaseUrlAndFormatting:
    @pytest.mark.parametrize(
        ("input_url", "expected_base"),
        [
            ("http://localhost:8000", "http://localhost:8000"),
            ("http://localhost:8000/", "http://localhost:8000"),
            ("http://localhost:8000/v1", "http://localhost:8000"),
            ("http://localhost:8000/v1/", "http://localhost:8000"),
            ("http://api.local:8080/custom/v1", "http://api.local:8080/custom"),
            ("http://api.local:8080/custom/v1/", "http://api.local:8080/custom"),
            ("http://api.local:8080/v2", "http://api.local:8080/v2"),
        ],
    )
    def test_normalize_openai_base_url(self, input_url: str, expected_base: str) -> None:
        """Strips literal trailing /v1 to prevent duplicate /v1/v1 in endpoint construction."""
        assert normalize_openai_base_url(input_url) == expected_base

    def test_single_v1_in_engine_request(self) -> None:
        """Engine configured with normalized URL calls /v1/chat/completions without repetition."""
        raw_url = "http://my-vllm-cluster:8000/v1/"
        normalized = normalize_openai_base_url(raw_url)
        engine = OpenAICompatEngine(host=normalized, api_key="sk-test-cluster")

        with respx.mock:
            route = respx.post("http://my-vllm-cluster:8000/v1/chat/completions").mock(
                return_value=httpx.Response(200, json=_MOCK_CHAT_RESPONSE)
            )
            engine.generate([Message(role=Role.USER, content="Ping")], model="cluster-model")

        assert route.called
        assert route.calls.last.request.url.path == "/v1/chat/completions"
