"""FastAPI routes for Ultron's Persistent Task Runner."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from openjarvis.tasks.runner import PersistentTaskRunner
from openjarvis.tasks.types import StepStatus, TaskStatus

logger = logging.getLogger(__name__)

task_router = APIRouter(prefix="/api/tasks", tags=["tasks"])


# ---------------------------------------------------------------------------
# Request & Response Schemas
# ---------------------------------------------------------------------------

class CreateTaskRequest(BaseModel):
    """Payload to create or plan a new persistent task."""
    prompt: str = Field(..., description="User request or directive prompt")
    steps: Optional[List[Dict[str, Any]]] = Field(None, description="Optional explicit DAG steps")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Metadata tags")
    auto_run: bool = Field(True, description="Whether to start execution immediately")
    idempotency_key: Optional[str] = Field(None, description="Client idempotency key for deduplication")


class ApproveStepRequest(BaseModel):
    """Payload to authorize a waiting_approval step."""
    step_id: Optional[str] = Field(None, description="ID of step to approve (defaults to first waiting step)")
    safety_code: Optional[str] = Field(None, description="User safety code if required by risk policy")
    token: Optional[str] = Field(None, description="Pre-issued action token if available")
    resolution: Optional[str] = Field(
        None,
        description="Resolution for uncertain external actions: 'mark_completed' or 'force_retry'",
    )
    confirm_duplicate_risk: bool = Field(
        False,
        description=(
            "Explicit operator confirmation acknowledging that force_retry may repeat external actions "
            "and cause duplicate messages, requests, or other unintended side effects."
        ),
    )
    tool_args: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional tool arguments provided by user to satisfy missing information",
    )


class RejectStepRequest(BaseModel):
    """Payload to reject authorization for a waiting step."""
    step_id: Optional[str] = Field(None, description="ID of step to reject")
    reason: Optional[str] = Field("User rejected approval request.", description="Reason for rejection")


class StepInputRequest(BaseModel):
    """Payload to supply user-provided arguments for a step missing essential parameters."""
    step_id: Optional[str] = Field(None, description="ID of step requiring input (defaults to first waiting step)")
    tool_args: Dict[str, Any] = Field(..., description="Tool arguments satisfying missing parameters")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_runner(request: Request) -> PersistentTaskRunner:
    """Retrieve or instantiate the PersistentTaskRunner on app.state."""
    app_runner = getattr(request.app.state, "task_runner", None)
    if app_runner is not None:
        return app_runner

    # Lazy fallback singleton
    runner = PersistentTaskRunner(
        bus=getattr(request.app.state, "bus", None),
        agent=getattr(request.app.state, "agent", None),
        capability_policy=getattr(request.app.state, "capability_policy", None),
        auto_recover=False,
    )
    request.app.state.task_runner = runner
    return runner


def _get_current_user_id(request: Request) -> Optional[str]:
    """Extract authenticated user id or username from request state."""
    user = getattr(request.state, "user", None)
    if user is not None:
        return getattr(user, "id", None) or getattr(user, "username", None)
    return None


def _check_task_access(task: Any, request: Request) -> None:
    """Enforce multi-user authorization and tenant isolation."""
    if not getattr(request.app.state, "multi_user", False):
        return
    user = getattr(request.state, "user", None)
    if not user:
        return
    if getattr(user, "role", "") == "admin":
        return
    user_id = _get_current_user_id(request)
    task_owner = task.metadata.get("owner_id")
    if task_owner and user_id and task_owner != user_id:
        raise HTTPException(
            status_code=403,
            detail="Access denied: you do not have permission to access or modify this task.",
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@task_router.post("", summary="Create and plan a persistent task")
def create_task(body: CreateTaskRequest, request: Request) -> Dict[str, Any]:
    """Create a persistent task, decompose into steps, and optionally begin execution."""
    runner = _get_runner(request)
    meta = dict(body.metadata or {})
    user_id = _get_current_user_id(request)
    if user_id and "owner_id" not in meta:
        meta["owner_id"] = user_id

    # Check idempotency key from body or header
    idempotency_key = body.idempotency_key or request.headers.get("Idempotency-Key") or request.headers.get("X-Idempotency-Key")
    if idempotency_key and str(idempotency_key).strip():
        clean_key = str(idempotency_key).strip()
        existing = runner.store.find_task_by_idempotency_key(clean_key)
        if existing:
            _check_task_access(existing, request)
            return {
                "status": "ok",
                "task": existing.to_dict(),
                "idempotent_replay": True,
            }
        meta["idempotency_key"] = clean_key

    try:
        task = runner.plan_task(
            prompt=body.prompt,
            steps=body.steps,
            metadata=meta,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if body.auto_run:
        runner.run_task(task.task_id, background=True)
        # Fetch fresh state after starting
        refreshed = runner.store.get_task(task.task_id)
        if refreshed:
            task = refreshed

    return {"status": "ok", "task": task.to_dict()}


@task_router.get("", summary="List persistent tasks")
def list_tasks(
    request: Request,
    status: Optional[str] = Query(None, description="Filter by status (queued, running, etc.)"),
    limit: int = Query(50, ge=1, le=200),
) -> Dict[str, Any]:
    """Retrieve all persistent tasks matching optional status filter."""
    runner = _get_runner(request)
    status_filter = TaskStatus(status) if status else None

    owner_id: Optional[str] = None
    if getattr(request.app.state, "multi_user", False):
        user = getattr(request.state, "user", None)
        if user and getattr(user, "role", "") != "admin":
            owner_id = _get_current_user_id(request)

    tasks = runner.store.list_tasks(status=status_filter, owner_id=owner_id, limit=limit)
    return {
        "status": "ok",
        "total": len(tasks),
        "tasks": [t.to_dict() for t in tasks],
    }


@task_router.get("/{task_id}", summary="Get task details and execution progress")
def get_task(task_id: str, request: Request) -> Dict[str, Any]:
    """Retrieve a specific task, including ordered step status, outputs, and artifacts."""
    runner = _get_runner(request)
    task = runner.store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")
    _check_task_access(task, request)
    return {"status": "ok", "task": task.to_dict()}


@task_router.post("/{task_id}/pause", summary="Pause running task")
def pause_task(task_id: str, request: Request) -> Dict[str, Any]:
    """Pause task execution cleanly after the active step completes."""
    runner = _get_runner(request)
    task = runner.store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")
    _check_task_access(task, request)

    success = runner.pause_task(task_id)
    if not success:
        refreshed = runner.store.get_task(task_id) or task
        raise HTTPException(
            status_code=400,
            detail=f"Cannot pause task '{task_id}' in state '{refreshed.status.value}'.",
        )
    return {"status": "paused", "task_id": task_id}


@task_router.post("/{task_id}/resume", summary="Resume paused task")
def resume_task(task_id: str, request: Request) -> Dict[str, Any]:
    """Resume execution of a paused task."""
    runner = _get_runner(request)
    task = runner.store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")
    _check_task_access(task, request)

    try:
        resumed = runner.resume_task(task_id, background=True)
        return {"status": "resumed", "task_id": task_id, "task": resumed.to_dict()}
    except ValueError as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=404, detail=str(exc))
        raise HTTPException(status_code=400, detail=str(exc))


@task_router.post("/{task_id}/cancel", summary="Cancel task")
def cancel_task(task_id: str, request: Request) -> Dict[str, Any]:
    """Cancel task, mark active steps cancelled, and abort downstream actions."""
    runner = _get_runner(request)
    task = runner.store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")
    _check_task_access(task, request)

    success = runner.cancel_task(task_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")
    return {"status": "cancelled", "task_id": task_id}


@task_router.post("/{task_id}/input", summary="Submit arguments for step waiting on user input")
def submit_step_input(task_id: str, body: StepInputRequest, request: Request) -> Dict[str, Any]:
    """Submit completed arguments for a step waiting for user input.

    Validates arguments against tool schema, resolves sequential runtime context,
    re-runs RBAC capability policy, and evaluates Safety Kernel checks.
    Never treats supplying missing information as automatic authorization for a risky action.
    """
    runner = _get_runner(request)
    task = runner.store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")
    _check_task_access(task, request)

    step_id = body.step_id
    if not step_id:
        for s in task.steps:
            if s.status == StepStatus.WAITING_APPROVAL and s.requires_user_input:
                step_id = s.step_id
                break
        if not step_id:
            for s in task.steps:
                if s.status == StepStatus.WAITING_APPROVAL:
                    step_id = s.step_id
                    break

    if not step_id:
        raise HTTPException(status_code=400, detail="No step in this task is waiting for user input.")

    try:
        res = runner.submit_step_input(
            task_id=task_id,
            step_id=step_id,
            tool_args=body.tool_args,
            auto_run=True,
        )
        return {
            "status": "ok",
            "step_status": res.get("status"),
            **{k: v for k, v in res.items() if k != "status"},
        }
    except ValueError as exc:
        err_str = str(exc)
        if "Validation failed" in err_str or "must be" in err_str:
            raise HTTPException(status_code=400, detail=err_str)
        if "Capability denied" in err_str or "Blocked by Safety" in err_str:
            raise HTTPException(status_code=403, detail=err_str)
        raise HTTPException(status_code=400, detail=err_str)


@task_router.post("/{task_id}/approve", summary="Approve waiting step with safety code")
def approve_step(task_id: str, body: ApproveStepRequest, request: Request) -> Dict[str, Any]:
    """Authorize a waiting_approval step. Validates safety code if required by risk policy."""
    runner = _get_runner(request)
    task = runner.store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")
    _check_task_access(task, request)

    step_id = body.step_id
    if not step_id:
        # Find first waiting step
        for s in task.steps:
            if s.status == StepStatus.WAITING_APPROVAL:
                step_id = s.step_id
                break

    if not step_id:
        raise HTTPException(status_code=400, detail="No step in this task is waiting for approval.")

    try:
        ok = runner.approve_step(
            task_id=task_id,
            step_id=step_id,
            safety_code=body.safety_code,
            token=body.token,
            resolution=body.resolution,
            confirm_duplicate_risk=body.confirm_duplicate_risk,
            tool_args=body.tool_args,
        )
        if not ok:
            raise HTTPException(status_code=400, detail=f"Step '{step_id}' could not be approved.")
        return {"status": "approved", "task_id": task_id, "step_id": step_id}
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@task_router.post("/{task_id}/reject", summary="Reject authorization for waiting step")
def reject_step(task_id: str, body: RejectStepRequest, request: Request) -> Dict[str, Any]:
    """Reject authorization for a waiting step, cancelling subsequent dependent steps."""
    runner = _get_runner(request)
    task = runner.store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")
    _check_task_access(task, request)

    step_id = body.step_id
    if not step_id:
        for s in task.steps:
            if s.status == StepStatus.WAITING_APPROVAL:
                step_id = s.step_id
                break

    if not step_id:
        raise HTTPException(status_code=400, detail="No step in this task is waiting for approval.")

    ok = runner.reject_step(task_id=task_id, step_id=step_id, reason=body.reason or "")
    if not ok:
        raise HTTPException(status_code=400, detail=f"Step '{step_id}' could not be rejected.")
    return {"status": "rejected", "task_id": task_id, "step_id": step_id}
