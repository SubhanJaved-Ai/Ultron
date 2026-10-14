"""Regression tests for production-grade Ultron startup and credential recovery.

Covers:
- First launch vs configured state
- Engine health and discovery on missing or revoked keys
- HTTP 401 authentication failure categorization
- HTTP 429 / 503 transient provider failure categorization
- Secret hygiene: credentials never leaked into logs, URLs, or errors
- Data preservation: user chat history and preferences preserved across credential changes
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import httpx
import pytest
import respx

from openjarvis.core.config import JarvisConfig
from openjarvis.core.registry import EngineRegistry
from openjarvis.engine._discovery import get_engine
from openjarvis.engine.openai_compat_engines import GeminiOpenAIEngine
from openjarvis.server.app import create_app


@pytest.fixture
def clean_registry():
    """Ensure engine registry state is pristine for each test."""
    original = dict(EngineRegistry._entries())
    yield
    EngineRegistry._entries().clear()
    EngineRegistry._entries().update(original)


class TestStartupAndCredentialRecoveryRegression:
    def test_gemini_missing_or_revoked_key_reports_actionable_error(self, clean_registry):
        """When an engine's key is rejected (HTTP 401), health() captures status and get_engine logs error."""
        engine = GeminiOpenAIEngine(
            host="https://generativelanguage.googleapis.com/v1beta/openai",
            api_key=None,
        )

        with respx.mock(assert_all_called=False) as respx_mock:
            respx_mock.get(
                "https://generativelanguage.googleapis.com/v1beta/openai/models"
            ).mock(
                return_value=httpx.Response(
                    401, json={"error": {"message": "API key not valid", "code": 401}}
                )
            )

            is_healthy = engine.health()
            assert is_healthy is False
            assert engine.last_health_status == 401
            assert "Authentication failed" in (engine.last_health_error or "")

    def test_transient_provider_failure_does_not_claim_auth_failure(self, clean_registry):
        """HTTP 503 / 429 is categorized as temporarily unavailable, not revoked credentials."""
        engine = GeminiOpenAIEngine(
            host="https://generativelanguage.googleapis.com/v1beta/openai",
            api_key="valid-mock-key",
        )

        with respx.mock(assert_all_called=False) as respx_mock:
            respx_mock.get(
                "https://generativelanguage.googleapis.com/v1beta/openai/models"
            ).mock(
                return_value=httpx.Response(
                    503, json={"error": {"message": "Backend overloaded", "code": 503}}
                )
            )

            is_healthy = engine.health()
            assert is_healthy is False
            assert engine.last_health_status == 503
            assert "temporarily unavailable" in (engine.last_health_error or "").lower()
            assert "Authentication failed" not in (engine.last_health_error or "")

    def test_get_engine_logs_actionable_auth_message(self, clean_registry, caplog):
        """get_engine logs a clear authentication error when engine health reports 401."""
        mock_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.engine_id = "gemini"
        mock_instance.last_health_status = 401
        mock_instance.last_health_error = "Authentication failed: API key rejected or revoked (HTTP 401)"
        mock_instance.health.return_value = False
        mock_cls.return_value = mock_instance

        EngineRegistry._entries()["gemini"] = mock_cls

        cfg = JarvisConfig()
        with caplog.at_level(logging.ERROR):
            engine = get_engine(cfg, engine_key="gemini", model="gemini-3.8-flash")
            assert engine is None
            assert any(
                "authentication failed (HTTP 401)" in record.message
                for record in caplog.records
            )

    def test_secrets_never_appear_in_error_logs_or_messages(self, clean_registry, caplog):
        """Ensures raw secret values are never included in log records or error messages."""
        secret_key = "super-secret-test-token-xyz987"
        engine = GeminiOpenAIEngine(
            host="https://generativelanguage.googleapis.com/v1beta/openai",
            api_key=secret_key,
        )

        with respx.mock(assert_all_called=False) as respx_mock:
            respx_mock.get(
                "https://generativelanguage.googleapis.com/v1beta/openai/models"
            ).mock(
                return_value=httpx.Response(401, json={"error": "unauthorized"})
            )

            with caplog.at_level(logging.DEBUG):
                engine.health()

                # Verify secret_key is nowhere in engine.last_health_error
                assert secret_key not in (engine.last_health_error or "")

                # Verify secret_key is nowhere in captured log records
                for record in caplog.records:
                    assert secret_key not in record.message

    def test_chat_history_preserved_across_credential_recovery(self, tmp_path, monkeypatch):
        """Chat history and user preferences remain intact when credentials change."""
        monkeypatch.setattr("openjarvis.core.paths.get_config_dir", lambda: tmp_path)

        mock_engine = MagicMock()
        mock_engine.engine_id = "mock"
        mock_engine.health.return_value = True
        mock_engine.list_models.return_value = ["gemini-3.8-flash"]

        app = create_app(mock_engine, "gemini-3.8-flash")
        from fastapi.testclient import TestClient
        client = TestClient(app)

        # User sets preference
        resp1 = client.post("/api/hologram/directive", json={"directive": "Call me Commander"})
        assert resp1.status_code == 200

        # Simulate user updating their credential (new engine instance)
        mock_engine_recovered = MagicMock()
        mock_engine_recovered.engine_id = "mock"
        mock_engine_recovered.health.return_value = True
        mock_engine_recovered.list_models.return_value = ["gemini-3.8-flash"]

        app_recovered = create_app(mock_engine_recovered, "gemini-3.8-flash")
        client_recovered = TestClient(app_recovered)

        # Verify preference remains intact!
        resp2 = client_recovered.post("/api/hologram/directive", json={"directive": "Who am I?"})
        assert resp2.status_code == 200
        assert "Commander" in resp2.json()["reply"]
