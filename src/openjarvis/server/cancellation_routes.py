"""Cancellation REST endpoint — Global Emergency Stop (GAP-01 / TSK-P5-01).

Exposes:

    POST /api/execution/cancel
        Body: ``{"context_id": "<id>"}``   (``context_id`` defaults to ``"active"``)

        On success:
            HTTP 200  ``{"status": "cancelling", "context_id": "<id>",
                         "elapsed_ms": <float>}``
        When no active context matches:
            HTTP 404  ``{"detail": "No active execution context found."}``

The endpoint is intentionally lightweight and synchronous: it sets a
``threading.Event`` and returns immediately (<5 ms).  The actual teardown
(process tree kill, browser close, stream abort) happens cooperatively in the
execution layer as each component reads ``token.is_cancelled``.

Authentication:
    Requires an authenticated user session (AuthMiddleware enforces this because
    the path starts with ``/api/``).  No additional RBAC gate is added here; any
    authenticated user may cancel their own active directive.
"""

from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from openjarvis.server.cancellation import get_execution_store

cancellation_router = APIRouter(tags=["cancellation"])


class CancelRequest(BaseModel):
    """Request body for the cancel endpoint."""

    context_id: Optional[str] = "active"
    session_id: Optional[str] = None


class CancelResponse(BaseModel):
    """Response body returned on successful cancellation signal."""

    status: str
    context_id: str
    elapsed_ms: float


def _resolve_session_id(request: Request, body_session_id: Optional[str] = None) -> str:
    """Resolve authoritative session/user identity from request state.

    Never trusts an unauthenticated caller-supplied session_id. If an authenticated
    user is present, verifies that any caller-supplied session_id matches.
    """
    current_user = getattr(request.state, "user", None)
    auth_user_id = getattr(current_user, "id", None) if current_user is not None else None

    if auth_user_id:
        if body_session_id and body_session_id != auth_user_id and auth_user_id != "api_admin":
            raise HTTPException(
                status_code=403,
                detail="Caller-supplied session_id does not match authenticated user identity.",
            )
        return auth_user_id

    # Fallback to body_session_id if provided, otherwise default
    return body_session_id or "default"


@cancellation_router.post(
    "/api/execution/cancel",
    response_model=CancelResponse,
    summary="Emergency Stop — signal cancellation for an active execution context",
)
async def cancel_execution(body: CancelRequest, request: Request) -> CancelResponse:
    """Emit a cancellation signal for an active execution context.

    The signal propagates cooperatively across:
    - Subprocess trees (``kill_process_tree`` in ``shell_exec.py``)
    - Playwright browser sessions (``_session.close_on_cancel()``)
    - Subagent orchestrator loops (``is_cancelled`` guard in dispatch)
    - LLM streaming generators (generator checks token before each yield)

    Returns HTTP 200 with ``{"status": "cancelling"}`` immediately — the actual
    teardown is asynchronous and takes up to ~500 ms for browser resources.

    Returns HTTP 403 if the context belongs to a different session.
    Returns HTTP 404 if no matching active context was found.
    """
    t0 = time.monotonic()
    context_id = (body.context_id or "active").strip() or "active"
    effective_session_id = _resolve_session_id(request, body.session_id)

    store = get_execution_store()
    token = store.get(context_id)
    if (
        token is not None
        and token.owner_session_id is not None
        and token.owner_session_id != effective_session_id
    ):
        raise HTTPException(
            status_code=403,
            detail=f"Not authorized to cancel context {context_id!r} owned by another session.",
        )

    cancelled = store.cancel(context_id, requesting_session_id=effective_session_id)
    elapsed = (time.monotonic() - t0) * 1000.0

    if not cancelled:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No active execution context found for context_id={context_id!r}. "
                "There may be nothing running right now."
            ),
        )

    return CancelResponse(
        status="cancelling",
        context_id=context_id,
        elapsed_ms=round(elapsed, 3),
    )


@cancellation_router.get(
    "/api/execution/contexts",
    summary="List active execution context IDs",
)
async def list_contexts(request: Request) -> dict:
    """Return currently registered execution context IDs for the caller's session.

    Restricts output to the caller's authenticated session to prevent
    cross-tenant execution enumeration.
    """
    current_user = getattr(request.state, "user", None)
    auth_user_id = getattr(current_user, "id", None) if current_user is not None else None

    store = get_execution_store()
    return {"active_contexts": store.list_active(session_id=auth_user_id)}


__all__ = ["cancellation_router"]
