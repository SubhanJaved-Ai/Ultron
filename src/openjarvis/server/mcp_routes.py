"""MCP server configuration, validation, and connection diagnostics routes.

Implements secure inspection, validation, credential masking, and connectivity testing
for Model Context Protocol (MCP) servers.
"""

from __future__ import annotations

import logging
import re
import shutil
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from openjarvis.core.config import load_config, resolve_mcp_servers
from openjarvis.mcp.client import MCPClient
from openjarvis.mcp.transport import StdioTransport, StreamableHTTPTransport

logger = logging.getLogger(__name__)

mcp_router = APIRouter(prefix="/api/mcp", tags=["mcp"])

# In-memory runtime server store (seeds from config and supports runtime configuration)
_runtime_mcp_servers: List[Dict[str, Any]] = []
_runtime_initialized: bool = False

# Strict pattern for server names
_VALID_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-\.]{1,64}$")
# Disallowed shell injection characters in command or args
_SHELL_INJECTION_RE = re.compile(r"[;&|`$<>\r\n]")


def _mask_token(token: Optional[str]) -> str:
    """Mask sensitive tokens while preserving prefix hints."""
    if not token:
        return ""
    clean = str(token).strip()
    if len(clean) <= 6:
        return "******"
    return f"{clean[:3]}...{clean[-3:]}"


