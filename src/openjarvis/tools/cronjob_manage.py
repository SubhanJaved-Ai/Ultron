"""CronjobManageTool — unified action-oriented background automation management.

Directly inspired by Hermes Agent's cronjob_tools: consolidates cron job management
into a single tool supporting add, list, remove, run (trigger now), pause, resume,
status, and execution history.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from openjarvis.core.paths import get_config_dir
from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.scheduler.scheduler import ScheduledTask, TaskScheduler
from openjarvis.scheduler.store import SchedulerStore
from openjarvis.tools._stubs import BaseTool, ToolSpec

logger = logging.getLogger(__name__)


@ToolRegistry.register("cronjob_manage")
class CronjobManageTool(BaseTool):
    """Unified management tool for scheduled background automation and cron jobs."""

    tool_id = "cronjob_manage"

    def __init__(
        self,
        scheduler: Optional[TaskScheduler] = None,
        store: Optional[SchedulerStore] = None,
        db_path: Optional[Path | str] = None,
    ) -> None:
        self._db_path = Path(db_path) if db_path else get_config_dir() / "scheduler.db"
        self._store = store
        self._scheduler = scheduler

    def _get_store(self) -> SchedulerStore:
        if self._store is None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._store = SchedulerStore(self._db_path)
        return self._store

    def _get_scheduler(self) -> TaskScheduler:
        if self._scheduler is None:
            store = self._get_store()
            self._scheduler = TaskScheduler(store=store)
        return self._scheduler

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="cronjob_manage",
            description=(
                "Unified cron and background automation manager. Actions: "
                "'add' (schedule new task), 'list' (view all scheduled tasks), "
                "'remove' (cancel task), 'run' (trigger execution immediately), "
                "'pause' (temporarily halt), 'resume' (unpause), "
                "'status' (view details), 'history' (view execution run logs)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "add",
                            "list",
                            "remove",
                            "run",
                            "pause",
                            "resume",
                            "status",
                            "history",
                        ],
                        "description": "Action to perform on scheduled tasks.",
                    },
                    "task_id": {
                        "type": "string",
                        "description": "ID of the target scheduled task.",
                    },
                    "prompt": {
                        "type": "string",
                        "description": "The prompt or instruction to execute on schedule (for 'add').",
                    },
                    "schedule": {
                        "type": "string",
                        "description": (
                            "Schedule expression: cron syntax (e.g. '0 9 * * *'), "
                            "interval in seconds (e.g. '3600'), or ISO datetime (for 'add')."
                        ),
                    },
                    "schedule_type": {
                        "type": "string",
                        "enum": ["cron", "interval", "once"],
                        "description": "Explicit schedule type (optional, auto-inferred if omitted).",
                    },
                    "context_mode": {
                        "type": "string",
                        "enum": ["isolated", "carryover"],
                        "description": "Context mode: 'isolated' or 'carryover' (default: 'isolated').",
                    },
                    "tools": {
                        "type": "string",
                        "description": "Comma-separated tool allowlist for this task.",
                    },
                },
                "required": ["action"],
            },
            category="scheduler",
        )

    def _infer_schedule_type(self, schedule_val: str) -> str:
        """Infer whether schedule is cron, interval, or once."""
        val = schedule_val.strip()
        if val.isdigit():
            return "interval"
        parts = val.split()
        if len(parts) == 5:
            return "cron"
        return "once"

    def execute(self, **params: Any) -> ToolResult:
        action = params.get("action", "list")
        task_id = params.get("task_id") or params.get("id") or ""
        user_id = (
            params.get("user_id")
            or params.get("operator_id")
            or getattr(self, "_user_id", None)
        )
        scheduler = self._get_scheduler()
        store = self._get_store()

        if action == "add":
            prompt = params.get("prompt", "").strip()
            schedule = params.get("schedule", "").strip()
            if not prompt or not schedule:
                return ToolResult(
                    tool_name=self.spec.name,
                    success=False,
                    content="Both 'prompt' and 'schedule' are required to add a cron job.",
                )
            stype = params.get("schedule_type") or self._infer_schedule_type(schedule)
            try:
                task = scheduler.create_task(
                    prompt=prompt,
                    schedule_type=stype,
                    schedule_value=schedule,
                    context_mode=params.get("context_mode", "isolated"),
                    tools=params.get("tools", ""),
                )
                if user_id:
                    task_dict = task.to_dict()
                    task_dict.setdefault("metadata", {})["owner_id"] = user_id
                    store.update_task(task_dict)
                return ToolResult(
                    tool_name=self.spec.name,
                    success=True,
                    content=(
                        f"Scheduled task created:\n"
                        f"- ID: {task.id}\n"
                        f"- Type: {task.schedule_type} ({task.schedule_value})\n"
                        f"- Next run: {task.next_run or 'pending'}\n"
                        f"- Prompt: {task.prompt}"
                    ),
                    metadata={"task_id": task.id},
                )
            except Exception as e:
                return ToolResult(
                    tool_name=self.spec.name,
                    success=False,
                    content=f"Failed to create scheduled task: {e}",
                )

        elif action == "list":
            tasks = store.list_tasks(user_id=user_id)
            if not tasks:
                return ToolResult(
                    tool_name=self.spec.name,
                    success=True,
                    content="No scheduled tasks found.",
                )
            lines = [f"Scheduled tasks ({len(tasks)}):"]
            for t in tasks:
                lines.append(
                    f"- [{t['id']}] Status: {t['status'].upper()} | {t['schedule_type']}: {t['schedule_value']} | Next: {t.get('next_run', 'none')} | Prompt: {t['prompt'][:60]}"
                )
            return ToolResult(
                tool_name=self.spec.name,
                success=True,
                content="\n".join(lines),
            )

        elif action == "remove":
            if not task_id:
                return ToolResult(
                    tool_name=self.spec.name,
                    success=False,
                    content="task_id is required to remove a scheduled task.",
                )
            existing = store.get_task(task_id, user_id=user_id)
            if not existing:
                return ToolResult(
                    tool_name=self.spec.name,
                    success=False,
                    content=f"Task not found: {task_id}",
                )
            try:
                scheduler.cancel_task(task_id)
                store.delete_task(task_id, user_id=user_id)
                return ToolResult(
                    tool_name=self.spec.name,
                    success=True,
                    content=f"Removed scheduled task: {task_id}",
                )
            except KeyError:
                return ToolResult(
                    tool_name=self.spec.name,
                    success=False,
                    content=f"Task not found: {task_id}",
                )

        elif action == "pause":
            if not task_id:
                return ToolResult(
                    tool_name=self.spec.name,
                    success=False,
                    content="task_id is required to pause.",
                )
            existing = store.get_task(task_id, user_id=user_id)
            if not existing:
                return ToolResult(
                    tool_name=self.spec.name,
                    success=False,
                    content=f"Task not found: {task_id}",
                )
            try:
                scheduler.pause_task(task_id)
                return ToolResult(
                    tool_name=self.spec.name,
                    success=True,
                    content=f"Paused scheduled task: {task_id}",
                )
            except KeyError:
                return ToolResult(
                    tool_name=self.spec.name,
                    success=False,
                    content=f"Task not found: {task_id}",
                )

        elif action == "resume":
            if not task_id:
                return ToolResult(
                    tool_name=self.spec.name,
                    success=False,
                    content="task_id is required to resume.",
                )
            existing = store.get_task(task_id, user_id=user_id)
            if not existing:
                return ToolResult(
                    tool_name=self.spec.name,
                    success=False,
                    content=f"Task not found: {task_id}",
                )
            try:
                scheduler.resume_task(task_id)
                return ToolResult(
                    tool_name=self.spec.name,
                    success=True,
                    content=f"Resumed scheduled task: {task_id}",
                )
            except KeyError:
                return ToolResult(
                    tool_name=self.spec.name,
                    success=False,
                    content=f"Task not found: {task_id}",
                )

        elif action == "status":
            if not task_id:
                return ToolResult(
                    tool_name=self.spec.name,
                    success=False,
                    content="task_id is required for status.",
                )
            task_dict = store.get_task(task_id, user_id=user_id)
            if not task_dict:
                return ToolResult(
                    tool_name=self.spec.name,
                    success=False,
                    content=f"Task not found: {task_id}",
                )
            return ToolResult(
                tool_name=self.spec.name,
                success=True,
                content=json.dumps(task_dict, indent=2),
            )

        elif action == "run":
            if not task_id:
                return ToolResult(
                    tool_name=self.spec.name,
                    success=False,
                    content="task_id is required to run a task.",
                )
            task_dict = store.get_task(task_id, user_id=user_id)
            if not task_dict:
                return ToolResult(
                    tool_name=self.spec.name,
                    success=False,
                    content=f"Task not found: {task_id}",
                )
            task = ScheduledTask.from_dict(task_dict)
            scheduler._execute_task(task)
            logs = store.get_run_logs(task_id, limit=1)
            last_log = logs[0] if logs else {}
            success = bool(last_log.get("success", False))
            res_str = last_log.get("result") or last_log.get("error") or "Executed"
            return ToolResult(
                tool_name=self.spec.name,
                success=success,
                content=f"Triggered immediate execution for task '{task_id}'. Result: {res_str}",
            )

        elif action == "history":
            if not task_id:
                return ToolResult(
                    tool_name=self.spec.name,
                    success=False,
                    content="task_id is required to fetch history.",
                )
            existing = store.get_task(task_id, user_id=user_id)
            if not existing:
                return ToolResult(
                    tool_name=self.spec.name,
                    success=False,
                    content=f"Task not found: {task_id}",
                )
            logs = store.get_run_logs(task_id, limit=10)
            if not logs:
                return ToolResult(
                    tool_name=self.spec.name,
                    success=True,
                    content=f"No run history logs found for task: {task_id}",
                )
            lines = [f"Execution history for task '{task_id}' ({len(logs)} runs):"]
            for log in logs:
                status = "SUCCESS" if log["success"] else "FAILED"
                lines.append(
                    f"- [{log['started_at']}] {status} | Error: {log['error'] or 'none'} | Result: {log['result'][:80]}"
                )
            return ToolResult(
                tool_name=self.spec.name,
                success=True,
                content="\n".join(lines),
            )

        return ToolResult(
            tool_name=self.spec.name,
            success=False,
            content=f"Unknown action: {action}",
        )
