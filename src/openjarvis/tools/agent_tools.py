"""Inter-agent lifecycle tools — subagents, sessions_spawn, and agent management.

These MCP tools allow an orchestrating agent (or the user/system) to manage
autonomous child agent lifecycles at runtime. Supports both modern OpenClaw-style
subagent workflows (`subagent_spawn` / `sessions_spawn`, `subagent_status`,
`subagent_result`, `subagent_list`) and legacy lifecycle management.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Dict

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state — legacy in-memory agent tracker
# ---------------------------------------------------------------------------

_SPAWNED_AGENTS: Dict[str, Dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# SubagentSpawnTool (OpenClaw `sessions_spawn` / `subagent_spawn`)
# ---------------------------------------------------------------------------


@ToolRegistry.register("subagent_spawn")
@ToolRegistry.register("sessions_spawn")
class SubagentSpawnTool(BaseTool):
    """Spawn an autonomous background subagent to execute a task in parallel."""

    tool_id = "subagent_spawn"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="subagent_spawn",
            description=(
                "Spawn a new autonomous subagent to perform a task (research, "
                "coding, document analysis, multi-step problem solving) in the background. "
                "Non-blocking by default; returns a subagent ID to monitor progress."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": (
                            "Detailed prompt or mission for the subagent to execute."
                        ),
                    },
                    "name": {
                        "type": "string",
                        "description": (
                            "Descriptive name for the subagent (e.g. 'Market Researcher', "
                            "'Bug Finder', 'Code Reviewer')."
                        ),
                    },
                    "agent_type": {
                        "type": "string",
                        "description": (
                            "Agent type from registry (default: 'orchestrator'). "
                            "Options include 'orchestrator', 'deep_research', 'simple'."
                        ),
                        "default": "orchestrator",
                    },
                    "tools": {
                        "type": "string",
                        "description": (
                            "Comma-separated list of tool names granted to the subagent "
                            "(e.g. 'web_search,file_read,calculator'). Defaults to standard tools."
                        ),
                    },
                    "wait": {
                        "type": "boolean",
                        "description": (
                            "If true, wait synchronously for the subagent to complete and "
                            "return findings immediately. If false (default), runs asynchronously in the background."
                        ),
                        "default": False,
                    },
                    "timeout": {
                        "type": "number",
                        "description": "Seconds to wait if wait=true (default 60.0).",
                        "default": 60.0,
                    },
                },
                "required": ["task"],
            },
            category="agents",
            required_capabilities=[],
        )

    def execute(self, **params: Any) -> ToolResult:
        task = (
            params.get("task") or params.get("query") or params.get("instruction", "")
        )
        if not task:
            return ToolResult(
                tool_name="subagent_spawn",
                content="No task provided for subagent.",
                success=False,
            )

        name = params.get("name")
        agent_type = params.get("agent_type", "orchestrator")
        tools = params.get("tools")
        wait = bool(params.get("wait", False))
        timeout = float(params.get("timeout", 60.0))

        try:
            from openjarvis.agents.subagents import get_subagent_manager

            mgr = get_subagent_manager()
            record = mgr.spawn(
                task=task,
                name=name,
                agent_type=agent_type,
                tools=tools,
                wait=wait,
                timeout=timeout,
            )

            # Mirror to legacy in-memory dict for backwards compatibility
            _SPAWNED_AGENTS[record.id] = {
                "agent_id": record.id,
                "agent_type": record.agent_type,
                "status": record.status,
                "created_at": record.created_at,
                "initial_query": record.task,
            }

            output = record.to_dict()
            return ToolResult(
                tool_name="subagent_spawn",
                content=json.dumps(output, indent=2),
                success=True,
                metadata={"subagent_id": record.id, "status": record.status},
            )
        except Exception as exc:
            logger.exception("Failed to spawn subagent")
            return ToolResult(
                tool_name="subagent_spawn",
                content=f"Failed to spawn subagent: {exc}",
                success=False,
            )


# ---------------------------------------------------------------------------
# SubagentStatusTool
# ---------------------------------------------------------------------------


@ToolRegistry.register("subagent_status")
class SubagentStatusTool(BaseTool):
    """Check the current execution status and progress of a subagent."""

    tool_id = "subagent_status"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="subagent_status",
            description="Check the current status, activity, and progress of a spawned subagent.",
            parameters={
                "type": "object",
                "properties": {
                    "subagent_id": {
                        "type": "string",
                        "description": "Unique identifier of the subagent.",
                    },
                },
                "required": ["subagent_id"],
            },
            category="agents",
            required_capabilities=[],
        )

    def execute(self, **params: Any) -> ToolResult:
        subagent_id = params.get("subagent_id", "")
        if not subagent_id:
            return ToolResult(
                tool_name="subagent_status",
                content="No subagent_id provided.",
                success=False,
            )

        from openjarvis.agents.subagents import get_subagent_manager

        mgr = get_subagent_manager()
        record = mgr.get(subagent_id)

        if record is None:
            # Fall back to legacy tracker
            if subagent_id in _SPAWNED_AGENTS:
                legacy = _SPAWNED_AGENTS[subagent_id]
                return ToolResult(
                    tool_name="subagent_status",
                    content=json.dumps(legacy, indent=2),
                    success=True,
                )
            return ToolResult(
                tool_name="subagent_status",
                content=f"Subagent '{subagent_id}' not found.",
                success=False,
            )

        return ToolResult(
            tool_name="subagent_status",
            content=json.dumps(record.to_dict(), indent=2),
            success=True,
            metadata={"status": record.status},
        )


# ---------------------------------------------------------------------------
# SubagentListTool
# ---------------------------------------------------------------------------


@ToolRegistry.register("subagent_list")
@ToolRegistry.register("sessions_list")
class SubagentListTool(BaseTool):
    """List all spawned subagents with their status, runtime, and task."""

    tool_id = "subagent_list"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="subagent_list",
            description="List active and completed subagents with their status, duration, and assigned task.",
            parameters={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Filter by status: 'running', 'completed', 'failed', or 'all'.",
                    },
                },
            },
            category="agents",
            required_capabilities=[],
        )

    def execute(self, **params: Any) -> ToolResult:
        from openjarvis.agents.subagents import get_subagent_manager

        mgr = get_subagent_manager()
        status_filter = params.get("status")
        records = mgr.list_subagents(status=status_filter)

        if not records:
            if _SPAWNED_AGENTS:
                return ToolResult(
                    tool_name="subagent_list",
                    content=json.dumps(list(_SPAWNED_AGENTS.values()), indent=2),
                    success=True,
                )
            return ToolResult(
                tool_name="subagent_list",
                content="No subagents found.",
                success=True,
            )

        data = [r.to_dict() for r in records]
        return ToolResult(
            tool_name="subagent_list",
            content=json.dumps(data, indent=2),
            success=True,
        )


# ---------------------------------------------------------------------------
# SubagentResultTool
# ---------------------------------------------------------------------------


@ToolRegistry.register("subagent_result")
class SubagentResultTool(BaseTool):
    """Retrieve the complete final findings and report of a subagent."""

    tool_id = "subagent_result"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="subagent_result",
            description="Retrieve the complete findings and generated report from a completed subagent.",
            parameters={
                "type": "object",
                "properties": {
                    "subagent_id": {
                        "type": "string",
                        "description": "Unique identifier of the subagent.",
                    },
                },
                "required": ["subagent_id"],
            },
            category="agents",
            required_capabilities=[],
        )

    def execute(self, **params: Any) -> ToolResult:
        subagent_id = params.get("subagent_id", "")
        if not subagent_id:
            return ToolResult(
                tool_name="subagent_result",
                content="No subagent_id provided.",
                success=False,
            )

        from openjarvis.agents.subagents import get_subagent_manager

        mgr = get_subagent_manager()
        record = mgr.get(subagent_id)

        if record is None:
            return ToolResult(
                tool_name="subagent_result",
                content=f"Subagent '{subagent_id}' not found.",
                success=False,
            )

        if record.status == "running":
            return ToolResult(
                tool_name="subagent_result",
                content=f"Subagent '{subagent_id}' is still running. Progress: {record.progress}",
                success=True,
                metadata={"status": "running"},
            )

        if record.status == "failed":
            return ToolResult(
                tool_name="subagent_result",
                content=f"Subagent '{subagent_id}' failed: {record.error}",
                success=False,
                metadata={"status": "failed"},
            )

        return ToolResult(
            tool_name="subagent_result",
            content=record.result or "No findings recorded.",
            success=True,
            metadata={"status": record.status},
        )


# ---------------------------------------------------------------------------
# SubagentKillTool
# ---------------------------------------------------------------------------


@ToolRegistry.register("subagent_kill")
class SubagentKillTool(BaseTool):
    """Terminate or cancel a running subagent."""

    tool_id = "subagent_kill"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="subagent_kill",
            description="Stop or terminate a running subagent by its ID.",
            parameters={
                "type": "object",
                "properties": {
                    "subagent_id": {
                        "type": "string",
                        "description": "ID of the subagent to terminate.",
                    },
                },
                "required": ["subagent_id"],
            },
            category="agents",
            required_capabilities=[],
        )

    def execute(self, **params: Any) -> ToolResult:
        subagent_id = params.get("subagent_id", "")
        if not subagent_id:
            return ToolResult(
                tool_name="subagent_kill",
                content="No subagent_id provided.",
                success=False,
            )

        from openjarvis.agents.subagents import get_subagent_manager

        mgr = get_subagent_manager()
        success = mgr.kill(subagent_id)

        if not success and subagent_id in _SPAWNED_AGENTS:
            _SPAWNED_AGENTS[subagent_id]["status"] = "stopped"
            success = True

        if not success:
            return ToolResult(
                tool_name="subagent_kill",
                content=f"Subagent '{subagent_id}' not found.",
                success=False,
            )

        return ToolResult(
            tool_name="subagent_kill",
            content=json.dumps({"subagent_id": subagent_id, "status": "stopped"}),
            success=True,
        )


# ---------------------------------------------------------------------------
# SubagentSendTool
# ---------------------------------------------------------------------------


@ToolRegistry.register("subagent_send")
class SubagentSendTool(BaseTool):
    """Send an updated instruction or message to an active subagent."""

    tool_id = "subagent_send"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="subagent_send",
            description="Send a message or follow-up instruction to an active subagent.",
            parameters={
                "type": "object",
                "properties": {
                    "subagent_id": {
                        "type": "string",
                        "description": "Target subagent ID.",
                    },
                    "message": {
                        "type": "string",
                        "description": "Message or additional instruction to send.",
                    },
                },
                "required": ["subagent_id", "message"],
            },
            category="agents",
            required_capabilities=[],
        )

    def execute(self, **params: Any) -> ToolResult:
        subagent_id = params.get("subagent_id", "")
        message = params.get("message", "")

        if not subagent_id or not message:
            return ToolResult(
                tool_name="subagent_send",
                content="Both subagent_id and message are required.",
                success=False,
            )

        from openjarvis.agents.subagents import get_subagent_manager

        mgr = get_subagent_manager()
        delivered = mgr.send_message(subagent_id, message)

        if not delivered and subagent_id in _SPAWNED_AGENTS:
            delivered = True

        if not delivered:
            return ToolResult(
                tool_name="subagent_send",
                content=f"Subagent '{subagent_id}' not found.",
                success=False,
            )

        return ToolResult(
            tool_name="subagent_send",
            content=json.dumps(
                {"subagent_id": subagent_id, "delivered": True, "message": message}
            ),
            success=True,
        )


# ---------------------------------------------------------------------------
# Legacy Tools (Fully Backward Compatible)
# ---------------------------------------------------------------------------


@ToolRegistry.register("agent_spawn")
class AgentSpawnTool(BaseTool):
    """Spawn a new agent instance and optionally send it an initial query."""

    tool_id = "agent_spawn"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="agent_spawn",
            description=(
                "Spawn a new agent instance by type. Optionally"
                " send an initial query and attach tools."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "agent_type": {
                        "type": "string",
                        "description": (
                            "Agent registry key (e.g. 'simple',"
                            " 'orchestrator', 'native_react')."
                        ),
                    },
                    "query": {
                        "type": "string",
                        "description": ("Optional initial query to send to the agent."),
                    },
                    "tools": {
                        "type": "string",
                        "description": (
                            "Comma-separated tool names to attach to the agent."
                        ),
                    },
                    "agent_id": {
                        "type": "string",
                        "description": (
                            "Custom agent ID. Auto-generated if not provided."
                        ),
                    },
                },
                "required": ["agent_type"],
            },
            category="agents",
            required_capabilities=["system:admin"],
        )

    def execute(self, **params: Any) -> ToolResult:
        agent_type = params.get("agent_type", "")
        if not agent_type:
            return ToolResult(
                tool_name="agent_spawn",
                content="No agent_type provided.",
                success=False,
            )

        agent_id = params.get("agent_id") or uuid.uuid4().hex[:12]
        query = params.get("query", "")
        tools = params.get("tools", "")

        entry: Dict[str, Any] = {
            "agent_id": agent_id,
            "agent_type": agent_type,
            "status": "running",
            "created_at": time.time(),
        }
        if tools:
            entry["tools"] = tools
        if query:
            entry["initial_query"] = query

        _SPAWNED_AGENTS[agent_id] = entry

        # Also register with SubagentManager if query is present
        if query:
            try:
                from openjarvis.agents.subagents import get_subagent_manager

                mgr = get_subagent_manager()
                mgr.spawn(
                    task=query,
                    name=f"Agent-{agent_id}",
                    agent_type=agent_type,
                    tools=tools,
                    subagent_id=agent_id,
                    wait=False,
                )
            except Exception as exc:
                logger.debug("SubagentManager background registration failed: %s", exc)

        result_data: Dict[str, Any] = {
            "agent_id": agent_id,
            "agent_type": agent_type,
            "status": "running",
        }
        if query:
            result_data["initial_query"] = query

        return ToolResult(
            tool_name="agent_spawn",
            content=json.dumps(result_data),
            success=True,
        )


@ToolRegistry.register("agent_send")
class AgentSendTool(BaseTool):
    """Send a message to a previously spawned agent."""

    tool_id = "agent_send"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="agent_send",
            description=("Send a message to a running agent by its ID."),
            parameters={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "ID of the target agent.",
                    },
                    "message": {
                        "type": "string",
                        "description": "Message to send.",
                    },
                },
                "required": ["agent_id", "message"],
            },
            category="agents",
            required_capabilities=["system:admin"],
        )

    def execute(self, **params: Any) -> ToolResult:
        agent_id = params.get("agent_id", "")
        message = params.get("message", "")

        if not agent_id:
            return ToolResult(
                tool_name="agent_send",
                content="No agent_id provided.",
                success=False,
            )

        if agent_id not in _SPAWNED_AGENTS:
            from openjarvis.agents.subagents import get_subagent_manager

            mgr = get_subagent_manager()
            if mgr.get(agent_id) is None:
                return ToolResult(
                    tool_name="agent_send",
                    content=f"Agent '{agent_id}' not found.",
                    success=False,
                )

        if not message:
            return ToolResult(
                tool_name="agent_send",
                content="No message provided.",
                success=False,
            )

        # Publish event if event bus is available
        try:
            from openjarvis.core.events import EventType, get_event_bus

            bus = get_event_bus()
            bus.publish(
                EventType.AGENT_TURN_START,
                {
                    "agent_id": agent_id,
                    "message": message,
                },
            )
        except Exception as exc:
            logger.debug("Event bus publish failed for agent_send: %s", exc)

        return ToolResult(
            tool_name="agent_send",
            content=json.dumps(
                {
                    "agent_id": agent_id,
                    "delivered": True,
                    "message": message,
                }
            ),
            success=True,
        )


@ToolRegistry.register("agent_list")
class AgentListTool(BaseTool):
    """List all spawned agents and their current status."""

    tool_id = "agent_list"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="agent_list",
            description=(
                "List all spawned agents with their status, type, and creation time."
            ),
            parameters={
                "type": "object",
                "properties": {},
            },
            category="agents",
            required_capabilities=["system:admin"],
        )

    def execute(self, **params: Any) -> ToolResult:
        if not _SPAWNED_AGENTS:
            return ToolResult(
                tool_name="agent_list",
                content="No agents spawned.",
                success=True,
            )

        agents = []
        for agent_id, info in _SPAWNED_AGENTS.items():
            agents.append(
                {
                    "agent_id": agent_id,
                    "agent_type": info["agent_type"],
                    "status": info["status"],
                    "created_at": info["created_at"],
                }
            )

        return ToolResult(
            tool_name="agent_list",
            content=json.dumps(agents, indent=2),
            success=True,
        )


@ToolRegistry.register("agent_kill")
class AgentKillTool(BaseTool):
    """Kill (stop) a spawned agent by its ID."""

    tool_id = "agent_kill"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="agent_kill",
            description=("Stop a running agent by its ID. Requires confirmation."),
            parameters={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "ID of the agent to stop.",
                    },
                },
                "required": ["agent_id"],
            },
            category="agents",
            requires_confirmation=True,
            required_capabilities=["system:admin"],
        )

    def execute(self, **params: Any) -> ToolResult:
        agent_id = params.get("agent_id", "")

        if not agent_id:
            return ToolResult(
                tool_name="agent_kill",
                content="No agent_id provided.",
                success=False,
            )

        if agent_id not in _SPAWNED_AGENTS:
            from openjarvis.agents.subagents import get_subagent_manager

            mgr = get_subagent_manager()
            if mgr.get(agent_id) is None:
                return ToolResult(
                    tool_name="agent_kill",
                    content=f"Agent '{agent_id}' not found.",
                    success=False,
                )
            mgr.kill(agent_id)

        if agent_id in _SPAWNED_AGENTS:
            _SPAWNED_AGENTS[agent_id]["status"] = "stopped"

        return ToolResult(
            tool_name="agent_kill",
            content=json.dumps(
                {
                    "agent_id": agent_id,
                    "status": "stopped",
                }
            ),
            success=True,
        )


# ---------------------------------------------------------------------------
# SubagentPipelineTool (Swarm pipeline orchestration)
# ---------------------------------------------------------------------------


@ToolRegistry.register("subagent_pipeline")
@ToolRegistry.register("swarm_pipeline")
class SubagentPipelineTool(BaseTool):
    """Execute a coordinated multi-stage subagent pipeline."""

    tool_id = "subagent_pipeline"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="subagent_pipeline",
            description=(
                "Run a multi-stage subagent swarm pipeline (e.g. Researcher -> Analyst -> Reviewer). "
                "Stages execute sequentially, automatically passing intermediate findings via {previous_result} "
                "and the shared swarm blackboard."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "stages": {
                        "description": (
                            "List of stage definitions (or JSON string). Each stage is an object with: "
                            "'name' (str), 'task' (str, can include {previous_result} and {blackboard}), "
                            "'agent_type' (optional str, default 'orchestrator'), 'tools' (optional list/str), "
                            "'timeout' (optional number), 'output_key' (optional str)."
                        ),
                    },
                    "name": {
                        "type": "string",
                        "description": "Descriptive name for the pipeline (e.g. 'Deep Market Analysis Pipeline').",
                    },
                    "swarm_id": {
                        "type": "string",
                        "description": "Optional custom swarm session ID (auto-generated if omitted).",
                    },
                    "timeout_per_stage": {
                        "type": "number",
                        "description": "Default timeout in seconds per stage (default: 120.0).",
                        "default": 120.0,
                    },
                },
                "required": ["stages"],
            },
            category="agents",
            required_capabilities=[],
        )

    def execute(self, **params: Any) -> ToolResult:
        stages_raw = params.get("stages")
        if not stages_raw:
            return ToolResult(
                tool_name="subagent_pipeline",
                content="Parameter 'stages' is required.",
                success=False,
            )

        if isinstance(stages_raw, str):
            try:
                stages = json.loads(stages_raw)
            except Exception as exc:
                return ToolResult(
                    tool_name="subagent_pipeline",
                    content=f"Failed to parse 'stages' JSON string: {exc}",
                    success=False,
                )
        elif isinstance(stages_raw, list):
            stages = stages_raw
        else:
            return ToolResult(
                tool_name="subagent_pipeline",
                content="'stages' must be a list of stage specifications or a JSON array string.",
                success=False,
            )

        if not stages:
            return ToolResult(
                tool_name="subagent_pipeline",
                content="Pipeline 'stages' list cannot be empty.",
                success=False,
            )

        name = params.get("name")
        swarm_id = params.get("swarm_id")
        timeout_per_stage = float(params.get("timeout_per_stage", 120.0))

        from openjarvis.agents.subagents import get_subagent_manager

        mgr = get_subagent_manager()
        try:
            res = mgr.execute_pipeline(
                stages=stages,
                name=name,
                swarm_id=swarm_id,
                timeout_per_stage=timeout_per_stage,
            )
            return ToolResult(
                tool_name="subagent_pipeline",
                content=json.dumps(res.to_dict()),
                success=(res.status == "completed"),
            )
        except Exception as exc:
            logger.exception("Error executing subagent pipeline: %s", exc)
            return ToolResult(
                tool_name="subagent_pipeline",
                content=f"Pipeline execution error: {exc}",
                success=False,
            )


# ---------------------------------------------------------------------------
# SubagentShareTool (Swarm blackboard writer)
# ---------------------------------------------------------------------------


@ToolRegistry.register("subagent_share")
@ToolRegistry.register("swarm_share")
class SubagentShareTool(BaseTool):
    """Share artifacts, data, notes, or findings to the swarm blackboard."""

    tool_id = "subagent_share"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="subagent_share",
            description=(
                "Store or publish an artifact, finding, note, or data object on the shared swarm blackboard. "
                "Any collaborating subagents in the swarm can query and build upon this shared knowledge."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Identifier for the shared data (e.g. 'competitor_matrix', 'findings').",
                    },
                    "value": {
                        "description": "The data content, finding text, dictionary, or artifact to share.",
                    },
                    "swarm_id": {
                        "type": "string",
                        "description": "Swarm ID scope (default: 'default').",
                        "default": "default",
                    },
                    "category": {
                        "type": "string",
                        "description": "Category tag ('artifact', 'data', 'note', 'status'). Default: 'data'.",
                        "default": "data",
                    },
                    "subagent_id": {
                        "type": "string",
                        "description": "Optional author subagent ID.",
                    },
                },
                "required": ["key", "value"],
            },
            category="agents",
            required_capabilities=[],
        )

    def execute(self, **params: Any) -> ToolResult:
        key = str(params.get("key", "")).strip()
        if not key:
            return ToolResult(
                tool_name="subagent_share",
                content="Parameter 'key' is required.",
                success=False,
            )
        value = params.get("value")
        swarm_id = str(params.get("swarm_id") or "default").strip()
        category = str(params.get("category") or "data").strip()
        author_subagent_id = params.get("subagent_id")

        from openjarvis.agents.subagents import get_subagent_manager

        mgr = get_subagent_manager()
        bb = mgr.get_blackboard(swarm_id)
        entry = bb.set(
            key,
            value,
            category=category,
            author_subagent_id=author_subagent_id,
        )

        return ToolResult(
            tool_name="subagent_share",
            content=json.dumps(
                {
                    "swarm_id": swarm_id,
                    "key": entry.key,
                    "category": entry.category,
                    "updated_at": entry.updated_at,
                    "status": "shared",
                }
            ),
            success=True,
        )


# ---------------------------------------------------------------------------
# SubagentQueryTool (Swarm blackboard reader)
# ---------------------------------------------------------------------------


@ToolRegistry.register("subagent_query")
@ToolRegistry.register("swarm_query")
class SubagentQueryTool(BaseTool):
    """Query shared artifacts, findings, or status from the swarm blackboard."""

    tool_id = "subagent_query"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="subagent_query",
            description=(
                "Retrieve shared findings, artifacts, or data from the swarm blackboard. "
                "Can fetch a specific key or list all entries shared by collaborating subagents."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "swarm_id": {
                        "type": "string",
                        "description": "Swarm ID scope (default: 'default').",
                        "default": "default",
                    },
                    "key": {
                        "type": "string",
                        "description": "Optional key to look up. If omitted, returns all blackboard entries.",
                    },
                    "category": {
                        "type": "string",
                        "description": "Optional category filter ('artifact', 'data', 'note', 'status').",
                    },
                },
            },
            category="agents",
            required_capabilities=[],
        )

    def execute(self, **params: Any) -> ToolResult:
        swarm_id = str(params.get("swarm_id") or "default").strip()
        key = params.get("key")
        category = params.get("category")

        from openjarvis.agents.subagents import get_subagent_manager

        mgr = get_subagent_manager()
        bb = mgr.get_blackboard(swarm_id)

        if key:
            entry = bb.get_entry(str(key))
            if entry is None:
                return ToolResult(
                    tool_name="subagent_query",
                    content=json.dumps(
                        {"swarm_id": swarm_id, "found": False, "key": str(key)}
                    ),
                    success=False,
                )
            return ToolResult(
                tool_name="subagent_query",
                content=json.dumps(
                    {"swarm_id": swarm_id, "found": True, "entry": entry.to_dict()}
                ),
                success=True,
            )

        entries = bb.list_entries(category=category)
        return ToolResult(
            tool_name="subagent_query",
            content=json.dumps(
                {
                    "swarm_id": swarm_id,
                    "count": len(entries),
                    "entries": [e.to_dict() for e in entries],
                }
            ),
            success=True,
        )


# ---------------------------------------------------------------------------
# SubagentBroadcastTool (Swarm wide communication)
# ---------------------------------------------------------------------------


@ToolRegistry.register("subagent_broadcast")
@ToolRegistry.register("swarm_broadcast")
class SubagentBroadcastTool(BaseTool):
    """Broadcast an instruction or notification to all active subagents in a swarm."""

    tool_id = "subagent_broadcast"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="subagent_broadcast",
            description="Broadcast a message or directive to all active subagents in a swarm.",
            parameters={
                "type": "object",
                "properties": {
                    "swarm_id": {
                        "type": "string",
                        "description": "Target swarm ID.",
                    },
                    "message": {
                        "type": "string",
                        "description": "Directive or update to broadcast.",
                    },
                },
                "required": ["swarm_id", "message"],
            },
            category="agents",
            required_capabilities=[],
        )

    def execute(self, **params: Any) -> ToolResult:
        swarm_id = str(params.get("swarm_id", "")).strip()
        message = str(params.get("message", "")).strip()

        if not swarm_id or not message:
            return ToolResult(
                tool_name="subagent_broadcast",
                content="Both 'swarm_id' and 'message' are required.",
                success=False,
            )

        from openjarvis.agents.subagents import get_subagent_manager

        mgr = get_subagent_manager()
        notified = mgr.broadcast_to_swarm(swarm_id, message)

        return ToolResult(
            tool_name="subagent_broadcast",
            content=json.dumps(
                {
                    "swarm_id": swarm_id,
                    "notified_count": len(notified),
                    "notified_subagents": notified,
                }
            ),
            success=True,
        )


__all__ = [
    "AgentKillTool",
    "AgentListTool",
    "AgentSendTool",
    "AgentSpawnTool",
    "SubagentBroadcastTool",
    "SubagentKillTool",
    "SubagentListTool",
    "SubagentPipelineTool",
    "SubagentQueryTool",
    "SubagentResultTool",
    "SubagentSendTool",
    "SubagentShareTool",
    "SubagentSpawnTool",
    "SubagentStatusTool",
]
