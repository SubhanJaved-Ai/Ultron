"""FastAPI routes for node registration and WebSocket tunneling."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from openjarvis.server.node_manager import NodeManager

logger = logging.getLogger(__name__)

node_router = APIRouter(prefix="/v1/node", tags=["node"])

# Global or app-bound node manager
_node_manager: Optional[NodeManager] = None


def get_node_manager(request: Optional[Request] = None) -> NodeManager:
    """Get the active NodeManager instance from app state or global."""
    global _node_manager
    if request and hasattr(request.app.state, "node_manager"):
        return request.app.state.node_manager
    if _node_manager is None:
        _node_manager = NodeManager()
    return _node_manager


class RegisterNodeRequest(BaseModel):
    device_name: str


@node_router.post("/register")
async def register_node(
    payload: RegisterNodeRequest,
    request: Request,
) -> Dict[str, Any]:
    """Register a new device/worker node and issue an authentication token."""
    mgr = get_node_manager(request)
    name = (payload.device_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="device_name cannot be empty")
    return mgr.register_device(name)


@node_router.get("/status")
async def get_node_status(request: Request) -> Dict[str, Any]:
    """Return status of all registered nodes and whether any are online."""
    mgr = get_node_manager(request)
    nodes = mgr.list_nodes()
    return {
        "nodes": nodes,
        "any_online": any(n.get("online") for n in nodes),
    }


@node_router.websocket("/tunnel")
async def node_tunnel(websocket: WebSocket) -> None:
    """WebSocket endpoint for local machine nodes to connect to Cloud Jarvis."""
    device_id = websocket.query_params.get("device_id", "")
    token = websocket.query_params.get("token", "")

    mgr = get_node_manager()
    if not device_id or not token or not mgr.verify_token(device_id, token):
        logger.warning("Rejected unauthorized node connection: %s", device_id)
        await websocket.close(code=1008)
        return

    await websocket.accept()
    await mgr.register_connection(device_id, websocket)

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "rpc_response":
                rpc_id = data.get("rpc_id", "")
                result = data.get("result", {})
                mgr.handle_rpc_response(rpc_id, result)

            elif msg_type == "ping":
                mgr.update_last_seen(device_id)
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug("Node tunnel error for %s: %s", device_id, exc)
    finally:
        await mgr.unregister_connection(device_id)


__all__ = ["node_router", "get_node_manager"]
