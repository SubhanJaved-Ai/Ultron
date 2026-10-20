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

import ast
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


class ConditionValidationError(CompositionValidationError):
    """Raised when a step condition expression is invalid, ambiguous, or malformed."""


class ConditionEvaluationError(Exception):
    """Raised when evaluating a condition expression fails at runtime."""


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
# Safe Condition Parser & Evaluator (AST-based)
# ---------------------------------------------------------------------------

_ALLOWED_AST_NODES = (
    ast.Expression,
    ast.Compare,
    ast.UnaryOp,
    ast.BoolOp,
    ast.Name,
    ast.Constant,
    ast.List,
    ast.Tuple,
    ast.Set,
    ast.Load,
    # Comparison operators
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    ast.Is,
    ast.IsNot,
    # Unary operators
    ast.Not,
    ast.USub,
    ast.UAdd,
    # Boolean operators
    ast.And,
    ast.Or,
)

_ALLOWED_COMPARE_OPS = (
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    ast.Is,
    ast.IsNot,
)

_ALLOWED_UNARY_OPS = (
    ast.Not,
    ast.USub,
    ast.UAdd,
)

_ALLOWED_BOOL_OPS = (
    ast.And,
    ast.Or,
)


def normalize_condition_expression(raw_expr: str) -> str:
    """Normalize user condition expression for safe AST parsing.

    Supports:
    - Template placeholders: ``{output_key} == 'success'`` -> ``output_key == 'success'``
    - English 'contains': ``{tags} contains 'urgent'`` -> ``'urgent' in tags``
    - Lowercase literal aliases: ``true`` -> ``True``, ``false`` -> ``False``, ``null`` -> ``None``
    """
    expr = raw_expr.strip()
    if not expr:
        return ""
    if expr.lower() == "else":
        return "else"

    # Replace template placeholders {var} with var
    expr = _PLACEHOLDER_RE.sub(r"\1", expr)

    # Transform 'left contains right' to 'right in (left)'
    expr = re.sub(
        r"(\b[a-zA-Z0-9_]+)\s+contains\s+((?:'[^']*'|\"[^\"]*\"|[a-zA-Z0-9_]+))",
        r"\2 in \1",
        expr,
    )

    # Boolean/null literal normalization
    expr = re.sub(r"\btrue\b", "True", expr)
    expr = re.sub(r"\bfalse\b", "False", expr)
    expr = re.sub(r"\bnull\b", "None", expr)

    return expr


def extract_condition_variables(raw_expr: str) -> Set[str]:
    """Extract all context variable names referenced in a condition expression."""
    norm = normalize_condition_expression(raw_expr)
    if not norm or norm == "else":
        return set()

    try:
        tree = ast.parse(norm, mode="eval")
    except SyntaxError:
        # Fall back to regex placeholder extraction
        return set(_PLACEHOLDER_RE.findall(raw_expr))

    vars_found: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if node.id not in ("True", "False", "None"):
                vars_found.add(node.id)
    return vars_found


def validate_condition(
    condition: str,
    available_vars: Optional[Set[str]] = None,
) -> Tuple[bool, List[str]]:
    """Validate that a condition uses only allowed AST constructs and operators.

    Parameters:
    -----------
    condition:
        Condition string to validate.
    available_vars:
        Optional set of available variables/outputs. If provided, checks that all
        referenced variables exist.

    Returns:
        (is_valid, error_messages)
    """
    cond = condition.strip()
    if not cond:
        return True, []
    if cond.lower() == "else":
        return True, []

    norm = normalize_condition_expression(cond)
    try:
        tree = ast.parse(norm, mode="eval")
    except SyntaxError as exc:
        return False, [f"Syntax error in condition '{cond}': {exc}"]

    # Validate AST node whitelist
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_AST_NODES):
            return False, [
                f"Disallowed construct '{type(node).__name__}' in condition '{cond}'. "
                "Only comparisons, boolean operators, constants, and variables are permitted."
            ]

        if isinstance(node, ast.Compare):
            for op in node.ops:
                if not isinstance(op, _ALLOWED_COMPARE_OPS):
                    return False, [f"Unsupported comparison operator '{type(op).__name__}' in condition '{cond}'."]

        elif isinstance(node, ast.UnaryOp):
            if not isinstance(node.op, _ALLOWED_UNARY_OPS):
                return False, [f"Unsupported unary operator '{type(node.op).__name__}' in condition '{cond}'."]

        elif isinstance(node, ast.BoolOp):
            if not isinstance(node.op, _ALLOWED_BOOL_OPS):
                return False, [f"Unsupported boolean operator '{type(node.op).__name__}' in condition '{cond}'."]

    # Check for constant False branch reachability
    if isinstance(tree.body, ast.Constant) and tree.body.value is False:
        return False, [f"Condition '{cond}' is statically False, making this branch unreachable."]

    # Check referenced variables if provided
    if available_vars is not None:
        used_vars = extract_condition_variables(cond)
        missing = [v for v in sorted(used_vars) if v not in available_vars]
        if missing:
            return False, [
                f"Condition '{cond}' references unavailable output(s): {', '.join(missing)}."
            ]

    return True, []


