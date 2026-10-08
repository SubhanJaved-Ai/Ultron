"""Unit tests for NodeManager, node tunneling routes, and NodeWorker daemon."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from openjarvis.daemon.node_worker import NodeWorker  # noqa: E402
from openjarvis.server.app import create_app  # noqa: E402
from openjarvis.server.node_manager import NodeManager  # noqa: E402


def _make_engine():
    engine = MagicMock()
    engine.engine_id = "mock"
    engine.health.return_value = True
    engine.list_models.return_value = ["test-model"]
    return engine


class TestNodeManager:
    def test_register_and_verify_token(self, tmp_path):
        db_file = tmp_path / "test_nodes.db"
        mgr = NodeManager(db_path=db_file)

        reg = mgr.register_device("my-laptop")
        dev_id = reg["device_id"]
        token = reg["token"]

        assert dev_id.startswith("node_")
        assert len(token) > 20

        assert mgr.verify_token(dev_id, token) is True
        assert mgr.verify_token(dev_id, "wrong-token") is False
        assert mgr.verify_token("unknown_node", token) is False

    def test_list_nodes_and_online_status(self, tmp_path):
        db_file = tmp_path / "test_nodes.db"
        mgr = NodeManager(db_path=db_file)

        assert mgr.is_node_online() is False

        reg = mgr.register_device("macbook-air")
        dev_id = reg["device_id"]

        nodes = mgr.list_nodes()
        assert len(nodes) == 1
        assert nodes[0]["device_id"] == dev_id
        assert nodes[0]["online"] is False

    @pytest.mark.asyncio
    async def test_dispatch_rpc_offline_error(self, tmp_path):
        db_file = tmp_path / "test_nodes.db"
        mgr = NodeManager(db_path=db_file)

        res = await mgr.dispatch_rpc("system_info", {})
        assert res["success"] is False
        assert "No local machine node is currently connected" in res["error"]

    @pytest.mark.asyncio
    async def test_dispatch_rpc_with_active_connection(self, tmp_path):
        db_file = tmp_path / "test_nodes.db"
        mgr = NodeManager(db_path=db_file)

        reg = mgr.register_device("desktop-pc")
        dev_id = reg["device_id"]

        mock_ws = AsyncMock()
        await mgr.register_connection(dev_id, mock_ws)
        assert mgr.is_node_online(dev_id) is True

        # Simulate background task resolving the RPC
        async def resolve_later():
            await asyncio.sleep(0.05)
            # Find the pending RPC ID from mock call
            call_args = mock_ws.send_json.call_args[0][0]
            rpc_id = call_args["rpc_id"]
            mgr.handle_rpc_response(rpc_id, {"success": True, "hostname": "DESKTOP-1"})

        asyncio.create_task(resolve_later())
        result = await mgr.dispatch_rpc("system_info", {}, device_id=dev_id)
        assert result.get("success") is True
        assert result.get("hostname") == "DESKTOP-1"

        await mgr.unregister_connection(dev_id)
        assert mgr.is_node_online(dev_id) is False


class TestNodeRoutes:
    def test_register_endpoint(self, tmp_path, monkeypatch):
        db_file = tmp_path / "route_nodes.db"
        test_mgr = NodeManager(db_path=db_file)

        monkeypatch.setattr(
            "openjarvis.server.node_routes.get_node_manager",
            lambda request=None: test_mgr,
        )

        engine = _make_engine()
        app = create_app(engine, "test-model")
        client = TestClient(app)

        resp = client.post("/v1/node/register", json={"device_name": "worker-1"})
        assert resp.status_code == 200
        data = resp.json()
        assert "device_id" in data
        assert "token" in data
        assert data["device_name"] == "worker-1"

    def test_status_endpoint(self, tmp_path, monkeypatch):
        db_file = tmp_path / "route_nodes.db"
        test_mgr = NodeManager(db_path=db_file)
        test_mgr.register_device("worker-2")

        monkeypatch.setattr(
            "openjarvis.server.node_routes.get_node_manager",
            lambda request=None: test_mgr,
        )

        engine = _make_engine()
        app = create_app(engine, "test-model")
        client = TestClient(app)

        resp = client.get("/v1/node/status")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["nodes"]) == 1
        assert data["any_online"] is False


class TestNodeWorker:
    @pytest.mark.asyncio
    async def test_handle_rpc_system_info(self):
        worker = NodeWorker("http://localhost:8000", "dev-1", "token-1")
        mock_ws = AsyncMock()

        request = {
            "rpc_id": "rpc-100",
            "action": "system_info",
            "params": {},
        }
        await worker._handle_rpc(mock_ws, request)
        mock_ws.send.assert_called_once()
        sent_data = mock_ws.send.call_args[0][0]
        assert "system_info" not in sent_data  # response is sent
        assert "rpc-100" in sent_data
        assert "platform" in sent_data

    @pytest.mark.asyncio
    async def test_handle_rpc_file_ops(self, tmp_path):
        worker = NodeWorker("http://localhost:8000", "dev-1", "token-1")
        mock_ws = AsyncMock()

        target_file = tmp_path / "sub" / "test.txt"
        # 1. Write file
        write_req = {
            "rpc_id": "rpc-write",
            "action": "write_file",
            "params": {"path": str(target_file), "content": "Hello from Cloud Jarvis!"},
        }
        await worker._handle_rpc(mock_ws, write_req)
        assert target_file.read_text(encoding="utf-8") == "Hello from Cloud Jarvis!"

        # 2. Read file
        read_req = {
            "rpc_id": "rpc-read",
            "action": "read_file",
            "params": {"path": str(target_file)},
        }
        await worker._handle_rpc(mock_ws, read_req)
        sent_data = mock_ws.send.call_args[0][0]
        assert "Hello from Cloud Jarvis!" in sent_data
