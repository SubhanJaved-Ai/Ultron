"""SkillExecutor — runs skill steps sequentially through ToolExecutor."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

from openjarvis.core.events import EventBus, EventType
from openjarvis.core.types import ToolCall, ToolResult
from openjarvis.skills.security import validate_capabilities
from openjarvis.skills.types import SkillManifest
from openjarvis.tools._stubs import ToolExecutor


@dataclass(slots=True)
class SkillResult:
    skill_name: str = ""
    success: bool = True
    step_results: List[ToolResult] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)


# Resolver callback: given a skill name, the current context, and call stack, returns a SkillResult.
SkillResolver = Callable[..., SkillResult]


class SkillExecutor:
    """Execute a skill manifest step-by-step.

    Each step's arguments_template supports ``{key}`` placeholders
    that are resolved from the context dict (populated by prior step outputs).
    Supports recursive skill composition with cycle detection, depth limits,
    and capability enforcement.
    """

    def __init__(
        self,
        tool_executor: ToolExecutor,
        *,
        bus: Optional[EventBus] = None,
        allowed_capabilities: Optional[Set[str]] = None,
        skill_manager: Optional[Any] = None,
        max_depth: int = 5,
    ) -> None:
        self._tool_executor = tool_executor
        self._bus = bus
        self._skill_resolver: Optional[SkillResolver] = None
        self._allowed_capabilities: Optional[Set[str]] = allowed_capabilities
        self._skill_manager = skill_manager
        self._max_depth = max_depth

    def set_skill_resolver(self, resolver: SkillResolver) -> None:
        """Register a callback used to delegate ``skill_name`` steps."""
        self._skill_resolver = resolver

    def run(
        self,
        manifest: SkillManifest,
        *,
        initial_context: Optional[Dict[str, Any]] = None,
        call_stack: Optional[List[str]] = None,
    ) -> SkillResult:
        """Execute all steps in a skill manifest."""
        current_stack = list(call_stack or [manifest.name])

        # Cycle detection
        if call_stack and manifest.name in call_stack[:-1]:
            return SkillResult(
                skill_name=manifest.name,
                success=False,
                step_results=[
                    ToolResult(
                        tool_name=manifest.name,
                        content=f"Circular dependency detected in skill composition: {' -> '.join(call_stack)}",
                        success=False,
                    )
                ],
                context=dict(initial_context or {}),
            )

        # Depth check
        if len(current_stack) > self._max_depth:
            return SkillResult(
                skill_name=manifest.name,
                success=False,
                step_results=[
                    ToolResult(
                        tool_name=manifest.name,
                        content=f"Composition depth limit ({self._max_depth}) exceeded by call chain: {' -> '.join(current_stack)}",
                        success=False,
                    )
                ],
                context=dict(initial_context or {}),
            )

        missing = (
            validate_capabilities(manifest, self._allowed_capabilities)
            if self._allowed_capabilities is not None
            else []
        )
        if missing:
            if self._bus:
                self._bus.publish(
                    EventType.SKILL_EXECUTE_START,
                    {"skill": manifest.name, "steps": len(manifest.steps)},
                )
                self._bus.publish(
                    EventType.SKILL_EXECUTE_END,
                    {"skill": manifest.name, "success": False},
                )
            return SkillResult(
                skill_name=manifest.name,
                success=False,
                step_results=[
                    ToolResult(
                        tool_name=manifest.name,
                        content=(
                            f"Blocked: skill '{manifest.name}' requires "
                            f"capabilities {missing} that were not granted "
                            "for this session."
                        ),
                        success=False,
                    )
                ],
                context=dict(initial_context or {}),
            )

        ctx: Dict[str, Any] = dict(initial_context or {})
        all_results: List[ToolResult] = []

        if self._bus:
            self._bus.publish(
                EventType.SKILL_EXECUTE_START,
                {"skill": manifest.name, "steps": len(manifest.steps)},
            )

        last_condition_met: Optional[bool] = None

        for i, step in enumerate(manifest.steps):
            is_else_step = step.is_else or (step.condition.strip().lower() == "else")

            target_tool = step.tool_name
            target_skill = step.skill_name
            target_template = step.arguments_template
            target_output_key = step.output_key

            if is_else_step:
                # Executes if and only if the preceding conditional step did not match
                if last_condition_met is not False:
                    # Skipped
                    continue
                last_condition_met = None
            elif step.condition:
                try:
                    from openjarvis.skills.composition import evaluate_condition
                    cond_val = evaluate_condition(step.condition, ctx)
                except Exception as exc:
                    result = ToolResult(
                        tool_name=step.tool_name or step.skill_name or "condition",
                        content=f"Condition evaluation error in step {i + 1}: {exc}",
                        success=False,
                    )
                    all_results.append(result)
                    break

                last_condition_met = cond_val
                if cond_val:
                    # Primary branch selected
                    pass
                else:
                    # Condition is False
                    if step.else_skill_name or step.else_tool_name:
                        # Inline alternative branch selected
                        target_tool = step.else_tool_name
                        target_skill = step.else_skill_name
                        target_template = step.else_arguments_template or "{}"
                        target_output_key = step.else_output_key or step.output_key
                    else:
                        # No inline alternative; step is skipped
                        continue
            else:
                last_condition_met = None

            step_id = target_tool or target_skill

            # Render template
            try:
                rendered = self._render_template(target_template, ctx)
            except Exception as exc:
                result = ToolResult(
                    tool_name=step_id,
                    content=f"Template rendering error: {exc}",
                    success=False,
                )
                all_results.append(result)
                break

            if target_skill:
                # Delegate to sub-skill resolver
                result = self._run_sub_skill(
                    target_skill, rendered, ctx, manifest.name, i, current_stack
                )
            else:
                # Execute via tool executor
                tool_call = ToolCall(
                    id=f"skill_{manifest.name}_{i}",
                    name=target_tool,
                    arguments=rendered,
                )
                result = self._tool_executor.execute(tool_call)

            all_results.append(result)

            if not result.success:
                break

            # Store output in context
            if target_output_key:
                ctx[target_output_key] = result.content

        success = all(r.success for r in all_results)

        if self._bus:
            self._bus.publish(
                EventType.SKILL_EXECUTE_END,
                {"skill": manifest.name, "success": success},
            )

        return SkillResult(
            skill_name=manifest.name,
            success=success,
            step_results=all_results,
            context=ctx,
        )

    def _run_sub_skill(
        self,
        skill_name: str,
        rendered_args: str,
        parent_ctx: Dict[str, Any],
        parent_skill: str,
        step_index: int,
        current_stack: List[str],
    ) -> ToolResult:
        """Invoke the skill resolver and convert its result to a ToolResult."""
        if self._skill_resolver is None:
            return ToolResult(
                tool_name=skill_name,
                content=f"No skill resolver registered for sub-skill '{skill_name}'",
                success=False,
            )

        # 1. Circular dependency check
        if skill_name in current_stack:
            return ToolResult(
                tool_name=skill_name,
                content=f"Circular dependency detected in skill composition: {' -> '.join(current_stack + [skill_name])}",
                success=False,
            )

        # 2. Composition depth limit check
        if len(current_stack) + 1 > self._max_depth:
            return ToolResult(
                tool_name=skill_name,
                content=f"Composition depth limit ({self._max_depth}) exceeded by call chain: {' -> '.join(current_stack + [skill_name])}",
                success=False,
            )

        # 3. If skill_manager is available, validate status & approvals & capabilities
        if self._skill_manager is not None:
            child_manifest = None
            if hasattr(self._skill_manager, "get"):
                child_manifest = self._skill_manager.get(skill_name)
            if child_manifest is None and hasattr(self._skill_manager, "resolve"):
                try:
                    child_manifest = self._skill_manager.resolve(skill_name)
                except Exception:
                    child_manifest = None

            if child_manifest is None:
                return ToolResult(
                    tool_name=skill_name,
                    content=f"Required child skill '{skill_name}' not found",
                    success=False,
                )

            from openjarvis.skills.composition import is_skill_approved_and_active

            is_ok, reason = is_skill_approved_and_active(child_manifest)
            if not is_ok:
                return ToolResult(
                    tool_name=skill_name,
                    content=f"Cannot execute child skill '{skill_name}': {reason}",
                    success=False,
                )

            if self._allowed_capabilities is not None:
                missing = validate_capabilities(child_manifest, self._allowed_capabilities)
                if missing:
                    return ToolResult(
                        tool_name=skill_name,
                        content=(
                            f"Blocked: child skill '{skill_name}' requires "
                            f"capabilities {missing} that were not granted."
                        ),
                        success=False,
                    )

        # Parse rendered args and merge into a copy of the parent context
        try:
            args: Dict[str, Any] = json.loads(rendered_args)
            if not isinstance(args, dict):
                args = {}
        except json.JSONDecodeError:
            args = {}

        child_ctx = {**parent_ctx, **args}

        next_stack = current_stack + [skill_name]
        try:
            import inspect

            sig = inspect.signature(self._skill_resolver)
            if "call_stack" in sig.parameters:
                sub_result: SkillResult = self._skill_resolver(
                    skill_name, child_ctx, call_stack=next_stack
                )
            else:
                sub_result = self._skill_resolver(skill_name, child_ctx)
        except Exception as exc:
            return ToolResult(
                tool_name=skill_name,
                content=f"Execution error in child skill '{skill_name}': {exc}",
                success=False,
            )

        # Handle child failure without falsely reporting success
        if not sub_result.success:
            err_msg = ""
            for sr in sub_result.step_results:
                if not sr.success:
                    err_msg = sr.content
                    break
            if not err_msg:
                err_msg = f"Child skill '{skill_name}' failed."
            return ToolResult(
                tool_name=skill_name,
                content=err_msg,
                success=False,
            )

        # Propagate child context back to parent
        if sub_result.context:
            parent_ctx.update(
                {k: v for k, v in sub_result.context.items() if k not in parent_ctx}
            )

        # Expose output
        content: Any = ""
        if sub_result.context:
            new_keys = [k for k in sub_result.context if k not in parent_ctx]
            if new_keys:
                content = sub_result.context[new_keys[-1]]
            else:
                content = (
                    list(sub_result.context.values())[-1] if sub_result.context else ""
                )
        elif sub_result.step_results:
            content = sub_result.step_results[-1].content

        return ToolResult(
            tool_name=skill_name,
            content=content,
            success=True,
        )

    @staticmethod
    def _render_template(template: str, ctx: Dict[str, Any]) -> str:
        """Render {key} and {{key}} placeholders from context."""

        def _replace_double(match: re.Match) -> str:
            key = match.group(1).strip()
            val = ctx.get(key, match.group(0))
            if isinstance(val, str):
                return val
            return json.dumps(val)

        def _replace_single(match: re.Match) -> str:
            key = match.group(1).strip()
            val = ctx.get(key, match.group(0))
            if isinstance(val, str):
                return val
            return json.dumps(val)

        res = re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", _replace_double, template)
        return re.sub(r"\{([a-zA-Z0-9_]+)\}", _replace_single, res)


__all__ = ["SkillExecutor", "SkillResolver", "SkillResult"]

