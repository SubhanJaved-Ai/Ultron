"""Tool Execution Intelligence for Ultron.

Provides schema-grounded tool discovery, argument validation, missing-parameter
detection, sequential context chaining, result verification, and failure recovery
classification for Ultron's Persistent Task Runner and agents.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.security.capabilities import (
    DEFAULT_TOOL_CAPABILITIES,
    Capability,
    CapabilityPolicy,
)
from openjarvis.tasks.types import TaskStep
from openjarvis.tools._stubs import ToolSpec

logger = logging.getLogger(__name__)

# Canonical placeholders that indicate missing/unspecified information
_PLACEHOLDER_PATTERNS = (
    re.compile(r"^<[\w\s\-_]+>$"),           # <path>, <missing>, <insert_url>
    re.compile(r"^\[[\w\s\-_]+\]$"),         # [file_path], [api_key]
    re.compile(r"^(TODO|FIXME|YOUR_[\w_]+|UNKNOWN|MISSING|PLACEHOLDER)$", re.IGNORECASE),
)

_BUILTIN_TOOL_MODULE_MAP: Dict[str, Tuple[str, str]] = {
    "file_write": ("openjarvis.tools.file_write", "FileWriteTool"),
    "file_read": ("openjarvis.tools.file_read", "FileReadTool"),
    "shell_exec": ("openjarvis.tools.shell_exec", "ShellExecTool"),
    "http_request": ("openjarvis.tools.http_request", "HttpRequestTool"),
    "calculator": ("openjarvis.tools.calculator", "CalculatorTool"),
    "web_search": ("openjarvis.tools.web_search", "WebSearchTool"),
}

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


def _ensure_builtin_tools() -> None:
    """Ensure standard built-in tools are registered in ToolRegistry."""
    for tool_name, (mod_name, cls_name) in _BUILTIN_TOOL_MODULE_MAP.items():
        if not ToolRegistry.contains(tool_name):
            try:
                import importlib
                mod = sys.modules.get(mod_name) or importlib.import_module(mod_name)
                cls = getattr(mod, cls_name, None)
                if cls and not ToolRegistry.contains(tool_name):
                    ToolRegistry.register_value(tool_name, cls)
            except Exception as exc:
                logger.debug("Could not auto-register built-in tool '%s': %s", tool_name, exc)


class FailureCategory(str, Enum):
    """Categorization of tool execution failures to govern safe recovery."""
    TRANSIENT = "transient"
    DETERMINISTIC = "deterministic"
    UNCERTAIN_EXTERNAL = "uncertain_external"


@dataclass(slots=True)
class ValidationResult:
    """Result of validating tool arguments against its actual schema."""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    missing_fields: List[str] = field(default_factory=list)

    @property
    def has_missing_essential_info(self) -> bool:
        """True if any required parameter is missing or set to a placeholder."""
        return len(self.missing_fields) > 0


@dataclass(slots=True)
class VerificationResult:
    """Result of honestly inspecting a tool's output against success criteria."""
    verified: bool
    error: Optional[str] = None
    artifacts: List[Dict[str, Any]] = field(default_factory=list)


