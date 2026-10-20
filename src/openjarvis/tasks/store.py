"""SQLite persistence layer for Ultron's Persistent Task Runner."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from functools import wraps
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from openjarvis.core.paths import get_config_dir
from openjarvis.tasks.types import StepStatus, TaskRecord, TaskStatus, TaskStep

logger = logging.getLogger(__name__)


def _db_locked(func):
    """Serialize database access across worker threads."""
    @wraps(func)
    def wrapped(self, *args, **kwargs):
        with self._db_lock:
            if getattr(self, "_closed", False):
                return None
            return func(self, *args, **kwargs)
    return wrapped


_CREATE_TASKS_TABLE = """\
CREATE TABLE IF NOT EXISTS tasks (
    task_id             TEXT PRIMARY KEY,
    prompt              TEXT NOT NULL,
    status              TEXT NOT NULL,
    created_at          REAL NOT NULL,
    updated_at          REAL NOT NULL,
    current_step_index  INTEGER NOT NULL DEFAULT 0,
    total_steps         INTEGER NOT NULL DEFAULT 0,
    error               TEXT,
    metadata            TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks (status);
CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks (created_at);
"""

_CREATE_STEPS_TABLE = """\
CREATE TABLE IF NOT EXISTS task_steps (
    step_id             TEXT PRIMARY KEY,
    task_id             TEXT NOT NULL,
    step_index          INTEGER NOT NULL,
    title               TEXT NOT NULL,
    tool_name           TEXT NOT NULL,
    tool_args           TEXT NOT NULL DEFAULT '{}',
    dependencies        TEXT NOT NULL DEFAULT '[]',
    expected_output     TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL,
    actual_output       TEXT,
    error               TEXT,
    retry_count         INTEGER NOT NULL DEFAULT 0,
    max_retries         INTEGER NOT NULL DEFAULT 3,
    idempotency_key     TEXT NOT NULL DEFAULT '',
    artifacts           TEXT NOT NULL DEFAULT '[]',
    safety_decision     TEXT,
    requires_code       INTEGER NOT NULL DEFAULT 0,
    approval_token      TEXT,
    started_at          REAL,
    finished_at         REAL,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_task_steps_task_id ON task_steps (task_id);
CREATE INDEX IF NOT EXISTS idx_task_steps_status ON task_steps (status);
"""


class TaskStore:
    """Thread-safe SQLite CRUD store for task definitions, steps, and progress logs."""

    def __init__(self, db_path: Optional[Union[str, Path]] = None) -> None:
        if db_path is None or str(db_path) == "":
            self._db_path = str(get_config_dir() / "tasks.db")
        else:
            self._db_path = str(db_path)

        if self._db_path != ":memory:":
            from openjarvis.security.file_utils import secure_create
            secure_create(Path(self._db_path))

        self._db_lock = threading.RLock()
        self._closed = False
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    @_db_locked
    def _init_schema(self) -> None:
        """Create tables and indices if not already present."""
        self._conn.executescript(_CREATE_TASKS_TABLE)
        self._conn.executescript(_CREATE_STEPS_TABLE)
        self._conn.commit()

    @_db_locked
    def save_task(self, task: TaskRecord) -> None:
        """Insert or replace a task record and its steps atomically."""
        now = time.time()
        task.updated_at = now
        total_steps = len(task.steps) if task.steps else task.total_steps

        with self._conn:
            self._conn.execute(
                """\
                INSERT INTO tasks (
                    task_id, prompt, status, created_at, updated_at,
                    current_step_index, total_steps, error, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    prompt = excluded.prompt,
                    status = excluded.status,
                    updated_at = excluded.updated_at,
                    current_step_index = excluded.current_step_index,
                    total_steps = excluded.total_steps,
                    error = excluded.error,
                    metadata = excluded.metadata
                """,
                (
                    task.task_id,
                    task.prompt,
                    task.status.value if isinstance(task.status, TaskStatus) else str(task.status),
                    task.created_at,
                    task.updated_at,
                    task.current_step_index,
                    total_steps,
                    task.error,
                    json.dumps(task.metadata),
                ),
            )

            for step in task.steps:
                self._save_step_internal(step)

    @_db_locked
    def _save_step_internal(self, step: TaskStep) -> None:
        """Internal helper to save a step within an existing transaction."""
        self._conn.execute(
            """\
            INSERT INTO task_steps (
                step_id, task_id, step_index, title, tool_name, tool_args,
                dependencies, expected_output, status, actual_output, error,
                retry_count, max_retries, idempotency_key, artifacts,
                safety_decision, requires_code, approval_token, started_at, finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(step_id) DO UPDATE SET
                step_index = excluded.step_index,
                title = excluded.title,
                tool_name = excluded.tool_name,
                tool_args = excluded.tool_args,
                dependencies = excluded.dependencies,
                expected_output = excluded.expected_output,
                status = excluded.status,
                actual_output = excluded.actual_output,
                error = excluded.error,
                retry_count = excluded.retry_count,
                max_retries = excluded.max_retries,
                idempotency_key = excluded.idempotency_key,
                artifacts = excluded.artifacts,
                safety_decision = excluded.safety_decision,
                requires_code = excluded.requires_code,
                approval_token = excluded.approval_token,
                started_at = excluded.started_at,
                finished_at = excluded.finished_at
            """,
            (
                step.step_id,
                step.task_id,
                step.step_index,
                step.title,
                step.tool_name,
                json.dumps(step.tool_args),
                json.dumps(step.dependencies),
                step.expected_output,
                step.status.value if isinstance(step.status, StepStatus) else str(step.status),
                step.actual_output,
                step.error,
                step.retry_count,
                step.max_retries,
                step.idempotency_key,
                json.dumps(step.artifacts),
                json.dumps(step.safety_decision) if step.safety_decision else None,
                1 if step.requires_code else 0,
                step.approval_token,
                step.started_at,
                step.finished_at,
            ),
        )

    @_db_locked
    def save_step(self, step: TaskStep) -> None:
        """Insert or replace a single step."""
        with self._conn:
            self._save_step_internal(step)
            # Update parent task timestamp
            self._conn.execute(
                "UPDATE tasks SET updated_at = ? WHERE task_id = ?",
                (time.time(), step.task_id),
            )

    @_db_locked
    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        """Retrieve a task record with all associated steps."""
        row = self._conn.execute(
            "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        if row is None:
            return None

        steps = self.get_steps_for_task(task_id)
        return TaskRecord(
            task_id=row["task_id"],
            prompt=row["prompt"],
            status=TaskStatus(row["status"]),
            steps=steps,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            current_step_index=row["current_step_index"],
            total_steps=row["total_steps"],
            error=row["error"],
            metadata=json.loads(row["metadata"] or "{}"),
        )

    @_db_locked
    def find_task_by_idempotency_key(self, idempotency_key: str) -> Optional[TaskRecord]:
        """Find an existing task matching a given client idempotency key stored in metadata."""
        if not idempotency_key or not str(idempotency_key).strip():
            return None
        key = str(idempotency_key).strip()
        rows = self._conn.execute(
            "SELECT task_id, metadata FROM tasks ORDER BY created_at DESC LIMIT 200"
        ).fetchall()
        for r in rows:
            try:
                meta = json.loads(r["metadata"] or "{}")
                if meta.get("idempotency_key") == key:
                    return self.get_task(r["task_id"])
            except Exception:
                continue
        return None

    @_db_locked
    def get_steps_for_task(self, task_id: str) -> List[TaskStep]:
        """Retrieve all steps for a task ordered by step_index."""
        rows = self._conn.execute(
            "SELECT * FROM task_steps WHERE task_id = ? ORDER BY step_index ASC",
            (task_id,),
        ).fetchall()
        return [self._row_to_step(r) for r in rows]

    @_db_locked
    def get_step(self, step_id: str) -> Optional[TaskStep]:
        """Retrieve a single step by ID."""
        row = self._conn.execute(
            "SELECT * FROM task_steps WHERE step_id = ?", (step_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_step(row)

    @_db_locked
    def claim_task(
        self,
        task_id: str,
        expected_statuses: Tuple[Union[TaskStatus, str], ...] = (TaskStatus.QUEUED, TaskStatus.PAUSED),
    ) -> bool:
        """Atomically claim a task for execution, transitioning its status to 'running'.

        Returns True if the task was successfully claimed by this caller, False otherwise.
        """
        status_vals = [
            s.value if isinstance(s, TaskStatus) else str(s)
            for s in expected_statuses
        ]
        placeholders = ", ".join("?" for _ in status_vals)
        now = time.time()
        with self._conn:
            cur = self._conn.execute(
                f"""\
                UPDATE tasks
                SET status = ?, updated_at = ?
                WHERE task_id = ? AND status IN ({placeholders})
                """,
                (TaskStatus.RUNNING.value, now, task_id, *status_vals),
            )
            return cur.rowcount > 0

    @_db_locked
    def list_tasks(
        self,
        status: Optional[Union[TaskStatus, str]] = None,
        owner_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[TaskRecord]:
        """List tasks ordered by created_at DESC, with optional status and owner filter."""
        query = "SELECT * FROM tasks"
        params: List[Any] = []
        where_clauses: List[str] = []

        if status:
            val = status.value if isinstance(status, TaskStatus) else str(status)
            where_clauses.append("status = ?")
            params.append(val)

        if owner_id:
            where_clauses.append("json_extract(metadata, '$.owner_id') = ?")
            params.append(owner_id)

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(query, params).fetchall()
        tasks: List[TaskRecord] = []
        for r in rows:
            steps = self.get_steps_for_task(r["task_id"])
            tasks.append(
                TaskRecord(
                    task_id=r["task_id"],
                    prompt=r["prompt"],
                    status=TaskStatus(r["status"]),
                    steps=steps,
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                    current_step_index=r["current_step_index"],
                    total_steps=r["total_steps"],
                    error=r["error"],
                    metadata=json.loads(r["metadata"] or "{}"),
                )
            )
        return tasks

    @_db_locked
    def update_task_status(
        self,
        task_id: str,
        status: Union[TaskStatus, str],
        error: Optional[str] = None,
        current_step_index: Optional[int] = None,
    ) -> None:
        """Update overarching task status."""
        status_val = status.value if isinstance(status, TaskStatus) else str(status)
        now = time.time()
        updates = ["status = ?", "updated_at = ?"]
        params: List[Any] = [status_val, now]

        if error is not None:
            updates.append("error = ?")
            params.append(error)
        if current_step_index is not None:
            updates.append("current_step_index = ?")
            params.append(current_step_index)

        params.append(task_id)
        with self._conn:
            self._conn.execute(
                f"UPDATE tasks SET {', '.join(updates)} WHERE task_id = ?",
                params,
            )

    @_db_locked
    def delete_task(self, task_id: str) -> bool:
        """Delete task and child steps."""
        with self._conn:
            self._conn.execute("DELETE FROM task_steps WHERE task_id = ?", (task_id,))
            res = self._conn.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
            return res.rowcount > 0

    @_db_locked
    def close(self) -> None:
        """Close SQLite connection."""
        self._closed = True
        try:
            self._conn.close()
        except Exception:
            pass

    def _row_to_step(self, row: sqlite3.Row) -> TaskStep:
        """Convert a sqlite3.Row into a TaskStep dataclass."""
        safety_dec = None
        if row["safety_decision"]:
            try:
                safety_dec = json.loads(row["safety_decision"])
            except Exception:
                pass

        return TaskStep(
            step_id=row["step_id"],
            task_id=row["task_id"],
            step_index=row["step_index"],
            title=row["title"],
            tool_name=row["tool_name"],
            tool_args=json.loads(row["tool_args"] or "{}"),
            dependencies=json.loads(row["dependencies"] or "[]"),
            expected_output=row["expected_output"] or "",
            status=StepStatus(row["status"]),
            actual_output=row["actual_output"],
            error=row["error"],
            retry_count=row["retry_count"],
            max_retries=row["max_retries"],
            idempotency_key=row["idempotency_key"] or "",
            artifacts=json.loads(row["artifacts"] or "[]"),
            safety_decision=safety_dec,
            requires_code=bool(row["requires_code"]),
            approval_token=row["approval_token"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
        )
