"""Tests for SSHExecTool."""

from unittest.mock import patch

from openjarvis.sandbox.environments import ExecutionResult
from openjarvis.tools.ssh_exec import SSHExecTool


def test_ssh_exec_validation():
    tool = SSHExecTool()
    res = tool.execute(host="", command="ls")
    assert res.success is False
    assert "Both 'host' and 'command' are required" in res.content


def test_ssh_exec_execution():
    tool = SSHExecTool()

    mock_result = ExecutionResult(
        exit_code=0,
        stdout="Linux cloud-instance 6.8.0 #1 SMP",
        stderr="",
        duration_seconds=0.45,
    )

    with patch(
        "openjarvis.tools.ssh_exec.SSHEnvironment.is_available", return_value=True
    ):
        with patch(
            "openjarvis.tools.ssh_exec.SSHEnvironment.execute", return_value=mock_result
        ):
            res = tool.execute(
                host="192.168.1.100",
                command="uname -a",
                user="admin",
                port=22,
            )

    assert res.success is True
    assert "Linux cloud-instance" in res.content
    assert res.metadata["exit_code"] == 0
