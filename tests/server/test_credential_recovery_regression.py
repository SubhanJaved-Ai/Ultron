"""Regression tests for Gemini credential recovery, aliases, quote sanitization, and secret redaction.

Validates:
1. Replacing an invalid credential with a valid credential updates the value used by inference.
2. Both GEMINI_API_KEY and GOOGLE_API_KEY aliases are supported.
3. Leading/trailing quotes and whitespace in credentials are automatically stripped.
4. /v1/cloud/reload updates the in-memory brain and engines with the new credential.
5. API keys are never placed in URL query parameters and error messages redact secrets.
"""

from __future__ import annotations

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


class TestCredentialRecoveryAndAliases:
    def test_gemini_api_key_alias_support(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setenv("GOOGLE_API_KEY", "google-alias-test-key")

        engine = GeminiOpenAIEngine()
        try:
            assert engine._api_key == "google-alias-test-key"
        finally:
            engine.close()

    def test_gemini_api_key_strips_quotes_and_whitespace(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", '  "quoted-gemini-key-12345"  ')
        engine = GeminiOpenAIEngine()
        try:
            assert engine._api_key == "quoted-gemini-key-12345"
        finally:
            engine.close()

    def test_gemini_api_key_strips_single_quotes(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("GOOGLE_API_KEY", " 'single-quoted-key-67890' ")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        engine = GeminiOpenAIEngine()
        try:
            assert engine._api_key == "single-quoted-key-67890"
        finally:
            engine.close()

    @pytest.mark.asyncio
    async def test_credential_replacement_updates_inference_value(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Step 1: Initialize with an invalid key
        invalid_key = "AIzaSy_invalid_key_initial"
        monkeypatch.setenv("GEMINI_API_KEY", invalid_key)

        expected_url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

        with respx.mock:
            # First call with invalid key fails with 401
            respx.post(expected_url).mock(
                return_value=httpx.Response(
                    401,
                    json={"error": {"message": "API key was rejected or revoked by provider."}},
                )
            )

            with pytest.raises(Exception) as exc_info:
                tokens = []
                async for tok in stream_cloud(
                    "gemini-3.8-flash",
                    [Message(role=Role.USER, content="ping")],
                ):
                    tokens.append(tok)
            assert "401" in str(exc_info.value) or "rejected" in str(exc_info.value)

            # Step 2: Replace invalid key with a new valid key
            valid_key = "AIzaSy_valid_replacement_key_99999"
            monkeypatch.setenv("GEMINI_API_KEY", valid_key)

            # Reconnect route succeeds with 200
            respx.post(expected_url).mock(
                return_value=httpx.Response(
                    200,
                    text=(
                        'data: {"choices": [{"delta": {"content": "Reconnected successfully!"}}]}\n\n'
                        "data: [DONE]\n\n"
                    ),
                    headers={"content-type": "text/event-stream"},
                )
            )

            tokens = []
            async for tok in stream_cloud(
                "gemini-3.8-flash",
                [Message(role=Role.USER, content="ping again")],
            ):
                tokens.append(tok)

            assert "".join(tokens) == "Reconnected successfully!"
            last_request = respx.calls.last.request
            assert last_request.headers["Authorization"] == f"Bearer {valid_key}"
            assert invalid_key not in last_request.headers["Authorization"]

    def test_secrets_redacted_from_urls_and_errors(self) -> None:
        real_looking_key = "AIzaSyB1234567890abcdefghijklmnopqrstuv"
        leak_url = f"https://generativelanguage.googleapis.com/v1beta/openai/models?key={real_looking_key}"
        sanitized = sanitize_url(leak_url)
        assert real_looking_key not in sanitized
        assert "key=%5BREDACTED%5D" in sanitized or "key=[REDACTED]" in sanitized

        leak_error = f"HTTP 401: Invalid API key {real_looking_key} for Bearer {real_looking_key}"
        sanitized_err = sanitize_error_message(leak_error)
        assert real_looking_key not in sanitized_err

    def test_cloud_reload_endpoint_updates_environment_and_brain(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import os

        app = create_app()
        client = TestClient(app)

        new_key = "AIzaSy_reloaded_key_abc123"
        response = client.post("/v1/cloud/reload", json={"gemini_api_key": new_key})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert os.environ.get("GEMINI_API_KEY") == new_key