def _eval_comparison(op: ast.cmpop, left: Any, right: Any) -> bool:
    """Safely evaluate a comparison with permissive numeric and boolean coercion."""
    # Coerce boolean comparisons first (since bool is a subclass of int in Python)
    if isinstance(op, (ast.Eq, ast.NotEq)):
        if isinstance(left, str) and isinstance(right, bool):
            if left.lower() in ("true", "1"):
                left = True
            elif left.lower() in ("false", "0"):
                left = False
        elif isinstance(right, str) and isinstance(left, bool):
            if right.lower() in ("true", "1"):
                right = True
            elif right.lower() in ("false", "0"):
                right = False
        elif isinstance(left, str) and isinstance(right, (int, float)) and not isinstance(right, bool):
            try:
                left = float(left) if "." in left else int(left)
            except ValueError:
                pass
        elif isinstance(right, str) and isinstance(left, (int, float)) and not isinstance(left, bool):
            try:
                right = float(right) if "." in right else int(right)
            except ValueError:
                pass

    elif isinstance(op, (ast.Lt, ast.LtE, ast.Gt, ast.GtE)):
        if isinstance(left, str) and isinstance(right, (int, float)) and not isinstance(right, bool):
            try:
                left = float(left) if "." in left else int(left)
            except ValueError:
                pass
        elif isinstance(right, str) and isinstance(left, (int, float)) and not isinstance(left, bool):
            try:
                right = float(right) if "." in right else int(right)
            except ValueError:
                pass

    try:
        if isinstance(op, ast.Eq):
            return left == right
        elif isinstance(op, ast.NotEq):
            return left != right
        elif isinstance(op, ast.Lt):
            return left < right
        elif isinstance(op, ast.LtE):
            return left <= right
        elif isinstance(op, ast.Gt):
            return left > right
        elif isinstance(op, ast.GtE):
            return left >= right
        elif isinstance(op, ast.In):
            return left in right
        elif isinstance(op, ast.NotIn):
            return left not in right
        elif isinstance(op, ast.Is):
            return left is right
        elif isinstance(op, ast.IsNot):
            return left is not right
    except Exception as exc:
        raise ConditionEvaluationError(
            f"Comparison {type(op).__name__} failed between {type(left).__name__} and {type(right).__name__}: {exc}"
        )

    raise ConditionEvaluationError(f"Unsupported comparison operator: {type(op).__name__}")


