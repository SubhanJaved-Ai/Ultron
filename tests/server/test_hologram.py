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
        assert "JARVIS 2.0" in resp.text
        assert "hologram-canvas" in resp.text

    def test_pwa_manifest_served_from_static(self):
        engine = _make_engine()
        app = create_app(engine, "test-model")
        client = TestClient(app)

        resp = client.get("/manifest.webmanifest")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("name") == "Jarvis 2.0 Autonomous Assistant"
        assert data.get("display") == "standalone"

    def test_service_worker_served_from_static(self):
        engine = _make_engine()
        app = create_app(engine, "test-model")
        client = TestClient(app)

        resp = client.get("/sw.js")
        assert resp.status_code == 200
        assert "jarvis-pwa" in resp.text
