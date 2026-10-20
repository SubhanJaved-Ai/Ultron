"""Subagent Runtime & Orchestration — OpenClaw-parity subagent system.

Provides autonomous background subagents that can be spawned dynamically
by conversational agents, API routes, or CLI commands. Supports depth
limiting, parallel execution, persistent tracking via AgentManager, and
synchronous or asynchronous execution modes.
"""

from __future__ import annotations

import concurrent.futures
import logging
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_MAX_DEPTH = 2
_DEFAULT_MAX_CONCURRENT_SUBAGENTS = 32


@dataclass
class BlackboardEntry:
    """A single artifact or shared note in a swarm blackboard."""

    key: str
    value: Any
    category: str = "data"  # data, note, artifact, status
    author_subagent_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SwarmBlackboard:
    """Thread-safe in-memory shared knowledge & artifact board for a subagent swarm."""

    def __init__(self, swarm_id: str) -> None:
        self.swarm_id = swarm_id
        self._lock = threading.RLock()
        self._entries: Dict[str, BlackboardEntry] = {}

    def set(
        self,
        key: str,
        value: Any,
        *,
        category: str = "data",
        author_subagent_id: Optional[str] = None,
    ) -> BlackboardEntry:
        """Store or update a key in the swarm blackboard."""
        key_clean = str(key).strip()
        now = time.time()
        with self._lock:
            if key_clean in self._entries:
                entry = self._entries[key_clean]
                entry.value = value
                entry.category = category
                if author_subagent_id:
                    entry.author_subagent_id = author_subagent_id
                entry.updated_at = now
            else:
                entry = BlackboardEntry(
                    key=key_clean,
                    value=value,
                    category=category,
                    author_subagent_id=author_subagent_id,
                    created_at=now,
                    updated_at=now,
                )
                self._entries[key_clean] = entry
            return entry

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve the value of a key, or default if missing."""
        with self._lock:
            entry = self._entries.get(str(key).strip())
            return entry.value if entry is not None else default

    def get_entry(self, key: str) -> Optional[BlackboardEntry]:
        """Retrieve the full BlackboardEntry for a key."""
        with self._lock:
            return self._entries.get(str(key).strip())

    def list_entries(self, category: Optional[str] = None) -> List[BlackboardEntry]:
        """List all entries, optionally filtered by category."""
        with self._lock:
            if category:
                return [e for e in self._entries.values() if e.category == category]
            return list(self._entries.values())

    def to_dict(self) -> Dict[str, Any]:
        """Return all entries as a JSON-compatible dictionary."""
        with self._lock:
            return {k: v.to_dict() for k, v in self._entries.items()}

    def to_summary_text(self) -> str:
        """Generate human/agent readable summary of current blackboard state."""
        with self._lock:
            if not self._entries:
                return "(empty blackboard)"
            lines = []
            for k, e in self._entries.items():
                val_repr = str(e.value)
                if len(val_repr) > 160:
                    val_repr = val_repr[:157] + "..."
                lines.append(f"- [{e.category}] {k}: {val_repr}")
            return "\n".join(lines)


@dataclass
class SwarmPipelineStage:
    """Specification for one stage in a multi-subagent pipeline."""

    name: str
    task: str
    agent_type: str = "orchestrator"
    tools: List[str] = field(default_factory=list)
    timeout: float = 120.0
    optional: bool = False
    output_key: Optional[str] = None  # Key in blackboard to store this stage's result


@dataclass
class SwarmPipelineResult:
    """Result of executing a multi-subagent pipeline."""

    swarm_id: str
    pipeline_name: str
    status: str  # completed, failed, partial
    stages_completed: int
    total_stages: int
    stage_results: List[Dict[str, Any]]
    final_output: str
    blackboard_summary: Dict[str, Any]
    duration_seconds: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SubagentRecord:
    """State record for an active or completed subagent."""

    id: str
    name: str
    task: str
    agent_type: str = "orchestrator"
    tools: List[str] = field(default_factory=list)
    status: str = "pending"  # pending, running, completed, failed, stopped
    progress: str = ""
    result: str = ""
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    parent_agent_id: Optional[str] = None
    parent_channel: Optional[str] = None
    parent_conversation_id: Optional[str] = None
    depth: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)
    swarm_id: Optional[str] = None
    pipeline_stage: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert record to a JSON-serializable dictionary."""
        data = asdict(self)
        if self.completed_at and self.started_at:
            data["duration_seconds"] = round(self.completed_at - self.started_at, 2)
        elif self.started_at:
            data["duration_seconds"] = round(time.time() - self.started_at, 2)
        else:
            data["duration_seconds"] = 0.0
        return data


