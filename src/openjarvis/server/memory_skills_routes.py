"""FastAPI routes for Ultron's Memory & Skills Control Center.

Provides administrative and operator endpoints to:
1. Search, filter, view, edit, and delete persistent memory facts, with explicit
   provenance tracking and quarantine isolation.
2. List, inspect, validate, approve, reject, disable, and re-enable learned skills,
   with tamper protection for core/system skills and RBAC enforcement.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from openjarvis.core.events import EventBus
from openjarvis.memory.store import (
    MEMORY_CATEGORIES,
    TRUST_AUTO,
    TRUST_TRUSTED,
    TRUST_UNTRUSTED,
    Fact,
    FactStore,
    LocalFactStore,
    create_fact_store,
    scrub_metadata,
    scrub_sensitive_data,
)
from openjarvis.memory.maintenance import (
    MaintenanceIssueType,
    MaintenanceSuggestion,
    MemoryMaintenanceManager,
    ProposedAction,
    SuggestionStatus,
)
from openjarvis.security.capabilities import Capability, CapabilityPolicy
from openjarvis.skills.learning import (
    PROTECTED_AUTHORS,
    PROTECTED_SKILL_TAGS,
    SkillApprovalStatus,
    WorkflowSkillLearner,
)
from openjarvis.skills.manager import SkillManager
from openjarvis.skills.types import SkillManifest

logger = logging.getLogger(__name__)

memory_skills_router = APIRouter(tags=["control_center"])


# ---------------------------------------------------------------------------
# Request & Response Schemas
# ---------------------------------------------------------------------------


class CreateMemoryRequest(BaseModel):
    """Payload to create a new persistent memory entry."""

    text: str = Field(..., description="Fact statement to store in memory")
    category: str = Field("general", description="Memory category")
    project: str = Field("default", description="Project scope")
    source: str = Field("user_direct", description="Source reference")
    source_type: Optional[str] = Field("user_direct", description="Source type")
    trust: str = Field(TRUST_TRUSTED, description="Trust level: 'trusted', 'auto', 'untrusted'")
    verified: bool = Field(True, description="Whether fact is verified")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Metadata dictionary")


class UpdateMemoryRequest(BaseModel):
    """Payload to update an existing persistent memory entry."""

    text: Optional[str] = Field(None, description="Updated fact statement")
    category: Optional[str] = Field(None, description="Updated category")
    project: Optional[str] = Field(None, description="Updated project scope")
    trust: Optional[str] = Field(None, description="Updated trust tier ('trusted', 'auto', 'untrusted')")
    verified: Optional[bool] = Field(None, description="Updated verification status")
    source_type: Optional[str] = Field(None, description="Updated source type")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Updated metadata")


class RejectSkillRequest(BaseModel):
    """Payload to reject a draft/pending_review learned skill."""

    reason: Optional[str] = Field(
        "Rejected during security review.",
        description="Reason for rejecting the skill",
    )


class DisableSkillRequest(BaseModel):
    """Payload to disable an approved learned skill."""

    reason: Optional[str] = Field(
        "Disabled by operator.",
        description="Reason for disabling the skill",
    )


class CreateCompositeSkillStep(BaseModel):
    """A single step in a candidate composite skill."""

    tool_name: Optional[str] = Field("", description="Tool name for step")
    skill_name: Optional[str] = Field("", description="Child skill name for step")
    arguments_template: Optional[str] = Field("{}", description="Arguments template")
    output_key: Optional[str] = Field("", description="Context output key")
    condition: Optional[str] = Field("", description="Boolean condition expression or 'else'")
    is_else: Optional[bool] = Field(False, description="Whether this step is an else branch")
    else_skill_name: Optional[str] = Field("", description="Optional inline alternative skill name")
    else_tool_name: Optional[str] = Field("", description="Optional inline alternative tool name")
    else_arguments_template: Optional[str] = Field("{}", description="Arguments template for inline else")
    else_output_key: Optional[str] = Field("", description="Context output key for inline else")


class CreateCompositeSkillRequest(BaseModel):
    """Payload to construct a new composite skill workflow."""

    name: str = Field(..., description="Unique name for the composite skill")
    description: Optional[str] = Field("", description="Description of the composite skill")
    steps: List[CreateCompositeSkillStep] = Field(..., description="Ordered workflow steps")
    require_approval: bool = Field(True, description="Whether newly composed skill requires review")
    tags: Optional[List[str]] = Field(default_factory=list, description="Tags for skill")



class ApproveMaintenanceRequest(BaseModel):
    """Payload to approve and apply a memory maintenance suggestion."""

    custom_text: Optional[str] = Field(None, description="Optional custom edited text for merged fact")
    target_trust: Optional[str] = Field(None, description="Optional target trust level")


class DismissMaintenanceRequest(BaseModel):
    """Payload to dismiss a memory maintenance suggestion."""

    reason: Optional[str] = Field("Dismissed by operator.", description="Reason for dismissing suggestion")


# ---------------------------------------------------------------------------
# Dependency Helpers
# ---------------------------------------------------------------------------


def _get_fact_store(request: Request) -> FactStore:
    """Retrieve or instantiate the FactStore."""
    # 1. From PersistentTaskRunner if present
    task_runner = getattr(request.app.state, "task_runner", None)
    if task_runner is not None and getattr(task_runner, "memory_store", None) is not None:
        return task_runner.memory_store

    # 2. From MemoryService if present
    mem_svc = getattr(request.app.state, "memory_service", None)
    if mem_svc is not None and hasattr(mem_svc, "_store") and mem_svc._store is not None:
        return mem_svc._store

    # 3. Direct app state cache
    store = getattr(request.app.state, "fact_store", None)
    if store is not None:
        return store

    # 4. Fallback singleton
    store = create_fact_store()
    request.app.state.fact_store = store
    return store


def _get_maintenance_manager(request: Request) -> MemoryMaintenanceManager:
    """Retrieve or instantiate MemoryMaintenanceManager."""
    mgr = getattr(request.app.state, "memory_maintenance_manager", None)
    if mgr is not None:
        return mgr
    store = _get_fact_store(request)
    mgr = MemoryMaintenanceManager(fact_store=store)
    request.app.state.memory_maintenance_manager = mgr
    return mgr


def _get_skill_learner(request: Request) -> WorkflowSkillLearner:
    """Retrieve or instantiate the WorkflowSkillLearner."""
    # 1. From PersistentTaskRunner if present
    task_runner = getattr(request.app.state, "task_runner", None)
    if task_runner is not None and getattr(task_runner, "workflow_skill_learner", None) is not None:
        return task_runner.workflow_skill_learner

    # 2. Direct app state cache
    learner = getattr(request.app.state, "workflow_skill_learner", None)
    if learner is not None:
        return learner

    # 3. Fallback with SkillManager
    mgr = getattr(request.app.state, "skill_manager", None)
    if mgr is None:
        bus = getattr(request.app.state, "bus", None) or EventBus()
        cap_policy = getattr(request.app.state, "capability_policy", None)
        mgr = SkillManager(bus=bus, capability_policy=cap_policy)
        request.app.state.skill_manager = mgr

    learner = WorkflowSkillLearner(
        skill_manager=mgr,
        ledger=getattr(mgr, "ledger", None) if hasattr(mgr, "ledger") else None,
    )
    request.app.state.workflow_skill_learner = learner
    return learner


def _get_current_user_and_role(request: Request) -> Tuple[Optional[str], str]:
    """Extract authenticated user id and role from request."""
    user = getattr(request.state, "user", None)
    multi_user = getattr(request.app.state, "multi_user", False)
    if not multi_user:
        return "admin", "admin"
    if user is not None:
        user_id = getattr(user, "id", None) or getattr(user, "username", None)
        role = getattr(user, "role", "user")
        return user_id, role
    return None, "anonymous"


def _check_admin_authorization(request: Request, action: str = "administrative_action") -> None:
    """Ensure user is authorized for administrative memory or skills mutation."""
    user_id, role = _get_current_user_and_role(request)
    multi_user = getattr(request.app.state, "multi_user", False)
    if not multi_user:
        return
    if not user_id or role == "anonymous":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    if role == "admin":
        return

    # In multi-user mode, non-admin role must be explicitly granted SYSTEM_ADMIN capability
    cap_policy: Optional[CapabilityPolicy] = getattr(request.app.state, "capability_policy", None)
    is_granted = False
    if cap_policy is not None and user_id:
        policy = getattr(cap_policy, "_policies", {}).get(user_id)
        if policy and any(g.capability in (Capability.SYSTEM_ADMIN.value, "*") for g in getattr(policy, "grants", [])):
            is_granted = True

    if not is_granted:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: '{action}' requires administrator privileges or '{Capability.SYSTEM_ADMIN.value}' capability.",
        )


def _check_memory_access(fact: Fact, request: Request, modifying: bool = False) -> None:
    """Ensure non-admin users can only view or modify memories within their project scope."""
    user_id, role = _get_current_user_and_role(request)
    multi_user = getattr(request.app.state, "multi_user", False)
    if not multi_user or role == "admin":
        return

    if not user_id:
        if modifying:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
        return

    # Check project ownership
    if fact.project != "default" and fact.project.lower() != user_id.lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: you do not have permission to access or modify this memory entry.",
        )


def _serialize_skill_manifest(
    manifest: SkillManifest,
    learner: WorkflowSkillLearner,
) -> Dict[str, Any]:
    """Serialize a SkillManifest with health, validation, and metadata."""
    is_approved = learner.is_skill_approved(manifest)
    is_healthy, health_issues = learner.validate_skill_health(manifest)
    is_valid, validation_errors = learner.validate_skill_for_approval(manifest)

    meta = dict(manifest.metadata or {})
    is_disabled = bool(meta.get("disabled", False))
    raw_status = meta.get("approval_status")
    if not raw_status:
        if is_approved:
            raw_status = SkillApprovalStatus.APPROVED
        elif "pending_review" in (manifest.tags or []):
            raw_status = SkillApprovalStatus.PENDING_REVIEW
        elif "rejected" in (manifest.tags or []):
            raw_status = SkillApprovalStatus.REJECTED
        else:
            raw_status = SkillApprovalStatus.APPROVED if is_approved else SkillApprovalStatus.PENDING_REVIEW

    is_protected = manifest.author.lower() in PROTECTED_AUTHORS or bool(
        set(manifest.tags or ()) & PROTECTED_SKILL_TAGS
    )

    return {
        "name": manifest.name,
        "version": manifest.version,
        "description": manifest.description,
        "author": manifest.author,
        "tags": list(manifest.tags or []),
        "required_capabilities": list(manifest.required_capabilities or []),
        "depends": list(manifest.depends or []),
        "user_invocable": manifest.user_invocable,
        "disable_model_invocation": manifest.disable_model_invocation,
        "approval_status": raw_status,
        "approved": is_approved,
        "disabled": is_disabled,
        "disabled_reason": meta.get("disabled_reason"),
        "is_protected": is_protected,
        "is_composite": bool(
            meta.get("composite", False)
            or any(s.skill_name for s in manifest.steps)
        ),
        "steps_count": len(manifest.steps),

        "steps": [
            {
                "tool_name": s.tool_name,
                "skill_name": s.skill_name,
                "arguments_template": s.arguments_template,
                "output_key": s.output_key,
                "condition": getattr(s, "condition", ""),
                "is_else": getattr(s, "is_else", False),
                "else_skill_name": getattr(s, "else_skill_name", ""),
                "else_tool_name": getattr(s, "else_tool_name", ""),
                "else_arguments_template": getattr(s, "else_arguments_template", "{}"),
                "else_output_key": getattr(s, "else_output_key", ""),
            }
            for s in manifest.steps
        ],
        "health": {
            "is_healthy": is_healthy,
            "issues": health_issues,
            "consecutive_failures": meta.get("consecutive_failures", 0),
            "execution_count": meta.get("execution_count", 0),
            "last_success_at": meta.get("last_success_at"),
            "last_failure_at": meta.get("last_failure_at"),
            "last_failure_reason": meta.get("last_failure_reason"),
            "outdated": bool(meta.get("outdated", False)),
            "outdated_reason": meta.get("outdated_reason"),
        },
        "validation": {
            "is_valid": is_valid,
            "errors": validation_errors,
        },
        "metadata": meta,
    }


# ===========================================================================
# 1. Memory Management Endpoints
# ===========================================================================


@memory_skills_router.get("/api/memory/facts", summary="List and search persistent memory facts")
def list_memory_facts(
    request: Request,
    q: Optional[str] = Query(None, description="Search term matching text or metadata"),
    category: Optional[str] = Query(None, description="Filter by memory category"),
    project: Optional[str] = Query(None, description="Filter by project scope"),
    trust: Optional[str] = Query(None, description="Filter by trust tier: 'trusted', 'auto', 'untrusted'"),
    verified: Optional[bool] = Query(None, description="Filter by verification state"),
    source_type: Optional[str] = Query(None, description="Filter by source type"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    """Retrieve saved memory facts with rich filtering, search, and provenance metrics."""
    store = _get_fact_store(request)
    all_facts = store.list()

    user_id, role = _get_current_user_and_role(request)
    multi_user = getattr(request.app.state, "multi_user", False)

    # Multi-user tenant isolation
    if multi_user and role != "admin" and user_id:
        all_facts = [
            f for f in all_facts
            if f.project == "default" or f.project.lower() == user_id.lower()
        ]

    # Calculate global overview stats across accessible facts
    total_count = len(all_facts)
    trusted_count = sum(1 for f in all_facts if (f.trust or "").strip().lower() == TRUST_TRUSTED)
    auto_count = sum(1 for f in all_facts if (f.trust or "").strip().lower() == TRUST_AUTO)
    untrusted_count = sum(1 for f in all_facts if (f.trust or "").strip().lower() == TRUST_UNTRUSTED)
    verified_count = sum(1 for f in all_facts if f.verified)
    unverified_count = total_count - verified_count
    available_projects = sorted(list({f.project for f in all_facts if f.project}))

    # Apply filters
    filtered = list(all_facts)

    if category and category != "*" and category != "all":
        cat_lower = category.strip().lower()
        filtered = [f for f in filtered if f.category.lower() == cat_lower]

    if project and project != "*" and project != "all":
        proj_lower = project.strip().lower()
        filtered = [f for f in filtered if f.project.lower() == proj_lower]

    if trust and trust != "*" and trust != "all":
        t_lower = trust.strip().lower()
        filtered = [f for f in filtered if (f.trust or "").strip().lower() == t_lower]

    if verified is not None:
        filtered = [f for f in filtered if f.verified == verified]

    if source_type and source_type != "*" and source_type != "all":
        st_lower = source_type.strip().lower()
        filtered = [f for f in filtered if f.resolved_source_type.lower() == st_lower]

    if q and q.strip():
        terms = [t.lower() for t in q.strip().split()]
        filtered = [
            f for f in filtered
            if any(
                t in f.text.lower()
                or t in f.id.lower()
                or t in f.source.lower()
                or t in f.category.lower()
                or t in f.project.lower()
                or t in str(f.metadata).lower()
                for t in terms
            )
        ]

    # Newest updated first
    filtered.sort(key=lambda x: x.updated_at or x.created_at, reverse=True)

    paginated = filtered[offset : offset + limit]

    return {
        "status": "ok",
        "memories": [f.to_dict() for f in paginated],
        "total": len(filtered),
        "offset": offset,
        "limit": limit,
        "categories": sorted(list(MEMORY_CATEGORIES)),
        "projects": available_projects,
        "stats": {
            "total_facts": total_count,
            "trusted_count": trusted_count,
            "auto_count": auto_count,
            "untrusted_count": untrusted_count,
            "verified_count": verified_count,
            "unverified_count": unverified_count,
        },
    }


@memory_skills_router.get("/api/memory/facts/{memory_id}", summary="Get specific memory entry")
def get_memory_fact(memory_id: str, request: Request) -> Dict[str, Any]:
    """Retrieve details for a single memory entry."""
    store = _get_fact_store(request)
    fact = store.get(memory_id)
    if fact is None:
        raise HTTPException(status_code=404, detail=f"Memory '{memory_id}' not found.")

    _check_memory_access(fact, request, modifying=False)
    return {"status": "ok", "memory": fact.to_dict()}


@memory_skills_router.post("/api/memory/facts", summary="Create new persistent memory entry")
def create_memory_fact(body: CreateMemoryRequest, request: Request) -> Dict[str, Any]:
    """Store a new memory fact with validation and secret scrubbing."""
    store = _get_fact_store(request)
    user_id, role = _get_current_user_and_role(request)
    multi_user = getattr(request.app.state, "multi_user", False)

    clean_text = scrub_sensitive_data(body.text).strip()
    if not clean_text:
        raise HTTPException(status_code=400, detail="Memory text cannot be empty.")

    target_category = body.category.strip().lower()
    if target_category not in MEMORY_CATEGORIES:
        target_category = "general"

    target_project = body.project.strip()
    if multi_user and role != "admin" and user_id:
        # Prevent non-admin from polluting other projects
        target_project = user_id

    target_trust = body.trust.strip().lower()
    if target_trust not in (TRUST_TRUSTED, TRUST_AUTO, TRUST_UNTRUSTED):
        target_trust = TRUST_TRUSTED

    clean_meta = scrub_metadata(body.metadata or {})
    if user_id:
        clean_meta["created_by"] = user_id

    success = store.add(
        text=clean_text,
        source=body.source,
        trust=target_trust,
        category=target_category,
        project=target_project,
        verified=body.verified,
        source_type=body.source_type or "",
        metadata=clean_meta,
    )

    if not success:
        # Check if duplicate exists
        query_res = store.query(project=target_project, category=target_category, query=clean_text, recallable_only=False)
        if query_res:
            return {"status": "duplicate", "memory": query_res[0].to_dict()}
        raise HTTPException(status_code=400, detail="Could not store memory entry.")

    # Find created fact
    created_facts = store.query(project=target_project, category=target_category, query=clean_text, recallable_only=False)
    created_fact = created_facts[0] if created_facts else None

    return {
        "status": "created",
        "memory": created_fact.to_dict() if created_fact else None,
    }


@memory_skills_router.put("/api/memory/facts/{memory_id}", summary="Update existing persistent memory entry")
def update_memory_fact(
    memory_id: str,
    body: UpdateMemoryRequest,
    request: Request,
) -> Dict[str, Any]:
    """Update a memory fact with validation, secret scrubbing, and trust verification."""
    store = _get_fact_store(request)
    fact = store.get(memory_id)
    if fact is None:
        raise HTTPException(status_code=404, detail=f"Memory '{memory_id}' not found.")

    _check_memory_access(fact, request, modifying=True)

    # Validations
    if body.category is not None:
        clean_cat = body.category.strip().lower()
        if clean_cat not in MEMORY_CATEGORIES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid category '{body.category}'. Allowed categories: {sorted(list(MEMORY_CATEGORIES))}",
            )

    if body.trust is not None:
        clean_trust = body.trust.strip().lower()
        if clean_trust not in (TRUST_TRUSTED, TRUST_AUTO, TRUST_UNTRUSTED):
            raise HTTPException(
                status_code=400,
                detail="Invalid trust level. Must be 'trusted', 'auto', or 'untrusted'.",
            )
        # Promoting quarantined memory to trusted requires administrator privileges
        if clean_trust == TRUST_TRUSTED and fact.trust == TRUST_UNTRUSTED:
            _check_admin_authorization(request, "promote_quarantined_memory")

    user_id, role = _get_current_user_and_role(request)
    update_meta = dict(body.metadata) if body.metadata is not None else None
    if update_meta is not None and user_id:
        update_meta["updated_by"] = user_id

    updated = store.update(
        memory_id=memory_id,
        text=body.text,
        category=body.category,
        project=body.project,
        trust=body.trust,
        verified=body.verified,
        source_type=body.source_type,
        metadata=update_meta,
    )

    if not updated:
        raise HTTPException(status_code=400, detail="Failed to update memory entry.")

    refreshed = store.get(memory_id)
    return {
        "status": "updated",
        "memory": refreshed.to_dict() if refreshed else None,
    }


@memory_skills_router.delete("/api/memory/facts/{memory_id}", summary="Delete persistent memory entry")
def delete_memory_fact(memory_id: str, request: Request) -> Dict[str, Any]:
    """Delete a persistent memory entry by ID."""
    store = _get_fact_store(request)
    fact = store.get(memory_id)
    if fact is None:
        raise HTTPException(status_code=404, detail=f"Memory '{memory_id}' not found.")

    _check_memory_access(fact, request, modifying=True)

    deleted = store.delete(memory_id)
    if not deleted:
        raise HTTPException(status_code=400, detail="Failed to delete memory entry.")

    return {"status": "deleted", "id": memory_id}


# ===========================================================================
# 2. Memory Maintenance & Consolidation Endpoints
# ===========================================================================


@memory_skills_router.post("/api/memory/maintenance/scan", summary="Run on-demand memory consolidation scan")
def scan_memory_maintenance(
    request: Request,
    project: Optional[str] = Query(None, description="Optional project scope to scan"),
) -> Dict[str, Any]:
    """Scan stored memories within project boundaries for duplicates, contradictions, and stale facts."""
    user_id, role = _get_current_user_and_role(request)
    multi_user = getattr(request.app.state, "multi_user", False)

    if multi_user and role != "admin" and user_id:
        project = user_id

    mgr = _get_maintenance_manager(request)
    suggestions = mgr.scan(project=project)

    if multi_user and role != "admin" and user_id:
        suggestions = [s for s in suggestions if s.project == user_id]

    return {
        "status": "success",
        "suggestions": [s.to_dict() for s in suggestions],
        "total": len(suggestions),
    }


@memory_skills_router.get("/api/memory/maintenance/suggestions", summary="List memory maintenance suggestions")
def list_memory_maintenance_suggestions(
    request: Request,
    project: Optional[str] = Query(None, description="Filter by project"),
    issue_type: Optional[str] = Query(None, description="Filter by issue type ('duplicate', 'contradiction', 'outdated')"),
    status: Optional[str] = Query(None, description="Filter by status ('pending', 'approved', 'dismissed')"),
) -> Dict[str, Any]:
    """Retrieve memory maintenance suggestions with optional filtering."""
    user_id, role = _get_current_user_and_role(request)
    multi_user = getattr(request.app.state, "multi_user", False)

    if multi_user and role != "admin" and user_id:
        project = user_id

    mgr = _get_maintenance_manager(request)
    suggestions = mgr.get_suggestions(project=project, issue_type=issue_type, status=status)

    if multi_user and role != "admin" and user_id:
        suggestions = [s for s in suggestions if s.project == user_id]

    return {
        "status": "success",
        "suggestions": [s.to_dict() for s in suggestions],
        "total": len(suggestions),
    }


@memory_skills_router.get("/api/memory/maintenance/suggestions/{suggestion_id}", summary="Get maintenance suggestion detail")
def get_memory_maintenance_suggestion(
    suggestion_id: str,
    request: Request,
) -> Dict[str, Any]:
    """Retrieve a single maintenance suggestion by ID."""
    mgr = _get_maintenance_manager(request)
    sug = mgr.get_suggestion(suggestion_id)
    if sug is None:
        raise HTTPException(status_code=404, detail=f"Suggestion '{suggestion_id}' not found.")

    user_id, role = _get_current_user_and_role(request)
    multi_user = getattr(request.app.state, "multi_user", False)
    if multi_user and role != "admin" and user_id and sug.project != user_id:
        raise HTTPException(status_code=403, detail="Access denied to suggestion in another project scope.")

    return {"status": "success", "suggestion": sug.to_dict()}


@memory_skills_router.post("/api/memory/maintenance/suggestions/{suggestion_id}/approve", summary="Approve and apply maintenance suggestion")
def approve_memory_maintenance_suggestion(
    suggestion_id: str,
    request: Request,
    body: Optional[ApproveMaintenanceRequest] = None,
) -> Dict[str, Any]:
    """Approve and execute a proposed maintenance resolution with human authorization."""
    _check_admin_authorization(request, "approve_memory_consolidation")
    user_id, role = _get_current_user_and_role(request)
    multi_user = getattr(request.app.state, "multi_user", False)

    mgr = _get_maintenance_manager(request)
    sug = mgr.get_suggestion(suggestion_id)
    if sug is None:
        raise HTTPException(status_code=404, detail=f"Suggestion '{suggestion_id}' not found.")

    if multi_user and role != "admin" and user_id and sug.project != user_id:
        raise HTTPException(status_code=403, detail="Access denied to suggestion in another project scope.")

    custom_text = body.custom_text if body else None
    target_trust = body.target_trust if body else None

    try:
        res = mgr.approve_suggestion(
            suggestion_id,
            custom_text=custom_text,
            target_trust=target_trust,
            user_id=user_id or "admin",
            user_role=role,
        )
        return res
    except PermissionError as p_err:
        raise HTTPException(status_code=400, detail=str(p_err))
    except ValueError as v_err:
        raise HTTPException(status_code=400, detail=str(v_err))
    except Exception as exc:
        logger.error("Failed to approve suggestion %s: %s", suggestion_id, exc)
        raise HTTPException(status_code=500, detail=f"Failed to execute maintenance action: {exc}")


@memory_skills_router.post("/api/memory/maintenance/suggestions/{suggestion_id}/dismiss", summary="Dismiss maintenance suggestion")
def dismiss_memory_maintenance_suggestion(
    suggestion_id: str,
    request: Request,
    body: Optional[DismissMaintenanceRequest] = None,
) -> Dict[str, Any]:
    """Dismiss a maintenance suggestion without altering any stored memories."""
    user_id, role = _get_current_user_and_role(request)
    multi_user = getattr(request.app.state, "multi_user", False)

    mgr = _get_maintenance_manager(request)
    sug = mgr.get_suggestion(suggestion_id)
    if sug is None:
        raise HTTPException(status_code=404, detail=f"Suggestion '{suggestion_id}' not found.")

    if multi_user and role != "admin" and user_id and sug.project != user_id:
        raise HTTPException(status_code=403, detail="Access denied to suggestion in another project scope.")

    reason = body.reason if body else "Dismissed by operator."
    try:
        res = mgr.dismiss_suggestion(
            suggestion_id,
            reason=reason,
            user_id=user_id or "admin",
        )
        return res
    except ValueError as v_err:
        raise HTTPException(status_code=400, detail=str(v_err))


# ===========================================================================
# 3. Learned Skills Management Endpoints
# ===========================================================================


@memory_skills_router.get("/api/skills/learned", summary="List learned skills and approval status")
def list_learned_skills(
    request: Request,
    status: Optional[str] = Query(None, description="Filter by approval status (all, pending_review, approved, rejected, disabled)"),
    q: Optional[str] = Query(None, description="Search term for skill name or description"),
) -> Dict[str, Any]:
    """List all registered and learned skills with validation, approval status, and health metrics."""
    learner = _get_skill_learner(request)
    all_skills = learner.list_skills()

    summaries = [_serialize_skill_manifest(s, learner) for s in all_skills]

    # Calculate global skill metrics
    total_skills = len(summaries)
    pending_count = sum(1 for s in summaries if s["approval_status"] == SkillApprovalStatus.PENDING_REVIEW)
    approved_count = sum(1 for s in summaries if s["approval_status"] == SkillApprovalStatus.APPROVED and not s["disabled"])
    disabled_count = sum(1 for s in summaries if s["disabled"])
    rejected_count = sum(1 for s in summaries if s["approval_status"] == SkillApprovalStatus.REJECTED)

    # Filter
    filtered = list(summaries)
    if status and status != "*" and status != "all":
        st_lower = status.strip().lower()
        if st_lower == "disabled":
            filtered = [s for s in filtered if s["disabled"]]
        else:
            filtered = [s for s in filtered if s["approval_status"].lower() == st_lower and not s["disabled"]]

    if q and q.strip():
        terms = [t.lower() for t in q.strip().split()]
        filtered = [
            s for s in filtered
            if any(t in s["name"].lower() or t in s["description"].lower() for t in terms)
        ]

    # Sort: pending_review first, then by name
    status_order = {SkillApprovalStatus.PENDING_REVIEW: 0, SkillApprovalStatus.APPROVED: 1, SkillApprovalStatus.REJECTED: 2}
    filtered.sort(key=lambda s: (status_order.get(s["approval_status"], 3), s["name"]))

    return {
        "status": "ok",
        "skills": filtered,
        "total": len(filtered),
        "stats": {
            "total_skills": total_skills,
            "pending_count": pending_count,
            "approved_count": approved_count,
            "disabled_count": disabled_count,
            "rejected_count": rejected_count,
        },
    }


@memory_skills_router.get("/api/skills/learned/{skill_name}", summary="Get detailed learned skill inspection")
def get_learned_skill_detail(skill_name: str, request: Request) -> Dict[str, Any]:
    """Retrieve full skill manifest, dependencies, validation checks, health history, and audit ledger."""
    learner = _get_skill_learner(request)
    if learner.skill_manager is None:
        raise HTTPException(status_code=500, detail="SkillManager not configured.")

    try:
        manifest = learner.skill_manager.resolve(skill_name)
    except KeyError:
        # Check if present on disk
        disk_skills = learner.list_skills()
        manifest = next((s for s in disk_skills if s.name == skill_name), None)
        if manifest is None:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found.")

    serialized = _serialize_skill_manifest(manifest, learner)

    # Audit history from ledger
    ledger_history = []
    if learner.ledger is not None:
        records = learner.ledger.get_history(skill_name=skill_name, limit=50)
        ledger_history = [r.to_dict() for r in records]

    serialized["audit_history"] = ledger_history
    return {"status": "ok", "skill": serialized}


@memory_skills_router.post("/api/skills/learned/{skill_name}/approve", summary="Approve pending learned skill")
def approve_learned_skill(skill_name: str, request: Request) -> Dict[str, Any]:
    """Approve a draft/pending_review learned skill after validating tools, schemas, and capabilities."""
    _check_admin_authorization(request, "approve_skill")

    learner = _get_skill_learner(request)
    user_id, _ = _get_current_user_and_role(request)
    approver_id = user_id or "admin"
    cap_policy: Optional[CapabilityPolicy] = getattr(request.app.state, "capability_policy", None)

    try:
        manifest = learner.approve_skill(
            skill_name=skill_name,
            approver_id=approver_id,
            capability_policy=cap_policy,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Skill '{skill_name}' not found.")

    return {
        "status": "approved",
        "skill": _serialize_skill_manifest(manifest, learner),
    }


@memory_skills_router.post("/api/skills/learned/{skill_name}/reject", summary="Reject pending learned skill")
def reject_learned_skill(
    skill_name: str,
    request: Request,
    body: Optional[RejectSkillRequest] = None,
) -> Dict[str, Any]:
    """Reject a draft/pending_review learned skill."""
    _check_admin_authorization(request, "reject_skill")

    learner = _get_skill_learner(request)
    user_id, _ = _get_current_user_and_role(request)
    reviewer_id = user_id or "admin"
    reject_reason = (body.reason if body else None) or "Rejected during security review."

    try:
        manifest = learner.reject_skill(
            skill_name=skill_name,
            reviewer_id=reviewer_id,
            reason=reject_reason,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Skill '{skill_name}' not found.")

    return {
        "status": "rejected",
        "skill": _serialize_skill_manifest(manifest, learner),
    }


@memory_skills_router.post("/api/skills/learned/{skill_name}/disable", summary="Disable approved learned skill")
def disable_learned_skill(
    skill_name: str,
    request: Request,
    body: Optional[DisableSkillRequest] = None,
) -> Dict[str, Any]:
    """Disable an active approved learned skill."""
    _check_admin_authorization(request, "disable_skill")

    learner = _get_skill_learner(request)
    user_id, _ = _get_current_user_and_role(request)
    operator_id = user_id or "admin"
    disable_reason = (body.reason if body else None) or "Disabled by operator."

    try:
        manifest = learner.disable_skill(
            skill_name=skill_name,
            operator_id=operator_id,
            reason=disable_reason,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Skill '{skill_name}' not found.")

    return {
        "status": "disabled",
        "skill": _serialize_skill_manifest(manifest, learner),
    }


@memory_skills_router.post("/api/skills/learned/{skill_name}/enable", summary="Re-enable disabled learned skill")
def enable_learned_skill(skill_name: str, request: Request) -> Dict[str, Any]:
    """Re-enable a previously disabled learned skill."""
    _check_admin_authorization(request, "enable_skill")

    learner = _get_skill_learner(request)
    user_id, _ = _get_current_user_and_role(request)
    operator_id = user_id or "admin"

    try:
        manifest = learner.enable_skill(
            skill_name=skill_name,
            operator_id=operator_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Skill '{skill_name}' not found.")

    return {
        "status": "enabled",
        "skill": _serialize_skill_manifest(manifest, learner),
    }


@memory_skills_router.post(
    "/api/skills/composite", summary="Create a new composite skill workflow"
)
def create_composite_skill(
    body: CreateCompositeSkillRequest, request: Request
) -> Dict[str, Any]:
    """Create, validate, and register a new composite skill combining existing skills."""
    _check_admin_authorization(request, "create_composite_skill")

    learner = _get_skill_learner(request)
    user_id, _ = _get_current_user_and_role(request)
    author_id = user_id or "operator"

    step_dicts = [s.model_dump() for s in body.steps]

    from openjarvis.skills.composition import (
        CompositionValidationError,
        DepthExceededError,
    )

    try:
        manifest = learner.compose_skills(
            name=body.name,
            steps=step_dicts,
            description=body.description or "",
            author=author_id,
            require_approval=body.require_approval,
            tags=body.tags or [],
        )
    except (CompositionValidationError, DepthExceededError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    return {
        "status": "created",
        "skill": _serialize_skill_manifest(manifest, learner),
    }


@memory_skills_router.post(
    "/api/skills/composite/validate",
    summary="Validate a candidate composite skill",
)
def validate_composite_skill_endpoint(
    body: CreateCompositeSkillRequest, request: Request
) -> Dict[str, Any]:
    """Validate dependencies, cycles, depth limits, and parameter flow for a candidate composite skill without saving."""
    learner = _get_skill_learner(request)
    from openjarvis.skills.composition import (
        CompositionValidationError,
        DepthExceededError,
        create_composite_manifest,
    )

    step_dicts = [s.model_dump() for s in body.steps]
    try:
        manifest = create_composite_manifest(
            name=body.name,
            steps=step_dicts,
            description=body.description or "",
            author="validator",
            skill_manager=learner.skill_manager,
            require_approval=body.require_approval,
            tags=body.tags or [],
        )
        return {
            "valid": True,
            "errors": [],
            "required_capabilities": manifest.required_capabilities,
            "dependencies": manifest.depends,
        }
    except (CompositionValidationError, DepthExceededError, ValueError) as exc:
        return {
            "valid": False,
            "errors": [str(exc)],
            "required_capabilities": [],
            "dependencies": [],
        }


__all__ = ["memory_skills_router"]

