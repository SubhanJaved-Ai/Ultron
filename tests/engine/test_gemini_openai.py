"""Tests for the Gemini OpenAI-compatible engine backend.

Validates that the OpenAI-compatible endpoint for Google Gemini uses
``/v1`` prefix, sends Bearer auth with GEMINI_API_KEY, and handles health/errors.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from openjarvis.core.registry import EngineRegistry
from openjarvis.core.types import Message, Role
from openjarvis.engine._base import EngineConnectionError
from openjarvis.engine.openai_compat_engines import GeminiOpenAIEngine


@pytest.fixture()
def engine() -> GeminiOpenAIEngine:
    EngineRegistry.register_value("gemini", GeminiOpenAIEngine)
    return GeminiOpenAIEngine(
        host="https://generativelanguage.googleapis.com/v1beta/openai",
        api_key="test-gemini-key",
    )


class TestGeminiOpenAIEngineBasics:
    def test_engine_id(self) -> None:
        assert GeminiOpenAIEngine.engine_id == "gemini"

    def test_default_host(self) -> None:
        assert (
            GeminiOpenAIEngine._default_host
            == "https://generativelanguage.googleapis.com/v1beta/openai"
        )

    def test_api_prefix(self) -> None:
        assert GeminiOpenAIEngine._api_prefix == ""

    def test_registry_registration(self) -> None:
        EngineRegistry.register_value("gemini", GeminiOpenAIEngine)
        assert EngineRegistry.contains("gemini")
        assert EngineRegistry.get("gemini") is GeminiOpenAIEngine

    def test_can_serve_gemini_models(self, engine: GeminiOpenAIEngine) -> None:
        assert engine.can_serve("gemini-3.8-flash") is True
        assert engine.can_serve("gemini-2.5-pro") is True

    def test_env_var_overrides_default_host(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("GEMINI_HOST", "https://proxy.example.com/v1beta/openai")
        eng = GeminiOpenAIEngine()
        try:
            assert eng._host == "https://proxy.example.com/v1beta/openai"
        finally:
            eng.close()

    def test_env_var_sets_api_key(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "env-gemini-key")
        eng = GeminiOpenAIEngine()
        try:
            assert eng._api_key == "env-gemini-key"
        finally:
            eng.close()


class TestGeminiOpenAIGenerate:
    def test_generate_sends_bearer_and_uses_openai_endpoint(
        self, engine: GeminiOpenAIEngine
    ) -> None:
        with respx.mock:
            route = respx.post(
                "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
            ).mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "choices": [
                            {
                                "message": {"content": "Hello from Gemini!"},
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {
                            "prompt_tokens": 10,
                            "completion_tokens": 5,
                            "total_tokens": 15,
                        },
                        "model": "gemini-3.8-flash",
                    },
                )
            )
            result = engine.generate(
                [Message(role=Role.USER, content="Hello")],
                model="gemini-3.8-flash",
            )

        assert route.called
        assert route.calls.last.request.headers["Authorization"] == "Bearer test-gemini-key"
        assert result["content"] == "Hello from Gemini!"
        assert result["model"] == "gemini-3.8-flash"

    def test_generate_connection_error(self, engine: GeminiOpenAIEngine) -> None:
        with respx.mock:
            respx.post(
                "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
            ).mock(side_effect=httpx.ConnectError("Connection refused"))
            with pytest.raises(EngineConnectionError) as exc_info:
                engine.generate(
                    [Message(role=Role.USER, content="Hello")],
                    model="gemini-3.8-flash",
                )
            assert "not reachable" in str(exc_info.value)


class TestGeminiOpenAIHealthAndModels:
    def test_health_true_on_200(self, engine: GeminiOpenAIEngine) -> None:
        with respx.mock:
            route = respx.get(
                "https://generativelanguage.googleapis.com/v1beta/openai/models"
            ).mock(
                return_value=httpx.Response(200, json={"data": [{"id": "gemini-3.8-flash"}]})
            )
            assert engine.health() is True
        assert route.calls.last.request.headers["Authorization"] == "Bearer test-gemini-key"

    def test_health_false_on_400_invalid_key(self, engine: GeminiOpenAIEngine) -> None:
        with respx.mock:
            respx.get(
                "https://generativelanguage.googleapis.com/v1beta/openai/models"
            ).mock(
                return_value=httpx.Response(
                    400,
                    json={
                        "error": {
                            "code": 400,
                            "message": "API key not valid",
                            "status": "INVALID_ARGUMENT",
                        }
                    },
                )
            )
            assert engine.health() is False

    def test_health_false_on_timeout(self, engine: GeminiOpenAIEngine) -> None:
        with respx.mock:
            respx.get(
                "https://generativelanguage.googleapis.com/v1beta/openai/models"
            ).mock(side_effect=httpx.TimeoutException("Timed out"))
            assert engine.health() is False

    def test_list_models_extracts_model_ids(self, engine: GeminiOpenAIEngine) -> None:
        with respx.mock:
            respx.get(
                "https://generativelanguage.googleapis.com/v1beta/openai/models"
            ).mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "object": "list",
                        "data": [
                            {"id": "gemini-3.8-flash", "object": "model"},
                            {"id": "gemini-2.5-pro", "object": "model"},
                        ],
                    },
                )
            )
            models = engine.list_models()
        assert models == ["gemini-3.8-flash", "gemini-2.5-pro"]