class ToolExecutionIntelligence:
    """Intelligent reasoning and execution engine for Ultron tools."""

    def __init__(
        self,
        runner: Optional[Any] = None,
        capability_policy: Optional[CapabilityPolicy] = None,
    ) -> None:
        self.runner = runner
        self.capability_policy = capability_policy

    # ----------------------------------------------------------------------
    # 1. Tool Discovery & Selection
    # ----------------------------------------------------------------------

    def discover_tools(self, owner_id: Optional[str] = None) -> Dict[str, ToolSpec]:
        """Discover all registered tool specifications and filter by capability policy."""
        _ensure_builtin_tools()
        specs: Dict[str, ToolSpec] = {}

        # 1. Built-in runner tools
        specs["think"] = ToolSpec(
            name="think",
            description="Internal reasoning or planning step. Has no side effects.",
            parameters={
                "type": "object",
                "properties": {
                    "thought": {
                        "type": "string",
                        "description": "Internal reasoning or thought content.",
                    }
                },
                "required": [],
            },
            category="cognition",
        )

        specs["delete_file"] = ToolSpec(
            name="delete_file",
            description="Safely delete or quarantine a file via the Safety Kernel.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to file to safely delete or quarantine.",
                    }
                },
                "required": ["path"],
            },
            category="filesystem",
            required_capabilities=["file:delete"],
        )

        specs["app_launch"] = ToolSpec(
            name="app_launch",
            description="Launch an application executable with Safety Kernel evaluation.",
            parameters={
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "Application name or binary to launch.",
                    },
                    "path": {
                        "type": "string",
                        "description": "Path to application executable.",
                    },
                    "target": {
                        "type": "string",
                        "description": "Target application name or path.",
                    },
                },
                "required": [],
            },
            category="system",
            required_capabilities=["system:admin"],
        )

        # 2. Custom tools registered on runner
        if self.runner is not None and hasattr(self.runner, "_custom_tools"):
            lock = getattr(self.runner, "_lock", None)
            custom_items: Dict[str, Callable[..., ToolResult]] = {}
            if lock:
                with lock:
                    custom_items = dict(self.runner._custom_tools)
            else:
                custom_items = dict(self.runner._custom_tools)

            for name, handler in custom_items.items():
                schema = getattr(handler, "schema", None) or {
                    "type": "object",
                    "properties": {},
                    "required": [],
                }
                desc = getattr(handler, "__doc__", "") or f"Custom runner tool '{name}'."
                specs[name] = ToolSpec(
                    name=name,
                    description=desc.strip(),
                    parameters=schema,
                    category="custom",
                )

        # 2b. Skills registered on runner's skill_manager
        if self.runner is not None and getattr(self.runner, "skill_manager", None) is not None:
            sm = self.runner.skill_manager
            learner = getattr(self.runner, "workflow_skill_learner", None)
            for skill_name in sm.skill_names():
                try:
                    manifest = sm.resolve(skill_name)
                    # Check approval status: unapproved learned skills must NEVER appear in normal discovery
                    if learner is not None:
                        if not learner.is_skill_approved(manifest):
                            continue
                        is_healthy, _ = learner.validate_skill_health(manifest)
                        if not is_healthy:
                            continue
                    else:
                        meta = manifest.metadata or {}
                        if meta.get("approved") is False or meta.get("approval_status") in ("pending_review", "draft", "rejected"):
                            continue
                    specs[skill_name] = ToolSpec(
                        name=skill_name,
                        description=f"[Learned Skill] {manifest.description}",
                        parameters={"type": "object", "properties": {}, "required": []},
                        category="learned_skill",
                        required_capabilities=list(manifest.required_capabilities or []),
                    )
                except Exception as exc:
                    logger.debug("Could not inspect skill '%s': %s", skill_name, exc)

        # 3. Global ToolRegistry
        for key in ToolRegistry.keys():
            try:
                entry = ToolRegistry.get(key)
                inst = entry() if callable(entry) else entry
                if hasattr(inst, "spec"):
                    s = inst.spec
                    specs[s.name] = s
                elif isinstance(entry, ToolSpec):
                    specs[entry.name] = entry
            except Exception as exc:
                logger.debug("Could not inspect spec for tool '%s': %s", key, exc)

        # 4. Filter by CapabilityPolicy if owner_id provided
        if self.capability_policy is not None and owner_id:
            filtered: Dict[str, ToolSpec] = {}
            for name, spec in specs.items():
                caps = spec.required_capabilities or DEFAULT_TOOL_CAPABILITIES.get(
                    name.lower(), [Capability.TOOL_INVOKE.value]
                )
                allowed = True
                for cap in caps:
                    cap_val = cap.value if hasattr(cap, "value") else str(cap)
                    if not self.capability_policy.check(owner_id, cap_val, name):
                        allowed = False
                        break
                if allowed:
                    filtered[name] = spec
            return filtered

        return specs

    def build_tool_catalog(self, owner_id: Optional[str] = None) -> str:
        """Build structured text catalog of available tools for agent planning."""
        tools = self.discover_tools(owner_id=owner_id)
        if not tools:
            return "No tools available."

        lines: List[str] = ["# Available Registered Tools:"]
        for name in sorted(tools.keys()):
            spec = tools[name]
            lines.append(f"\n### `{spec.name}`")
            lines.append(f"Description: {spec.description}")
            if spec.category:
                lines.append(f"Category: {spec.category}")
            params = spec.parameters or {}
            props = params.get("properties", {})
            req = set(params.get("required", []))
            if props:
                lines.append("Parameters:")
                for p_name, p_info in props.items():
                    p_type = p_info.get("type", "any")
                    r_flag = " (REQUIRED)" if p_name in req else " (optional)"
                    p_desc = p_info.get("description", "")
                    lines.append(f"  - `{p_name}` [{p_type}]{r_flag}: {p_desc}")
            else:
                lines.append("Parameters: None")

        return "\n".join(lines)

    def select_tool(
        self,
        step_intent: str,
        available_tools: Optional[Dict[str, ToolSpec]] = None,
        owner_id: Optional[str] = None,
    ) -> Optional[str]:
        """Select the appropriate registered tool for a given task step intent.

        Uses registered tool names, descriptions, parameter schemas, categories,
        and capability policies. Strictly rejects unknown or unsupported tools.
        """
        tools = available_tools if available_tools is not None else self.discover_tools(owner_id=owner_id)
        intent_clean = (step_intent or "").strip()
        if not intent_clean:
            return None

        intent_lower = intent_clean.lower()

        # 1. Exact match against registered tool names (case-insensitive)
        for name in tools:
            if name.lower() == intent_lower:
                return name

        # 2. Canonical mapping via runner or GENERIC_VERB_MAP
        normalized_verb = intent_lower.replace(" ", "_")
        if self.runner and hasattr(self.runner, "resolve_tool_handler"):
            canonical_name, handler, _ = self.runner.resolve_tool_handler(intent_lower)
            if handler is None:
                canonical_name, handler, _ = self.runner.resolve_tool_handler(normalized_verb)
            if handler is not None and canonical_name in tools:
                return canonical_name

        canonical_mapped = GENERIC_VERB_MAP.get(intent_lower) or GENERIC_VERB_MAP.get(normalized_verb)
        if canonical_mapped and canonical_mapped in tools:
            return canonical_mapped

        # 3. Semantic keyword & token scoring against registered ToolSpec metadata
        stop_words = {
            "a", "an", "the", "in", "on", "to", "for", "of", "and", "or", "is",
            "at", "by", "from", "with", "into", "step", "tool", "task", "run",
            "execute", "perform", "please", "using", "use",
        }
        tokens = [t for t in re.findall(r"\b\w+\b", intent_lower) if len(t) > 1 and t not in stop_words]
        if not tokens:
            return None

        best_tool: Optional[str] = None
        best_score = 0.0

        for name, spec in tools.items():
            score = 0.0
            name_lower = name.lower()
            name_parts = name_lower.split("_")

            desc_lower = (spec.description or "").lower()
            cat_lower = (spec.category or "").lower()
            params = spec.parameters or {}
            props = params.get("properties", {})
            prop_names = [p.lower() for p in props.keys()]

            for token in tokens:
                # Name matching gives highest weight
                if token in name_parts or token == name_lower:
                    score += 5.0
                elif token in name_lower:
                    score += 3.0

                # Parameter names
                if token in prop_names:
                    score += 2.5

                # Category match
                if token in cat_lower:
                    score += 2.0

                # Description word match
                if re.search(rf"\b{re.escape(token)}\b", desc_lower):
                    score += 1.5
                elif token in desc_lower:
                    score += 0.8

            if score > best_score:
                best_score = score
                best_tool = name

        # Require a minimum score threshold for semantic match to avoid guessing
        if best_tool and best_score >= 2.0:
            return best_tool

        # Known verbs mapping fallback as last resort for common expressions
        keywords_to_tool = [
            (("read", "inspect file", "view file", "file content"), "file_read"),
            (("write", "create file", "save file", "write file"), "file_write"),
            (("delete", "remove file", "unlink"), "delete_file"),
            (("search", "google", "query internet"), "web_search"),
            (("shell", "bash", "powershell", "terminal"), "shell_exec"),
            (("calculate", "math", "evaluate expression"), "calculator"),
            (("http", "fetch", "webhook", "api request", "curl"), "http_request"),
            (("think", "reason", "plan", "analyze"), "think"),
            (("launch", "open app", "run application"), "app_launch"),
        ]
        for triggers, target_tool in keywords_to_tool:
            if target_tool in tools:
                if any(tr in intent_lower for tr in triggers):
                    return target_tool

        return None

    # ----------------------------------------------------------------------
    # 2. Argument Generation & Validation
    # ----------------------------------------------------------------------

    def validate_tool_arguments(
        self,
        tool_name: str,
        args: Dict[str, Any],
        schema: Optional[Dict[str, Any]] = None,
    ) -> ValidationResult:
        """Validate arguments against tool schema: required fields, types, and constraints."""
        if not isinstance(args, dict):
            return ValidationResult(
                is_valid=False,
                errors=[f"Arguments must be an object (dictionary), got {type(args).__name__}"],
            )

        # Resolve schema if not explicitly provided
        if schema is None:
            if self.runner and hasattr(self.runner, "resolve_tool_handler"):
                _, _, schema = self.runner.resolve_tool_handler(tool_name)
            if schema is None:
                tools = self.discover_tools()
                if tool_name in tools:
                    schema = tools[tool_name].parameters

        if not schema or not isinstance(schema, dict):
            return ValidationResult(is_valid=True)

        properties = schema.get("properties", {})
        required = schema.get("required", [])
        errors: List[str] = []
        missing_fields: List[str] = []

        # 1. Required parameters check
        for req in required:
            if req not in args:
                errors.append(f"Missing required parameter '{req}' for tool '{tool_name}'")
                missing_fields.append(req)
                continue

            val = args[req]
            if val is None:
                errors.append(f"Required parameter '{req}' cannot be null for tool '{tool_name}'")
                missing_fields.append(req)
            elif isinstance(val, str):
                s_val = val.strip()
                if not s_val:
                    errors.append(f"Required parameter '{req}' cannot be an empty string for tool '{tool_name}'")
                    missing_fields.append(req)
                elif any(p.match(s_val) for p in _PLACEHOLDER_PATTERNS):
                    errors.append(
                        f"Required parameter '{req}' contains unresolved placeholder '{s_val}'. "
                        "Essential information must be provided by user rather than guessed."
                    )
                    missing_fields.append(req)

        # 2. Property types & constraints check
        for param, val in args.items():
            if val is None:
                continue

            prop_info = properties.get(param)
            if not prop_info or not isinstance(prop_info, dict):
                continue

            expected_type = prop_info.get("type")
            if expected_type == "string":
                if not isinstance(val, str):
                    errors.append(f"Parameter '{param}' must be a string, got {type(val).__name__}")
                else:
                    min_len = prop_info.get("minLength")
                    if min_len is not None and len(val) < min_len:
                        errors.append(f"Parameter '{param}' length must be at least {min_len}")
                    max_len = prop_info.get("maxLength")
                    if max_len is not None and len(val) > max_len:
                        errors.append(f"Parameter '{param}' length must be at most {max_len}")
                    pattern = prop_info.get("pattern")
                    if pattern and not re.search(pattern, val):
                        errors.append(f"Parameter '{param}' does not match required pattern '{pattern}'")
                    enum_vals = prop_info.get("enum")
                    if enum_vals and val not in enum_vals:
                        errors.append(f"Parameter '{param}' must be one of {enum_vals}, got {val!r}")

            elif expected_type == "integer":
                if not isinstance(val, int) or isinstance(val, bool):
                    errors.append(f"Parameter '{param}' must be an integer, got {type(val).__name__}")
                else:
                    min_val = prop_info.get("minimum")
                    if min_val is not None and val < min_val:
                        errors.append(f"Parameter '{param}' must be >= {min_val}")
                    max_val = prop_info.get("maximum")
                    if max_val is not None and val > max_val:
                        errors.append(f"Parameter '{param}' must be <= {max_val}")
                    enum_vals = prop_info.get("enum")
                    if enum_vals and val not in enum_vals:
                        errors.append(f"Parameter '{param}' must be one of {enum_vals}, got {val!r}")

            elif expected_type == "number":
                if not isinstance(val, (int, float)) or isinstance(val, bool):
                    errors.append(f"Parameter '{param}' must be a number, got {type(val).__name__}")
                else:
                    min_val = prop_info.get("minimum")
                    if min_val is not None and val < min_val:
                        errors.append(f"Parameter '{param}' must be >= {min_val}")
                    max_val = prop_info.get("maximum")
                    if max_val is not None and val > max_val:
                        errors.append(f"Parameter '{param}' must be <= {max_val}")

            elif expected_type == "boolean":
                if not isinstance(val, bool):
                    errors.append(f"Parameter '{param}' must be a boolean, got {type(val).__name__}")

            elif expected_type == "array":
                if not isinstance(val, (list, tuple)):
                    errors.append(f"Parameter '{param}' must be an array (list), got {type(val).__name__}")

            elif expected_type == "object":
                if not isinstance(val, dict):
                    errors.append(f"Parameter '{param}' must be an object (dict), got {type(val).__name__}")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            missing_fields=missing_fields,
        )

    def generate_arguments(
        self,
        tool_name: str,
        step_intent: str,
        available_context: Optional[Dict[str, Any]] = None,
        schema: Optional[Dict[str, Any]] = None,
        agent: Optional[Any] = None,
        context: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Tuple[Dict[str, Any], ValidationResult, Optional[str]]:
        """Generate arguments matching the tool's actual schema.

        Validates required fields, types, and constraints before execution.
        If essential information is missing, produces a prompt for the user instead
        of guessing hallucinated values.

        Returns:
            (arguments_dict, validation_result, prompt_for_user_or_None)
        """
        # Resolve schema
        if schema is None:
            tools = self.discover_tools()
            if tool_name in tools:
                schema = tools[tool_name].parameters

        generated: Dict[str, Any] = {}
        context = available_context or context or {}

        # 1. If an agent is available, use it to synthesize arguments according to schema
        if agent is not None and schema:
            try:
                schema_str = json.dumps(schema, indent=2)
                context_str = json.dumps(context, default=str)
                prompt = (
                    f"You are an argument generator for the tool '{tool_name}'.\n"
                    f"Tool Parameter Schema:\n{schema_str}\n\n"
                    f"Step Intent: {step_intent}\n"
                    f"Available Context: {context_str}\n\n"
                    "Generate the exact JSON dictionary of arguments matching this schema.\n"
                    "Do NOT invent or guess values for missing required information.\n"
                    "If essential information is not provided in the intent or context, omit that field.\n"
                    "Return ONLY a valid JSON object."
                )
                raw = ""
                if hasattr(agent, "run") and callable(agent.run):
                    res = agent.run(prompt)
                    raw = getattr(res, "content", str(res))
                elif hasattr(agent, "chat") and callable(agent.chat):
                    res = agent.chat(prompt)
                    raw = getattr(res, "content", str(res))
                elif callable(agent):
                    res = agent(prompt)
                    raw = getattr(res, "content", str(res))

                if raw:
                    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
                    clean = m.group(1).strip() if m else raw.strip()
                    start = clean.find("{")
                    end = clean.rfind("}")
                    if start != -1 and end != -1:
                        parsed = json.loads(clean[start : end + 1])
                        if isinstance(parsed, dict):
                            generated = parsed
            except Exception as exc:
                logger.debug("Agent argument generation failed (%s); falling back to heuristics.", exc)

        # 2. Heuristic extraction fallback if agent not used or produced empty
        if not generated and schema:
            properties = schema.get("properties", {})
            intent = step_intent.strip()

            if "thought" in properties and tool_name == "think":
                generated["thought"] = intent or context.get("prompt", "Analyze step")

            if "path" in properties:
                # Find quoted path or file token
                m = re.search(r'["\']([^"\']+\.[a-zA-Z0-9_]+)["\']', intent)
                if m:
                    generated["path"] = m.group(1)
                elif "path" in context:
                    generated["path"] = str(context["path"])

            if "content" in properties:
                m = re.search(r'(?:with content|write|content:)\s*["\']([^"\']+)["\']', intent, re.IGNORECASE)
                if m:
                    generated["content"] = m.group(1)
                elif "content" in context:
                    generated["content"] = str(context["content"])

            if "command" in properties:
                m = re.search(r'`([^`]+)`', intent)
                if m:
                    generated["command"] = m.group(1)
                elif "command" in context:
                    generated["command"] = str(context["command"])

            if "url" in properties:
                m = re.search(r'https?://[^\s"\']+', intent)
                if m:
                    generated["url"] = m.group(0)
                elif "url" in context:
                    generated["url"] = str(context["url"])

            if "query" in properties:
                m = re.search(r'(?:search for|query)\s*["\']?([^"\']+)["\']?', intent, re.IGNORECASE)
                if m:
                    generated["query"] = m.group(1).strip()
                elif intent:
                    generated["query"] = intent

            if "expression" in properties and tool_name == "calculator":
                m = re.search(r'[\d\.\s\+\-\*\/\(\)\^%]+', intent)
                if m and len(m.group(0).strip()) >= 3:
                    generated["expression"] = m.group(0).strip()

        # 3. Validate generated arguments
        val_res = self.validate_tool_arguments(tool_name, generated, schema=schema)

        prompt_user: Optional[str] = None
        if val_res.has_missing_essential_info:
            missing_str = ", ".join(f"'{f}'" for f in val_res.missing_fields)
            prompt_user = (
                f"Tool '{tool_name}' for step '{step_intent}' requires missing essential parameter(s): {missing_str}. "
                "Please specify the required information to proceed."
            )

        return generated, val_res, prompt_user

    # Alias for generate_arguments
    generate_tool_arguments = generate_arguments

    # ----------------------------------------------------------------------
    # 3. Sequential Reasoning & Context Chaining
    # ----------------------------------------------------------------------

    def resolve_sequential_context(
        self,
        step: TaskStep,
        completed_deps: Dict[str, TaskStep],
        agent: Optional[Any] = None,
        schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Resolve step arguments using outputs and artifacts of completed dependencies."""
        raw_args = dict(step.tool_args or {})
        if not completed_deps and not raw_args:
            return raw_args

        # 1. Primary / most recent predecessor output
        primary_dep: Optional[TaskStep] = None
        for dep_id in reversed(step.dependencies):
            if dep_id in completed_deps:
                primary_dep = completed_deps[dep_id]
                break
        if primary_dep is None and completed_deps:
            primary_dep = list(completed_deps.values())[-1]

        primary_output = (primary_dep.actual_output or "") if primary_dep else ""
        primary_artifact_path = ""
        if primary_dep and primary_dep.artifacts:
            primary_artifact_path = str(primary_dep.artifacts[0].get("path", ""))

        # 2. Extract JSON field from structured string
        def _get_json_path(raw_text: str, path: str) -> Optional[str]:
            try:
                data = json.loads(raw_text)
                cur: Any = data
                for part in path.split("."):
                    if isinstance(cur, dict) and part in cur:
                        cur = cur[part]
                    elif isinstance(cur, list) and part.isdigit():
                        cur = cur[int(part)]
                    else:
                        return None
                return str(cur)
            except Exception:
                return None

        # 3. Template substitution helper
        def _substitute_val(val: Any) -> Any:
            if not isinstance(val, str):
                return val

            res = val
            # General placeholders
            res = res.replace("{{previous_output}}", primary_output)
            res = res.replace("{{output}}", primary_output)
            res = res.replace("{{artifact_path}}", primary_artifact_path)
            res = res.replace("$output", primary_output)

            # Check for JSON path in previous_output e.g. {{previous_output.some_field}}
            for m in re.finditer(r"\{\{previous_output\.([\w\.]+)\}\}", res):
                extracted = _get_json_path(primary_output, m.group(1))
                if extracted is not None:
                    res = res.replace(m.group(0), extracted)

            for m in re.finditer(r"\{\{output\.([\w\.]+)\}\}", res):
                extracted = _get_json_path(primary_output, m.group(1))
                if extracted is not None:
                    res = res.replace(m.group(0), extracted)

            # Specific dependency placeholders: {{dep_id.output}}, {{dep_id.actual_output}}, etc.
            for d_id, dep in completed_deps.items():
                dep_out = dep.actual_output or ""
                dep_path = str(dep.artifacts[0].get("path", "")) if dep.artifacts else ""
                res = res.replace(f"{{{{{d_id}.output}}}}", dep_out)
                res = res.replace(f"{{{{{d_id}.actual_output}}}}", dep_out)
                res = res.replace(f"{{{{{d_id}.artifact_path}}}}", dep_path)
                res = res.replace(f"${d_id}.output", dep_out)

                # Nested JSON paths for dep_id: {{dep_id.output.key}}
                d_pat = r"\{\{" + re.escape(d_id) + r"\.output\.([\w\.]+)\}\}"
                for m in re.finditer(d_pat, res):
                    extracted = _get_json_path(dep_out, m.group(1))
                    if extracted is not None:
                        res = res.replace(m.group(0), extracted)

                # Shorthand: step index matching e.g. {{s1.output}}, {{1.output}}
                s_idx = f"s{dep.step_index + 1}"
                res = res.replace(f"{{{{{s_idx}.output}}}}", dep_out)
                res = res.replace(f"{{{{{dep.step_index + 1}.output}}}}", dep_out)

                s_pat = r"\{\{" + re.escape(s_idx) + r"\.output\.([\w\.]+)\}\}"
                for m in re.finditer(s_pat, res):
                    extracted = _get_json_path(dep_out, m.group(1))
                    if extracted is not None:
                        res = res.replace(m.group(0), extracted)

            return res

        resolved: Dict[str, Any] = {}
        for k, v in raw_args.items():
            if isinstance(v, str):
                resolved[k] = _substitute_val(v)
            elif isinstance(v, dict):
                resolved[k] = {ik: _substitute_val(iv) for ik, iv in v.items()}
            elif isinstance(v, list):
                resolved[k] = [_substitute_val(iv) for iv in v]
            else:
                resolved[k] = v

        # 4. Optional schema-guided type casting for exact substitutions
        if schema and isinstance(schema, dict):
            properties = schema.get("properties", {})
            for k, val in list(resolved.items()):
                if not isinstance(val, str) or k not in properties:
                    continue
                orig_val = raw_args.get(k)
                if isinstance(orig_val, str) and ("{{" in orig_val or "$" in orig_val):
                    prop_type = properties[k].get("type")
                    if prop_type == "integer":
                        try:
                            resolved[k] = int(val.strip())
                        except ValueError:
                            pass
                    elif prop_type == "number":
                        try:
                            resolved[k] = float(val.strip()) if "." in val else int(val.strip())
                        except ValueError:
                            pass
                    elif prop_type == "boolean":
                        if val.strip().lower() in ("true", "1"):
                            resolved[k] = True
                        elif val.strip().lower() in ("false", "0"):
                            resolved[k] = False
                    elif prop_type in ("object", "array"):
                        try:
                            parsed_json = json.loads(val)
                            if (prop_type == "object" and isinstance(parsed_json, dict)) or (
                                prop_type == "array" and isinstance(parsed_json, (list, tuple))
                            ):
                                resolved[k] = parsed_json
                        except Exception:
                            pass

        return resolved

    # ----------------------------------------------------------------------
    # 4. Result Verification
    # ----------------------------------------------------------------------

    def verify_result(
        self,
        step: TaskStep,
        result: ToolResult,
    ) -> VerificationResult:
        """Inspect tool result honestly without fabricating success."""
        artifacts: List[Dict[str, Any]] = []

        # 1. Base execution status check
        if not result.success:
            err_msg = result.content or "Tool reported execution failure."
            return VerificationResult(verified=False, error=err_msg, artifacts=artifacts)

        actual_content = str(result.content or "").strip()

        # 2. Expected output pattern or constraint verification
        if step.expected_output:
            expected = step.expected_output.strip()
            # Regex pattern check e.g. /pattern/
            if expected.startswith("/") and expected.endswith("/") and len(expected) > 2:
                pattern_str = expected[1:-1]
                if not re.search(pattern_str, actual_content, re.IGNORECASE):
                    return VerificationResult(
                        verified=False,
                        error=f"Actual output does not match expected regex pattern: {expected}",
                        artifacts=artifacts,
                    )
            else:
                # Substring case-insensitive match
                if expected.lower() not in actual_content.lower():
                    return VerificationResult(
                        verified=False,
                        error=f"Expected criteria '{expected}' was not satisfied by tool output.",
                        artifacts=artifacts,
                    )

        # 3. File artifact inspection & ground truth check
        tool_lower = step.tool_name.lower()
        args = step.tool_args or {}

        if tool_lower in ("file_write", "create_file") and "path" in args:
            target_path = Path(args["path"])
            if not target_path.exists():
                return VerificationResult(
                    verified=False,
                    error=f"Verification failed: output file '{target_path}' was not created on disk.",
                    artifacts=artifacts,
                )
            try:
                stat = target_path.stat()
                artifacts.append({
                    "path": str(target_path.resolve()),
                    "size_bytes": stat.st_size,
                    "verified_at": stat.st_mtime,
                })
            except OSError as exc:
                return VerificationResult(
                    verified=False,
                    error=f"Verification failed: could not stat output file '{target_path}': {exc}",
                    artifacts=artifacts,
                )

        elif tool_lower in ("delete_file", "file_delete", "remove_file") and "path" in args:
            target_path = Path(args["path"])
            if target_path.exists():
                return VerificationResult(
                    verified=False,
                    error=f"Verification failed: target file '{target_path}' still exists after delete.",
                    artifacts=artifacts,
                )
            artifacts.append({
                "path": str(target_path.resolve()),
                "deleted": True,
            })

        return VerificationResult(verified=True, error=None, artifacts=artifacts)

    # ----------------------------------------------------------------------
    # 5. Failure Classification & Safe Recovery
    # ----------------------------------------------------------------------

    def classify_failure(
        self,
        step: TaskStep,
        error_msg: str,
        exc: Optional[Exception] = None,
    ) -> FailureCategory:
        """Classify a failure into TRANSIENT, DETERMINISTIC, or UNCERTAIN_EXTERNAL."""
        # 1. Check for uncertain external actions with duplicate-action risk
        if self.runner and hasattr(self.runner, "_is_uncertain_failure"):
            if self.runner._is_uncertain_failure(step, error_msg, exc):
                return FailureCategory.UNCERTAIN_EXTERNAL

        err_lower = (error_msg or "").lower()

        # 2. Deterministic / unrecoverable without plan change
        deterministic_signals = (
            "missing required",
            "invalid argument",
            "unknown tool",
            "not found",
            "does not exist",
            "permission denied",
            "access denied",
            "syntax error",
            "unsupported",
            "blocked by safety kernel",
            "capability denied",
            "unresolved placeholder",
        )
        if any(sig in err_lower for sig in deterministic_signals):
            return FailureCategory.DETERMINISTIC
        if exc is not None and isinstance(
            exc, (FileNotFoundError, PermissionError, KeyError, ValueError, TypeError)
        ):
            return FailureCategory.DETERMINISTIC

        # 3. Transient / recoverable via retry
        transient_signals = (
            "rate limit",
            "too many requests",
            "429",
            "503",
            "502",
            "504",
            "500",
            "temporarily unavailable",
            "lock held",
            "busy",
            "try again",
            "timeout",
            "timed out",
            "connection",
            "temporary",
            "transient",
            "network",
            "econnreset",
            "econnrefused",
            "server error",
        )
        if any(sig in err_lower for sig in transient_signals):
            return FailureCategory.TRANSIENT

        # Default for non-deterministic tool failures is TRANSIENT so bounded retries apply
        return FailureCategory.TRANSIENT

    def recommend_recovery(
        self,
        step: TaskStep,
        category: FailureCategory,
        error_msg: str,
    ) -> Dict[str, Any]:
        """Provide structured recovery guidance based on failure classification."""
        if category == FailureCategory.TRANSIENT:
            can_retry = step.retry_count < step.max_retries
            return {
                "action": "retry" if can_retry else "report_blocker",
                "safe_to_retry": can_retry,
                "backoff_seconds": 0.05 * (2 ** step.retry_count),
                "reason": "Transient failure detected; bounded retry with backoff is safe.",
            }
        elif category == FailureCategory.UNCERTAIN_EXTERNAL:
            return {
                "action": "require_operator_approval",
                "safe_to_retry": False,
                "duplicate_action_risk": True,
                "reason": (
                    "Uncertain external action failure detected. Blindly retrying carries duplicate-action "
                    "risk (e.g., multiple webhooks, duplicate messages, double charges). "
                    "Operator must verify external state and approve with 'mark_completed' or 'force_retry'."
                ),
            }
        else:
            return {
                "action": "report_blocker",
                "safe_to_retry": False,
                "duplicate_action_risk": False,
                "reason": (
                    f"Deterministic error detected ({error_msg}). Retrying will not succeed without "
                    "plan adjustment or user clarification."
                ),
            }


__all__ = [
    "FailureCategory",
    "ToolExecutionIntelligence",
    "ValidationResult",
    "VerificationResult",
]