class SubagentManager:
    """Manages autonomous subagent lifecycles, execution, and tracking."""

    def __init__(
        self,
        *,
        max_depth: int = _DEFAULT_MAX_DEPTH,
        max_workers: int = _DEFAULT_MAX_CONCURRENT_SUBAGENTS,
    ) -> None:
        self.max_depth = max_depth
        self._lock = threading.RLock()
        self._subagents: Dict[str, SubagentRecord] = {}
        self._blackboards: Dict[str, SwarmBlackboard] = {}
        self._futures: Dict[str, concurrent.futures.Future] = {}
        self._pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="subagent-worker",
        )
        self._engine: Optional[Any] = None
        self._model: Optional[str] = None
        self._system: Optional[Any] = None
        self._manager: Optional[Any] = None
        self._bus: Optional[Any] = None
        self._agent_runner: Optional[Callable[[SubagentRecord], str]] = None

    def set_dependencies(
        self,
        *,
        engine: Optional[Any] = None,
        model: Optional[str] = None,
        system: Optional[Any] = None,
        manager: Optional[Any] = None,
        bus: Optional[Any] = None,
        agent_runner: Optional[Callable[[SubagentRecord], str]] = None,
    ) -> None:
        """Inject runtime dependencies for execution and event emission."""
        with self._lock:
            if engine is not None:
                self._engine = engine
            if model is not None:
                self._model = model
            if system is not None:
                self._system = system
                if self._engine is None and hasattr(system, "engine"):
                    self._engine = system.engine
                if self._model is None and hasattr(system, "model"):
                    self._model = system.model
                if self._manager is None and hasattr(system, "agent_manager"):
                    self._manager = system.agent_manager
                if self._bus is None and hasattr(system, "bus"):
                    self._bus = system.bus
            if manager is not None:
                self._manager = manager
            if bus is not None:
                self._bus = bus
            if agent_runner is not None:
                self._agent_runner = agent_runner

    def spawn(
        self,
        task: str,
        *,
        name: Optional[str] = None,
        agent_type: str = "orchestrator",
        tools: Optional[List[str] | str] = None,
        parent_agent_id: Optional[str] = None,
        parent_channel: Optional[str] = None,
        parent_conversation_id: Optional[str] = None,
        depth: int = 1,
        wait: bool = False,
        timeout: float = 60.0,
        subagent_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        swarm_id: Optional[str] = None,
        pipeline_stage: Optional[str] = None,
    ) -> SubagentRecord:
        """Spawn a new subagent to handle a task.

        Parameters
        ----------
        task:
            The instruction or prompt for the subagent.
        name:
            Human-readable label for the subagent.
        agent_type:
            Agent class key in AgentRegistry (e.g., 'orchestrator', 'deep_research').
        tools:
            Optional tool names granted to this subagent.
        parent_agent_id:
            ID of the spawning agent if nested.
        parent_channel:
            Channel origin for user notifications upon completion.
        parent_conversation_id:
            Session ID for routing replies.
        depth:
            Nesting depth (depth-1 main, depth-2 subagent).
        wait:
            If True, blocks until the subagent completes or times out.
        timeout:
            Seconds to wait if ``wait=True``.
        subagent_id:
            Custom identifier (auto-generated if omitted).
        """
        task_str = (task or "").strip()
        if not task_str:
            raise ValueError("Subagent task cannot be empty")

        if depth > self.max_depth:
            raise ValueError(
                f"Maximum subagent nesting depth ({self.max_depth}) exceeded. "
                "Subagents cannot spawn further subagents beyond this limit."
            )

        sid = subagent_id or f"subagent_{uuid.uuid4().hex[:8]}"
        display_name = name or f"Subagent: {task_str[:28]}"

        tool_list: List[str] = []
        if isinstance(tools, str):
            tool_list = [t.strip() for t in tools.split(",") if t.strip()]
        elif isinstance(tools, list):
            tool_list = [str(t).strip() for t in tools if str(t).strip()]

        record = SubagentRecord(
            id=sid,
            name=display_name,
            task=task_str,
            agent_type=agent_type or "orchestrator",
            tools=tool_list,
            parent_agent_id=parent_agent_id,
            parent_channel=parent_channel,
            parent_conversation_id=parent_conversation_id,
            depth=depth,
            metadata=dict(metadata or {}),
            swarm_id=swarm_id,
            pipeline_stage=pipeline_stage,
        )

        with self._lock:
            self._subagents[sid] = record

        # Register in persistent AgentManager if available
        if self._manager is not None:
            try:
                self._manager.create_agent(
                    name=display_name,
                    agent_type=agent_type,
                    config={
                        "instruction": task_str,
                        "is_subagent": True,
                        "parent_id": parent_agent_id,
                        "depth": depth,
                    },
                )
                self._manager.create_task(
                    agent_id=sid,
                    description=task_str,
                )
            except Exception as exc:
                logger.debug("Failed to register subagent in AgentManager: %s", exc)

        # Submit task to worker pool
        future = self._pool.submit(self._execute_subagent, record)
        with self._lock:
            self._futures[sid] = future

        if wait:
            try:
                future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                logger.warning("Subagent %s timed out after %.1fs", sid, timeout)
            except Exception as exc:
                logger.error("Subagent %s failed: %s", sid, exc)

        return record

    def get(self, subagent_id: str) -> Optional[SubagentRecord]:
        """Fetch a subagent record by ID."""
        with self._lock:
            return self._subagents.get(subagent_id)

    def list_subagents(
        self,
        status: Optional[str] = None,
    ) -> List[SubagentRecord]:
        """List tracked subagents, optionally filtered by status."""
        with self._lock:
            records = list(self._subagents.values())
        if status and status.lower() != "all":
            target = status.lower()
            records = [r for r in records if r.status.lower() == target]
        return sorted(records, key=lambda r: r.created_at, reverse=True)

    def kill(self, subagent_id: str) -> bool:
        """Stop or cancel a running subagent."""
        with self._lock:
            record = self._subagents.get(subagent_id)
            future = self._futures.get(subagent_id)

            if not record:
                return False

            if record.status in ("completed", "failed", "stopped"):
                return True

            if future and not future.done():
                future.cancel()

            record.status = "stopped"
            record.completed_at = time.time()
            record.error = "Subagent cancelled by user or parent agent."

        if self._manager is not None:
            try:
                self._manager.update_agent(subagent_id, status="stopped")
            except Exception:
                pass

        if self._bus is not None:
            try:
                self._bus.publish(
                    "subagent.stopped",
                    {"subagent_id": subagent_id, "status": "stopped"},
                )
            except Exception:
                pass

        return True

    def send_message(self, subagent_id: str, message: str) -> bool:
        """Send an updated instruction or query to a subagent."""
        with self._lock:
            record = self._subagents.get(subagent_id)
            if not record:
                return False
            record.task = f"{record.task}\n\nUpdate: {message}"

        if self._manager is not None:
            try:
                self._manager.send_message(subagent_id, message)
            except Exception:
                pass

        return True

    def get_blackboard(self, swarm_id: str) -> SwarmBlackboard:
        """Get or create the shared SwarmBlackboard for a swarm."""
        sid = str(swarm_id or "default").strip()
        with self._lock:
            if sid not in self._blackboards:
                self._blackboards[sid] = SwarmBlackboard(swarm_id=sid)
            return self._blackboards[sid]

    def broadcast_to_swarm(self, swarm_id: str, message: str) -> List[str]:
        """Broadcast a message or status update to all active subagents in a swarm."""
        sid = str(swarm_id or "").strip()
        if not sid:
            return []
        notified = []
        with self._lock:
            records = [
                r
                for r in self._subagents.values()
                if r.swarm_id == sid and r.status in ("pending", "running")
            ]
        for r in records:
            if self.send_message(r.id, message):
                notified.append(r.id)

        bb = self.get_blackboard(sid)
        bb.set(
            f"broadcast:{int(time.time() * 1000)}",
            message,
            category="note",
        )
        return notified

    def execute_pipeline(
        self,
        stages: List[Dict[str, Any] | SwarmPipelineStage],
        *,
        name: Optional[str] = None,
        swarm_id: Optional[str] = None,
        parent_agent_id: Optional[str] = None,
        parent_channel: Optional[str] = None,
        parent_conversation_id: Optional[str] = None,
        depth: int = 1,
        timeout_per_stage: float = 120.0,
    ) -> SwarmPipelineResult:
        """Execute a coordinated multi-stage pipeline of subagents."""
        if not stages:
            raise ValueError("Pipeline must have at least one stage")

        pipeline_name = name or f"Pipeline-{uuid.uuid4().hex[:6]}"
        sid = swarm_id or f"swarm_{uuid.uuid4().hex[:8]}"
        bb = self.get_blackboard(sid)
        bb.set("pipeline_name", pipeline_name, category="status")
        bb.set("status", "running", category="status")

        start_time = time.time()
        stage_results: List[Dict[str, Any]] = []
        previous_result = ""
        pipeline_status = "completed"
        pipeline_error = None

        for idx, stage_spec in enumerate(stages):
            if isinstance(stage_spec, dict):
                st_name = str(stage_spec.get("name") or f"Stage-{idx + 1}")
                st_task = str(stage_spec.get("task", ""))
                st_agent_type = str(stage_spec.get("agent_type", "orchestrator"))
                st_tools = stage_spec.get("tools")
                st_timeout = float(stage_spec.get("timeout", timeout_per_stage))
                st_optional = bool(stage_spec.get("optional", False))
                st_output_key = stage_spec.get("output_key")
            elif isinstance(stage_spec, SwarmPipelineStage):
                st_name = stage_spec.name
                st_task = stage_spec.task
                st_agent_type = stage_spec.agent_type
                st_tools = stage_spec.tools
                st_timeout = stage_spec.timeout
                st_optional = stage_spec.optional
                st_output_key = stage_spec.output_key
            else:
                continue

            # Template expansion
            task_rendered = st_task
            task_rendered = task_rendered.replace("{previous_result}", previous_result)
            task_rendered = task_rendered.replace("{blackboard}", bb.to_summary_text())
            for prev_stage in stage_results:
                task_rendered = task_rendered.replace(
                    f"{{stage:{prev_stage['name']}}}",
                    prev_stage.get("result", ""),
                )

            record = self.spawn(
                task=task_rendered,
                name=f"{pipeline_name} :: {st_name}",
                agent_type=st_agent_type,
                tools=st_tools,
                parent_agent_id=parent_agent_id,
                parent_channel=parent_channel,
                parent_conversation_id=parent_conversation_id,
                depth=depth,
                wait=True,
                timeout=st_timeout,
                swarm_id=sid,
                pipeline_stage=st_name,
                metadata={
                    "pipeline_name": pipeline_name,
                    "stage_index": idx,
                    "stage_name": st_name,
                },
            )

            stage_info = {
                "stage": idx + 1,
                "name": st_name,
                "subagent_id": record.id,
                "status": record.status,
                "result": record.result,
                "error": record.error,
                "duration_seconds": round(
                    (record.completed_at or time.time())
                    - (record.started_at or time.time()),
                    2,
                ),
            }
            stage_results.append(stage_info)

            if record.status == "completed":
                previous_result = record.result
                bb.set(
                    f"stage:{st_name}:result",
                    record.result,
                    category="artifact",
                    author_subagent_id=record.id,
                )
                if st_output_key:
                    bb.set(
                        str(st_output_key),
                        record.result,
                        category="data",
                        author_subagent_id=record.id,
                    )
            else:
                bb.set(
                    f"stage:{st_name}:error",
                    record.error or "Unknown failure",
                    category="status",
                    author_subagent_id=record.id,
                )
                if not st_optional:
                    pipeline_status = "failed"
                    pipeline_error = f"Stage '{st_name}' failed: {record.error}"
                    break

        duration = round(time.time() - start_time, 2)
        bb.set("status", pipeline_status, category="status")
        bb.set("duration_seconds", duration, category="status")

        final_out = (
            previous_result
            if pipeline_status == "completed"
            else (pipeline_error or "")
        )

        return SwarmPipelineResult(
            swarm_id=sid,
            pipeline_name=pipeline_name,
            status=pipeline_status,
            stages_completed=len(
                [s for s in stage_results if s["status"] == "completed"]
            ),
            total_stages=len(stages),
            stage_results=stage_results,
            final_output=final_out,
            blackboard_summary=bb.to_dict(),
            duration_seconds=duration,
            error=pipeline_error,
        )

    def _execute_subagent(self, record: SubagentRecord) -> None:
        """Execution worker that runs inside the thread pool."""
        record.status = "running"
        record.started_at = time.time()
        record.progress = "Starting execution..."

        if self._manager is not None:
            try:
                self._manager.update_agent(
                    record.id,
                    status="running",
                    current_activity="Executing task",
                )
            except Exception:
                pass

        if self._bus is not None:
            try:
                self._bus.publish(
                    "subagent.started",
                    {
                        "subagent_id": record.id,
                        "name": record.name,
                        "task": record.task,
                    },
                )
            except Exception:
                pass

        try:
            # 1. Custom runner hook (used in tests or special plugins)
            if self._agent_runner is not None:
                output = self._agent_runner(record)
            else:
                output = self._run_agent_turn(record)

            record.result = str(output or "")
            record.status = "completed"
            record.completed_at = time.time()
            record.progress = "Completed successfully."

            # Update AgentManager
            if self._manager is not None:
                try:
                    self._manager.update_agent(
                        record.id,
                        status="idle",
                        current_activity="",
                        summary_memory=record.result[:8000],
                    )
                except Exception:
                    pass

            # Publish completion event
            if self._bus is not None:
                try:
                    self._bus.publish(
                        "subagent.completed",
                        {
                            "subagent_id": record.id,
                            "name": record.name,
                            "task": record.task,
                            "result": record.result,
                            "duration": record.completed_at - (record.started_at or 0),
                        },
                    )
                except Exception:
                    pass

            # Optional notification dispatch to parent channel
            self._notify_parent_channel(record)

        except Exception as exc:
            logger.exception("Error executing subagent %s", record.id)
            record.status = "failed"
            record.error = str(exc)
            record.completed_at = time.time()
            record.progress = f"Failed: {exc}"

            if self._manager is not None:
                try:
                    self._manager.update_agent(
                        record.id,
                        status="error",
                        current_activity="",
                    )
                except Exception:
                    pass

            if self._bus is not None:
                try:
                    self._bus.publish(
                        "subagent.failed",
                        {
                            "subagent_id": record.id,
                            "name": record.name,
                            "error": str(exc),
                        },
                    )
                except Exception:
                    pass

    def _run_agent_turn(self, record: SubagentRecord) -> str:
        """Run the actual AI agent for this subagent task."""
        from openjarvis.core.registry import AgentRegistry, ToolRegistry

        # 1. Resolve Engine & Model
        engine = self._engine
        model = self._model

        if engine is None and self._system is not None:
            engine = getattr(self._system, "engine", None)
            model = model or getattr(self._system, "model", None)

        if engine is None:
            try:
                from openjarvis.core.config import load_config
                from openjarvis.engine._discovery import get_engine

                cfg = load_config()
                resolved = get_engine(cfg)
                if resolved:
                    _, engine = resolved
                    model = model or getattr(cfg.intelligence, "default_model", "")
            except Exception as exc:
                logger.debug("Engine auto-discovery failed: %s", exc)

        if engine is None:
            # Fallback when running without a live inference engine
            return (
                f"[Subagent completed: task '{record.task}' "
                "processed without engine connection]"
            )

        # 2. Resolve Agent Class
        agent_type = record.agent_type or "orchestrator"
        try:
            agent_cls = AgentRegistry.get(agent_type)
        except KeyError:
            from openjarvis.agents.orchestrator import OrchestratorAgent

            agent_cls = OrchestratorAgent

        # 3. Resolve Tools for Subagent
        subagent_tools = self._resolve_tools_for_subagent(record)

        # 4. Construct and Run Agent
        system_prompt = (
            f"You are subagent '{record.name}' (ID: {record.id}).\n"
            f"You were spawned to autonomously complete the following mission:\n"
            f"{record.task}\n\n"
            "Use your tools to carry out the necessary work, research, or execution. "
            "When finished, provide a comprehensive, well-structured final "
            "report and findings."
        )

        agent_kwargs: Dict[str, Any] = {
            "bus": self._bus,
        }
        if (
            getattr(agent_cls, "accepts_tools", False)
            or issubclass(
                agent_cls,
                ToolRegistry.get("orchestrator")
                if ToolRegistry.contains("orchestrator")
                else object,
            )
            or hasattr(agent_cls, "__init__")
        ):
            agent_kwargs["tools"] = subagent_tools
            agent_kwargs["system_prompt"] = system_prompt

        try:
            agent_inst = agent_cls(
                engine=engine,
                model=model or "default",
                **agent_kwargs,
            )
        except TypeError:
            try:
                agent_inst = agent_cls(
                    engine=engine,
                    model=model or "default",
                    system_prompt=system_prompt,
                )
            except TypeError:
                agent_inst = agent_cls(engine=engine, model=model or "default")

        result = agent_inst.run(record.task)
        content = getattr(result, "content", None)
        return str(content) if content is not None else str(result)

    def _resolve_tools_for_subagent(self, record: SubagentRecord) -> List[Any]:
        """Resolve tools accessible to this subagent."""
        from openjarvis.core.registry import ToolRegistry

        resolved_tools: List[Any] = []
        requested = record.tools

        # Exclude administrative and runaway spawn tools from child agents at max depth
        denied_tools = {"agent_kill", "subagent_kill"}
        if record.depth >= self.max_depth:
            denied_tools.update({"subagent_spawn", "sessions_spawn", "agent_spawn"})

        if requested:
            for t_name in requested:
                if t_name in denied_tools:
                    continue
                if ToolRegistry.contains(t_name):
                    tool = ToolRegistry.create(t_name)
                    resolved_tools.append(tool)
        else:
            # Grant default safe toolset
            default_safe = [
                "calculator",
                "think",
                "web_search",
                "file_read",
                "code_interpreter",
                "repl",
                "browser_extract",
                "clawhub_search",
                "clawhub_info",
                "subagent_share",
                "subagent_query",
            ]
            # If not at max depth, allow subagent spawning for depth-1 subagents
            if record.depth < self.max_depth:
                default_safe.append("subagent_spawn")

            for t_name in default_safe:
                if ToolRegistry.contains(t_name) and t_name not in denied_tools:
                    try:
                        resolved_tools.append(ToolRegistry.create(t_name))
                    except Exception:
                        pass

        return resolved_tools

    def _notify_parent_channel(self, record: SubagentRecord) -> None:
        """Send a completion message back to user if channel info is present."""
        if not record.parent_channel or self._system is None:
            return
        channel_backend = getattr(self._system, "channel_backend", None)
        if not channel_backend:
            return
        try:
            summary = f"Subagent '{record.name}' completed:\n\n{record.result[:1000]}"
            if len(record.result) > 1000:
                summary += "\n\n... (full report saved in subagent results)"
            channel_backend.send(
                record.parent_channel,
                summary,
                conversation_id=record.parent_conversation_id or "",
            )
        except Exception as exc:
            logger.debug("Failed to dispatch subagent channel notification: %s", exc)


# Global singleton instance
_GLOBAL_SUBAGENT_MANAGER: Optional[SubagentManager] = None
_GLOBAL_LOCK = threading.Lock()


def get_subagent_manager() -> SubagentManager:
    """Return the global SubagentManager singleton."""
    global _GLOBAL_SUBAGENT_MANAGER
    with _GLOBAL_LOCK:
        if _GLOBAL_SUBAGENT_MANAGER is None:
            _GLOBAL_SUBAGENT_MANAGER = SubagentManager()
        return _GLOBAL_SUBAGENT_MANAGER


def reset_subagent_manager() -> None:
    """Reset the global SubagentManager (primarily for test isolation)."""
    global _GLOBAL_SUBAGENT_MANAGER
    with _GLOBAL_LOCK:
        _GLOBAL_SUBAGENT_MANAGER = None


__all__ = [
    "BlackboardEntry",
    "SubagentManager",
    "SubagentRecord",
    "SwarmBlackboard",
    "SwarmPipelineResult",
    "SwarmPipelineStage",
    "get_subagent_manager",
    "reset_subagent_manager",
]
