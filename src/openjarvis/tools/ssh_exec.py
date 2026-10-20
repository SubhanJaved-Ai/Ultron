"""SSHExecTool — execute commands on remote servers, cloud VPS, and GPU clusters via SSH.

Directly inspired by Hermes Agent's SSH backend: enables OpenJarvis agents
to automate remote infrastructure, run tasks on servers, and manage remote environments.
"""

from __future__ import annotations

import logging
from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.sandbox.environments import SSHEnvironment
from openjarvis.tools._stubs import BaseTool, ToolSpec

logger = logging.getLogger(__name__)


@ToolRegistry.register("ssh_exec")
class SSHExecTool(BaseTool):
    """Execute commands on remote SSH servers and cloud environments."""

    tool_id = "ssh_exec"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="ssh_exec",
            description=(
                "Execute a shell command on a remote host over SSH. "
                "Supports custom port, username, private key path, and timeout."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "host": {
                        "type": "string",
                        "description": "Remote server hostname or IP address.",
                    },
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute on the remote machine.",
                    },
                    "user": {
                        "type": "string",
                        "description": "SSH username (e.g. 'ubuntu', 'root', 'debian').",
                    },
                    "port": {
                        "type": "integer",
                        "description": "SSH port (default: 22).",
                    },
                    "key_path": {
                        "type": "string",
                        "description": "Path to SSH private key file (optional).",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Execution timeout in seconds (default: 30).",
                    },
                },
                "required": ["host", "command"],
            },
            category="system",
        )

    def execute(self, **params: Any) -> ToolResult:
        host = (params.get("host") or "").strip()
        command = (params.get("command") or "").strip()
        user = params.get("user")
        port = int(params.get("port") or 22)
        key_path = params.get("key_path")
        timeout = int(params.get("timeout") or 30)

        if not host or not command:
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content="Both 'host' and 'command' are required for ssh_exec.",
            )

        env = SSHEnvironment(
            host=host,
            user=user,
            port=port,
            key_path=key_path,
        )

        if not env.is_available():
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content="SSH client executable ('ssh') is not found on system PATH.",
            )

        res = env.execute(command, timeout=timeout)

        output_parts = []
        if res.stdout:
            output_parts.append(res.stdout)
        if res.stderr:
            output_parts.append(f"[STDERR]\n{res.stderr}")

        output_str = "\n".join(output_parts).strip() or (
            f"Command finished with exit code {res.exit_code} (no output)"
        )

        return ToolResult(
            tool_name=self.spec.name,
            success=res.success,
            content=output_str,
            metadata={
                "exit_code": res.exit_code,
                "duration_seconds": res.duration_seconds,
            },
        )