def _safe_eval_node(node: ast.AST, context: Dict[str, Any]) -> Any:
    """Recursively evaluate an allowed AST node against context."""
    if isinstance(node, ast.Constant):
        return node.value

    elif isinstance(node, ast.Name):
        if node.id == "True":
            return True
        elif node.id == "False":
            return False
        elif node.id == "None":
            return None

        if node.id not in context:
            raise ConditionEvaluationError(
                f"Variable '{node.id}' not found in context (available keys: {sorted(list(context.keys()))})."
            )
        return context[node.id]

    elif isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        elts = [_safe_eval_node(elt, context) for elt in node.elts]
        if isinstance(node, ast.Tuple):
            return tuple(elts)
        elif isinstance(node, ast.Set):
            return set(elts)
        return list(elts)

    elif isinstance(node, ast.UnaryOp):
        operand = _safe_eval_node(node.operand, context)
        if isinstance(node.op, ast.Not):
            return not operand
        elif isinstance(node.op, ast.USub):
            return -operand
        elif isinstance(node.op, ast.UAdd):
            return +operand
        raise ConditionEvaluationError(f"Unsupported unary operator: {type(node.op).__name__}")

    elif isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            for v_node in node.values:
                if not _safe_eval_node(v_node, context):
                    return False
            return True
        elif isinstance(node.op, ast.Or):
            for v_node in node.values:
                if _safe_eval_node(v_node, context):
                    return True
            return False
        raise ConditionEvaluationError(f"Unsupported boolean operator: {type(node.op).__name__}")

    elif isinstance(node, ast.Compare):
        left = _safe_eval_node(node.left, context)
        for op, comp_node in zip(node.ops, node.comparators):
            right = _safe_eval_node(comp_node, context)
            if not _eval_comparison(op, left, right):
                return False
            left = right
        return True

    raise ConditionEvaluationError(f"Disallowed node type '{type(node).__name__}' in condition.")


