"""Ultron Persistent Task Runner.

Orchestrates multi-step DAG task execution with state persistence,
crash-recovery without repeating completed steps, bounded retries,
idempotency / reconciliation to prevent duplicate external side-effects,
step verification, and strict Safety Kernel integration.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from openjarvis.core.events import EventBus, EventType
from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.learning.experience import ExperienceLearner
from openjarvis.memory.store import FactStore
from openjarvis.security.capabilities import (
    DEFAULT_TOOL_CAPABILITIES,
    Capability,
    CapabilityPolicy,
)
from openjarvis.security.kernel import (
    ActionEffect,
    SafetyKernel,
    get_safety_kernel,
)
from openjarvis.skills.manager import SkillManager
from openjarvis.tasks.intelligence import (
    FailureCategory,
    ToolExecutionIntelligence,
)
from openjarvis.tasks.store import TaskStore
from openjarvis.tasks.types import StepStatus, TaskRecord, TaskStatus, TaskStep

try:
    import openjarvis.tools  # noqa: F401 - populate ToolRegistry with built-in tools
except ImportError:
    pass

logger = logging.getLogger(__name__)


class TaskPlanPermissionError(PermissionError, ValueError):
    """Raised when task plan validation fails due to capability or security permissions."""
    pass

GENERIC_VERB_MAP: Dict[str, str] = {
    "create_file": "file_write",
    "write_file": "file_write",
    "read_file": "file_read",
    "cmd_exec": "shell_exec",
    "bash": "shell_exec",
    "powershell": "shell_exec",
    "webhook": "http_request",
    "fetch_url": "http_request",
    "delete_file": "delete_file",
    "file_delete": "delete_file",
    "remove_file": "delete_file",
    "delete_cache": "delete_file",
    "clean_cache": "delete_file",
    "launch_app": "app_launch",
    "open_app": "app_launch",
}

_BUILTIN_TOOL_MODULE_MAP: Dict[str, Tuple[str, str]] = {
    "file_write": ("openjarvis.tools.file_write", "FileWriteTool"),
    "file_read": ("openjarvis.tools.file_read", "FileReadTool"),
    "shell_exec": ("openjarvis.tools.shell_exec", "ShellExecTool"),
    "http_request": ("openjarvis.tools.http_request", "HttpRequestTool"),
    "calculator": ("openjarvis.tools.calculator", "CalculatorTool"),
    "web_search": ("openjarvis.tools.web_search", "WebSearchTool"),
}


def _ensure_tool_registered(tool_name: str) -> None:
    """Ensure standard built-in tool is registered in ToolRegistry even if registries were cleared."""
    if not tool_name or ToolRegistry.contains(tool_name):
        return
    if tool_name in _BUILTIN_TOOL_MODULE_MAP:
        mod_name, cls_name = _BUILTIN_TOOL_MODULE_MAP[tool_name]
        try:
            import importlib

            mod = sys.modules.get(mod_name) or importlib.import_module(mod_name)
            cls = getattr(mod, cls_name, None)
            if cls and not ToolRegistry.contains(tool_name):
                ToolRegistry.register_value(tool_name, cls)
        except Exception:
            pass


class PersistentTaskRunner:
    """Enterprise-grade persistent task runner for Ultron."""

    def __init__(
        self,
        store: Optional[TaskStore] = None,
        bus: Optional[EventBus] = None,
        kernel: Optional[SafetyKernel] = None,
        agent: Optional[Any] = None,
        capability_policy: Optional[CapabilityPolicy] = None,
        auto_recover: bool = False,
        memory_store: Optional[FactStore] = None,
        skill_manager: Optional[SkillManager] = None,
    ) -> None:
        self.store = store or TaskStore()
        self.bus = bus
        self.kernel = kernel or get_safety_kernel()
        self.agent = agent
        self.capability_policy = capability_policy
        self.memory_store = memory_store
        self.skill_manager = skill_manager

        self._active_cancels: Dict[str, threading.Event] = {}
        self._active_threads: Dict[str, threading.Thread] = {}
        self._custom_tools: Dict[str, Callable[..., ToolResult]] = {}
        self._custom_reconcilers: Dict[str, Callable[[TaskStep], bool]] = {}
        self._lock = threading.Lock()

        # Wire Tool Execution Intelligence
        self.intelligence = ToolExecutionIntelligence(
            runner=self,
            capability_policy=self.capability_policy,
        )

        # Wire Experience Learning & Reusable Skill Systems
        from openjarvis.skills.learning import WorkflowSkillLearner

        self.experience_learner = ExperienceLearner(memory_store=self.memory_store)
        self.workflow_skill_learner = WorkflowSkillLearner(
            skill_manager=self.skill_manager,
            ledger=self.skill_manager.get_ledger() if self.skill_manager and hasattr(self.skill_manager, "get_ledger") else None,
        )

        if auto_recover:
            self.recover_interrupted_tasks()

    # ------------------------------------------------------------------
    # Tool & Reconciler Registration (for extension & test mocks)
    # ------------------------------------------------------------------

    def register_custom_tool(self, name: str, handler: Callable[..., ToolResult]) -> None:
        """Register a custom tool callable."""
        with self._lock:
            self._custom_tools[name] = handler

    def register_reconciler(self, tool_name: str, handler: Callable[[TaskStep], bool]) -> None:
        """Register a custom reconciliation checker for a tool."""
        with self._lock:
            self._custom_reconcilers[tool_name] = handler

    # ------------------------------------------------------------------
    # 1. Tool Validation & Task Planning
    # ------------------------------------------------------------------

    def resolve_tool_handler(
        self, tool_name: str
    ) -> Tuple[str, Optional[Callable[..., ToolResult]], Optional[Dict[str, Any]]]:
        """Resolve a tool name or generic verb to its canonical name, handler, and argument schema.

        Returns (canonical_name, handler_callable, schema_dict_or_None).
        If tool cannot be resolved to any supported registered handler, handler is None.
        """
        if not tool_name or not isinstance(tool_name, str):
            return "", None, None

        t_clean = tool_name.strip()
        t_lower = t_clean.lower()

        # 1. Custom runner tools registered on this instance
        with self._lock:
            if t_clean in self._custom_tools:
                handler = self._custom_tools[t_clean]
                schema = getattr(handler, "schema", None)
                return t_clean, handler, schema
            if t_lower in self._custom_tools:
                handler = self._custom_tools[t_lower]
                schema = getattr(handler, "schema", None)
                return t_lower, handler, schema

        # 2. Built-in runner handlers
        if t_lower == "think":
            schema = {
                "type": "object",
                "properties": {
                    "thought": {"type": "string", "description": "Internal reasoning or thought content."}
                },
                "required": [],
            }
            return "think", self._execute_think, schema

        if t_lower in ("delete_file", "file_delete", "remove_file", "delete_cache", "clean_cache"):
            schema = {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to file to safely delete or quarantine."}
                },
                "required": ["path"],
            }
            return "delete_file", self._execute_delete_file, schema

        if t_lower in ("app_launch", "launch_app", "open_app"):
            schema = {
                "type": "object",
                "properties": {
                    "app_name": {"type": "string", "description": "Application name or binary to launch."},
                    "path": {"type": "string", "description": "Path to application executable."},
                    "target": {"type": "string", "description": "Target application name or path."},
                },
                "required": [],
            }
            return "app_launch", self._execute_app_launch, schema

        # 3. Mapped generic task verbs
        canonical_name = GENERIC_VERB_MAP.get(t_lower)
        if canonical_name:
            _ensure_tool_registered(canonical_name)
            # Check custom tools under canonical name
            with self._lock:
                if canonical_name in self._custom_tools:
                    handler = self._custom_tools[canonical_name]
                    return canonical_name, handler, getattr(handler, "schema", None)

            # Check ToolRegistry
            if ToolRegistry.contains(canonical_name):
                tool_entry = ToolRegistry.get(canonical_name)
                tool_inst = tool_entry() if callable(tool_entry) else tool_entry
                schema = getattr(tool_inst, "spec", None).parameters if hasattr(tool_inst, "spec") else None
                return canonical_name, tool_inst.execute, schema

        # 4. Global ToolRegistry direct match
        _ensure_tool_registered(t_clean)
        _ensure_tool_registered(t_lower)
        target_key = t_clean if ToolRegistry.contains(t_clean) else (t_lower if ToolRegistry.contains(t_lower) else None)
        if target_key:
            tool_entry = ToolRegistry.get(target_key)
            tool_inst = tool_entry() if callable(tool_entry) else tool_entry
            schema = getattr(tool_inst, "spec", None).parameters if hasattr(tool_inst, "spec") else None
            return target_key, tool_inst.execute, schema

        # 5. Registered SkillManager reusable skills
        if self.skill_manager is not None:
            skill_names = self.skill_manager.skill_names()
            target_skill = t_clean if t_clean in skill_names else (t_lower if t_lower in skill_names else None)
            if target_skill:
                try:
                    manifest = self.skill_manager.resolve(target_skill)

                    def skill_handler(**kwargs: Any) -> ToolResult:
                        # Check approval before execution
                        if self.workflow_skill_learner is not None and not self.workflow_skill_learner.is_skill_approved(manifest):
                            return ToolResult(
                                tool_name=target_skill,
                                content=(
                                    f"Refusing to execute unapproved learned skill '{target_skill}'. "
                                    f"Skill is currently in '{manifest.metadata.get('approval_status', 'pending_review')}' "
                                    "state and must be explicitly approved before execution."
                                ),
                                success=False,
                            )
                        # Validate health before reuse
                        if self.workflow_skill_learner is not None:
                            is_healthy, issues = self.workflow_skill_learner.validate_skill_health(manifest)
                            if not is_healthy:
                                return ToolResult(
                                    tool_name=target_skill,
                                    content=f"Refusing to execute outdated/unhealthy skill '{target_skill}': {'; '.join(issues)}",
                                    success=False,
                                )
                        # If composite skill, validate before execution
                        if any(s.skill_name for s in manifest.steps):
                            from openjarvis.skills.composition import (
                                CompositionValidationError,
                                DepthExceededError,
                                validate_composite_skill,
                            )

                            try:
                                validate_composite_skill(manifest, self.skill_manager)
                            except (CompositionValidationError, DepthExceededError) as exc:
                                return ToolResult(
                                    tool_name=target_skill,
                                    content=f"Refusing to execute invalid composite skill '{target_skill}': {exc}",
                                    success=False,
                                )
                        res = self.skill_manager.execute(target_skill, context=kwargs)

                        output_str = getattr(res, "output", "") or getattr(res, "content", "")
                        if not output_str and hasattr(res, "step_results") and res.step_results:
                            if not getattr(res, "success", True):
                                for sr in res.step_results:
                                    if not sr.success:
                                        output_str = sr.content
                                        break
                            else:
                                final_step = manifest.steps[-1] if manifest.steps else None
                                if final_step and final_step.output_key and final_step.output_key in getattr(res, "context", {}):
                                    output_str = res.context[final_step.output_key]
                                else:
                                    output_str = res.step_results[-1].content
                        if not output_str and hasattr(res, "context") and res.context:
                            output_str = str(list(res.context.values())[-1])
                        if not output_str:
                            output_str = str(res)

                        success_val = getattr(res, "success", True)
                        return ToolResult(
                            tool_name=target_skill,
                            content=str(output_str),
                            success=bool(success_val),
                        )

                    schema = {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    }
                    return target_skill, skill_handler, schema
                except Exception as exc:
                    logger.debug("Error resolving skill '%s': %s", target_skill, exc)

        # Not resolved
        return t_clean, None, None

    def _execute_think(self, **kwargs: Any) -> ToolResult:
        """Execute built-in think tool."""
        return ToolResult(
            tool_name="think",
            content=str(kwargs.get("thought", "Thought registered.")),
            success=True,
        )

    def _execute_delete_file(self, path: str = "", **kwargs: Any) -> ToolResult:
        """Safely delete or quarantine a file via the Safety Kernel."""
        if not path:
            return ToolResult(tool_name="delete_file", content="Missing 'path' argument", success=False)
        ok, msg = self.kernel.safe_delete_or_quarantine(path)
        return ToolResult(tool_name="delete_file", content=msg, success=ok)

    def _execute_app_launch(self, app_name: str = "", path: str = "", target: str = "", **kwargs: Any) -> ToolResult:
        """Launch an application with Safety Kernel validation."""
        target_app = (app_name or path or target or "").strip()
        if not target_app:
            return ToolResult(tool_name="app_launch", content="Missing application name or path", success=False)
        decision = self.kernel.evaluate("app_launch", target=target_app)
        if decision.effect == ActionEffect.BLOCK:
            return ToolResult(tool_name="app_launch", content=f"Blocked by Safety Kernel: {decision.reason}", success=False)
        import subprocess
        try:
            proc = subprocess.Popen([target_app], shell=True)
            return ToolResult(tool_name="app_launch", content=f"Launched '{target_app}' (pid={proc.pid})", success=True)
        except Exception as exc:
            return ToolResult(tool_name="app_launch", content=f"Failed to launch '{target_app}': {exc}", success=False)

    def is_tool_known(self, tool_name: str) -> bool:
        """Check whether a tool name corresponds to a registered or recognized tool with an executable handler."""
        if not tool_name or not isinstance(tool_name, str):
            return False
        _, handler, _ = self.resolve_tool_handler(tool_name)
        return handler is not None

    def validate_plan(
        self,
        steps: List[TaskStep],
        owner_id: str = "_default",
    ) -> None:
        """Validate tool names, argument schemas, dependencies, and DAG structure before execution.

        Rejects:
        - Malformed or empty plan
        - Unknown or unregistered tools and unsupported generic verbs
        - Invalid or malformed argument schemas against actual tool schemas
        - Non-existent dependencies, self-dependencies, and circular dependencies
        - Unauthorized tools under CapabilityPolicy
        - Steps blocked by the Safety Kernel
        """
        if not steps or not isinstance(steps, list):
            raise ValueError("Task plan validation failed: Plan contains no executable steps.")

        step_ids: Set[str] = set()
        adj: Dict[str, List[str]] = {}

        # 1. Structure, Tool Name, Schema, and Identity Check
        for idx, step in enumerate(steps):
            if not isinstance(step, TaskStep):
                raise ValueError(f"Task plan validation failed: Step at index {idx} is malformed (not a TaskStep).")

            s_id = (step.step_id or "").strip()
            if not s_id:
                raise ValueError(f"Task plan validation failed: Step at index {idx} has an empty or missing step_id.")

            if s_id in step_ids:
                raise ValueError(f"Task plan validation failed: Duplicate step_id '{s_id}' found in plan.")
            step_ids.add(s_id)

            # Tool existence & handler resolution check
            canonical_name, handler, schema = self.resolve_tool_handler(step.tool_name)
            if handler is None:
                raise ValueError(
                    f"Task plan validation failed: Unknown or unrecognized tool '{step.tool_name}' in step '{s_id}'. "
                    "Generic verbs must map to supported handlers, and unknown tools must be rejected."
                )

            # Argument schema check
            if not isinstance(step.tool_args, dict):
                raise ValueError(
                    f"Task plan validation failed: Invalid argument schema in step '{s_id}'. "
                    f"Expected dictionary, got {type(step.tool_args).__name__}."
                )

            args = step.tool_args

            # Tool-schema validation against ToolSpec.parameters
            if schema and isinstance(schema, dict):
                properties = schema.get("properties", {})
                required = schema.get("required", [])

                # 1. Check required parameters
                for req in required:
                    if req not in args:
                        prop_info = properties.get(req, {})
                        if prop_info.get("type") == "string":
                            raise ValueError(
                                f"Task plan validation failed: Step '{s_id}' for '{step.tool_name}' "
                                f"requires non-empty string argument '{req}'."
                            )
                        else:
                            raise ValueError(
                                f"Task plan validation failed: Step '{s_id}' for '{step.tool_name}' "
                                f"missing required argument '{req}'."
                            )

                    req_val = args[req]
                    prop_info = properties.get(req, {})
                    if prop_info.get("type") == "string":
                        if isinstance(req_val, str) and not req_val.strip():
                            raise ValueError(
                                f"Task plan validation failed: Step '{s_id}' for '{step.tool_name}' "
                                f"requires non-empty string argument '{req}'."
                            )

                # 2. Check property types for provided arguments
                for param, val in args.items():
                    if param in properties:
                        # Allow template expressions (e.g., {{s1.output}}) during static plan validation
                        if isinstance(val, str) and ("{{" in val or "$" in val):
                            continue
                        expected_type = properties[param].get("type")
                        if expected_type == "string":
                            if not isinstance(val, str):
                                raise ValueError(
                                    f"Task plan validation failed: Step '{s_id}' for '{step.tool_name}' "
                                    f"argument '{param}' must be a string, got {type(val).__name__}."
                                )
                        elif expected_type == "integer":
                            if not isinstance(val, int) or isinstance(val, bool):
                                raise ValueError(
                                    f"Task plan validation failed: Step '{s_id}' for '{step.tool_name}' "
                                    f"argument '{param}' must be an integer, got {type(val).__name__}."
                                )
                        elif expected_type == "number":
                            if not isinstance(val, (int, float)) or isinstance(val, bool):
                                raise ValueError(
                                    f"Task plan validation failed: Step '{s_id}' for '{step.tool_name}' "
                                    f"argument '{param}' must be a number, got {type(val).__name__}."
                                )
                        elif expected_type == "boolean":
                            if not isinstance(val, bool):
                                raise ValueError(
                                    f"Task plan validation failed: Step '{s_id}' for '{step.tool_name}' "
                                    f"argument '{param}' must be a boolean, got {type(val).__name__}."
                                )
                        elif expected_type == "array":
                            if not isinstance(val, (list, tuple)):
                                raise ValueError(
                                    f"Task plan validation failed: Step '{s_id}' for '{step.tool_name}' "
                                    f"argument '{param}' must be an array (list), got {type(val).__name__}."
                                )
                        elif expected_type == "object":
                            if not isinstance(val, dict):
                                raise ValueError(
                                    f"Task plan validation failed: Step '{s_id}' for '{step.tool_name}' "
                                    f"argument '{param}' must be an object (dict), got {type(val).__name__}."
                                )

            # Additional checks for special tool verbs (e.g. app_launch)
            t_lower = step.tool_name.lower().strip()
            if canonical_name == "app_launch" or t_lower in ("app_launch", "launch_app", "open_app"):
                if not any(k in args and isinstance(args[k], str) and args[k].strip() for k in ("app_name", "path", "target")):
                    raise ValueError(f"Task plan validation failed: Step '{s_id}' for '{step.tool_name}' requires argument 'app_name' or 'path'.")

            # Dependencies list check
            if not isinstance(step.dependencies, (list, tuple, set)):
                raise ValueError(f"Task plan validation failed: Step '{s_id}' dependencies must be a list of step IDs.")

            adj[s_id] = list(step.dependencies)

        # 2. Dependency existence & Self-dependency check
        for s_id, deps in adj.items():
            for dep in deps:
                if not isinstance(dep, str) or not dep.strip():
                    raise ValueError(f"Task plan validation failed: Step '{s_id}' contains invalid dependency ID {dep!r}.")
                if dep == s_id:
                    raise ValueError(f"Task plan validation failed: Self-referencing dependency in step '{s_id}'.")
                if dep not in step_ids:
                    raise ValueError(f"Task plan validation failed: Step '{s_id}' depends on non-existent step '{dep}'.")

        # 3. DAG Structure & Circular Dependency Detection (DFS 3-color)
        state: Dict[str, int] = {s_id: 0 for s_id in step_ids}  # 0=unvisited, 1=visiting, 2=visited
        path: List[str] = []

        def dfs(node: str) -> Optional[List[str]]:
            state[node] = 1
            path.append(node)
            for neighbor in adj.get(node, []):
                if state.get(neighbor) == 1:
                    cycle_start = path.index(neighbor)
                    return path[cycle_start:] + [neighbor]
                if state.get(neighbor) == 0:
                    cycle = dfs(neighbor)
                    if cycle:
                        return cycle
            path.pop()
            state[node] = 2
            return None

        for s_id in step_ids:
            if state[s_id] == 0:
                cycle = dfs(s_id)
                if cycle:
                    cycle_str = " -> ".join(cycle)
                    raise ValueError(f"Task plan validation failed: Circular dependency detected in DAG: {cycle_str}")

        # 4. Capability Policy & Safety Kernel Pre-Flight Checks
        for step in steps:
            canonical_name, _, _ = self.resolve_tool_handler(step.tool_name)

            # Check learned-skill approval and composite validation
            if self.skill_manager is not None and (
                step.tool_name in self.skill_manager.skill_names()
                or canonical_name in self.skill_manager.skill_names()
            ):
                target_s = (
                    step.tool_name
                    if step.tool_name in self.skill_manager.skill_names()
                    else canonical_name
                )
                manifest = self.skill_manager.resolve(target_s)
                if (
                    self.workflow_skill_learner is not None
                    and not self.workflow_skill_learner.is_skill_approved(manifest)
                ):
                    status_val = (manifest.metadata or {}).get(
                        "approval_status", "pending_review"
                    )
                    raise TaskPlanPermissionError(
                        f"Task plan validation failed: Skill '{step.tool_name}' in step '{step.step_id}' "
                        f"is not approved (status: '{status_val}'). Learned skills cannot be executed until explicitly approved."
                    )
                # Check composite skills
                if any(s.skill_name for s in manifest.steps):
                    from openjarvis.skills.composition import (
                        CompositionValidationError,
                        DepthExceededError,
                        validate_composite_skill,
                    )

                    try:
                        validate_composite_skill(manifest, self.skill_manager)
                    except (CompositionValidationError, DepthExceededError) as exc:
                        raise TaskPlanPermissionError(
                            f"Task plan validation failed: Composite skill '{step.tool_name}' in step '{step.step_id}' failed validation: {exc}"
                        )

            # Capability check
            if self.capability_policy:
                caps = DEFAULT_TOOL_CAPABILITIES.get(
                    canonical_name.lower()
                ) or DEFAULT_TOOL_CAPABILITIES.get(step.tool_name.lower())
                if caps is None:
                    if self.skill_manager is not None and (
                        step.tool_name in self.skill_manager.skill_names()
                        or canonical_name in self.skill_manager.skill_names()
                    ):
                        target_s = (
                            step.tool_name
                            if step.tool_name in self.skill_manager.skill_names()
                            else canonical_name
                        )
                        manifest = self.skill_manager.resolve(target_s)
                        from openjarvis.skills.composition import (
                            compute_composite_capabilities,
                        )

                        caps = compute_composite_capabilities(
                            manifest, self.skill_manager
                        )
                    else:
                        caps = [Capability.TOOL_INVOKE.value]
                for cap in caps:
                    cap_val = cap.value if hasattr(cap, "value") else str(cap)
                    if not self.capability_policy.check(
                        owner_id, cap_val, step.tool_name
                    ):
                        raise TaskPlanPermissionError(
                            f"Task plan validation failed: Unauthorized tool '{step.tool_name}' in step '{step.step_id}'. "
                            f"Agent/owner '{owner_id}' is not authorized; lacks capability '{cap_val}'."
                        )


            # Safety Kernel upfront evaluation
            action_type, target = self._map_to_safety_action(step)
            decision = self.kernel.evaluate(action_type, target=target, params=step.tool_args)
            if decision.effect == ActionEffect.BLOCK:
                raise ValueError(
                    f"Task plan validation failed: Step '{step.step_id}' blocked by Safety Kernel: {decision.reason}"
                )

    def plan_task(
        self,
        prompt: str,
        steps: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None,
    ) -> TaskRecord:
        """Decompose a user request into ordered DAG steps with dependencies."""
        if not task_id:
            task_id = f"task_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"

        task_steps: List[TaskStep] = []

        # Retrieve relevant persistent memory context for planning
        project = (metadata or {}).get("project", "default")
        memory_context = ""
        if self.memory_store is not None:
            try:
                retrieval = self.experience_learner.retrieve_planning_context(prompt, project=project)
                memory_context = retrieval.get("markdown", "")
                if memory_context:
                    metadata = dict(metadata or {})
                    metadata["retrieved_memories"] = memory_context
            except Exception as exc:
                logger.debug("Could not retrieve memory planning context: %s", exc)

        if steps:
            normalized_steps = [
                s.to_dict() if isinstance(s, TaskStep) else s
                for s in steps
            ]
            # First pass: map indices and shorthand names to step_ids
            step_id_map: Dict[Any, str] = {}
            for idx, s in enumerate(normalized_steps):
                s_id = s.get("step_id") or f"{task_id}_s{idx + 1}"
                step_id_map[idx + 1] = s_id
                step_id_map[str(idx + 1)] = s_id
                step_id_map[f"s{idx + 1}"] = s_id
                step_id_map[s_id] = s_id

            # Explicit step definitions provided by user or higher-level planner
            for idx, s in enumerate(normalized_steps):
                step_id = s.get("step_id") or f"{task_id}_s{idx + 1}"
                tool_name = s.get("tool_name", "")
                tool_args = s.get("tool_args", {})
                raw_deps = s.get("dependencies", [])
                dependencies = [step_id_map.get(d, d) for d in raw_deps]

                # Auto-generate idempotency key if not explicitly given
                idempotency_key = s.get("idempotency_key")
                if not idempotency_key:
                    args_blob = json.dumps(tool_args, sort_keys=True)
                    idempotency_key = hashlib.sha256(
                        f"{task_id}:{tool_name}:{args_blob}".encode("utf-8")
                    ).hexdigest()

                task_steps.append(
                    TaskStep(
                        step_id=step_id,
                        task_id=task_id,
                        step_index=idx,
                        title=s.get("title", f"Step {idx + 1}: {tool_name}"),
                        tool_name=tool_name,
                        tool_args=tool_args,
                        dependencies=dependencies,
                        expected_output=s.get("expected_output", ""),
                        status=StepStatus.PENDING,
                        max_retries=s.get("max_retries", 3),
                        idempotency_key=idempotency_key,
                    )
                )
        else:
            # Autonomous decomposition of complex user requests into ordered steps
            if self.agent is not None:
                task_steps = self._plan_with_agent(task_id, prompt, memory_context=memory_context)
            else:
                task_steps = self._decompose_prompt_to_steps(task_id, prompt, memory_context=memory_context)

        # Pre-execution plan validation check
        owner_id = (metadata or {}).get("owner_id") or (metadata or {}).get("agent_id") or "_default"
        self.validate_plan(task_steps, owner_id=owner_id)

        record = TaskRecord(
            task_id=task_id,
            prompt=prompt,
            status=TaskStatus.QUEUED,
            steps=task_steps,
            created_at=time.time(),
            updated_at=time.time(),
            current_step_index=0,
            total_steps=len(task_steps),
            metadata=metadata or {},
        )

        self.store.save_task(record)
        self._emit_event("task_created", record.to_dict())
        return record

    create_task = plan_task

    def _plan_with_agent(self, task_id: str, prompt: str, memory_context: str = "") -> List[TaskStep]:
        """Convert user prompt into ordered executable DAG task steps using the existing agent."""
        try:
            catalog = self.intelligence.build_tool_catalog()
            mem_section = f"\n\n{memory_context}" if memory_context else ""
            planning_prompt = (
                "You are Ultron's Task Planning Agent. Convert the following user request into "
                "an ordered JSON array of executable task steps.\n\n"
                f"{catalog}"
                f"{mem_section}\n\n"
                "Each item in the array must be an object with:\n"
                '- "title": concise summary of what this step does\n'
                '- "tool_name": the exact registered tool to call (e.g., file_write, file_read, shell_exec, think, http_request)\n'
                '- "tool_args": dictionary of tool arguments matching the parameter schema\n'
                '- "dependencies": list of step IDs or 1-based indices that must complete before this step\n'
                '- "expected_output": brief string describing what success looks like\n\n'
                f'User Request: "{prompt}"\n\n'
                "Return ONLY a valid JSON array of step objects, without any markdown formatting or commentary."
            )
            raw_output = ""
            if hasattr(self.agent, "run") and callable(self.agent.run):
                res = self.agent.run(planning_prompt)
                if hasattr(res, "content"):
                    raw_output = res.content
                elif hasattr(res, "output"):
                    raw_output = res.output
                elif isinstance(res, str):
                    raw_output = res
                else:
                    raw_output = str(res)
            elif hasattr(self.agent, "chat") and callable(self.agent.chat):
                res = self.agent.chat(planning_prompt)
                raw_output = getattr(res, "content", str(res))
            elif callable(self.agent):
                res = self.agent(planning_prompt)
                raw_output = getattr(res, "content", str(res))

            # Clean markdown code fences if present
            clean_json = raw_output.strip()
            if "```" in clean_json:
                m = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", clean_json, re.DOTALL)
                if m:
                    clean_json = m.group(1).strip()
                else:
                    clean_json = re.sub(r"^```.*$", "", clean_json, flags=re.MULTILINE).strip()

            # Find bounding JSON array brackets
            start_idx = clean_json.find("[")
            end_idx = clean_json.rfind("]")
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                clean_json = clean_json[start_idx : end_idx + 1]

            parsed = json.loads(clean_json)
            if isinstance(parsed, list) and len(parsed) > 0:
                steps: List[TaskStep] = []
                step_id_map: Dict[Any, str] = {}
                for idx, item in enumerate(parsed):
                    if not isinstance(item, dict):
                        continue
                    s_id = item.get("step_id") or f"{task_id}_s{idx + 1}"
                    step_id_map[idx + 1] = s_id
                    step_id_map[str(idx + 1)] = s_id
                    tool_name = item.get("tool_name", "think")
                    tool_args = item.get("tool_args", {})
                    raw_deps = item.get("dependencies", [])
                    deps: List[str] = []
                    for d in raw_deps:
                        if d in step_id_map:
                            deps.append(step_id_map[d])
                        elif isinstance(d, str):
                            deps.append(d)

                    args_blob = json.dumps(tool_args, sort_keys=True)
                    idempotency_key = item.get("idempotency_key") or hashlib.sha256(
                        f"{task_id}:{tool_name}:{args_blob}".encode("utf-8")
                    ).hexdigest()

                    steps.append(
                        TaskStep(
                            step_id=s_id,
                            task_id=task_id,
                            step_index=idx,
                            title=item.get("title", f"Step {idx + 1}: {tool_name}"),
                            tool_name=tool_name,
                            tool_args=tool_args,
                            dependencies=deps,
                            expected_output=item.get("expected_output", ""),
                            status=StepStatus.PENDING,
                            max_retries=item.get("max_retries", 3),
                            idempotency_key=idempotency_key,
                        )
                    )
                if steps:
                    logger.info("Successfully planned %d steps for task %s via agent.", len(steps), task_id)
                    return steps
        except Exception as exc:
            logger.warning("Agent planning for task %s failed (%s), falling back to heuristics.", task_id, exc)

        return self._decompose_prompt_to_steps(task_id, prompt, memory_context=memory_context)

    def _decompose_prompt_to_steps(self, task_id: str, prompt: str, memory_context: str = "") -> List[TaskStep]:
        """Convert a complex user prompt into an ordered pipeline of steps."""
        p_lower = prompt.lower()
        steps: List[TaskStep] = []

        # Example: File write / generation request
        if "write" in p_lower or "create file" in p_lower or "save to" in p_lower:
            # Step 1: Preparation / Inspection
            s1_id = f"{task_id}_s1"
            steps.append(
                TaskStep(
                    step_id=s1_id,
                    task_id=task_id,
                    step_index=0,
                    title="Inspect workspace and prepare environment",
                    tool_name="think",
                    tool_args={"thought": f"Planning execution for: {prompt}"},
                    dependencies=[],
                    expected_output="Planning complete",
                    idempotency_key=hashlib.sha256(f"{task_id}:s1".encode()).hexdigest(),
                )
            )
            # Step 2: Primary execution
            s2_id = f"{task_id}_s2"
            steps.append(
                TaskStep(
                    step_id=s2_id,
                    task_id=task_id,
                    step_index=1,
                    title="Execute primary file operation",
                    tool_name="file_write",
                    tool_args={"path": "output.txt", "content": f"Result for: {prompt}"},
                    dependencies=[s1_id],
                    expected_output="File written successfully",
                    idempotency_key=hashlib.sha256(f"{task_id}:s2".encode()).hexdigest(),
                )
            )
            # Step 3: Verification
            s3_id = f"{task_id}_s3"
            steps.append(
                TaskStep(
                    step_id=s3_id,
                    task_id=task_id,
                    step_index=2,
                    title="Verify generated output and file integrity",
                    tool_name="file_read",
                    tool_args={"path": "output.txt"},
                    dependencies=[s2_id],
                    expected_output="File content verified",
                    idempotency_key=hashlib.sha256(f"{task_id}:s3".encode()).hexdigest(),
                )
            )
        else:
            # Standard generic ordered pipeline
            s1_id = f"{task_id}_s1"
            steps.append(
                TaskStep(
                    step_id=s1_id,
                    task_id=task_id,
                    step_index=0,
                    title=f"Analyze request: {prompt[:40]}",
                    tool_name="think",
                    tool_args={"thought": f"Analyzing task: {prompt}"},
                    dependencies=[],
                    expected_output="Analysis complete",
                    idempotency_key=hashlib.sha256(f"{task_id}:s1".encode()).hexdigest(),
                )
            )

        return steps

    # ------------------------------------------------------------------
    # 2. Execution & Lifecycle Management
    # ------------------------------------------------------------------

    def run_task(self, task_id: str, background: bool = False) -> TaskRecord:
        """Run or resume a task. If background is True, runs in a worker thread."""
        task = self.store.get_task(task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found.")

        if task.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED):
            return task

        if not task.steps:
            return task

        with self._lock:
            existing_thread = self._active_threads.get(task_id)
            if existing_thread and existing_thread.is_alive():
                logger.warning("Task %s is already running in active thread %s", task_id, existing_thread.name)
                return task

            cancel_ev = threading.Event()
            self._active_cancels[task_id] = cancel_ev

            if background:
                thread = threading.Thread(
                    target=self._execute_task_loop,
                    args=(task_id, cancel_ev),
                    name=f"TaskRunner-{task_id}",
                    daemon=True,
                )
                self._active_threads[task_id] = thread
                thread.start()
                return task
            else:
                self._active_threads[task_id] = threading.current_thread()

        self._execute_task_loop(task_id, cancel_ev)
        return self.store.get_task(task_id) or task

    def _execute_task_loop(self, task_id: str, cancel_ev: threading.Event) -> None:
        """Main execution loop for a task, evaluating DAG dependencies step-by-step."""
        try:
            task = self.store.get_task(task_id)
            if not task:
                return

            # Atomic task claiming to prevent concurrent execution races across threads or processes
            claimed = self.store.claim_task(
                task_id,
                expected_statuses=(TaskStatus.QUEUED, TaskStatus.PAUSED, TaskStatus.RUNNING),
            )
            if not claimed:
                refreshed = self.store.get_task(task_id)
                if not refreshed or refreshed.status not in (TaskStatus.RUNNING, TaskStatus.QUEUED, TaskStatus.PAUSED):
                    logger.info("Task %s could not be claimed (status: %s). Exiting loop.", task_id, getattr(refreshed, "status", None))
                    return

            # Pre-execution plan validation check
            owner_id = task.metadata.get("owner_id") or task.metadata.get("agent_id") or "_default"
            try:
                self.validate_plan(task.steps, owner_id=owner_id)
            except ValueError as exc:
                logger.error("Task %s failed pre-execution plan validation: %s", task_id, exc)
                for s in task.steps:
                    if s.status == StepStatus.PENDING:
                        s.status = StepStatus.FAILED
                        s.error = str(exc)
                        s.finished_at = time.time()
                        self.store.save_step(s)
                self.store.update_task_status(task_id, TaskStatus.FAILED, error=str(exc))
                self._emit_event("task_failed", {"task_id": task_id, "error": str(exc)})
                return

            self._emit_event("task_started", {"task_id": task_id})

            while True:
                if cancel_ev.is_set():
                    logger.info("Task %s cancelled by execution signal.", task_id)
                    self._handle_cancellation(task_id)
                    return

                # Refresh task and steps from persistent store
                task = self.store.get_task(task_id)
                if not task:
                    return

                # Check if task was paused or cancelled externally
                if task.status == TaskStatus.PAUSED:
                    logger.info("Task %s is paused. Halting loop.", task_id)
                    return
                if task.status == TaskStatus.CANCELLED:
                    self._handle_cancellation(task_id)
                    return
                if task.status == TaskStatus.WAITING_APPROVAL:
                    logger.info("Task %s is waiting for approval. Halting loop.", task_id)
                    return

                # Find next executable steps
                steps = task.steps
                step_map = {s.step_id: s for s in steps}

                # Check for completion
                all_done = True
                for s in steps:
                    if s.status != StepStatus.COMPLETED:
                        all_done = False
                        break

                if all_done:
                    self.store.update_task_status(task_id, TaskStatus.COMPLETED)
                    self._emit_event("task_completed", {"task_id": task_id})
                    self._on_task_completed(task)
                    return

                # Find candidate steps whose dependencies are all COMPLETED
                executable_step: Optional[TaskStep] = None
                for s in steps:
                    if s.status == StepStatus.PENDING:
                        # Check dependencies
                        deps_ok = True
                        for dep_id in s.dependencies:
                            dep = step_map.get(dep_id)
                            if not dep or dep.status != StepStatus.COMPLETED:
                                deps_ok = False
                                if dep and dep.status in (StepStatus.FAILED, StepStatus.CANCELLED, StepStatus.SKIPPED):
                                    # Downstream dependency cannot run! Mark skipped
                                    s.status = StepStatus.SKIPPED
                                    s.error = f"Dependency '{dep_id}' was {dep.status.value}"
                                    self.store.save_step(s)
                                break
                        if deps_ok and s.status == StepStatus.PENDING:
                            executable_step = s
                            break

                if executable_step is None:
                    # No pending step can execute. Check if any step failed or is waiting
                    has_failed = any(s.status == StepStatus.FAILED for s in steps)
                    has_waiting = any(s.status == StepStatus.WAITING_APPROVAL for s in steps)
                    if has_waiting:
                        self.store.update_task_status(task_id, TaskStatus.WAITING_APPROVAL)
                        return
                    if any(s.status == StepStatus.RUNNING for s in steps):
                        time.sleep(0.05)
                        continue
                    if has_failed:
                        self.store.update_task_status(
                            task_id, TaskStatus.FAILED, error="One or more steps failed."
                        )
                        self._emit_event("task_failed", {"task_id": task_id})
                        self._on_task_failed(task)
                        return
                    # All done or skipped
                    self.store.update_task_status(task_id, TaskStatus.COMPLETED)
                    self._emit_event("task_completed", {"task_id": task_id})
                    self._on_task_completed(task)
                    return

                # Update current step index
                self.store.update_task_status(
                    task_id, TaskStatus.RUNNING, current_step_index=executable_step.step_index
                )

                # Execute this step
                step_res = self._execute_step(task, executable_step, cancel_ev)
                if step_res == StepStatus.WAITING_APPROVAL:
                    # Halt loop until approval
                    return
                elif step_res in (StepStatus.FAILED, StepStatus.CANCELLED):
                    # Check if error is fatal
                    task_after = self.store.get_task(task_id)
                    if task_after and task_after.status in (TaskStatus.FAILED, TaskStatus.CANCELLED):
                        return

        except Exception as exc:
            logger.exception("Fatal error in task loop for %s: %s", task_id, exc)
            self.store.update_task_status(task_id, TaskStatus.FAILED, error=str(exc))
            self._emit_event("task_failed", {"task_id": task_id, "error": str(exc)})
        finally:
            with self._lock:
                self._active_cancels.pop(task_id, None)
                self._active_threads.pop(task_id, None)

    # ------------------------------------------------------------------
    # 3. Step Execution, Safety Kernel Gating & Verification
    # ------------------------------------------------------------------

    def _execute_step(
        self,
        task: TaskRecord,
        step: TaskStep,
        cancel_ev: threading.Event,
    ) -> StepStatus:
        """Execute a single step with safety checks, idempotency, bounded retries, and verification."""
        if cancel_ev.is_set():
            step.status = StepStatus.CANCELLED
            self.store.save_step(step)
            return StepStatus.CANCELLED

        # Defense-in-depth: if step has an uncertain external outcome, refuse to repeat without force_retry
        if step.safety_decision and step.safety_decision.get("uncertain_external_action"):
            if not step.safety_decision.get("force_retry_authorized") and step.status != StepStatus.COMPLETED:
                logger.warning(
                    "Step %s has uncertain external action without force_retry authorization. Halting to prevent duplicate side effects.",
                    step.step_id,
                )
                step.status = StepStatus.WAITING_APPROVAL
                self.store.save_step(step)
                self.store.update_task_status(task.task_id, TaskStatus.WAITING_APPROVAL)
                return StepStatus.WAITING_APPROVAL

        # Step is now running
        step.status = StepStatus.RUNNING
        step.started_at = step.started_at or time.time()
        self.store.save_step(step)
        self._emit_event("step_started", {"task_id": task.task_id, "step_id": step.step_id})

        # --- 0. Sequential Reasoning & Context Chaining ---
        completed_steps: Dict[str, TaskStep] = {}
        all_steps = self.store.get_steps_for_task(task.task_id)
        for s in all_steps:
            if s.status == StepStatus.COMPLETED:
                completed_steps[s.step_id] = s
                completed_steps[f"s{s.step_index + 1}"] = s
                completed_steps[str(s.step_index + 1)] = s

        canonical_name, handler, schema = self.resolve_tool_handler(step.tool_name)
        if completed_steps and step.tool_args:
            step.tool_args = self.intelligence.resolve_sequential_context(
                step, completed_steps, schema=schema
            )

        # --- 1. Tool Argument Validation & Missing Information Detection ---
        val_res = self.intelligence.validate_tool_arguments(
            canonical_name or step.tool_name,
            step.tool_args,
            schema=schema,
        )

        if val_res.has_missing_essential_info:
            missing_str = ", ".join(f"'{f}'" for f in val_res.missing_fields)
            prompt_user = (
                f"Step '{step.title}' requires tool '{step.tool_name}' with missing essential parameter(s): {missing_str}. "
                "Please specify the required information to proceed."
            )
            logger.warning("Step %s missing essential information: %s", step.step_id, missing_str)
            step.status = StepStatus.WAITING_APPROVAL
            step.error = f"Missing essential parameter(s): {missing_str}. Please provide tool arguments."
            step.safety_decision = {
                "requires_user_input": True,
                "missing_fields": val_res.missing_fields,
                "prompt": prompt_user,
                "tool_name": step.tool_name,
                "schema": schema,
            }
            self.store.save_step(step)
            self.store.update_task_status(task.task_id, TaskStatus.WAITING_APPROVAL, error=step.error)
            self._emit_event(
                "waiting_user_input",
                {
                    "task_id": task.task_id,
                    "step_id": step.step_id,
                    "tool": step.tool_name,
                    "missing_fields": val_res.missing_fields,
                    "prompt": prompt_user,
                    "schema": schema,
                },
            )
            return StepStatus.WAITING_APPROVAL

        if not val_res.is_valid:
            step.status = StepStatus.FAILED
            step.error = f"Invalid tool arguments for '{step.tool_name}': {'; '.join(val_res.errors)}"
            step.finished_at = time.time()
            self.store.save_step(step)
            self.store.update_task_status(task.task_id, TaskStatus.FAILED, error=step.error)
            self._emit_event("step_failed", {"task_id": task.task_id, "step_id": step.step_id, "error": step.error})
            return StepStatus.FAILED

        # --- 2. RBAC Capability Policy Enforcement ---
        if self.capability_policy:
            owner_id = task.metadata.get("owner_id") or task.metadata.get("agent_id") or "_default"
            canonical_name, _, _ = self.resolve_tool_handler(step.tool_name)
            caps = DEFAULT_TOOL_CAPABILITIES.get(canonical_name.lower()) or DEFAULT_TOOL_CAPABILITIES.get(step.tool_name.lower())
            if caps is None:
                caps = [Capability.TOOL_INVOKE.value]
            for cap in caps:
                cap_val = cap.value if hasattr(cap, "value") else str(cap)
                if not self.capability_policy.check(owner_id, cap_val, step.tool_name):
                    step.status = StepStatus.FAILED
                    step.error = f"Capability denied by policy: agent/owner '{owner_id}' lacks capability '{cap_val}' for tool '{step.tool_name}'"
                    step.finished_at = time.time()
                    self.store.save_step(step)
                    self.store.update_task_status(task.task_id, TaskStatus.FAILED, error=step.error)
                    self._emit_event(
                        "capability_denied",
                        {"task_id": task.task_id, "step_id": step.step_id, "capability": cap_val, "tool": step.tool_name},
                    )
                    return StepStatus.FAILED

        # --- A. Safety Kernel Evaluation ---
        action_type, target = self._map_to_safety_action(step)
        decision = self.kernel.evaluate(action_type, target=target, params=step.tool_args)

        if decision.effect == ActionEffect.BLOCK:
            step.status = StepStatus.FAILED
            step.error = f"Blocked by Safety Kernel: {decision.reason}"
            step.safety_decision = decision.to_dict()
            step.finished_at = time.time()
            self.store.save_step(step)
            self.store.update_task_status(task.task_id, TaskStatus.FAILED, error=step.error)
            self._emit_event("safety_block", {"task_id": task.task_id, "step_id": step.step_id, "reason": decision.reason})
            return StepStatus.FAILED

        if decision.effect in (ActionEffect.ASK, ActionEffect.ASK_WITH_CODE):
            # Check if this step already has a valid approval token bound to exact action & arguments fingerprint
            is_approved = False
            if step.approval_token:
                is_approved = self.kernel.code_mgr.is_token_valid(step.approval_token, decision.fingerprint)
                if not is_approved:
                    logger.warning(
                        "Step %s approval token %s invalid or action arguments modified (fingerprint mismatch: %s)",
                        step.step_id,
                        step.approval_token,
                        decision.fingerprint,
                    )

            if not is_approved:
                step.status = StepStatus.WAITING_APPROVAL
                step.safety_decision = decision.to_dict()
                step.requires_code = decision.requires_code
                self.store.save_step(step)
                self.store.update_task_status(task.task_id, TaskStatus.WAITING_APPROVAL)
                self._emit_event(
                    "waiting_approval",
                    {
                        "task_id": task.task_id,
                        "step_id": step.step_id,
                        "risk_level": decision.risk_level.value,
                        "requires_code": decision.requires_code,
                        "reason": decision.reason,
                    },
                )
                return StepStatus.WAITING_APPROVAL

        # --- B. Idempotency & Reconciliation Pre-Check ---
        if self._reconcile_step(step):
            logger.info("Step %s already completed (reconciled via idempotency).", step.step_id)
            step.status = StepStatus.COMPLETED
            step.actual_output = step.actual_output or "Action verified as already completed (idempotency reconciliation)."
            step.finished_at = time.time()
            self.store.save_step(step)
            self._emit_event("step_completed", {"task_id": task.task_id, "step_id": step.step_id, "reconciled": True})
            return StepStatus.COMPLETED

        # --- C. Bounded Retries Loop ---
        while step.retry_count <= step.max_retries:
            if cancel_ev.is_set():
                step.status = StepStatus.CANCELLED
                self.store.save_step(step)
                return StepStatus.CANCELLED

            try:
                # Dispatch tool
                result = self._dispatch_tool(step.tool_name, step.tool_args)

                # --- D. Verification ---
                verified, v_error, artifacts = self._verify_step_result(step, result)

                if verified:
                    step.status = StepStatus.COMPLETED
                    step.actual_output = result.content
                    step.error = None
                    step.artifacts = artifacts
                    step.finished_at = time.time()
                    self.store.save_step(step)
                    self._emit_event("step_completed", {"task_id": task.task_id, "step_id": step.step_id})
                    if self.skill_manager is not None:
                        try:
                            self.workflow_skill_learner.mark_skill_execution_result(
                                step.tool_name,
                                success=True,
                            )
                        except Exception:
                            pass
                    return StepStatus.COMPLETED
                else:
                    step.error = v_error
                    if self.skill_manager is not None:
                        try:
                            self.workflow_skill_learner.mark_skill_execution_result(
                                step.tool_name,
                                success=False,
                                error_reason=v_error,
                            )
                        except Exception:
                            pass
                    fail_cat = self.intelligence.classify_failure(step, v_error or "")
                    # If verification failed due to uncertain external failure, do not blindly retry
                    if fail_cat == FailureCategory.UNCERTAIN_EXTERNAL or self._is_uncertain_failure(step, v_error or ""):
                        if self._reconcile_step(step):
                            step.status = StepStatus.COMPLETED
                            step.actual_output = step.actual_output or "Reconciled external action outcome as completed."
                            step.finished_at = time.time()
                            self.store.save_step(step)
                            self._emit_event("step_completed", {"task_id": task.task_id, "step_id": step.step_id, "reconciled": True})
                            return StepStatus.COMPLETED

                        step.status = StepStatus.WAITING_APPROVAL
                        duplicate_risk_msg = (
                            f"External action '{step.tool_name}' verification failed with uncertain outcome ({v_error}). "
                            "Duplicate-Action Risk: Blindly retrying could result in duplicate external side effects "
                            "(e.g., duplicate message sends, multiple financial charges, or double webhooks). "
                            "Verify external state manually and approve with resolution='mark_completed' or resolution='force_retry'."
                        )
                        step.error = f"Uncertain external action outcome ({v_error}). Duplicate-action risk: manual review required."
                        step.safety_decision = {
                            "uncertain_external_action": True,
                            "tool_name": step.tool_name,
                            "error": v_error,
                            "duplicate_action_risk": duplicate_risk_msg,
                            "force_retry_warning": (
                                "WARNING: Force-retrying may repeat the external action and cause duplicate messages, "
                                "requests, or other side effects. Explicit operator confirmation is required."
                            ),
                            "reconcile_attempted": True,
                            "reconcile_succeeded": False,
                            "force_retry_authorized": False,
                        }
                        step.finished_at = time.time()
                        self.store.save_step(step)
                        self.store.update_task_status(task.task_id, TaskStatus.WAITING_APPROVAL, error=step.error)
                        self._emit_event(
                            "uncertain_failure",
                            {
                                "task_id": task.task_id,
                                "step_id": step.step_id,
                                "error": step.error,
                                "duplicate_action_risk": duplicate_risk_msg,
                            },
                        )
                        return StepStatus.WAITING_APPROVAL
                    elif fail_cat == FailureCategory.DETERMINISTIC:
                        logger.warning(
                            "Step %s encountered deterministic failure (%s). Failing immediately without retry.",
                            step.step_id,
                            v_error,
                        )
                        break

                    step.retry_count += 1
                    logger.warning(
                        "Step %s verification failed (attempt %d/%d): %s",
                        step.step_id,
                        step.retry_count,
                        step.max_retries,
                        v_error,
                    )
            except Exception as exc:
                err_str = f"Tool execution error: {exc}"
                step.error = err_str

                fail_cat = self.intelligence.classify_failure(step, err_str, exc)
                # Check if this failure leaves external side-effects uncertain
                if fail_cat == FailureCategory.UNCERTAIN_EXTERNAL or self._is_uncertain_failure(step, err_str, exc):
                    logger.warning(
                        "Step %s encountered uncertain external failure: %s. Checking reconciliation before retrying.",
                        step.step_id,
                        err_str,
                    )
                    # Attempt reconciliation to see if it actually succeeded
                    if self._reconcile_step(step):
                        logger.info("Step %s reconciled as succeeded despite error.", step.step_id)
                        step.status = StepStatus.COMPLETED
                        step.actual_output = step.actual_output or "Reconciled external action outcome as completed."
                        step.finished_at = time.time()
                        self.store.save_step(step)
                        self._emit_event("step_completed", {"task_id": task.task_id, "step_id": step.step_id, "reconciled": True})
                        return StepStatus.COMPLETED

                    # Outcome is truly uncertain: halt blind retries to prevent duplicate side effects!
                    step.status = StepStatus.WAITING_APPROVAL
                    duplicate_risk_msg = (
                        f"External action '{step.tool_name}' timed out or disconnected ({err_str}). "
                        "Duplicate-Action Risk: Blindly retrying could result in duplicate external side effects "
                        "(e.g., duplicate message sends, multiple financial charges, or double webhooks). "
                        "Verify external state manually and approve with resolution='mark_completed' or resolution='force_retry'."
                    )
                    step.error = f"Uncertain external action outcome ({err_str}). Duplicate-action risk: manual review required."
                    step.safety_decision = {
                        "uncertain_external_action": True,
                        "tool_name": step.tool_name,
                        "error": err_str,
                        "duplicate_action_risk": duplicate_risk_msg,
                        "force_retry_warning": (
                            "WARNING: Force-retrying may repeat the external action and cause duplicate messages, "
                            "requests, or other side effects. Explicit operator confirmation is required."
                        ),
                        "reconcile_attempted": True,
                        "reconcile_succeeded": False,
                        "force_retry_authorized": False,
                    }
                    step.finished_at = time.time()
                    self.store.save_step(step)
                    self.store.update_task_status(task.task_id, TaskStatus.WAITING_APPROVAL, error=step.error)
                    self._emit_event(
                        "uncertain_failure",
                        {
                            "task_id": task.task_id,
                            "step_id": step.step_id,
                            "error": step.error,
                            "duplicate_action_risk": duplicate_risk_msg,
                        },
                    )
                    return StepStatus.WAITING_APPROVAL
                elif fail_cat == FailureCategory.DETERMINISTIC:
                    logger.warning(
                        "Step %s encountered deterministic exception (%s). Failing immediately without retry.",
                        step.step_id,
                        exc,
                    )
                    break

                step.retry_count += 1
                logger.warning(
                    "Step %s error (attempt %d/%d): %s",
                    step.step_id,
                    step.retry_count,
                    step.max_retries,
                    exc,
                )

            # Check if retries remain
            if step.retry_count <= step.max_retries:
                self.store.save_step(step)
                time.sleep(0.05 * step.retry_count)  # Small backoff
            else:
                break

        # Retries exhausted: honest failure report
        step.status = StepStatus.FAILED
        step.finished_at = time.time()
        self.store.save_step(step)
        self.store.update_task_status(
            task.task_id,
            TaskStatus.FAILED,
            error=f"Step '{step.title}' failed: {step.error}",
        )
        self._emit_event("step_failed", {"task_id": task.task_id, "step_id": step.step_id, "error": step.error})
        self._on_task_failed(task)
        return StepStatus.FAILED

    def _map_to_safety_action(self, step: TaskStep) -> Tuple[str, str]:
        """Map tool and step arguments to SafetyKernel action_type and target."""
        name = step.tool_name.lower()
        args = step.tool_args or {}

        target = str(args.get("path") or args.get("command") or args.get("target") or args.get("url") or step.title)

        if any(w in name for w in ("delete", "remove", "unlink", "cleanup", "rm")):
            return "delete", target
        if any(w in name for w in ("write", "create_file", "append", "modify")):
            return "write", target
        if any(w in name for w in ("shell", "exec", "cmd", "bash", "powershell")):
            return "shell", target
        if any(w in name for w in ("app_launch", "launch_app", "open_app")):
            return "app_launch", target
        if any(w in name for w in ("http", "fetch", "webhook", "network", "api", "request")):
            return "network", target

        # If tool corresponds to a registered skill, map safety action from skill manifest
        if self.skill_manager is not None:
            skill_names = self.skill_manager.skill_names()
            target_skill = step.tool_name if step.tool_name in skill_names else None
            if target_skill:
                try:
                    manifest = self.skill_manager.resolve(target_skill)
                    caps = set(manifest.required_capabilities or [])
                    inner_tools = " ".join(s.tool_name.lower() for s in manifest.steps)
                    if "file:delete" in caps or any(w in inner_tools for w in ("delete", "remove", "unlink", "rm")):
                        return "delete", target
                    if "file:write" in caps or any(w in inner_tools for w in ("write", "create_file", "modify", "save")):
                        return "write", target
                    if "code:execute" in caps or any(w in inner_tools for w in ("shell", "exec", "cmd", "bash", "powershell")):
                        return "shell", target
                except Exception:
                    pass

        return "query", target

    def _is_uncertain_failure(
        self,
        step: TaskStep,
        error_msg: str,
        exc: Optional[Exception] = None,
    ) -> bool:
        """Determine if an execution failure has an uncertain external outcome.

        For external actions (HTTP, channels, webhooks, payments, shell), network timeouts
        or disconnects leave the server-side execution status unknown. Blindly retrying could
        lead to duplicate side effects (e.g., duplicate message sends, double payments).
        """
        tool = step.tool_name.lower()
        external_tools = {
            "http_request",
            "channel_send",
            "webhook",
            "shell_exec",
            "cmd_exec",
            "bash",
            "powershell",
            "send_message",
            "send_email",
            "execute_pending_actions",
        }
        is_external = tool in external_tools or any(
            ext in tool for ext in ("send", "post", "webhook", "payment", "dispatch")
        )
        if not is_external:
            return False

        lower_err = error_msg.lower()
        uncertainty_signals = (
            "timeout",
            "timed out",
            "time out",
            "connection reset",
            "connection aborted",
            "connection closed",
            "broken pipe",
            "econnreset",
            "gateway timeout",
            "504",
            "502",
            "uncertain",
        )
        if any(sig in lower_err for sig in uncertainty_signals):
            return True
        if exc is not None and isinstance(
            exc, (TimeoutError, ConnectionResetError, ConnectionAbortedError)
        ):
            return True
        return False

    def _reconcile_step(self, step: TaskStep) -> bool:
        """Check whether an uncertain external action or interrupted step already succeeded."""
        tool = step.tool_name.lower()
        args = step.tool_args or {}

        # 1. Custom reconciler check
        if tool in self._custom_reconcilers:
            try:
                return self._custom_reconcilers[tool](step)
            except Exception:
                pass

        # 2. Filesystem write reconciliation: check if target file exists with valid content
        if tool in ("file_write", "create_file") and "path" in args:
            path = Path(args["path"])
            if path.is_file():
                content = args.get("content")
                if content is not None:
                    try:
                        existing = path.read_text(encoding="utf-8")
                        if existing == content:
                            step.artifacts = [{"path": str(path.resolve()), "type": "file", "verified": True}]
                            return True
                    except Exception:
                        pass
                else:
                    step.artifacts = [{"path": str(path.resolve()), "type": "file", "verified": True}]
                    return True

        return False

    def _dispatch_tool(self, tool_name: str, args: Dict[str, Any]) -> ToolResult:
        """Invoke a tool through custom registry, generic mapping, or core ToolRegistry."""
        canonical_name, handler, _ = self.resolve_tool_handler(tool_name)
        if handler is not None:
            return handler(**args)

        return ToolResult(
            tool_name=tool_name,
            content=f"Unknown or uninstalled tool: '{tool_name}'",
            success=False,
        )

    def _verify_step_result(
        self, step: TaskStep, result: ToolResult
    ) -> Tuple[bool, Optional[str], List[Dict[str, Any]]]:
        """Verify step results honestly without fabricating success."""
        ver_res = self.intelligence.verify_result(step, result)
        return ver_res.verified, ver_res.error, ver_res.artifacts

    def _on_task_completed(self, task: TaskRecord) -> None:
        """Trigger experience learning and reusable skill extraction upon verified task success."""
        try:
            t = self.store.get_task(task.task_id) or task
            if self.memory_store is not None:
                self.experience_learner.learn_from_task(t)
            if self.skill_manager is not None:
                self.workflow_skill_learner.learn_skill_from_task(t)
        except Exception as exc:
            logger.warning("Error during post-task completion learning for %s: %s", task.task_id, exc)

    def _on_task_failed(self, task: TaskRecord) -> None:
        """Trigger experience learning upon task failure to record recurring failure lessons."""
        try:
            t = self.store.get_task(task.task_id) or task
            if self.memory_store is not None:
                self.experience_learner.learn_from_task(t)
        except Exception as exc:
            logger.warning("Error during post-task failure learning for %s: %s", task.task_id, exc)

    # ------------------------------------------------------------------
    # 4. Controls: Pause, Resume, Cancel, Approval
    # ------------------------------------------------------------------

    def pause_task(self, task_id: str) -> bool:
        """Pause a running task after the current in-flight step."""
        task = self.store.get_task(task_id)
        if not task or task.status not in (TaskStatus.RUNNING, TaskStatus.QUEUED):
            return False

        self.store.update_task_status(task_id, TaskStatus.PAUSED)
        self._emit_event("task_paused", {"task_id": task_id})
        return True

    def resume_task(self, task_id: str, background: bool = True) -> TaskRecord:
        """Resume a paused task. Refuses to resume if an uncertain external action is unresolved."""
        task = self.store.get_task(task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found.")

        # Guard: Check for any step with unresolved uncertain external action
        for s in task.steps:
            if s.safety_decision and s.safety_decision.get("uncertain_external_action"):
                if not s.safety_decision.get("force_retry_authorized") and s.status != StepStatus.COMPLETED:
                    raise ValueError(
                        f"Cannot blindly resume task '{task_id}': step '{s.step_id}' encountered an uncertain external "
                        f"outcome with duplicate-action risk. Resolve the step first via approve_step with resolution='mark_completed' or 'force_retry'."
                    )

        if task.status != TaskStatus.PAUSED:
            return task

        self.store.update_task_status(task_id, TaskStatus.RUNNING)
        self._emit_event("task_resumed", {"task_id": task_id})
        return self.run_task(task_id, background=background)

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a task and all non-completed steps."""
        task = self.store.get_task(task_id)
        if not task:
            return False

        with self._lock:
            cancel_ev = self._active_cancels.get(task_id)
            if cancel_ev:
                cancel_ev.set()

        self._handle_cancellation(task_id)
        return True

    def _handle_cancellation(self, task_id: str) -> None:
        """Mark task and all pending/running/waiting steps as CANCELLED."""
        self.store.update_task_status(task_id, TaskStatus.CANCELLED, error="Task was cancelled by user.")
        steps = self.store.get_steps_for_task(task_id)
        for s in steps:
            if s.status in (StepStatus.PENDING, StepStatus.RUNNING, StepStatus.WAITING_APPROVAL):
                s.status = StepStatus.CANCELLED
                s.finished_at = time.time()
                self.store.save_step(s)
        self._emit_event("task_cancelled", {"task_id": task_id})

    def approve_step(
        self,
        task_id: str,
        step_id: str,
        safety_code: Optional[str] = None,
        token: Optional[str] = None,
        resolution: Optional[str] = None,
        confirm_duplicate_risk: bool = False,
        tool_args: Optional[Dict[str, Any]] = None,
        auto_run: bool = True,
    ) -> bool:
        """Authorize a waiting_approval step using token and/or verified safety code.

        For steps paused due to uncertain external action failure, caller MUST provide
        resolution='mark_completed' (confirmed succeeded externally) or resolution='force_retry'
        (confirmed safe to re-execute). Blind approvals are rejected.
        When resolution='force_retry', explicit operator confirmation (confirm_duplicate_risk=True)
        is required because retrying an uncertain external action may cause duplicate messages,
        requests, charges, or other side effects.
        """
        step = self.store.get_step(step_id)
        if not step or step.status not in (StepStatus.WAITING_APPROVAL, StepStatus.PENDING):
            return False

        # --- Handle User-Provided Arguments for Missing Information ---
        if tool_args and isinstance(tool_args, dict):
            canonical_name, _, schema = self.resolve_tool_handler(step.tool_name)
            merged = dict(step.tool_args or {})
            merged.update(tool_args)
            val_res = self.intelligence.validate_tool_arguments(
                canonical_name or step.tool_name,
                merged,
                schema=schema,
            )
            if not val_res.is_valid or val_res.has_missing_essential_info:
                err_msg = "; ".join(val_res.errors) or f"Missing required parameter(s): {', '.join(val_res.missing_fields)}"
                raise ValueError(f"Invalid tool arguments: {err_msg}")
            step.tool_args = merged
            if step.safety_decision and step.safety_decision.get("requires_user_input"):
                step.safety_decision["requires_user_input"] = False
            step.error = None

        # --- Handle Uncertain External Action Resolution ---
        if step.safety_decision and step.safety_decision.get("uncertain_external_action"):
            if not resolution:
                raise ValueError(
                    f"Step '{step_id}' encountered an uncertain external action outcome with duplicate-action risk. "
                    "Blind approval is prohibited. You must provide resolution='mark_completed' (if verified externally) "
                    "or resolution='force_retry' (if verified safe to re-execute with explicit confirmation)."
                )

            clean_res = resolution.strip().lower()
            if clean_res in ("mark_completed", "completed", "already_succeeded"):
                logger.info("Step %s approved with resolution 'mark_completed'. Marking complete without re-executing.", step_id)
                step.status = StepStatus.COMPLETED
                step.actual_output = "Manually verified external outcome as completed without repeating side effect."
                step.error = None
                step.finished_at = time.time()
                step.safety_decision["uncertain_resolved"] = "mark_completed"
                self.store.save_step(step)
                self.store.update_task_status(task_id, TaskStatus.RUNNING)
                self._emit_event("step_approved", {"task_id": task_id, "step_id": step_id, "resolution": "mark_completed"})
                if auto_run:
                    self.run_task(task_id, background=True)
                return True

            elif clean_res in ("force_retry", "retry"):
                if not confirm_duplicate_risk:
                    raise ValueError(
                        f"Step '{step_id}' force_retry requires explicit operator confirmation (confirm_duplicate_risk=True). "
                        "WARNING: Forcing a retry of an uncertain external action may repeat the action on the external system, "
                        "potentially causing duplicate messages, redundant API requests, multiple financial charges, or other unintended side effects."
                    )
                logger.info("Step %s approved with resolution 'force_retry' (operator confirmed duplicate risk). Authorizing re-execution.", step_id)
                step.safety_decision["force_retry_authorized"] = True
                step.safety_decision["uncertain_resolved"] = "force_retry"
                step.safety_decision["operator_confirmed_duplicate_risk"] = True
                # Fall through to proceed with token/safety code validation & transition to PENDING
            else:
                raise ValueError(
                    f"Invalid resolution '{resolution}'. Must be 'mark_completed' or 'force_retry'."
                )

        # Re-evaluate Safety Kernel on exact current step action and arguments
        action_type, target = self._map_to_safety_action(step)
        decision = self.kernel.evaluate(action_type, target=target, params=step.tool_args)
        if decision.effect == ActionEffect.BLOCK:
            raise ValueError(f"Step is blocked by safety policy and cannot be approved: {decision.reason}")

        # If safety code required, verify with kernel code manager
        if decision.requires_code or step.requires_code:
            if not safety_code:
                raise ValueError("Safety code is required to authorize this high-risk step.")
            if not self.kernel.code_mgr.verify_code(safety_code):
                raise ValueError("Invalid safety code.")

        # If caller provided an action token, verify it matches current action & arguments fingerprint
        if token:
            if not self.kernel.code_mgr.is_token_valid(token, decision.fingerprint):
                raise ValueError("Supplied action token is invalid or does not match the target/arguments.")
        else:
            token = self.kernel.code_mgr.generate_action_token(decision.fingerprint, ttl_seconds=300.0)

        step.approval_token = token
        # Preserve uncertain_external_action flags in safety_decision if present
        curr_sd = dict(step.safety_decision or {})
        curr_sd.update(decision.to_dict())
        step.safety_decision = curr_sd

        step.status = StepStatus.PENDING  # Ready for immediate re-execution
        self.store.save_step(step)

        # Transition task back to RUNNING and optionally trigger execution
        self.store.update_task_status(task_id, TaskStatus.RUNNING)
        self._emit_event("step_approved", {"task_id": task_id, "step_id": step_id})
        if auto_run:
            self.run_task(task_id, background=True)
        return True

    def submit_step_input(
        self,
        task_id: str,
        step_id: str,
        tool_args: Dict[str, Any],
        auto_run: bool = True,
    ) -> Dict[str, Any]:
        """Submit user-supplied arguments for a step waiting for missing parameters.

        Validates against the actual tool schema, resolves sequential runtime context,
        re-runs RBAC capability policy and Safety Kernel checks.
        Never treats supplying missing information as automatic authorization for a risky action.
        """
        step = self.store.get_step(step_id)
        if not step:
            raise ValueError(f"Step '{step_id}' not found.")
        task = self.store.get_task(task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found.")

        if step.status not in (StepStatus.WAITING_APPROVAL, StepStatus.PENDING):
            raise ValueError(
                f"Step '{step_id}' is not waiting for user input or approval (current status: {step.status.value})."
            )

        if not isinstance(tool_args, dict):
            raise ValueError(f"tool_args must be a dictionary, got {type(tool_args).__name__}.")

        canonical_name, handler, schema = self.resolve_tool_handler(step.tool_name)

        # Merge tool arguments
        merged_args = dict(step.tool_args or {})
        merged_args.update(tool_args)

        # Sequential context resolution if placeholders/references exist
        completed_steps: Dict[str, TaskStep] = {}
        all_steps = self.store.get_steps_for_task(task_id)
        for s in all_steps:
            if s.status == StepStatus.COMPLETED:
                completed_steps[s.step_id] = s
                completed_steps[f"s{s.step_index + 1}"] = s
                completed_steps[str(s.step_index + 1)] = s

        step_for_ctx = TaskStep(
            step_id=step.step_id,
            task_id=step.task_id,
            step_index=step.step_index,
            title=step.title,
            tool_name=step.tool_name,
            tool_args=merged_args,
        )
        if completed_steps:
            merged_args = self.intelligence.resolve_sequential_context(
                step_for_ctx, completed_steps, schema=schema
            )

        # Validate against actual tool schema
        val_res = self.intelligence.validate_tool_arguments(
            canonical_name or step.tool_name,
            merged_args,
            schema=schema,
        )
        if not val_res.is_valid or val_res.has_missing_essential_info:
            err_msg = "; ".join(val_res.errors) or f"Missing required parameter(s): {', '.join(val_res.missing_fields)}"
            step.error = f"Invalid tool arguments: {err_msg}"
            self.store.save_step(step)
            raise ValueError(f"Validation failed: {err_msg}")

        step.tool_args = merged_args
        step.error = None

        # Re-verify RBAC capability policy
        if self.capability_policy:
            owner_id = task.metadata.get("owner_id") or task.metadata.get("agent_id") or "_default"
            caps = DEFAULT_TOOL_CAPABILITIES.get(canonical_name.lower()) or DEFAULT_TOOL_CAPABILITIES.get(step.tool_name.lower())
            if caps is None:
                caps = [Capability.TOOL_INVOKE.value]
            for cap in caps:
                cap_val = cap.value if hasattr(cap, "value") else str(cap)
                if not self.capability_policy.check(owner_id, cap_val, step.tool_name):
                    step.status = StepStatus.FAILED
                    step.error = f"Capability denied by policy: owner '{owner_id}' lacks capability '{cap_val}' for tool '{step.tool_name}'"
                    step.finished_at = time.time()
                    self.store.save_step(step)
                    self.store.update_task_status(task_id, TaskStatus.FAILED, error=step.error)
                    self._emit_event(
                        "capability_denied",
                        {"task_id": task_id, "step_id": step.step_id, "capability": cap_val, "tool": step.tool_name},
                    )
                    raise ValueError(step.error)

        # Re-evaluate Safety Kernel on actual target and arguments
        action_type, target = self._map_to_safety_action(step)
        decision = self.kernel.evaluate(action_type, target=target, params=step.tool_args)

        if decision.effect == ActionEffect.BLOCK:
            step.status = StepStatus.FAILED
            step.error = f"Blocked by Safety Kernel: {decision.reason}"
            step.safety_decision = decision.to_dict()
            step.finished_at = time.time()
            self.store.save_step(step)
            self.store.update_task_status(task_id, TaskStatus.FAILED, error=step.error)
            self._emit_event("step_failed", {"task_id": task_id, "step_id": step.step_id, "error": step.error})
            raise ValueError(step.error)

        sd = decision.to_dict()
        sd["requires_user_input"] = False
        step.safety_decision = sd

        if decision.effect in (ActionEffect.ASK, ActionEffect.ASK_WITH_CODE):
            # Preserving security: Risky actions REQUIRE explicit operator approval!
            # Do NOT treat supplying missing input as automatic authorization.
            step.requires_code = decision.requires_code
            step.approval_token = None
            step.status = StepStatus.WAITING_APPROVAL
            self.store.save_step(step)
            self.store.update_task_status(task_id, TaskStatus.WAITING_APPROVAL)
            self._emit_event(
                "waiting_approval",
                {
                    "task_id": task_id,
                    "step_id": step.step_id,
                    "requires_code": decision.requires_code,
                    "decision": sd,
                },
            )
            return {
                "status": "waiting_approval",
                "task_id": task_id,
                "step_id": step_id,
                "requires_approval": True,
                "requires_code": decision.requires_code,
                "decision": sd,
            }

        # For safe tools (ALLOW effect): transition to PENDING and resume execution
        token = self.kernel.code_mgr.generate_action_token(decision.fingerprint, ttl_seconds=300.0)
        step.approval_token = token
        step.status = StepStatus.PENDING
        step.requires_code = False
        self.store.save_step(step)
        self.store.update_task_status(task_id, TaskStatus.RUNNING)
        self._emit_event("step_resumed", {"task_id": task_id, "step_id": step_id})

        if auto_run:
            self.run_task(task_id, background=True)

        return {
            "status": "pending",
            "task_id": task_id,
            "step_id": step_id,
            "resumed": True,
            "requires_approval": False,
        }

    def reject_step(self, task_id: str, step_id: str, reason: str = "") -> bool:
        """Reject authorization for a waiting_approval step, cancelling subsequent dependent steps."""
        step = self.store.get_step(step_id)
        if not step or step.status != StepStatus.WAITING_APPROVAL:
            return False

        step.status = StepStatus.FAILED
        step.error = f"Authorization rejected: {reason or 'User denied approval'}"
        step.finished_at = time.time()
        self.store.save_step(step)

        # Cancel remaining downstream dependent steps
        self.store.update_task_status(
            task_id, TaskStatus.FAILED, error=f"Task aborted: Step '{step.title}' was rejected."
        )
        self._emit_event("step_rejected", {"task_id": task_id, "step_id": step_id, "reason": reason})
        return True

    # ------------------------------------------------------------------
    # 5. Restart Recovery
    # ------------------------------------------------------------------

    def recover_interrupted_tasks(self) -> List[str]:
        """Scan SQLite store on runner startup and resume interrupted tasks without repeating completed steps."""
        interrupted = self.store.list_tasks(status=TaskStatus.RUNNING)
        queued = self.store.list_tasks(status=TaskStatus.QUEUED)
        candidates = interrupted + queued

        recovered_ids: List[str] = []
        for task in candidates:
            # Reconcile any step that was left in RUNNING when the app restarted
            for s in task.steps:
                if s.status == StepStatus.RUNNING:
                    # Check idempotency: did it complete before the crash?
                    if self._reconcile_step(s):
                        s.status = StepStatus.COMPLETED
                        s.actual_output = s.actual_output or "Reconciled after restart."
                        s.finished_at = time.time()
                        self.store.save_step(s)
                    else:
                        # Reset back to PENDING so it can be cleanly retried
                        s.status = StepStatus.PENDING
                        s.retry_count = min(s.retry_count + 1, s.max_retries)
                        self.store.save_step(s)

            # Reset task status to QUEUED if it was left in RUNNING so atomic claim succeeds
            if task.status == TaskStatus.RUNNING:
                self.store.update_task_status(task.task_id, TaskStatus.QUEUED)

            # Resume task execution in background
            self.run_task(task.task_id, background=True)
            recovered_ids.append(task.task_id)
            logger.info("Recovered interrupted task %s on runner startup.", task.task_id)

        return recovered_ids

    def join_all(self, timeout: float = 2.0) -> None:
        """Wait for all active background task runner threads to terminate."""
        with self._lock:
            threads = list(self._active_threads.values())
            for ev in self._active_cancels.values():
                ev.set()
        for t in threads:
            if t.is_alive():
                t.join(timeout=timeout)

    # ------------------------------------------------------------------
    # Telemetry
    # ------------------------------------------------------------------

    def _emit_event(self, event_name: str, payload: Dict[str, Any]) -> None:
        """Emit telemetry event via EventBus if available."""
        if self.bus:
            try:
                self.bus.publish(EventType.SCHEDULER_TASK_START, {"event": event_name, **payload})
            except Exception:
                pass
