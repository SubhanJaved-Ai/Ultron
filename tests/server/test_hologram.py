"""Unit tests for the 3D Hologram web interface and PWA routes."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from openjarvis.server.app import create_app  # noqa: E402


def _make_engine():
    engine = MagicMock()
    engine.engine_id = "mock"
    engine.health.return_value = True
    engine.list_models.return_value = ["test-model"]
    return engine


class TestHologramRoutes:
    def test_hologram_endpoint_serves_html(self):
        engine = _make_engine()
        app = create_app(engine, "test-model")
        client = TestClient(app)

        resp = client.get("/hologram")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        assert "ULTRON" in resp.text
        assert "hologram-canvas" in resp.text

    def test_pwa_manifest_served_from_static(self):
        engine = _make_engine()
        app = create_app(engine, "test-model")
        client = TestClient(app)

        resp = client.get("/manifest.webmanifest")
        assert resp.status_code == 200
        data = resp.json()
        assert "Ultron" in data.get("name", "")
        assert data.get("display") == "standalone"

    def test_service_worker_served_from_static(self):
        engine = _make_engine()
        app = create_app(engine, "test-model")
        client = TestClient(app)

        resp = client.get("/sw.js")
        assert resp.status_code == 200
        assert "jarvis-pwa" in resp.text

    def test_hologram_directive_endpoint(self):
        engine = _make_engine()
        app = create_app(engine, "test-model")
        client = TestClient(app)

        resp = client.post(
            "/api/hologram/directive", json={"directive": "Who are you?"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "reply" in data
        assert "JARVIS" in data["reply"]

    def test_hologram_tts_endpoint(self):
        engine = _make_engine()
        app = create_app(engine, "test-model")
        client = TestClient(app)

        resp = client.get("/api/tts?text=Systems+operational")
        assert resp.status_code == 200
        assert resp.headers.get("content-type") == "audio/wav"
        assert len(resp.content) > 1000

    def test_hologram_directive_executes_via_jarvis_system(self):
        engine = _make_engine()
        mock_system = MagicMock()
        mock_system.ask.return_value = {
            "content": "All subagents deployed and workflow scheduled, sir.",
            "tool_calls": [{"name": "delegate_task", "arguments": "{}"}],
        }
        app = create_app(engine, "test-model", system=mock_system)
        client = TestClient(app)

        resp = client.post(
            "/api/hologram/directive",
            json={"directive": "Deploy subagents to index code"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "executed"
        assert "All subagents deployed" in data["reply"]
        assert len(data.get("actions", [])) == 1
        mock_system.ask.assert_called_once_with("Deploy subagents to index code")

    def test_hologram_rejects_idle_chat_and_demands_tasks(self):
        engine = _make_engine()
        app = create_app(engine, "test-model")
        client = TestClient(app)

        resp = client.post(
            "/api/hologram/directive", json={"directive": "Can you just chat with me?"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "not just ChatGPT" in data["reply"]
        assert "give me the task and I will do it" in data["reply"]

    def test_hologram_html_contains_interruption_logic(self):
        engine = _make_engine()
        app = create_app(engine, "test-model")
        client = TestClient(app)

        resp = client.get("/hologram")
        assert resp.status_code == 200
        html = resp.text
        assert "interruptUltron" in html
        assert "INTERRUPTED: LISTENING TO YOU" in html
        assert "window._currentSpeakingText" in html

