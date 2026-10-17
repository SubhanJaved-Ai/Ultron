"""Safety routes for Ultron Safety Kernel, Risk Levels, Safety Code, and Custom Safety Rules."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from openjarvis.security.kernel import ActionEffect, CustomRule, get_safety_kernel

logger = logging.getLogger(__name__)

safety_router = APIRouter(prefix="/api/safety", tags=["safety"])


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------

class SetSafetyCodeRequest(BaseModel):
    code: str = Field(..., min_length=4, description="New safety code (min 4 characters)")
    old_code: Optional[str] = Field(None, description="Current safety code (required if updating)")


class VerifySafetyCodeRequest(BaseModel):
    code: str = Field(..., description="Safety code to verify")
    action_type: str = Field(..., description="Action type to authorize (e.g. file_delete, shell_exec)")
    target: str = Field(..., description="Action target (e.g. file path or command)")
    params: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Action parameters")


class CompileRuleRequest(BaseModel):
    instruction: str = Field(..., min_length=3, description="Plain language instruction")


class SaveRulesRequest(BaseModel):
    rules: List[Dict[str, Any]] = Field(..., description="Structured rules to save after preview approval")


class CleanupPreviewRequest(BaseModel):
    targets: List[str] = Field(..., description="List of target paths to preview for cleanup")


class ExecuteCleanupRequest(BaseModel):
    target: str = Field(..., description="Target path to safely delete or quarantine")
    token: str = Field(..., description="Single-use action authorization token")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@safety_router.get("/status")
async def get_safety_status() -> Dict[str, Any]:
    """Return Safety Kernel configuration status, rules, and token stats."""
    kernel = get_safety_kernel()
    rules = [r.to_dict() for r in kernel.rules_engine.list_rules()]
    return {
        "status": "active",
        "configured": kernel.code_mgr.is_code_set(),
        "rules_count": len(rules),
        "rules": rules,
        "active_tokens_count": len(kernel.code_mgr._tokens),
    }


@safety_router.post("/code/set")
async def set_safety_code(req: SetSafetyCodeRequest) -> Dict[str, Any]:
    """Configure or update the safety code with PBKDF2 hashing (zero plain-text leaks)."""
    kernel = get_safety_kernel()
    # Security note: Never log req.code or req.old_code
    success, msg = kernel.code_mgr.set_safety_code(req.code, old_code=req.old_code)
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return {"success": True, "message": msg}


@safety_router.post("/code/verify")
async def verify_safety_code(req: VerifySafetyCodeRequest) -> Dict[str, Any]:
    """Verify safety code and issue a single-use action token bound to exact action fingerprint."""
    kernel = get_safety_kernel()
    if not kernel.code_mgr.is_code_set():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Safety code is not configured. Please set a safety code first.",
        )

    # Security note: Never log req.code
    valid = kernel.code_mgr.verify_safety_code(req.code)
    if not valid:
        return {"valid": False, "message": "Incorrect safety code."}

    fingerprint = kernel.code_mgr.compute_fingerprint(req.action_type, req.target, req.params)
    token = kernel.code_mgr.generate_action_token(fingerprint, ttl_seconds=300.0)

    return {
        "valid": True,
        "token": token,
        "fingerprint": fingerprint,
        "expires_in": 300,
        "message": "Authorization token issued for single-use execution.",
    }


@safety_router.get("/rules")
async def list_custom_rules() -> Dict[str, Any]:
    """List all saved custom safety rules."""
    kernel = get_safety_kernel()
    return {"rules": [r.to_dict() for r in kernel.rules_engine.list_rules()]}


@safety_router.post("/rules/compile")
async def compile_custom_rules(req: CompileRuleRequest) -> Dict[str, Any]:
    """Compile plain-language instructions into structured rules and return a preview."""
    kernel = get_safety_kernel()
    compiled = kernel.rules_engine.compile_plain_language(req.instruction)
    return {
        "preview_rules": [r.to_dict() for r in compiled],
        "message": "Preview generated. User approval is required before saving.",
    }


@safety_router.post("/rules/save")
async def save_custom_rules(req: SaveRulesRequest) -> Dict[str, Any]:
    """Save user-approved custom safety rules."""
    kernel = get_safety_kernel()
    saved = []
    for r in req.rules:
        rule = CustomRule.from_dict(r)
        kernel.rules_engine.add_rule(rule)
        saved.append(rule.to_dict())
    return {"success": True, "saved_rules": saved, "count": len(saved)}


@safety_router.delete("/rules/{rule_id}")
async def delete_custom_rule(rule_id: str) -> Dict[str, Any]:
    """Remove a custom safety rule by ID."""
    kernel = get_safety_kernel()
    removed = kernel.rules_engine.remove_rule(rule_id)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Rule {rule_id} not found.")
    return {"success": True, "rule_id": rule_id}


@safety_router.post("/cleanup/preview")
async def preview_cleanup(req: CleanupPreviewRequest) -> Dict[str, Any]:
    """Preview cleanup impact showing exact targets, count, total bytes, and destination."""
    kernel = get_safety_kernel()
    preview = kernel.preview_cleanup(req.targets)
    return {"preview": preview}


@safety_router.post("/cleanup/execute")
async def execute_cleanup(req: ExecuteCleanupRequest) -> Dict[str, Any]:
    """Execute safe deletion (Recycle Bin / Quarantine) using verified single-use action token."""
    kernel = get_safety_kernel()
    target = req.target

    # Re-evaluate to get canonical fingerprint
    decision = kernel.evaluate("delete", target=target)
    if decision.effect == ActionEffect.BLOCK:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Safety Kernel Blocked: {decision.reason}",
        )

    # Invalidate / consume single-use token
    valid, token_msg = kernel.code_mgr.consume_action_token(req.token, decision.fingerprint)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Authorization Failed: {token_msg}",
        )

    # Perform safe deletion via Windows Recycle Bin or safe quarantine
    success, del_msg = kernel.safe_delete_or_quarantine(target)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=del_msg,
        )

    return {"success": True, "message": del_msg}
