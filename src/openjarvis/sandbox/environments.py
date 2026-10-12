"""Execution environments abstraction: Local, Docker, and SSH backends.

Directly inspired by Hermes Agent's terminal_tool_backends and environments:
provides a unified execution protocol across host machines, container sandboxes,
and remote SSH servers (e.g. cloud VPS, GPU clusters).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Result of command execution within an environment."""

    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float = 0.0

    @property
    def success(self) -> bool:
        return self.exit_code == 0


class ExecutionEnvironment(ABC):
    """Abstract base protocol for an execution environment."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the environment backend."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if backend dependencies/runtime are ready."""

    @abstractmethod
    def execute(
        self,
        command: str,
        *,
        timeout: int = 30,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> ExecutionResult:
        """Execute command in this environment."""


class LocalEnvironment(ExecutionEnvironment):
    """Local host execution environment with timeout and security boundaries."""

    @property
    def name(self) -> str:
        return "local"

    def is_available(self) -> bool:
        return True

    def execute(
        self,
        command: str,
        *,
        timeout: int = 30,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> ExecutionResult:
        start = time.time()
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)

        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                env=merged_env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return ExecutionResult(
                exit_code=proc.returncode,
                stdout=proc.stdout or "",
                stderr=proc.stderr or "",
                duration_seconds=round(time.time() - start, 2),
            )
        except subprocess.TimeoutExpired as exc:
            return ExecutionResult(
                exit_code=-1,
                stdout=exc.stdout or "" if isinstance(exc.stdout, str) else "",
                stderr=f"Command timed out after {timeout}s",
                duration_seconds=timeout,
            )
        except Exception as exc:
            return ExecutionResult(
                exit_code=-1,
                stdout="",
                stderr=f"Execution error: {exc}",
                duration_seconds=round(time.time() - start, 2),
            )


class DockerEnvironment(ExecutionEnvironment):
    """Docker container execution environment."""

    def __init__(
        self,
        container_id: Optional[str] = None,
        image: str = "python:3.12-slim",
    ) -> None:
        self.container_id = container_id
        self.image = image

    @property
    def name(self) -> str:
        return "docker"

    def is_available(self) -> bool:
        return shutil.which("docker") is not None

    def execute(
        self,
        command: str,
        *,
        timeout: int = 30,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> ExecutionResult:
        if not self.is_available():
            return ExecutionResult(
                exit_code=-1,
                stdout="",
                stderr="Docker executable is not available on PATH.",
            )

        start = time.time()
        docker_cmd: List[str] = ["docker"]

        if self.container_id:
            docker_cmd.extend(["exec"])
            if cwd:
                docker_cmd.extend(["-w", cwd])
            if env:
                for k, v in env.items():
                    docker_cmd.extend(["-e", f"{k}={v}"])
            docker_cmd.extend([self.container_id, "sh", "-c", command])
        else:
            docker_cmd.extend(["run", "--rm"])
            if cwd:
                docker_cmd.extend(["-w", cwd])
            if env:
                for k, v in env.items():
                    docker_cmd.extend(["-e", f"{k}={v}"])
            docker_cmd.extend([self.image, "sh", "-c", command])

        try:
            proc = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return ExecutionResult(
                exit_code=proc.returncode,
                stdout=proc.stdout or "",
                stderr=proc.stderr or "",
                duration_seconds=round(time.time() - start, 2),
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                exit_code=-1,
                stdout="",
                stderr=f"Docker command timed out after {timeout}s",
                duration_seconds=timeout,
            )
        except Exception as exc:
            return ExecutionResult(
                exit_code=-1,
                stdout="",
                stderr=f"Docker error: {exc}",
                duration_seconds=round(time.time() - start, 2),
            )


class SSHEnvironment(ExecutionEnvironment):
    """Remote SSH execution environment for cloud VPS, GPU clusters, and servers."""

    def __init__(
        self,
        host: str,
        *,
        user: Optional[str] = None,
        port: int = 22,
        key_path: Optional[str | Path] = None,
        connect_timeout: int = 10,
    ) -> None:
        self.host = host
        self.user = user
        self.port = port
        self.key_path = Path(key_path).expanduser() if key_path else None
        self.connect_timeout = connect_timeout

    @property
    def name(self) -> str:
        return "ssh"

    def is_available(self) -> bool:
        return shutil.which("ssh") is not None

    def build_ssh_args(
        self,
        command: str,
        cwd: Optional[str] = None,
    ) -> List[str]:
        """Build argument vector for subprocess ssh call."""
        ssh_bin = shutil.which("ssh") or "ssh"
        args = [
            ssh_bin,
            "-p",
            str(self.port),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            f"ConnectTimeout={self.connect_timeout}",
        ]
        if self.key_path:
            args.extend(["-i", str(self.key_path)])

        target = f"{self.user}@{self.host}" if self.user else self.host
        args.append(target)

        remote_cmd = f"cd {cwd} && {command}" if cwd else command
        args.append(remote_cmd)
        return args

    def execute(
        self,
        command: str,
        *,
        timeout: int = 30,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> ExecutionResult:
        if not self.is_available():
            return ExecutionResult(
                exit_code=-1,
                stdout="",
                stderr="SSH client executable ('ssh') is not found on system PATH.",
            )

        start = time.time()
        # Prepend env exports if provided
        cmd_to_run = command
        if env:
            env_prefixes = " ".join(f"{k}='{v}'" for k, v in env.items())
            cmd_to_run = f"{env_prefixes} {command}"

        args = self.build_ssh_args(cmd_to_run, cwd=cwd)

        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return ExecutionResult(
                exit_code=proc.returncode,
                stdout=proc.stdout or "",
                stderr=proc.stderr or "",
                duration_seconds=round(time.time() - start, 2),
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                exit_code=-1,
                stdout="",
                stderr=f"SSH command timed out after {timeout}s",
                duration_seconds=timeout,
            )
        except Exception as exc:
            return ExecutionResult(
                exit_code=-1,
                stdout="",
                stderr=f"SSH connection error: {exc}",
                duration_seconds=round(time.time() - start, 2),
            )


def get_environment(env_type: str, **kwargs: Any) -> ExecutionEnvironment:
    """Factory to instantiate execution environment by type."""
    t = env_type.lower().strip()
    if t == "local":
        return LocalEnvironment()
    elif t == "docker":
        return DockerEnvironment(
            container_id=kwargs.get("container_id"),
            image=kwargs.get("image", "python:3.12-slim"),
        )
    elif t == "ssh":
        return SSHEnvironment(
            host=kwargs.get("host", "localhost"),
            user=kwargs.get("user"),
            port=int(kwargs.get("port", 22)),
            key_path=kwargs.get("key_path"),
            connect_timeout=int(kwargs.get("connect_timeout", 10)),
        )
    raise ValueError(
        f"Unknown environment type: {env_type!r}. Supported: 'local', 'docker', 'ssh'"
    )
