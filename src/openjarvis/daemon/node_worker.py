"""NodeWorker — client-side daemon for connecting home computer to Cloud Jarvis."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


class NodeWorker:
    """Connects a user machine to Cloud Jarvis over an encrypted WebSocket tunnel."""

    def __init__(
        self,
        server_url: str,
        device_id: str,
        token: str,
        *,
        reconnect_delay: float = 3.0,
    ) -> None:
        self.server_url = server_url.rstrip("/")
        self.device_id = device_id
        self.token = token
        self.reconnect_delay = reconnect_delay
        self._stop_event = asyncio.Event()

    def stop(self) -> None:
        """Signal the worker to stop."""
        self._stop_event.set()

    async def run(self) -> None:
        """Run the persistent connection loop with automatic reconnection."""
        try:
            import websockets
        except ImportError:
            raise ImportError(
                "websockets is required. Install with: pip install websockets"
            )

        ws_scheme = "wss" if self.server_url.startswith("https") else "ws"
        host_part = self.server_url.split("://")[-1]
        tunnel_url = (
            f"{ws_scheme}://{host_part}/v1/node/tunnel"
            f"?device_id={self.device_id}&token={self.token}"
        )

        logger.info("Connecting to Cloud Jarvis tunnel at %s", self.server_url)

        while not self._stop_event.is_set():
            try:
                async with websockets.connect(tunnel_url) as ws:
                    logger.info("Tunnel connected! Device online.")
                    ping_task = asyncio.create_task(self._ping_loop(ws))
                    try:
                        while not self._stop_event.is_set():
                            raw_msg = await ws.recv()
                            msg = json.loads(raw_msg)
                            if msg.get("type") == "rpc_request":
                                await self._handle_rpc(ws, msg)
                    finally:
                        ping_task.cancel()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                if self._stop_event.is_set():
                    break
                logger.warning(
                    "Tunnel disconnected (%s). Reconnecting in %.1fs...",
                    exc,
                    self.reconnect_delay,
                )
                await asyncio.sleep(self.reconnect_delay)

    async def _ping_loop(self, ws: Any) -> None:
        """Send heartbeats every 15 seconds."""
        while not self._stop_event.is_set():
            try:
                await asyncio.sleep(15.0)
                await ws.send(json.dumps({"type": "ping"}))
            except Exception:
                break

    async def _handle_rpc(self, ws: Any, request: Dict[str, Any]) -> None:
        """Process an incoming RPC request from Cloud Jarvis and reply."""
        rpc_id = request.get("rpc_id", "")
        action = request.get("action", "")
        params = request.get("params", {})

        result: Dict[str, Any] = {"success": True}
        try:
            if action == "system_info":
                result["data"] = {
                    "platform": platform.platform(),
                    "system": platform.system(),
                    "machine": platform.machine(),
                    "python": sys.version,
                }
            elif action == "execute_shell":
                cmd = params.get("command", "")
                res = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=params.get("timeout", 60),
                )
                result["data"] = {
                    "stdout": res.stdout,
                    "stderr": res.stderr,
                    "exit_code": res.returncode,
                }
            elif action == "read_file":
                filepath = Path(params.get("path", "")).expanduser()
                if not filepath.is_file():
                    result["success"] = False
                    result["error"] = f"File not found: {filepath}"
                else:
                    result["content"] = filepath.read_text(
                        encoding=params.get("encoding", "utf-8"),
                        errors="replace",
                    )
            elif action == "write_file":
                filepath = Path(params.get("path", "")).expanduser()
                filepath.parent.mkdir(parents=True, exist_ok=True)
                filepath.write_text(
                    params.get("content", ""),
                    encoding=params.get("encoding", "utf-8"),
                )
                result["written"] = True
            elif action == "open_app":
                app_name = params.get("name", "")
                if platform.system() == "Windows":
                    os.startfile(app_name)
                elif platform.system() == "Darwin":
                    subprocess.run(["open", "-a", app_name])
                else:
                    subprocess.run(["xdg-open", app_name])
                result["opened"] = True
            else:
                result["success"] = False
                result["error"] = f"Unknown action: {action}"
        except Exception as exc:
            result["success"] = False
            result["error"] = str(exc)

        response = {
            "type": "rpc_response",
            "rpc_id": rpc_id,
            "result": result,
        }
        await ws.send(json.dumps(response))


__all__ = ["NodeWorker"]