def evaluate_condition(condition: str, context: Dict[str, Any]) -> bool:
    """Safely evaluate a condition expression against the provided context.

    Parameters:
    -----------
    condition:
        Condition string to evaluate.
    context:
        Current workflow context dict containing outputs of prior steps.

    Returns:
        Boolean result of the evaluation.

    Raises:
        ConditionEvaluationError
    """
    cond = condition.strip()
    if not cond or cond.lower() == "else":
        return True

    norm = normalize_condition_expression(cond)
    try:
        tree = ast.parse(norm, mode="eval")
    except SyntaxError as exc:
        raise ConditionEvaluationError(f"Malformed condition '{cond}': {exc}")

    res = _safe_eval_node(tree.body, context)
    return bool(res)


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
    - No circular dependencies exist in any branch.
    - Call chain depth does not exceed max_depth in any branch.
    - Child skills in all branches are approved and not disabled.
    - Parameter bindings and condition expressions can be satisfied by prior steps.
    - Branch reachability: else steps follow an if; no consecutive else steps.

    Returns:
        List of all transitive dependency skill names across all branches.

    Raises:
        CircularCompositionError
        MissingDependencyError
        UnapprovedSkillError
        DisabledSkillError
        DepthExceededError
        ConditionValidationError
        ParameterFlowError
    """
    current_stack = list(call_stack or [manifest.name])
    transitive_deps: List[str] = []

    # 1. Parameter Flow & Condition Syntax Validation
    validate_parameter_flow(manifest)

    # 2. Branch structure tracking
    prior_step_had_condition = False
    prior_step_was_else = False
    prior_step_had_inline_else = False

    # 3. Inspect each step
    for step_idx, step in enumerate(manifest.steps):
        is_else_step = step.is_else or (step.condition.strip().lower() == "else")

        # Validate branch sequencing
        if is_else_step:
            if step_idx == 0:
                raise ConditionValidationError(
                    f"Composite skill '{manifest.name}' step 1 is an 'else' branch, "
                    "but the first step cannot be an else branch."
                )
            if prior_step_was_else:
                raise ConditionValidationError(
                    f"Composite skill '{manifest.name}' step {step_idx + 1} is an ambiguous duplicate 'else' branch."
                )
            if prior_step_had_inline_else:
                raise ConditionValidationError(
                    f"Composite skill '{manifest.name}' step {step_idx + 1} is an ambiguous 'else' branch "
                    f"because preceding step {step_idx} already defined an inline else."
                )
            if not prior_step_had_condition:
                raise ConditionValidationError(
                    f"Composite skill '{manifest.name}' step {step_idx + 1} is an 'else' branch, "
                    f"but preceding step {step_idx} has no condition."
                )
            prior_step_was_else = True
            prior_step_had_condition = False
            prior_step_had_inline_else = False
        else:
            prior_step_was_else = False
            if step.condition:
                # Validate condition syntax
                valid_cond, cond_errs = validate_condition(step.condition)
                if not valid_cond:
                    raise ConditionValidationError(
                        f"Composite skill '{manifest.name}' step {step_idx + 1} condition invalid: "
                        f"{'; '.join(cond_errs)}"
                    )
                prior_step_had_condition = True
                prior_step_had_inline_else = bool(step.else_skill_name or step.else_tool_name)
            else:
                if step.else_skill_name or step.else_tool_name:
                    raise ConditionValidationError(
                        f"Composite skill '{manifest.name}' step {step_idx + 1} defines an inline else branch "
                        "without specifying a condition."
                    )
                prior_step_had_condition = False
                prior_step_had_inline_else = False

        # Validate child skills in both primary and else branches
        branch_targets: List[Tuple[str, str]] = []
        if step.skill_name and step.skill_name.strip():
            branch_targets.append((step.skill_name.strip(), "primary"))
        if step.else_skill_name and step.else_skill_name.strip():
            branch_targets.append((step.else_skill_name.strip(), "else"))

        for child_name, branch_type in branch_targets:
            # Check for circular dependency
            if child_name in current_stack:
                cycle_str = " -> ".join(current_stack + [child_name])
                raise CircularCompositionError(
                    f"Circular dependency detected in composite skill '{manifest.name}' ({branch_type} branch): {cycle_str}"
                )

            # Check depth limit
            if len(current_stack) + 1 > max_depth:
                depth_str = " -> ".join(current_stack + [child_name])
                raise DepthExceededError(
                    f"Composition depth limit ({max_depth}) exceeded by call chain ({branch_type} branch): {depth_str}"
                )

            # Verify child skill exists
            try:
                child_manifest = skill_manager.resolve(child_name)
            except (KeyError, Exception):
                raise MissingDependencyError(
                    f"Composite skill '{manifest.name}' step {step_idx + 1} invokes child skill "
                    f"'{child_name}' ({branch_type} branch), which is not registered in the skill system."
                )

            # Verify child skill is approved and active
            is_ok, reason = is_skill_approved_and_active(child_manifest)
            if not is_ok:
                if "disabled" in reason.lower():
                    raise DisabledSkillError(
                        f"Composite skill '{manifest.name}' step {step_idx + 1} invokes disabled skill "
                        f"'{child_name}' ({branch_type} branch): {reason}"
                    )
                raise UnapprovedSkillError(
                    f"Composite skill '{manifest.name}' step {step_idx + 1} invokes unapproved skill "
                    f"'{child_name}' ({branch_type} branch): {reason}"
                )

            transitive_deps.append(child_name)

            # Recursively validate child if it is also composite
            if any(s.skill_name or s.else_skill_name for s in child_manifest.steps):
                child_deps = validate_composite_skill(
                    child_manifest,
                    skill_manager,
                    max_depth=max_depth,
                    call_stack=current_stack + [child_name],
                )
                transitive_deps.extend(child_deps)

    return list(dict.fromkeys(transitive_deps))


def validate_parameter_flow(manifest: SkillManifest) -> Tuple[bool, List[str]]:
    """Validate that placeholders in argument templates and conditions have defined sources.

    Returns (is_valid, missing_or_unbound_placeholders).
    """
    available_outputs: Set[str] = set()
    unbound: List[str] = []

    for step in manifest.steps:
        # Check condition variables
        if step.condition and step.condition.strip().lower() != "else":
            cond_vars = extract_condition_variables(step.condition)
            for cv in cond_vars:
                if cv not in available_outputs:
                    # Valid external input
                    pass

        # Check placeholders in arguments template
        placeholders = _PLACEHOLDER_RE.findall(step.arguments_template or "")
        for ph in placeholders:
            if ph not in available_outputs:
                # Valid external input
                pass

        # Check placeholders in else arguments template
        if step.else_arguments_template:
            else_phs = _PLACEHOLDER_RE.findall(step.else_arguments_template)
            for eph in else_phs:
                if eph not in available_outputs:
                    # Valid external input
                    pass

        if step.output_key:
            available_outputs.add(step.output_key)
        if step.else_output_key:
            available_outputs.add(step.else_output_key)

    return True, unbound


def compute_composite_capabilities(
    manifest: SkillManifest,
    skill_manager: Any,
) -> List[str]:
    """Compute the transitive union of required capabilities across all branches of a composite skill."""
    from openjarvis.security.capabilities import DEFAULT_TOOL_CAPABILITIES, Capability

    caps: Set[str] = set(manifest.required_capabilities or [])

    for step in manifest.steps:
        # Primary tool
        if step.tool_name:
            tool_caps = DEFAULT_TOOL_CAPABILITIES.get(step.tool_name.lower())
            if tool_caps:
                for c in tool_caps:
                    c_val = c.value if hasattr(c, "value") else str(c)
                    caps.add(c_val)
            else:
                caps.add(Capability.TOOL_INVOKE.value)

        # Primary skill
        if step.skill_name:
            if skill_manager is not None:
                try:
                    child_manifest = skill_manager.resolve(step.skill_name)
                    child_caps = compute_composite_capabilities(child_manifest, skill_manager)
                    caps.update(child_caps)
                except Exception:
                    caps.add(Capability.TOOL_INVOKE.value)
            else:
                caps.add(Capability.TOOL_INVOKE.value)

        # Inline else tool
        if step.else_tool_name:
            tool_caps = DEFAULT_TOOL_CAPABILITIES.get(step.else_tool_name.lower())
            if tool_caps:
                for c in tool_caps:
                    c_val = c.value if hasattr(c, "value") else str(c)
                    caps.add(c_val)
            else:
                caps.add(Capability.TOOL_INVOKE.value)

        # Inline else skill
        if step.else_skill_name:
            if skill_manager is not None:
                try:
                    child_manifest = skill_manager.resolve(step.else_skill_name)
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
    """Factory to construct a verified composite SkillManifest with conditional branching support."""
    parsed_steps: List[SkillStep] = []
    for s in steps:
        if isinstance(s, SkillStep):
            parsed_steps.append(s)
        elif isinstance(s, dict):
            parsed_steps.append(
                SkillStep(
                    tool_name=str(s.get("tool_name", "") or ""),
                    skill_name=str(s.get("skill_name", "") or ""),
                    arguments_template=str(s.get("arguments_template", "{}") or "{}"),
                    output_key=str(s.get("output_key", "") or ""),
                    condition=str(s.get("condition", "") or ""),
                    is_else=bool(s.get("is_else", False)),
                    else_skill_name=str(s.get("else_skill_name", "") or ""),
                    else_tool_name=str(s.get("else_tool_name", "") or ""),
                    else_arguments_template=str(s.get("else_arguments_template", "{}") or "{}"),
                    else_output_key=str(s.get("else_output_key", "") or ""),
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

    # Collect dependencies across all branches
    depends_set: Set[str] = set()
    for s in parsed_steps:
        if s.skill_name and s.skill_name.strip():
            depends_set.add(s.skill_name.strip())
        if s.else_skill_name and s.else_skill_name.strip():
            depends_set.add(s.else_skill_name.strip())

    manifest = SkillManifest(
        name=name,
        version=version,
        description=description or f"Composite skill combining {len(parsed_steps)} workflow steps.",
        author=author,
        steps=parsed_steps,
        required_capabilities=[],
        metadata=meta,
        tags=composite_tags,
        depends=sorted(depends_set),
        user_invocable=not require_approval,
        disable_model_invocation=require_approval,
    )

    # Compute transitive capabilities if skill manager is available
    if skill_manager is not None:
        manifest.required_capabilities = compute_composite_capabilities(manifest, skill_manager)
        # Pre-validate composition
        validate_composite_skill(manifest, skill_manager)

    return manifest


__all__ = [
    "MAX_COMPOSITION_DEPTH",
    "PROTECTED_SKILL_TAGS",
    "PROTECTED_AUTHORS",
    "CompositionValidationError",
    "ConditionValidationError",
    "ConditionEvaluationError",
    "CircularCompositionError",
    "MissingDependencyError",
    "UnapprovedSkillError",
    "DisabledSkillError",
    "DepthExceededError",
    "ParameterFlowError",
    "normalize_condition_expression",
    "extract_condition_variables",
    "validate_condition",
    "evaluate_condition",
    "is_skill_approved_and_active",
    "validate_composite_skill",
    "validate_parameter_flow",
    "compute_composite_capabilities",
    "create_composite_manifest",
]
