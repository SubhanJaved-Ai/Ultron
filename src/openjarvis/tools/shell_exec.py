"""Shell execution tool — run shell commands with security constraints.

Changes from baseline (TSK-P5-01 — Global Emergency Stop):
- The subprocess path now uses ``subprocess.Popen`` (instead of
  ``subprocess.run``) with ``CREATE_NEW_PROCESS_GROUP`` on Windows /
  ``os.setsid`` on POSIX, so the process tree can be killed cleanly.
- Accepts an optional ``cancellation_token`` keyword argument (a
  ``CancellationToken`` from ``openjarvis.server.cancellation``).  When the
  token is set the process tree is terminated immediately via
  ``kill_process_tree`` from ``subprocess_sandbox``.
- The ``execute`` method now polls the cancellation token during output
  collection and aborts if signalled.
"""

from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path
from typing import Any, List, Optional

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec

# Maximum output size per stream (100 KB)
_MAX_OUTPUT_BYTES = 102_400

# Maximum allowed timeout (seconds)
_MAX_TIMEOUT = 300

# Default timeout (seconds)
_DEFAULT_TIMEOUT = 30

# Environment variables always passed through on every platform.
_PORTABLE_ENV_KEYS = (
    "PATH",
    "HOME",
    "USER",
    "LANG",
    "TERM",
)

# Windows needs these to bootstrap ordinary child processes: missing
# SystemRoot breaks Winsock/DNS initialization, while missing LOCALAPPDATA
# can make the Store Python launcher provision a fresh interpreter in cwd.
# Keep them conditional so a POSIX host that happens to define similarly
# named variables does not expand the tool's minimal environment.
_WINDOWS_ENV_KEYS = (
    "SystemRoot",
    "SystemDrive",
    "COMSPEC",
    "PATHEXT",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "LOCALAPPDATA",
    "APPDATA",
)
_BASE_ENV_KEYS = _PORTABLE_ENV_KEYS + (_WINDOWS_ENV_KEYS if os.name == "nt" else ())

# Poll interval (seconds) when waiting for Popen to finish
_POLL_INTERVAL = 0.1


def _run_subprocess_cancellable(
    command: str,
    *,
    timeout: int,
    working_dir: Optional[str],
    env: dict[str, str],
    cancellation_token: Any = None,
) -> tuple[int, str, str, bool]:
    """Run *command* in a new process group; abort early if cancellation is signalled.

    Returns:
        (returncode, stdout, stderr, was_cancelled)
    """
    popen_kwargs: dict[str, Any] = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "shell": True,  # nosec B602
        "cwd": working_dir,
        "env": env,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    elif hasattr(os, "setsid"):
        popen_kwargs["preexec_fn"] = os.setsid

    proc = subprocess.Popen(command, **popen_kwargs)  # nosec B602

    # Collect output in background threads so we can poll for cancellation
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []

    def _read_stdout() -> None:
        if proc.stdout:
            for chunk in iter(lambda: proc.stdout.read(4096), ""):
                stdout_chunks.append(chunk)

    def _read_stderr() -> None:
        if proc.stderr:
            for chunk in iter(lambda: proc.stderr.read(4096), ""):
                stderr_chunks.append(chunk)

    t_out = threading.Thread(target=_read_stdout, daemon=True)
    t_err = threading.Thread(target=_read_stderr, daemon=True)
    t_out.start()
    t_err.start()

    deadline = None
    if timeout and timeout > 0:
        import time

        deadline = time.monotonic() + timeout

    import time as _time

    while True:
        # Check cancellation token first
        if cancellation_token is not None and getattr(
            cancellation_token, "is_cancelled", False
        ):
            _kill_tree(proc.pid)
            t_out.join(timeout=1)
            t_err.join(timeout=1)
            return (
                -1,
                "".join(stdout_chunks)[:_MAX_OUTPUT_BYTES],
                "".join(stderr_chunks)[:_MAX_OUTPUT_BYTES],
                True,
            )

        # Check timeout
        if deadline is not None and _time.monotonic() > deadline:
            _kill_tree(proc.pid)
            t_out.join(timeout=1)
            t_err.join(timeout=1)
            return (
                -1,
                "(timed out)",
                "",
                False,
            )

        rc = proc.poll()
        if rc is not None:
            t_out.join(timeout=2)
            t_err.join(timeout=2)
            return (
                rc,
                "".join(stdout_chunks)[:_MAX_OUTPUT_BYTES],
                "".join(stderr_chunks)[:_MAX_OUTPUT_BYTES],
                False,
            )

        _time.sleep(_POLL_INTERVAL)


def _kill_tree(pid: int) -> None:
    """Kill process tree via subprocess_sandbox utility (best effort)."""
    try:
        from openjarvis.security.subprocess_sandbox import kill_process_tree

        kill_process_tree(pid)
    except Exception:
        # Last-resort fallback
        try:
            import signal

            os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))
        except Exception:
            pass


