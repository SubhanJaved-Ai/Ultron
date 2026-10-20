"""WorkflowManageTool — manage, synthesize, and execute DAG automation workflows.

Directly inspired by n8n workflow creation: lets agents construct multi-node
DAG automations (agents, tools, conditions, transforms), inspect their topology,
execute them with step-by-step tracing, and link them to inbound webhook triggers.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from openjarvis.core.paths import get_config_dir
from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec
from openjarvis.workflow.engine import WorkflowEngine
from openjarvis.workflow.graph import WorkflowGraph
from openjarvis.workflow.loader import load_workflow
from openjarvis.workflow.types import NodeType, WorkflowEdge, WorkflowNode

logger = logging.getLogger(__name__)


@ToolRegistry.register("workflow_manage")
class WorkflowManageTool(BaseTool):
    """Manage, synthesize, and execute DAG automation workflows."""

    tool_id = "workflow_manage"

    def __init__(
        self,
        workflows_dir: Optional[Path | str] = None,
        system: Any = None,
    ) -> None:
        if workflows_dir is None:
            workflows_dir = get_config_dir() / "workflows"
        self._workflows_dir = Path(workflows_dir).expanduser()
        self._workflows_dir.mkdir(parents=True, exist_ok=True)
        self._system = system

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="workflow_manage",
            description=(
                "Build, inspect, execute, or delete multi-step DAG workflows (n8n-style). "
                "Actions: "
                "'create' (define a new DAG workflow from nodes and edges), "
                "'list' (view all saved workflows), "
                "'inspect' (view node topology and execution order), "
                "'run' (execute workflow and view step-by-step trace), "
                "'delete' (remove workflow file), "
                "'register_webhook' (link workflow to an inbound HTTP webhook trigger)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "create",
                            "list",
                            "inspect",
                            "run",
                            "delete",
                            "register_webhook",
                        ],
                        "description": "Action to perform.",
                    },
                    "name": {
                        "type": "string",
                        "description": "Workflow identifier name.",
                    },
                    "nodes": {
                        "type": "array",
                        "description": (
                            "List of node definitions for 'create'. "
                            "Each item: {'id': str, 'type': 'agent'|'tool'|'condition'|'transform'|'loop', "
                            "'agent'?: str, 'tools'?: [str], 'config'?: object, 'condition_expr'?: str}."
                        ),
                        "items": {"type": "object"},
                    },
                    "edges": {
                        "type": "array",
                        "description": (
                            "List of edge connections for 'create'. "
                            "Each item: {'source': str, 'target': str, 'condition'?: str}."
                        ),
                        "items": {"type": "object"},
                    },
                    "input": {
                        "type": "string",
                        "description": "Initial input payload string for 'run'.",
                    },
                    "webhook_slug": {
                        "type": "string",
                        "description": "URL slug for 'register_webhook' trigger.",
                    },
                },
                "required": ["action"],
            },
            category="workflow",
        )

    def execute(self, **params: Any) -> ToolResult:
        action = params.get("action", "list")
        name = (params.get("name") or "").strip()
        user_id = (
            params.get("user_id")
            or params.get("operator_id")
            or getattr(self, "_user_id", None)
        )

        if action == "create":
            return self._create(
                name,
                params.get("nodes", []),
                params.get("edges", []),
                user_id=user_id,
            )
        elif action == "list":
            return self._list(user_id=user_id)
        elif action == "inspect":
            return self._inspect(name, user_id=user_id)
        elif action == "run":
            return self._run(
                name, initial_input=params.get("input", ""), user_id=user_id
            )
        elif action == "delete":
            return self._delete(name, user_id=user_id)
        elif action == "register_webhook":
            return self._register_webhook(
                name, slug=params.get("webhook_slug") or name, user_id=user_id
            )

        return ToolResult(
            tool_name=self.spec.name,
            success=False,
            content=f"Unknown action: {action}",
        )

    def _get_workflow_dir(self, user_id: Optional[str] = None) -> Path:
        import re

        if user_id and user_id != "default":
            safe_uid = re.sub(r"[^\w\-]", "_", str(user_id))
            target_dir = self._workflows_dir / safe_uid
            target_dir.mkdir(parents=True, exist_ok=True)
            return target_dir
        return self._workflows_dir

    def _get_workflow_path(self, name: str, user_id: Optional[str] = None) -> Path:
        clean_name = Path(name).name
        if clean_name.endswith(".toml"):
            clean_name = clean_name[:-5]
        return self._get_workflow_dir(user_id) / f"{clean_name}.toml"

    def _create(
        self,
        name: str,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        user_id: Optional[str] = None,
    ) -> ToolResult:
        if not name:
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content="Workflow 'name' is required for create.",
            )
        if not nodes:
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content="At least one node is required for create.",
            )

        # Validate DAG structure using WorkflowGraph
        graph = WorkflowGraph(name=name)
        for n in nodes:
            nid = n.get("id")
            if not nid:
                return ToolResult(
                    tool_name=self.spec.name,
                    success=False,
                    content="Each node must have an 'id'.",
                )
            ntype_str = n.get("type", "agent")
            try:
                ntype = NodeType(ntype_str)
            except ValueError:
                ntype = NodeType.AGENT

            graph.add_node(
                WorkflowNode(
                    id=nid,
                    node_type=ntype,
                    agent=n.get("agent", "simple"),
                    tools=n.get("tools", []),
                    config=n.get("config", {}),
                    condition_expr=n.get("condition_expr", ""),
                    transform_expr=n.get("transform_expr", ""),
                )
            )

        for e in edges:
            src = e.get("source")
            tgt = e.get("target")
            if not src or not tgt:
                continue
            graph.add_edge(
                WorkflowEdge(
                    source=src,
                    target=tgt,
                    condition=e.get("condition", ""),
                )
            )

        valid, msg = graph.validate()
        if not valid:
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content=f"Invalid workflow DAG: {msg}",
            )

        # Serialize to TOML
        lines = [
            "[workflow]",
            f'name = "{name}"',
            "",
        ]
        for n in nodes:
            lines.append("[[workflow.nodes]]")
            lines.append(f'id = "{n["id"]}"')
            lines.append(f'type = "{n.get("type", "agent")}"')
            if "agent" in n:
                lines.append(f'agent = "{n["agent"]}"')
            if "tools" in n and n["tools"]:
                t_list = json.dumps(n["tools"])
                lines.append(f"tools = {t_list}")
            if "condition_expr" in n and n["condition_expr"]:
                lines.append(f'condition_expr = "{n["condition_expr"]}"')
            if "transform_expr" in n and n["transform_expr"]:
                lines.append(f'transform_expr = "{n["transform_expr"]}"')
            lines.append("")

        for e in edges:
            lines.append("[[workflow.edges]]")
            lines.append(f'source = "{e["source"]}"')
            lines.append(f'target = "{e["target"]}"')
            if "condition" in e and e["condition"]:
                lines.append(f'condition = "{e["condition"]}"')
            lines.append("")

        wf_path = self._get_workflow_path(name, user_id=user_id)
        wf_path.write_text("\n".join(lines), encoding="utf-8")

        return ToolResult(
            tool_name=self.spec.name,
            success=True,
            content=f"Created workflow DAG '{name}' with {len(nodes)} nodes and {len(edges)} edges.",
        )

    def _list(self, user_id: Optional[str] = None) -> ToolResult:
        files = sorted(self._get_workflow_dir(user_id).glob("*.toml"))
        if not files:
            return ToolResult(
                tool_name=self.spec.name,
                success=True,
                content="No saved workflows found.",
            )
        lines = [f"Available workflows ({len(files)}):"]
        for f in files:
            try:
                g = load_workflow(f)
                lines.append(
                    f"- **{g.name}**: {len(g.nodes)} nodes, {len(g.edges)} edges"
                )
            except Exception:
                lines.append(f"- {f.stem}")
        return ToolResult(
            tool_name=self.spec.name,
            success=True,
            content="\n".join(lines),
        )

    def _inspect(self, name: str, user_id: Optional[str] = None) -> ToolResult:
        if not name:
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content="Workflow 'name' is required to inspect.",
            )
        path = self._get_workflow_path(name, user_id=user_id)
        if not path.exists():
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content=f"Workflow not found: '{name}'",
            )
        try:
            graph = load_workflow(path)
            lines = [
                f"# Workflow: {graph.name}",
                f"File: {path}",
                "",
                "## Nodes:",
            ]
            for n in graph.nodes:
                lines.append(
                    f"- [{n.id}] Type: {n.node_type.value} | Agent: {n.agent or 'none'} | Tools: {n.tools}"
                )
            lines.append("\n## Edges:")
            for e in graph.edges:
                cond = f" (if: {e.condition})" if e.condition else ""
                lines.append(f"- {e.source} -> {e.target}{cond}")

            return ToolResult(
                tool_name=self.spec.name,
                success=True,
                content="\n".join(lines),
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content=f"Error inspecting workflow: {e}",
            )

    def _run(
        self, name: str, initial_input: str = "", user_id: Optional[str] = None
    ) -> ToolResult:
        if not name:
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content="Workflow 'name' is required to run.",
            )
        path = self._get_workflow_path(name, user_id=user_id)
        if not path.exists():
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content=f"Workflow not found: '{name}'",
            )
        try:
            graph = load_workflow(path)
            engine = WorkflowEngine()

            class _DefaultWorkflowSystem:
                def ask(self, input_text: str, **kwargs: Any) -> Dict[str, Any]:
                    return {"content": f"Step processed: {input_text[:80]}"}

            sys_to_use = self._system or _DefaultWorkflowSystem()
            result = engine.run(graph, system=sys_to_use, initial_input=initial_input)

            trace_lines = [
                f"# Execution Trace: {graph.name} ({result.total_duration_seconds:.2f}s)",
                f"**Status**: {'SUCCESS' if result.success else 'FAILED'}",
                "",
                "## Step Results:",
            ]
            for step in result.steps:
                status_str = "SUCCESS" if step.success else "FAILED"
                trace_lines.append(
                    f"- **Node [{step.node_id}]**: {status_str} ({step.duration_seconds:.2f}s)"
                )
                if step.output:
                    snippet = step.output[:120] + (
                        "..." if len(step.output) > 120 else ""
                    )
                    trace_lines.append(f"  Output: {snippet}")

            trace_lines.append(f"\n## Final Output:\n{result.final_output}")

            return ToolResult(
                tool_name=self.spec.name,
                success=result.success,
                content="\n".join(trace_lines),
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content=f"Execution error: {e}",
            )

    def _delete(self, name: str, user_id: Optional[str] = None) -> ToolResult:
        path = self._get_workflow_path(name, user_id=user_id)
        if not path.exists():
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content=f"Workflow not found: '{name}'",
            )
        path.unlink()
        return ToolResult(
            tool_name=self.spec.name,
            success=True,
            content=f"Deleted workflow: '{name}'",
        )

    def _register_webhook(
        self, name: str, slug: str, user_id: Optional[str] = None
    ) -> ToolResult:
        from openjarvis.server.webhook_trigger import WebhookTriggerRegistry

        path = self._get_workflow_path(name, user_id=user_id)
        if not path.exists():
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content=f"Workflow not found: '{name}'",
            )
        reg = WebhookTriggerRegistry()
        trigger = reg.register(
            slug=slug,
            target_type="workflow",
            target_name=name,
            description=f"Inbound webhook for workflow {name}",
        )
        return ToolResult(
            tool_name=self.spec.name,
            success=True,
            content=(
                f"Registered webhook endpoint for workflow '{name}':\n"
                f"- Slug: {trigger.slug}\n"
                f"- Trigger URL: /webhooks/trigger/{trigger.slug}"
            ),
        )
