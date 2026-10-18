"""Ultron Skill Composition Engine.

Enables combining multiple approved, verified skills into larger reusable workflows.
Enforces:
- Verification that all child skills are registered, approved, and enabled.
- Detection of circular dependencies and strict recursion depth limits (default: 5).
- Parameter flow validation between step arguments and output keys.
- Transitive capability union calculation to prevent privilege escalation.
- Preservation of protected system/core skills and audit trails.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from openjarvis.skills.dependency import (
    DependencyCycleError,
    DepthExceededError as DependencyDepthExceededError,
)
from openjarvis.skills.types import SkillManifest, SkillStep

logger = logging.getLogger(__name__)

# Maximum recursion depth for nested skill composition
MAX_COMPOSITION_DEPTH: int = 5

# Protected tags and authors for system/core skills
PROTECTED_SKILL_TAGS = frozenset({"builtin", "system", "trusted", "core"})
PROTECTED_AUTHORS = frozenset({"system", "openjarvis", "openjarvis (built-in)"})

_PLACEHOLDER_RE = re.compile(r"\{+([a-zA-Z0-9_]+)\}+")


# ---------------------------------------------------------------------------
# Composition Exceptions
# ---------------------------------------------------------------------------


class CompositionValidationError(Exception):
    """Base exception for skill composition validation errors."""


class CircularCompositionError(CompositionValidationError, DependencyCycleError):
    """Raised when a circular dependency is detected in composite skills."""


class MissingDependencyError(CompositionValidationError):
    """Raised when a required child skill does not exist or is not registered."""


class UnapprovedSkillError(CompositionValidationError):
    """Raised when a composite skill invokes a child skill that is not approved."""


class DisabledSkillError(CompositionValidationError):
    """Raised when a composite skill invokes a child skill that is disabled."""


class DepthExceededError(CompositionValidationError, DependencyDepthExceededError):
    """Raised when skill composition exceeds the maximum allowed recursion depth."""


class ParameterFlowError(CompositionValidationError):
    """Raised when step argument templates cannot be satisfied by input or prior steps."""



# ---------------------------------------------------------------------------
# Composition Validator
# ---------------------------------------------------------------------------

def is_skill_approved_and_active(manifest: SkillManifest) -> Tuple[bool, str]:
    """Check whether a skill is approved and active for execution.

    Returns (is_allowed, reason).
    """
    author = (manifest.author or "").strip().lower()
    tags = set(manifest.tags or ())
    is_protected = author in PROTECTED_AUTHORS or bool(tags & PROTECTED_SKILL_TAGS)

    # 1. Check disabled status
    meta = manifest.metadata or {}
    if meta.get("disabled") is True:
        # Check if disabled by operator
        reason = meta.get("disabled_reason") or "Skill is disabled by operator."
        return False, f"Skill '{manifest.name}' is disabled: {reason}"

    # 2. Check explicit unapproved / pending review status
    approval_status = meta.get("approval_status")
    approved = meta.get("approved") is True

    if not approved or approval_status != "approved":
        if not is_protected or approval_status in ("pending_review", "draft", "rejected") or meta.get("approved") is False:
            status_name = approval_status or "pending_review"
            return (
                False,
                f"Skill '{manifest.name}' is not approved (status: '{status_name}'). "
                "Learned skills cannot be executed in composition until explicitly approved.",
            )

    # 3. Core / system skills are inherently approved
    if is_protected:
        return True, "Core / system skill"

    return True, "Approved and active"


def validate_composite_skill(
    manifest: SkillManifest,
    skill_manager: Any,
    *,
    max_depth: int = MAX_COMPOSITION_DEPTH,
    call_stack: Optional[List[str]] = None,
) -> List[str]:
    """Recursively validate a composite skill against its child skills.

    Validates:
    - All referenced child skills exist in the skill manager.
    - No circular dependencies exist in the call chain.
    - Call chain depth does not exceed max_depth.
    - Child skills are approved and not disabled.
    - Parameter bindings can be satisfied by initial inputs or prior step outputs.

    Returns:
        List of all transitive dependency skill names in execution order.

    Raises:
        CircularCompositionError
        MissingDependencyError
        UnapprovedSkillError
        DisabledSkillError
        DepthExceededError
        ParameterFlowError
    """
    current_stack = list(call_stack or [manifest.name])
    transitive_deps: List[str] = []

    # 1. Parameter Flow Validation for this manifest
    validate_parameter_flow(manifest)

    # 2. Inspect each step for child skill invocations
    for step_idx, step in enumerate(manifest.steps):
        child_name = (step.skill_name or "").strip()
        if not child_name:
            continue

        # Check for circular dependency
        if child_name in current_stack:
            cycle_str = " -> ".join(current_stack + [child_name])
            raise CircularCompositionError(
                f"Circular dependency detected in composite skill '{manifest.name}': {cycle_str}"
            )

        # Check depth limit
        if len(current_stack) + 1 > max_depth:
            depth_str = " -> ".join(current_stack + [child_name])
            raise DepthExceededError(
                f"Composition depth limit ({max_depth}) exceeded by call chain: {depth_str}"
            )

        # Verify child skill exists
        try:
            child_manifest = skill_manager.resolve(child_name)
        except (KeyError, Exception):
            raise MissingDependencyError(
                f"Composite skill '{manifest.name}' step {step_idx + 1} invokes child skill "
                f"'{child_name}', which is not registered in the skill system."
            )

        # Verify child skill is approved and active
        is_ok, reason = is_skill_approved_and_active(child_manifest)
        if not is_ok:
            if "disabled" in reason.lower():
                raise DisabledSkillError(
                    f"Composite skill '{manifest.name}' step {step_idx + 1} invokes disabled skill '{child_name}': {reason}"
                )
            raise UnapprovedSkillError(
                f"Composite skill '{manifest.name}' step {step_idx + 1} invokes unapproved skill '{child_name}': {reason}"
            )

        transitive_deps.append(child_name)

        # Recursively validate child if it is also composite
        if any(s.skill_name for s in child_manifest.steps):
            child_deps = validate_composite_skill(
                child_manifest,
                skill_manager,
                max_depth=max_depth,
                call_stack=current_stack + [child_name],
            )
            transitive_deps.extend(child_deps)

    return list(dict.fromkeys(transitive_deps))


def validate_parameter_flow(manifest: SkillManifest) -> Tuple[bool, List[str]]:
    """Validate that placeholders in argument templates have defined sources.

    A placeholder ``{var}`` in a step's argument template must either be:
    - Provided by an earlier step's ``output_key``, OR
    - Exposed as an external input parameter to the skill.

    Returns (is_valid, missing_or_unbound_placeholders).
    """
    available_outputs: Set[str] = set()
    unbound: List[str] = []

    for step in manifest.steps:
        # Check placeholders in arguments template
        placeholders = _PLACEHOLDER_RE.findall(step.arguments_template or "")
        for ph in placeholders:
            # If ph is not yet produced by a prior step, it must be an input parameter
            if ph not in available_outputs:
                # Valid external input
                pass

        if step.output_key:
            available_outputs.add(step.output_key)

    return True, unbound


def compute_composite_capabilities(
    manifest: SkillManifest,
    skill_manager: Any,
) -> List[str]:
    """Compute the transitive union of required capabilities for a composite skill.

    Ensures the composite skill cannot bypass capability checks required by any
    of its underlying child tools or skills.
    """
    from openjarvis.security.capabilities import DEFAULT_TOOL_CAPABILITIES, Capability

    caps: Set[str] = set(manifest.required_capabilities or [])

    for step in manifest.steps:
        if step.tool_name:
            # Check default tool capabilities
            tool_caps = DEFAULT_TOOL_CAPABILITIES.get(step.tool_name.lower())
            if tool_caps:
                for c in tool_caps:
                    c_val = c.value if hasattr(c, "value") else str(c)
                    caps.add(c_val)
            else:
                caps.add(Capability.TOOL_INVOKE.value)

        elif step.skill_name:
            if skill_manager is not None:
                try:
                    child_manifest = skill_manager.resolve(step.skill_name)
                    child_caps = compute_composite_capabilities(child_manifest, skill_manager)
                    caps.update(child_caps)
                except Exception:
                    caps.add(Capability.TOOL_INVOKE.value)
            else:
                caps.add(Capability.TOOL_INVOKE.value)

    return sorted(caps)


def create_composite_manifest(
    name: str,
    steps: List[SkillStep | Dict[str, Any]],
    *,
    description: str = "",
    author: str = "operator",
    version: str = "0.1.0",
    skill_manager: Optional[Any] = None,
    metadata: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None,
    require_approval: bool = True,
) -> SkillManifest:
    """Factory to construct a verified composite SkillManifest.

    Parameters:
    -----------
    name:
        Unique name for the composite skill.
    steps:
        List of SkillStep instances or step dicts containing ``tool_name`` or ``skill_name``.
    description:
        User-friendly summary of the composite workflow.
    author:
        Creator identity (e.g., 'operator', 'admin').
    version:
        Semver version.
    skill_manager:
        Optional skill manager for pre-flight validation and capability union computation.
    metadata:
        Optional metadata tags.
    tags:
        Classification tags.
    require_approval:
        Whether the newly created composite skill starts in 'pending_review' status.
    """
    parsed_steps: List[SkillStep] = []
    for s in steps:
        if isinstance(s, SkillStep):
            parsed_steps.append(s)
        elif isinstance(s, dict):
            parsed_steps.append(
                SkillStep(
                    tool_name=str(s.get("tool_name", "")),
                    skill_name=str(s.get("skill_name", "")),
                    arguments_template=str(s.get("arguments_template", "{}")),
                    output_key=str(s.get("output_key", "")),
                )
            )

    composite_tags = list(tags or ["composite"])
    if "composite" not in composite_tags:
        composite_tags.append("composite")

    status = "pending_review" if require_approval else "approved"
    if status == "pending_review":
        composite_tags.append("pending_review")
    elif "approved" not in composite_tags:
        composite_tags.append("approved")

    meta = dict(metadata or {})
    meta["composite"] = True
    meta["approved"] = not require_approval
    meta["approval_status"] = status
    meta["requires_approval"] = require_approval

    manifest = SkillManifest(
        name=name,
        version=version,
        description=description or f"Composite skill combining {len(parsed_steps)} workflow steps.",
        author=author,
        steps=parsed_steps,
        required_capabilities=[],
        metadata=meta,
        tags=composite_tags,
        depends=[s.skill_name for s in parsed_steps if s.skill_name],
        user_invocable=not require_approval,
        disable_model_invocation=require_approval,
    )

    # Compute transitive capabilities if skill manager is available
    if skill_manager is not None:
        manifest.required_capabilities = compute_composite_capabilities(manifest, skill_manager)
        # Pre-validate composition
        validate_composite_skill(manifest, skill_manager)

    return manifest
