"""Unit tests for user address preference and memory database backend management."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from openjarvis.server.app import create_app  # noqa: E402
from openjarvis.tools.memory_backend_manage import (  # noqa: E402
    MemoryBackendManageTool,
)


def _make_engine():
    engine = MagicMock()
    engine.engine_id = "mock"
    engine.health.return_value = True
    engine.list_models.return_value = ["test-model"]
    return engine


class TestUserAddressPreferences:
    def test_first_chat_without_address_does_not_assume_sir(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr("openjarvis.core.paths.get_config_dir", lambda: tmp_path)
        app = create_app(_make_engine(), "test-model")
        client = TestClient(app)

        # Before any preference is set
        resp = client.post("/api/hologram/directive", json={"directive": "Who am I?"})
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "haven't specified" in reply.lower()
        assert "call me" in reply.lower()

    def test_user_sets_address_to_maam(self, tmp_path, monkeypatch):
        monkeypatch.setattr("openjarvis.core.paths.get_config_dir", lambda: tmp_path)
        app = create_app(_make_engine(), "test-model")
        client = TestClient(app)

        resp = client.post(
            "/api/hologram/directive", json={"directive": "Call me ma'am"}
        )
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "ma'am" in reply

        # Verify subsequent query addresses as ma'am
        resp2 = client.post(
            "/api/hologram/directive", json={"directive": "What is the status?"}
        )
        assert resp2.status_code == 200
        assert "ma'am" in resp2.json()["reply"]

    def test_user_sets_address_to_custom_name(self, tmp_path, monkeypatch):
        monkeypatch.setattr("openjarvis.core.paths.get_config_dir", lambda: tmp_path)
        app = create_app(_make_engine(), "test-model")
        client = TestClient(app)

        resp = client.post(
            "/api/hologram/directive", json={"directive": "My name is Alex"}
        )
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "Alex" in reply

        # Check who am I
        resp2 = client.post("/api/hologram/directive", json={"directive": "Who am I?"})
        assert resp2.status_code == 200
        assert "Alex" in resp2.json()["reply"]


class TestMemoryDatabaseBackend:
    def test_memory_status_reports_local_and_cloud_option(self, tmp_path, monkeypatch):
        monkeypatch.setattr("openjarvis.core.paths.get_config_dir", lambda: tmp_path)
        app = create_app(_make_engine(), "test-model")
        client = TestClient(app)

        resp = client.post(
            "/api/hologram/directive", json={"directive": "Where is my memory saved?"}
        )
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "local memory" in reply.lower()
        assert "supabase" in reply.lower()
        assert "isolated to you" in reply.lower()

    def test_memory_backend_tool_status_and_attach(self, tmp_path, monkeypatch):
        monkeypatch.setattr("openjarvis.core.paths.get_config_dir", lambda: tmp_path)
        tool = MemoryBackendManageTool()

        # Status
        status_res = tool.execute(action="status")
        assert status_res.success is True
        assert "local memory" in status_res.content.lower()

        # Attach Supabase
        attach_res = tool.execute(
            action="attach",
            backend_type="supabase",
            connection_string="postgresql://postgres:secret123@db.proj.supabase.co:5432/postgres",
        )
        assert attach_res.success is True
        assert "SUPABASE" in attach_res.content

        # Verify status shows cloud and masks secret
        status2 = tool.execute(action="status")
        assert status2.success is True
        assert "****" in status2.metadata["connection_target"]
        assert "secret123" not in status2.metadata["connection_target"]

        # Detach
        detach_res = tool.execute(action="detach")
        assert detach_res.success is True
        assert "local memory" in detach_res.content.lower()
