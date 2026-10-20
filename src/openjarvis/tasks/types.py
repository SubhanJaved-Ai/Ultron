"""Data models and enums for Ultron's Persistent Task Runner."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class TaskStatus(str, Enum):
    """Execution lifecycle status of an overarching task."""
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    PAUSED = "paused"
    FAILED = "failed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class StepStatus(str, Enum):
    """Execution lifecycle status of an individual step."""
    PENDING = "pending"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


@dataclass
class TaskStep:
    """A discrete, verifiable unit of execution within a task plan."""
    step_id: str
    task_id: str
    step_index: int
    title: str
    tool_name: str
    tool_args: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    expected_output: str = ""
    status: StepStatus = StepStatus.PENDING
    actual_output: Optional[str] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    idempotency_key: str = ""
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    safety_decision: Optional[Dict[str, Any]] = None
    requires_code: bool = False
    approval_token: Optional[str] = None
    started_at: Optional[float] = None
    finished_at: Optional[float] = None

    @property
    def requires_user_input(self) -> bool:
        """True if the step is paused specifically waiting for missing user inputs."""
        return bool(self.safety_decision and self.safety_decision.get("requires_user_input"))

    def to_dict(self) -> Dict[str, Any]:
        """Convert step to JSON-serializable dictionary."""
        data = asdict(self)
        data["status"] = self.status.value
        data["requires_user_input"] = self.requires_user_input
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TaskStep:
        """Hydrate TaskStep from dictionary."""
        raw = dict(data)
        raw.pop("requires_user_input", None)
        if isinstance(raw.get("status"), str):
            raw["status"] = StepStatus(raw["status"])
        return cls(**raw)


@dataclass
class TaskRecord:
    """Persistent representation of a task and its execution graph."""
    task_id: str
    prompt: str
    status: TaskStatus = TaskStatus.QUEUED
    steps: List[TaskStep] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    current_step_index: int = 0
    total_steps: int = 0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert task record and nested steps to JSON-serializable dict."""
        return {
            "task_id": self.task_id,
            "prompt": self.prompt,
            "status": self.status.value,
            "steps": [s.to_dict() for s in self.steps],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "current_step_index": self.current_step_index,
            "total_steps": self.total_steps or len(self.steps),
            "error": self.error,
            "metadata": self.metadata,
            "progress": self.progress_summary(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TaskRecord:
        """Hydrate TaskRecord from dictionary."""
        raw = dict(data)
        raw.pop("progress", None)
        if isinstance(raw.get("status"), str):
            raw["status"] = TaskStatus(raw["status"])
        steps_raw = raw.pop("steps", [])
        steps = [
            s if isinstance(s, TaskStep) else TaskStep.from_dict(s)
            for s in steps_raw
        ]
        return cls(steps=steps, **raw)

    def progress_summary(self) -> Dict[str, Any]:
        """Generate clear progress statistics for the task."""
        total = len(self.steps) if self.steps else self.total_steps
        if total == 0:
            pct = 100.0 if self.status == TaskStatus.COMPLETED else 0.0
            return {
                "total_steps": 0,
                "completed_steps": 0,
                "percent_complete": pct,
                "current_step": None,
                "remaining_steps": 0,
                "status": self.status.value,
            }

        completed = sum(1 for s in self.steps if s.status == StepStatus.COMPLETED)
        pct = round((completed / total) * 100, 1)

        current = None
        for s in self.steps:
            if s.status in (StepStatus.RUNNING, StepStatus.WAITING_APPROVAL):
                current = {"step_id": s.step_id, "title": s.title, "status": s.status.value}
                break

        return {
            "total_steps": total,
            "completed_steps": completed,
            "percent_complete": pct,
            "current_step": current,
            "remaining_steps": total - completed,
            "status": self.status.value,
        }
