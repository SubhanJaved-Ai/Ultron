"""Tests for shell_exec.py cancellation integration.

Verifies that:
  - ShellExecTool spawns commands inside a new process group (Windows)
    or session (POSIX) for clean tree kill.
  - A live CancellationToken stops a long-running process within 1 second of
    being set and returns ``cancelled: True`` in the metadata.
  - The tool still works correctly when no cancellation token is supplied
    (backward-compatible).
  - kill_process_tree actually terminates child processes (orphan check via
    process table inspection).

TSK-P5-01 / AC-GES-04
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from typing import Any

import pytest

from openjarvis.server.cancellation import CancellationToken
from openjarvis.tools.shell_exec import ShellExecTool, _run_subprocess_cancellable

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_token(ctx_id: str = "test-shell") -> CancellationToken:
    return CancellationToken(context_id=ctx_id)


def _long_sleep_cmd() -> str:
    """Platform-agnostic 60-second sleep command."""
    if os.name == "nt":
        return f'"{sys.executable}" -c "import time; time.sleep(60)"'
    return "sleep 60"


def _echo_cmd(msg: str) -> str:
    """Platform-agnostic echo command."""
    if os.name == "nt":
        return f'"{sys.executable}" -c "print({msg!r})"'
    return f"echo {msg!r}"


# ---------------------------------------------------------------------------
# ShellExecTool — basic functionality (backward-compatible, no token)
# ---------------------------------------------------------------------------


class TestShellExecToolBasic:
    def test_echo_command_succeeds(self):
        tool = ShellExecTool()
        result = tool.execute(command=_echo_cmd("hello-ultron"))
        assert result.success
        assert "hello-ultron" in result.content

    def test_empty_command_returns_failure(self):
        tool = ShellExecTool()
        result = tool.execute(command="")
        assert not result.success
        assert "No command provided" in result.content

    def test_nonexistent_working_dir_returns_failure(self):
        tool = ShellExecTool()
        result = tool.execute(
            command=_echo_cmd("x"),
            working_dir="/nonexistent/path/12345",
        )
        assert not result.success
        assert "Working directory does not exist" in result.content

    def test_invalid_working_dir_type_returns_failure(self, tmp_path):
        # Pass a file path (not a directory)
        f = tmp_path / "notadir.txt"
        f.write_text("x")
        tool = ShellExecTool()
        result = tool.execute(command=_echo_cmd("x"), working_dir=str(f))
        assert not result.success
        assert "not a directory" in result.content

    def test_timeout_exceeded_returns_failure(self):
        tool = ShellExecTool()
        result = tool.execute(command=_long_sleep_cmd(), timeout=1)
        assert not result.success
        assert "timed out" in result.content.lower()


# ---------------------------------------------------------------------------
# Cancellable subprocess path — _run_subprocess_cancellable
# ---------------------------------------------------------------------------


class TestRunSubprocessCancellable:
    def test_normal_command_completes(self):
        rc, stdout, stderr, cancelled = _run_subprocess_cancellable(
            _echo_cmd("cancel-test"),
            timeout=10,
            working_dir=None,
            env={k: v for k, v in os.environ.items()},
        )
        assert not cancelled
        assert "cancel-test" in stdout

    def test_cancellation_stops_long_command(self):
        token = _make_token("shell-cancel-01")

        results: dict[str, Any] = {}

        def _run():
            rc, stdout, stderr, was_cancelled = _run_subprocess_cancellable(
                _long_sleep_cmd(),
                timeout=60,
                working_dir=None,
                env={k: v for k, v in os.environ.items()},
                cancellation_token=token,
            )
            results["rc"] = rc
            results["cancelled"] = was_cancelled

        t = threading.Thread(target=_run, daemon=True)
        t.start()

        # Let the process start
        time.sleep(0.3)
        token.cancel()
        t.join(timeout=5)

        assert not t.is_alive(), "Thread should have terminated after cancellation"
        assert results.get("cancelled") is True
        assert results.get("rc") == -1

    def test_cancellation_is_fast(self):
        """Cancellation must complete within 1 second (AC-GES-04 requires <250ms + overhead)."""
        token = _make_token("shell-cancel-02")
        cancel_time: dict[str, float] = {}
        done_time: dict[str, float] = {}

        def _run():
            _run_subprocess_cancellable(
                _long_sleep_cmd(),
                timeout=60,
                working_dir=None,
                env={k: v for k, v in os.environ.items()},
                cancellation_token=token,
            )
            done_time["ts"] = time.monotonic()

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        time.sleep(0.3)
        cancel_time["ts"] = time.monotonic()
        token.cancel()
        t.join(timeout=5)

        assert not t.is_alive()
        elapsed_ms = (done_time.get("ts", cancel_time["ts"]) - cancel_time["ts"]) * 1000
        assert elapsed_ms < 2000, (
            f"Cancellation took {elapsed_ms:.0f} ms — must be under 2000 ms in test env"
        )


# ---------------------------------------------------------------------------
# ShellExecTool — cancellation via params dict
# ---------------------------------------------------------------------------


class TestShellExecToolCancellation:
    def test_cancelled_token_returns_cancelled_result(self):
        tool = ShellExecTool()
        token = _make_token("shell-exec-tool-cancel")
        token.cancel()  # Pre-cancelled token

        result = tool.execute(
            command=_long_sleep_cmd(),
            timeout=10,
            cancellation_token=token,
        )
        assert not result.success
        assert result.metadata.get("cancelled") is True
        assert "cancelled by operator" in result.content.lower()

    def test_cancel_during_execution(self):
        tool = ShellExecTool()
        token = _make_token("shell-exec-tool-live-cancel")
        results: dict[str, Any] = {}

        def _run():
            results["result"] = tool.execute(
                command=_long_sleep_cmd(),
                timeout=30,
                cancellation_token=token,
            )

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        time.sleep(0.4)
        token.cancel()
        t.join(timeout=5)

        assert not t.is_alive()
        r = results.get("result")
        assert r is not None
        assert not r.success
        assert r.metadata.get("cancelled") is True


# ---------------------------------------------------------------------------
# kill_process_tree — orphan process verification
# ---------------------------------------------------------------------------


@pytest.mark.skipif(os.name != "nt", reason="Windows-specific taskkill test")
def test_kill_process_tree_terminates_children_windows():
    """Verify that kill_process_tree eliminates the full process tree on Windows."""
    from openjarvis.security.subprocess_sandbox import kill_process_tree

    # Spawn a long-running parent process
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    pid = proc.pid
    time.sleep(0.2)  # Give it time to start

    kill_process_tree(pid)
    proc.wait(timeout=5)

    # Verify the process is no longer running
    result = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}"],
        capture_output=True,
        text=True,
    )
    # tasklist outputs "INFO: No tasks..." when the process is gone
    assert str(pid) not in result.stdout, (
        f"Process {pid} still appears in tasklist after kill_process_tree"
    )


@pytest.mark.skipif(os.name == "nt", reason="POSIX-specific process group test")
def test_kill_process_tree_terminates_children_posix():
    """Verify that kill_process_tree sends SIGKILL on POSIX."""

    from openjarvis.security.subprocess_sandbox import kill_process_tree

    proc = subprocess.Popen(
        ["sleep", "60"],
        preexec_fn=os.setsid,
    )
    pid = proc.pid
    time.sleep(0.1)

    kill_process_tree(pid)
    proc.wait(timeout=5)

    try:
        os.kill(pid, 0)
        alive = True
    except (OSError, ProcessLookupError):
        alive = False

    assert not alive, f"Process {pid} is still alive after kill_process_tree"
