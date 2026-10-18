"""Tests for MCP configuration, validation, diagnostics, and credential masking routes."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from openjarvis.server.app import create_app
from openjarvis.server.mcp_routes import reset_runtime_mcp_servers
from openjarvis.tools._stubs import BaseTool, ToolSpec


class DummyTool(BaseTool):
    tool_id = "dummy_tool"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(name="dummy_tool", description="A mock MCP tool")

    def execute(self, **kwargs):
        pass


@pytest.fixture
def client():
    reset_runtime_mcp_servers()
    app = create_app()
    with TestClient(app) as tc:
        yield tc
    reset_runtime_mcp_servers()


class TestMCPRoutes:
    def test_list_servers_empty_and_populated_with_masking(self, client: TestClient):
        # 1. Empty initially
        resp = client.get("/api/mcp/servers")
        assert resp.status_code == 200
        assert resp.json() == []

        # 2. Add an authenticated server with secret token
        server_payload = {
            "name": "github-mcp",
            "url": "https://api.github.com/mcp",
            "token": "ghp_secret_access_token_1234567890",
            "include_tools": ["search_code"],
            "enabled": True,
        }
        create_resp = client.post("/api/mcp/servers", json=server_payload)
        assert create_resp.status_code == 201
        created = create_resp.json()
        assert created["name"] == "github-mcp"
        # Token must be masked
        assert created["token"] != "ghp_secret_access_token_1234567890"
        assert "ghp" in created["token"]
        assert "890" in created["token"]
        assert "..." in created["token"]

        # 3. Read back via GET
        list_resp = client.get("/api/mcp/servers")
        assert list_resp.status_code == 200
        servers = list_resp.json()
        assert len(servers) == 1
        assert servers[0]["name"] == "github-mcp"
        assert servers[0]["transport"] == "http"
        assert servers[0]["token"] == created["token"]

    def test_validate_server_valid_and_invalid(self, client: TestClient):
        # Valid stdio configuration
        valid_stdio = {
            "name": "local-fs",
            "command": "python",
            "args": ["-m", "mcp_server_filesystem"],
        }
        res = client.post("/api/mcp/servers/validate", json=valid_stdio)
        assert res.status_code == 200
        assert res.json()["valid"] is True

        # Invalid name with spaces and special chars
        bad_name = {
            "name": "Invalid Server Name!",
            "command": "python",
        }
        res_bad_name = client.post("/api/mcp/servers/validate", json=bad_name)
        assert res_bad_name.status_code == 200
        assert res_bad_name.json()["valid"] is False
        assert any("Invalid server name" in err for err in res_bad_name.json()["errors"])

        # Neither url nor command
        missing_transport = {"name": "empty-transport"}
        res_missing = client.post("/api/mcp/servers/validate", json=missing_transport)
        assert res_missing.json()["valid"] is False
        assert any("either 'url'" in err for err in res_missing.json()["errors"])

        # Both url and command
        both_transports = {
            "name": "conflicted",
            "url": "https://mcp.example.com",
            "command": "node",
        }
        res_both = client.post("/api/mcp/servers/validate", json=both_transports)
        assert res_both.json()["valid"] is False
        assert any("cannot specify both" in err for err in res_both.json()["errors"])

        # Invalid URL scheme
        bad_scheme = {
            "name": "ftp-server",
            "url": "ftp://files.example.com/mcp",
        }
        res_bad_scheme = client.post("/api/mcp/servers/validate", json=bad_scheme)
        assert res_bad_scheme.json()["valid"] is False
        assert any("Invalid URL scheme" in err for err in res_bad_scheme.json()["errors"])

    def test_validate_rejects_shell_injection(self, client: TestClient):
        """Security: reject dangerous shell metacharacters in commands and args."""
        dangerous_payloads = [
            {"name": "evil-1", "command": "python; rm -rf /"},
            {"name": "evil-2", "command": "node", "args": ["server.js", "&&", "cat /etc/passwd"]},
            {"name": "evil-3", "command": "curl | bash"},
            {"name": "evil-4", "command": "`whoami`"},
            {"name": "evil-5", "command": "python $(reboot)"},
        ]
        for payload in dangerous_payloads:
            res = client.post("/api/mcp/servers/validate", json=payload)
            assert res.status_code == 200
            assert res.json()["valid"] is False
            assert any("forbidden shell metacharacters" in err for err in res.json()["errors"])

    def test_test_server_nonexistent_binary(self, client: TestClient):
        """Test diagnostic reporting when command binary is missing."""
        payload = {
            "name": "missing-bin",
            "command": "nonexistent_mcp_binary_xyz_998877",
            "args": ["--port", "9000"],
        }
        res = client.post("/api/mcp/servers/test", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["connected"] is False
        assert "not found in system PATH" in data["error"]

    def test_test_server_http_unreachable(self, client: TestClient):
        """Test diagnostic reporting when HTTP host is unreachable."""
        payload = {
            "name": "unreachable-http",
            "url": "http://127.0.0.1:59999/mcp",
            "token": "secret_token_123",
        }
        res = client.post("/api/mcp/servers/test", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["connected"] is False
        assert "HTTP connection failed" in data["error"]
        # Secret token must not be leaked in error message
        assert "secret_token_123" not in data["error"]

    @patch("openjarvis.server.mcp_routes.MCPClient")
    @patch("openjarvis.tools.mcp_adapter.MCPToolProvider")
    def test_test_server_mocked_success(self, mock_provider_cls, mock_client_cls, client: TestClient):
        """Test successful connection response with discovered tools."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        mock_tool = DummyTool()
        mock_provider = MagicMock()
        mock_provider.discover.return_value = [mock_tool]
        mock_provider_cls.return_value = mock_provider

        payload = {
            "name": "mock-connected",
            "url": "https://mcp.mock.internal",
            "token": "tok_12345",
        }
        res = client.post("/api/mcp/servers/test", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["connected"] is True
        assert data["discovered_tools_count"] == 1
        assert data["tools"] == ["dummy_tool"]
        assert data["latency_ms"] is not None

    def test_delete_mcp_server(self, client: TestClient):
        # Add server first
        payload = {"name": "to-delete", "url": "https://mcp.example.com"}
        client.post("/api/mcp/servers", json=payload)

        # Delete it
        del_res = client.delete("/api/mcp/servers/to-delete")
        assert del_res.status_code == 200
        assert del_res.json()["status"] == "deleted"

        # Delete nonexistent -> 404
        del_missing = client.delete("/api/mcp/servers/to-delete")
        assert del_missing.status_code == 404