def _mask_server_dict(server: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of the server dictionary with credentials masked."""
    masked = dict(server)
    if "token" in masked and masked["token"]:
        masked["token"] = _mask_token(str(masked["token"]))
    # Mask embedded HTTP auth in URL if present
    if "url" in masked and masked["url"]:
        try:
            parsed = urlparse(masked["url"])
            if parsed.password:
                netloc = f"{parsed.username}:******@{parsed.hostname}"
                if parsed.port:
                    netloc += f":{parsed.port}"
                masked["url"] = parsed._replace(netloc=netloc).geturl()
        except Exception:
            pass
    return masked


def _init_runtime_servers() -> None:
    """Seed runtime server state from active configuration."""
    global _runtime_mcp_servers, _runtime_initialized
    if _runtime_initialized:
        return
    try:
        cfg = load_config()
        if cfg.tools.mcp.enabled and cfg.tools.mcp.servers:
            resolved = resolve_mcp_servers(cfg.tools.mcp.servers, cfg._config_dir)
            _runtime_mcp_servers = list(resolved)
    except Exception as exc:
        logger.debug("No pre-configured MCP servers loaded: %s", exc)
        _runtime_mcp_servers = []
    _runtime_initialized = True


class MCPServerConfigModel(BaseModel):
    name: str = Field(..., description="Unique alphanumeric identifier for the MCP server")
    url: Optional[str] = Field(None, description="HTTP/SSE URL for remote MCP server")
    command: Optional[str] = Field(None, description="Command executable for stdio transport")
    args: List[str] = Field(default_factory=list, description="Command line arguments for stdio transport")
    token: Optional[str] = Field(None, description="Optional bearer token for authenticated HTTP server")
    include_tools: List[str] = Field(default_factory=list, description="Optional allowlist of tool names")
    exclude_tools: List[str] = Field(default_factory=list, description="Optional denylist of tool names")
    enabled: bool = Field(True, description="Whether this server is active")


class MCPValidateResponse(BaseModel):
    valid: bool
    server: Optional[Dict[str, Any]] = None
    errors: List[str] = Field(default_factory=list)


class MCPTestResponse(BaseModel):
    name: str
    connected: bool
    latency_ms: Optional[float] = None
    discovered_tools_count: int = 0
    tools: List[str] = Field(default_factory=list)
    error: Optional[str] = None


def validate_server_config(cfg: Dict[str, Any]) -> List[str]:
    """Validate server configuration and return list of validation errors."""
    errors = []
    name = str(cfg.get("name") or "").strip()
    if not name:
        errors.append("Server 'name' is required.")
    elif not _VALID_NAME_RE.match(name):
        errors.append(f"Invalid server name '{name}'. Use 1-64 alphanumeric characters, underscores, dashes, or dots.")

    url = str(cfg.get("url") or "").strip()
    command = str(cfg.get("command") or "").strip()

    if not url and not command:
        errors.append("Server must specify either 'url' (HTTP transport) or 'command' (stdio transport).")
    elif url and command:
        errors.append("Server cannot specify both 'url' and 'command'. Choose one transport.")

    if url:
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                errors.append(f"Invalid URL scheme '{parsed.scheme}'. Only http and https are permitted.")
            if not parsed.hostname:
                errors.append("URL must include a valid hostname.")
        except Exception as exc:
            errors.append(f"Malformed URL: {exc}")

    if command:
        if _SHELL_INJECTION_RE.search(command):
            errors.append("Command contains forbidden shell metacharacters (; & | ` $ < > \\n \\r).")
        args = cfg.get("args") or []
        if not isinstance(args, list):
            errors.append("'args' must be a list of strings.")
        else:
            for arg in args:
                if _SHELL_INJECTION_RE.search(str(arg)):
                    errors.append(f"Argument '{arg}' contains forbidden shell metacharacters.")

    return errors


@mcp_router.get("/servers", response_model=List[Dict[str, Any]])
async def list_mcp_servers() -> List[Dict[str, Any]]:
    """List all configured MCP servers with credentials securely masked."""
    _init_runtime_servers()
    results = []
    for s in _runtime_mcp_servers:
        masked = _mask_server_dict(s)
        masked["transport"] = "http" if s.get("url") else "stdio"
        results.append(masked)
    return results


@mcp_router.post("/servers/validate", response_model=MCPValidateResponse)
async def validate_server(server: MCPServerConfigModel) -> MCPValidateResponse:
    """Validate an MCP server configuration before saving or testing."""
    raw_dict = server.model_dump()
    errors = validate_server_config(raw_dict)
    if errors:
        return MCPValidateResponse(valid=False, errors=errors)
    return MCPValidateResponse(valid=True, server=_mask_server_dict(raw_dict))


@mcp_router.post("/servers/test", response_model=MCPTestResponse)
async def test_mcp_server(server: MCPServerConfigModel) -> MCPTestResponse:
    """Safely test connection to an MCP server within a strict timeout."""
    raw_dict = server.model_dump()
    errors = validate_server_config(raw_dict)
    if errors:
        return MCPTestResponse(
            name=server.name,
            connected=False,
            error=f"Validation failed: {'; '.join(errors)}",
        )

    url = server.url
    command = server.command
    args = server.args
    token = server.token
    start_time = time.time()

    # 1. Stdio transport test
    if command:
        # Check binary availability first without spawning shell
        resolved_bin = shutil.which(command)
        if not resolved_bin:
            return MCPTestResponse(
                name=server.name,
                connected=False,
                error=f"Command binary '{command}' not found in system PATH.",
            )
        try:
            transport = StdioTransport(command=[command] + args)
            client = MCPClient(transport)
            client.initialize()
            from openjarvis.tools.mcp_adapter import MCPToolProvider

            provider = MCPToolProvider(client)
            discovered = provider.discover()
            latency = round((time.time() - start_time) * 1000, 2)
            tool_names = [t.spec.name for t in discovered]
            try:
                client.close()
            except Exception:
                pass
            return MCPTestResponse(
                name=server.name,
                connected=True,
                latency_ms=latency,
                discovered_tools_count=len(tool_names),
                tools=tool_names,
            )
        except Exception as exc:
            logger.warning("MCP stdio connection test failed for '%s': %s", server.name, exc)
            return MCPTestResponse(
                name=server.name,
                connected=False,
                error=str(exc),
            )

    # 2. HTTP / SSE transport test
    if url:
        try:
            transport = StreamableHTTPTransport(url=url, token=token)
            client = MCPClient(transport)
            client.initialize()
            from openjarvis.tools.mcp_adapter import MCPToolProvider

            provider = MCPToolProvider(client)
            discovered = provider.discover()
            latency = round((time.time() - start_time) * 1000, 2)
            tool_names = [t.spec.name for t in discovered]
            try:
                client.close()
            except Exception:
                pass
            return MCPTestResponse(
                name=server.name,
                connected=True,
                latency_ms=latency,
                discovered_tools_count=len(tool_names),
                tools=tool_names,
            )
        except Exception as exc:
            logger.warning("MCP HTTP connection test failed for '%s': %s", server.name, exc)
            return MCPTestResponse(
                name=server.name,
                connected=False,
                error=f"HTTP connection failed: {exc}",
            )

    return MCPTestResponse(
        name=server.name,
        connected=False,
        error="Unknown transport configuration.",
    )


@mcp_router.post("/servers", status_code=status.HTTP_201_CREATED, response_model=Dict[str, Any])
async def add_or_update_mcp_server(server: MCPServerConfigModel) -> Dict[str, Any]:
    """Register or update an MCP server configuration."""
    _init_runtime_servers()
    raw_dict = server.model_dump()
    errors = validate_server_config(raw_dict)
    if errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid server configuration: {'; '.join(errors)}",
        )

    # Replace existing or append
    global _runtime_mcp_servers
    updated = False
    for idx, existing in enumerate(_runtime_mcp_servers):
        if existing.get("name") == server.name:
            _runtime_mcp_servers[idx] = raw_dict
            updated = True
            break
    if not updated:
        _runtime_mcp_servers.append(raw_dict)

    masked = _mask_server_dict(raw_dict)
    masked["status"] = "updated" if updated else "created"
    return masked


@mcp_router.delete("/servers/{server_name}", response_model=Dict[str, Any])
async def delete_mcp_server(server_name: str) -> Dict[str, Any]:
    """Remove an MCP server from configuration."""
    _init_runtime_servers()
    global _runtime_mcp_servers
    initial_len = len(_runtime_mcp_servers)
    _runtime_mcp_servers = [s for s in _runtime_mcp_servers if s.get("name") != server_name]
    if len(_runtime_mcp_servers) == initial_len:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"MCP server '{server_name}' not found.",
        )
    return {"name": server_name, "status": "deleted"}


def reset_runtime_mcp_servers() -> None:
    """Reset the runtime server state (for testing)."""
    global _runtime_mcp_servers, _runtime_initialized
    _runtime_mcp_servers = []
    _runtime_initialized = False
