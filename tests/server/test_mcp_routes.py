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

    def test_validate_rejects_ssrf_and_metadata(self, client: TestClient):
        """Security: reject cloud metadata and link-local addresses for SSRF prevention."""
        ssrf_targets = [
            "http://169.254.169.254/latest/meta-data/",
            "http://metadata.google.internal/computeMetadata/v1/",
            "http://100.100.100.200/latest/meta-data/",
            "http://169.254.10.20/mcp",
            "http://metadata.internal/mcp",
        ]
        for url in ssrf_targets:
            payload = {"name": "ssrf-test", "url": url}
            res = client.post("/api/mcp/servers/validate", json=payload)
            assert res.status_code == 200
            data = res.json()
            assert data["valid"] is False
            assert any(
                "cloud metadata" in err or "link-local" in err
                for err in data["errors"]
            ), f"Failed to reject SSRF target: {url}"

    def test_validate_rejects_restricted_ports(self, client: TestClient):
        """Security: reject well-known dangerous ports for SSRF port scanning prevention."""
        blocked_ports = [21, 22, 23, 25, 445, 3389, 6379]
        for port in blocked_ports:
            payload = {"name": f"port-{port}", "url": f"http://127.0.0.1:{port}/mcp"}
            res = client.post("/api/mcp/servers/validate", json=payload)
            assert res.status_code == 200
            data = res.json()
            assert data["valid"] is False
            assert any(f"Port {port} is restricted" in err for err in data["errors"])

    def test_validate_rejects_dangerous_command_binaries(self, client: TestClient):
        """Security: reject dangerous system shells and utilities from stdio transport."""
        dangerous_commands = [
            "cmd.exe",
            "powershell",
            "bash",
            "sh",
            "curl",
            "wget",
            "rm",
            "del",
        ]
        for cmd in dangerous_commands:
            payload = {"name": "cmd-test", "command": cmd, "args": ["--help"]}
            res = client.post("/api/mcp/servers/validate", json=payload)
            assert res.status_code == 200
            data = res.json()
            assert data["valid"] is False
            assert any("Execution of dangerous system command" in err for err in data["errors"])

    def test_test_server_sanitizes_credentials_in_errors(self, client: TestClient):
        """Security: ensure sensitive tokens and passwords in URLs are scrubbed from test errors."""
        payload = {
            "name": "sanitized-err",
            "url": "http://admin:super_secret_pw@127.0.0.1:59998/mcp",
            "token": "sensitive_bearer_token_xyz987",
        }
        res = client.post("/api/mcp/servers/test", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["connected"] is False
        assert "super_secret_pw" not in data["error"]
        assert "sensitive_bearer_token_xyz987" not in data["error"]

    def test_mock_mcp_server_disabled_by_default(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        """Security: mock MCP server endpoint is disabled by default (returns 404)."""
        monkeypatch.delenv("OPENJARVIS_ENABLE_MCP_MOCK_SERVER", raising=False)
        monkeypatch.delenv("ULTRON_ENABLE_MCP_MOCK_SERVER", raising=False)
        res = client.post(
            "/api/mcp/mock-server",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        )
        assert res.status_code == 404
        assert "disabled by default" in res.json()["detail"]

    def test_mock_mcp_server_prohibited_in_production(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        """Security: mock MCP server endpoint is strictly prohibited in production mode (returns 403)."""
        monkeypatch.setenv("OPENJARVIS_ENABLE_MCP_MOCK_SERVER", "true")
        for prod_env in ("production", "prod"):
            monkeypatch.setenv("ENVIRONMENT", prod_env)
            res = client.post(
                "/api/mcp/mock-server",
                json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
            )
            assert res.status_code == 403
            assert "strictly prohibited in production mode" in res.json()["detail"]

    def test_mock_mcp_server_protocol_endpoints(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        """Verify the deterministic mock MCP endpoint satisfies JSON-RPC 2.0 MCP protocol when explicitly enabled."""
        monkeypatch.setenv("OPENJARVIS_ENABLE_MCP_MOCK_SERVER", "true")
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("OPENJARVIS_ENV", raising=False)

        # 1. Initialize
        init_res = client.post(
            "/api/mcp/mock-server",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-03-26"},
            },
        )
        assert init_res.status_code == 200
        init_data = init_res.json()
        assert init_data["id"] == 1
        assert init_data["result"]["protocolVersion"] == "2025-03-26"
        assert init_data["result"]["serverInfo"]["name"] == "ultron-mock-mcp"

        # 2. Initialized notification
        notif_res = client.post(
            "/api/mcp/mock-server",
            json={
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            },
        )
        assert notif_res.status_code == 200

        # 3. Tools list
        tools_res = client.post(
            "/api/mcp/mock-server",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            },
        )
        assert tools_res.status_code == 200
        tools_data = tools_res.json()
        assert tools_data["id"] == 2
        tools = tools_data["result"]["tools"]
        assert len(tools) == 1
        assert tools[0]["name"] == "system_diagnostics"

    def test_authorization_non_admin_forbidden_in_multi_user(self, monkeypatch: pytest.MonkeyPatch):
        """Security: untrusted/non-admin users cannot configure or test MCP servers, nor access mock server."""
        monkeypatch.setenv("OPENJARVIS_ENABLE_MCP_MOCK_SERVER", "true")
        from starlette.middleware.base import BaseHTTPMiddleware
        from starlette.requests import Request

        from openjarvis.auth.models import Role, User

        app = create_app()

        # Add mock middleware that simulates an authenticated non-admin user
        class NonAdminMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request: Request, call_next):
                request.state.user = User(id="user2", username="regular_user", role=Role.USER.value)
                return await call_next(request)

        app.add_middleware(NonAdminMiddleware)

        with TestClient(app) as tc:
            # 1. POST /api/mcp/servers -> 403
            add_res = tc.post("/api/mcp/servers", json={"name": "test-srv", "url": "https://mcp.example.com"})
            assert add_res.status_code == 403
            assert "Administrator privileges required" in add_res.json()["detail"]

            # 2. DELETE /api/mcp/servers/xyz -> 403
            del_res = tc.delete("/api/mcp/servers/xyz")
            assert del_res.status_code == 403

            # 3. POST /api/mcp/servers/test -> 403
            test_res = tc.post("/api/mcp/servers/test", json={"name": "test-srv", "url": "https://mcp.example.com"})
            assert test_res.status_code == 403

            # 4. POST /api/mcp/servers/validate -> 403
            val_res = tc.post("/api/mcp/servers/validate", json={"name": "test-srv", "url": "https://mcp.example.com"})
            assert val_res.status_code == 403

            # 5. POST /api/mcp/mock-server -> 403 (unauthorized/non-admin cannot access mock endpoint)
            mock_res = tc.post("/api/mcp/mock-server", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
            assert mock_res.status_code == 403
            assert "Administrator privileges required" in mock_res.json()["detail"]


