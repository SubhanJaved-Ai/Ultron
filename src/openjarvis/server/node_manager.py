"""NodeManager — coordinates cloud-to-device tunneling and RPC execution."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class NodeManager:
    """Manages registered desktop/mobile worker nodes and active tunnel sessions."""

    def __init__(self, db_path: Optional[Path | str] = None) -> None:
        if db_path is None:
            from openjarvis.core.paths import get_data_dir

            db_path = get_data_dir() / "nodes.db"
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

        # Active websocket connections: device_id -> (websocket, pending_futures)
        self._active_nodes: Dict[str, Any] = {}
        self._pending_rpc: Dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS registered_nodes (
                    device_id TEXT PRIMARY KEY,
                    device_name TEXT NOT NULL,
                    token_hash TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    last_seen REAL NOT NULL
                )
                """
            )
            conn.commit()

    def register_device(self, device_name: str) -> Dict[str, str]:
        """Register a new device and generate a secret token."""
        device_id = f"node_{secrets.token_hex(8)}"
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        now = time.time()

        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO registered_nodes
                (device_id, device_name, token_hash, created_at, last_seen)
                VALUES (?, ?, ?, ?, ?)
                """,
                (device_id, device_name, token_hash, now, now),
            )
            conn.commit()

        return {
            "device_id": device_id,
            "device_name": device_name,
            "token": raw_token,
        }

    def verify_token(self, device_id: str, token: str) -> bool:
        """Verify the authentication token presented by a connecting node."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT token_hash FROM registered_nodes WHERE device_id = ?",
                (device_id,),
            ).fetchone()
            if not row:
                return False
            expected_hash = row["token_hash"]
            provided_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
            return hmac.compare_digest(expected_hash, provided_hash)

    def update_last_seen(self, device_id: str) -> None:
        """Update last seen timestamp for a node."""
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE registered_nodes SET last_seen = ? WHERE device_id = ?",
                (time.time(), device_id),
            )
            conn.commit()

    async def register_connection(self, device_id: str, websocket: Any) -> None:
        """Register an active WebSocket tunnel for a verified node."""
        async with self._lock:
            self._active_nodes[device_id] = websocket
            self.update_last_seen(device_id)
            logger.info("Node %s connected to cloud tunnel", device_id)

    async def unregister_connection(self, device_id: str) -> None:
        """Unregister a disconnected WebSocket tunnel."""
        async with self._lock:
            if device_id in self._active_nodes:
                del self._active_nodes[device_id]
                logger.info("Node %s disconnected from cloud tunnel", device_id)

    def is_node_online(self, device_id: Optional[str] = None) -> bool:
        """Check if a specific node or any node is currently online."""
        if device_id:
            return device_id in self._active_nodes
        return len(self._active_nodes) > 0

    def list_nodes(self) -> List[Dict[str, Any]]:
        """List all registered devices with their online status."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT device_id, device_name, created_at, last_seen "
                "FROM registered_nodes ORDER BY last_seen DESC"
            ).fetchall()

            results = []
            for row in rows:
                dev_id = row["device_id"]
                results.append(
                    {
                        "device_id": dev_id,
                        "device_name": row["device_name"],
                        "created_at": row["created_at"],
                        "last_seen": row["last_seen"],
                        "online": dev_id in self._active_nodes,
                    }
                )
            return results

    async def dispatch_rpc(
        self,
        action: str,
        params: Dict[str, Any],
        *,
        device_id: Optional[str] = None,
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        """Dispatch an RPC request to an online node through the tunnel."""
        target_id = device_id
        async with self._lock:
            if not target_id:
                if not self._active_nodes:
                    return {
                        "success": False,
                        "error": (
                            "No local machine node is currently connected. "
                            "Local computer is offline or powered off."
                        ),
                    }
                # Default to the first active node
                target_id = next(iter(self._active_nodes.keys()))

            ws = self._active_nodes.get(target_id)
            if not ws:
                return {
                    "success": False,
                    "error": f"Node {target_id} is not connected.",
                }

        rpc_id = secrets.token_hex(8)
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending_rpc[rpc_id] = future

        message = {
            "type": "rpc_request",
            "rpc_id": rpc_id,
            "action": action,
            "params": params,
        }

        try:
            await ws.send_json(message)
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": f"RPC timed out after {timeout} seconds on node {target_id}.",
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}
        finally:
            self._pending_rpc.pop(rpc_id, None)

    def handle_rpc_response(self, rpc_id: str, result: Dict[str, Any]) -> bool:
        """Resolve a pending RPC future with the received result."""
        future = self._pending_rpc.get(rpc_id)
        if future and not future.done():
            future.set_result(result)
            return True
        return False


__all__ = ["NodeManager"]