@ToolRegistry.register("shell_exec")
class ShellExecTool(BaseTool):
    """Execute shell commands with a sanitised environment."""

    tool_id = "shell_exec"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="shell_exec",
            description=(
                "Execute a shell command and return its stdout/stderr."
                " Runs with a minimal environment for security."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute.",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": ("Timeout in seconds (default 30, max 300)."),
                    },
                    "working_dir": {
                        "type": "string",
                        "description": (
                            "Working directory for the command."
                            " Must exist and be a directory."
                        ),
                    },
                    "env_passthrough": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Additional environment variable names"
                            " to pass through from the host."
                        ),
                    },
                },
                "required": ["command"],
            },
            category="system",
            requires_confirmation=True,
            timeout_seconds=60.0,
            required_capabilities=["code:execute"],
        )

    def execute(self, **params: Any) -> ToolResult:
        command = params.get("command", "")
        if not command:
            return ToolResult(
                tool_name="shell_exec",
                content="No command provided.",
                success=False,
            )

        # Resolve timeout (capped at _MAX_TIMEOUT)
        timeout = params.get("timeout", _DEFAULT_TIMEOUT)
        try:
            timeout = int(timeout)
        except (TypeError, ValueError):
            timeout = _DEFAULT_TIMEOUT
        if timeout < 1:
            timeout = 1
        if timeout > _MAX_TIMEOUT:
            timeout = _MAX_TIMEOUT

        # Validate working_dir
        working_dir = params.get("working_dir")
        if working_dir is not None:
            wd_path = Path(working_dir)
            if not wd_path.exists():
                return ToolResult(
                    tool_name="shell_exec",
                    content=f"Working directory does not exist: {working_dir}",
                    success=False,
                )
            if not wd_path.is_dir():
                return ToolResult(
                    tool_name="shell_exec",
                    content=f"Working directory is not a directory: {working_dir}",
                    success=False,
                )

        # Build sanitised environment
        env: dict[str, str] = {}
        for key in _BASE_ENV_KEYS:
            val = os.environ.get(key)
            if val is not None:
                env[key] = val

        env_passthrough: List[str] = params.get("env_passthrough") or []
        for key in env_passthrough:
            val = os.environ.get(key)
            if val is not None:
                env[key] = val

        # Optional cancellation token passed by the orchestrator
        cancellation_token = params.get("cancellation_token")

        # Enforce Safety Kernel checks on shell command
        from openjarvis.security.kernel import ActionEffect, get_safety_kernel

        kernel = get_safety_kernel()
        decision = kernel.evaluate("shell_exec", target=command, params={"command": command, "working_dir": working_dir})
        if decision.effect == ActionEffect.BLOCK:
            return ToolResult(
                tool_name="shell_exec",
                content=f"Safety Kernel Policy Violation: {decision.reason}",
                success=False,
                metadata={"safety_decision": decision.to_dict(), "guardrails": "BLOCKED"},
            )

        if decision.effect in (ActionEffect.ASK, ActionEffect.ASK_WITH_CODE):
            auth_token = params.get("authorization_token")
            if auth_token:
                valid, msg = kernel.code_mgr.consume_action_token(auth_token, decision.fingerprint)
                if not valid:
                    return ToolResult(
                        tool_name="shell_exec",
                        content=f"Safety Kernel Authorization Error: {msg}",
                        success=False,
                        metadata={"safety_decision": decision.to_dict(), "guardrails": "AUTH_REQUIRED"},
                    )
            else:
                return ToolResult(
                    tool_name="shell_exec",
                    content=f"Safety Kernel Approval Required ({decision.risk_level.value}): {decision.reason}",
                    success=False,
                    metadata={"safety_decision": decision.to_dict(), "guardrails": "AUTH_REQUIRED"},
                )

        try:
            from openjarvis._rust_bridge import get_rust_module

            _rust = get_rust_module()
            output = _rust.ShellExecTool().execute(command, working_dir)
            return ToolResult(
                tool_name="shell_exec",
                content=output or "(no output)",
                success=True,
                metadata={
                    "returncode": 0,
                    "timeout_used": timeout,
                    "working_dir": working_dir,
                },
            )
        except ImportError:
            pass  # Fall through to Popen path below
        except Exception as exc:
            return ToolResult(
                tool_name="shell_exec",
                content=str(exc),
                success=False,
                metadata={
                    "returncode": -1,
                    "timeout_used": timeout,
                    "working_dir": working_dir,
                },
            )

        # --- Cancellable Popen path (TSK-P5-01) ---
        try:
            returncode, stdout, stderr, was_cancelled = _run_subprocess_cancellable(
                command,
                timeout=timeout,
                working_dir=working_dir,
                env=env,
                cancellation_token=cancellation_token,
            )
        except PermissionError as exc:
            return ToolResult(
                tool_name="shell_exec",
                content=f"Permission denied: {exc}",
                success=False,
            )
        except OSError as exc:
            return ToolResult(
                tool_name="shell_exec",
                content=f"OS error: {exc}",
                success=False,
            )

        if was_cancelled:
            return ToolResult(
                tool_name="shell_exec",
                content="Command execution was cancelled by operator emergency stop.",
                success=False,
                metadata={
                    "returncode": -1,
                    "timeout_used": timeout,
                    "working_dir": working_dir,
                    "cancelled": True,
                },
            )

        if returncode == -1 and stdout == "(timed out)":
            return ToolResult(
                tool_name="shell_exec",
                content=f"Command timed out after {timeout} seconds.",
                success=False,
                metadata={
                    "returncode": -1,
                    "timeout_used": timeout,
                    "working_dir": working_dir,
                },
            )

        # Truncate output if needed
        if len(stdout) > _MAX_OUTPUT_BYTES:
            stdout = stdout[:_MAX_OUTPUT_BYTES] + "\n... (stdout truncated)"
        if len(stderr) > _MAX_OUTPUT_BYTES:
            stderr = stderr[:_MAX_OUTPUT_BYTES] + "\n... (stderr truncated)"

        # Format output
        sections: list[str] = []
        if stdout:
            sections.append(f"=== STDOUT ===\n{stdout}")
        if stderr:
            sections.append(f"=== STDERR ===\n{stderr}")
        content = "\n".join(sections) if sections else "(no output)"

        return ToolResult(
            tool_name="shell_exec",
            content=content,
            success=returncode == 0,
            metadata={
                "returncode": returncode,
                "timeout_used": timeout,
                "working_dir": working_dir,
            },
        )


__all__ = ["ShellExecTool"]
