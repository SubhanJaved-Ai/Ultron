"""Application-level end-to-end integration tests for task execution and approval workflows.

Exercises the real supported application workflow:
Task submitted via API -> Persisted task created -> Approval / required-input gate ->
Authorized execution -> Result persisted -> Final result retrieved.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from openjarvis.core.events import EventBus
from openjarvis.core.types import ToolResult
from openjarvis.security.kernel import CustomRuleEngine, SafetyCodeManager, SafetyKernel
from openjarvis.server.app import create_app
from openjarvis.tasks.runner import PersistentTaskRunner
from openjarvis.tasks.store import TaskStore
from openjarvis.tasks.types import StepStatus, TaskStatus, TaskStep


def _make_mock_engine():
    engine = MagicMock()
    engine.engine_id = "mock"
    engine.health.return_value = True
    engine.list_models.return_value = ["test-model"]
    return engine


@pytest.fixture
def e2e_env(tmp_path: Path):
    """Setup an end-to-end environment with real store, kernel, runner, and FastAPI app."""
    db_file = tmp_path / "e2e_tasks.db"
    store = TaskStore(db_file)

    code_file = tmp_path / "safety_code.json"
    rules_file = tmp_path / "custom_rules.json"
    code_mgr = SafetyCodeManager(storage_path=code_file)
    rules_engine = CustomRuleEngine(storage_path=rules_file)
    kernel = SafetyKernel(code_manager=code_mgr, rules_engine=rules_engine)
    code_mgr.set_code("998877")

    bus = EventBus(record_history=False)

    runner = PersistentTaskRunner(
        store=store,
        bus=bus,
        kernel=kernel,
        auto_recover=False,
    )

    runner.register_custom_tool(
        "safe_calc",
        lambda **args: ToolResult(tool_name="safe_calc", content=f"Calculated: {args.get('val', 42)}"),
    )
    runner.register_custom_tool(
        "file_cleanup",
        lambda **args: ToolResult(tool_name="file_cleanup", content="Cleanup finished successfully."),
    )

    def _failing_handler(**args):
        raise RuntimeError("Underlying service connection refused.")

    runner.register_custom_tool("failing_tool", _failing_handler)
    runner.register_custom_tool(
        "parameterized_tool",
        lambda **args: ToolResult(tool_name="parameterized_tool", content=f"Executed with {args.get('api_key')}"),
    )

    app = create_app(_make_mock_engine(), "test-model")
    app.state.task_runner = runner

    # Middleware to inject test users for multi-user tests
    @app.middleware("http")
    async def inject_mock_user(request: Request, call_next):
        mock_user_id = request.headers.get("X-Mock-User")
        if mock_user_id:
            user = MagicMock()
            user.id = mock_user_id
            user.username = mock_user_id
            user.role = request.headers.get("X-Mock-Role", "member")
            request.state.user = user
        return await call_next(request)

    client = TestClient(app)

    yield {
        "store": store,
        "kernel": kernel,
        "runner": runner,
        "app": app,
        "client": client,
        "code_mgr": code_mgr,
    }

    store.close()


class TestTaskExecutionAndApprovalE2E:
    """Integration suite verifying real task execution, gating, and persistence."""

    def test_successful_task_execution_and_persisted_final_output(self, e2e_env):
        """Task submitted -> executed -> final output retrieved via API."""
        client = e2e_env["client"]
        runner = e2e_env["runner"]

        # 1. Submit task with explicit safe steps
        payload = {
            "prompt": "Calculate daily budget report",
            "auto_run": False,
            "steps": [
                {
                    "step_id": "step_1",
                    "title": "Compute balance",
                    "tool_name": "safe_calc",
                    "tool_args": {"val": 1500},
                },
                {
                    "step_id": "step_2",
                    "title": "Compute variance",
                    "tool_name": "safe_calc",
                    "tool_args": {"val": 250},
                    "dependencies": ["step_1"],
                },
            ],
        }
        create_resp = client.post("/api/tasks", json=payload)
        assert create_resp.status_code == 200
        task_data = create_resp.json()["task"]
        task_id = task_data["task_id"]
        assert task_data["status"] == "queued"
        assert len(task_data["steps"]) == 2

        # 2. Run the task synchronously through runner
        task = runner.run_task(task_id, background=False)
        assert task.status == TaskStatus.COMPLETED

        # 3. Retrieve final persisted task through API
        get_resp = client.get(f"/api/tasks/{task_id}")
        assert get_resp.status_code == 200
        retrieved = get_resp.json()["task"]
        assert retrieved["status"] == "completed"
        assert len(retrieved["steps"]) == 2
        assert retrieved["steps"][0]["status"] == "completed"
        assert "Calculated: 1500" in (retrieved["steps"][0]["actual_output"] or "")
        assert retrieved["steps"][1]["status"] == "completed"
        assert "Calculated: 250" in (retrieved["steps"][1]["actual_output"] or "")

    def test_approval_gated_execution_and_rejection_halts_downstream(self, e2e_env):
        """Risky step enters WAITING_APPROVAL -> Rejection halts downstream execution."""
        client = e2e_env["client"]
        runner = e2e_env["runner"]

        payload = {
            "prompt": "Purge cache and notify",
            "auto_run": False,
            "steps": [
                {
                    "step_id": "cleanup_step",
                    "title": "Delete temporary directory",
                    "tool_name": "file_cleanup",
                    "tool_args": {"target": "/tmp/cache"},
                },
                {
                    "step_id": "downstream_notify",
                    "title": "Notify operator",
                    "tool_name": "safe_calc",
                    "tool_args": {"val": 1},
                    "dependencies": ["cleanup_step"],
                },
            ],
        }
        create_resp = client.post("/api/tasks", json=payload)
        task_id = create_resp.json()["task"]["task_id"]

        # Run task: cleanup_step should be gated by Safety Kernel (ActionEffect.ASK_WITH_CODE)
        task = runner.run_task(task_id, background=False)
        assert task.status in (TaskStatus.WAITING_APPROVAL, TaskStatus.PAUSED, TaskStatus.RUNNING)
        assert task.steps[0].status == StepStatus.WAITING_APPROVAL
        assert task.steps[0].safety_decision is not None
        assert task.steps[1].status == StepStatus.PENDING

        # Reject the approval request via API
        reject_resp = client.post(
            f"/api/tasks/{task_id}/reject",
            json={"step_id": "cleanup_step", "reason": "Operator denied file cleanup."},
        )
        assert reject_resp.status_code == 200
        assert reject_resp.json()["status"] == "rejected"

        # Verify task state in database: cleanup_step marked FAILED with rejection message
        refreshed = runner.store.get_task(task_id)
        assert refreshed.steps[0].status == StepStatus.FAILED
        assert "Authorization rejected" in (refreshed.steps[0].error or "")
        assert refreshed.status == TaskStatus.FAILED
        assert refreshed.steps[0].actual_output is None or refreshed.steps[0].actual_output == ""
        assert refreshed.steps[1].actual_output is None or refreshed.steps[1].actual_output == ""

    def test_approval_with_safety_code_authorizes_and_completes_task(self, e2e_env):
        """Risky step approved with correct safety code executes and completes task."""
        client = e2e_env["client"]
        runner = e2e_env["runner"]

        payload = {
            "prompt": "Authorized cleanup task",
            "auto_run": False,
            "steps": [
                {
                    "step_id": "auth_cleanup",
                    "title": "Clean temporary storage",
                    "tool_name": "file_cleanup",
                    "tool_args": {"target": "D:/temp"},
                }
            ],
        }
        create_resp = client.post("/api/tasks", json=payload)
        task_id = create_resp.json()["task"]["task_id"]

        # Run task -> pauses on approval
        runner.run_task(task_id, background=False)
        step = runner.store.get_task(task_id).steps[0]
        assert step.status == StepStatus.WAITING_APPROVAL

        # Invalid safety code should be rejected (403)
        bad_approve = client.post(
            f"/api/tasks/{task_id}/approve",
            json={"step_id": "auth_cleanup", "safety_code": "000000"},
        )
        assert bad_approve.status_code == 403

        # Valid safety code ("998877") should approve
        good_approve = client.post(
            f"/api/tasks/{task_id}/approve",
            json={"step_id": "auth_cleanup", "safety_code": "998877"},
        )
        assert good_approve.status_code == 200
        assert good_approve.json()["status"] == "approved"

        # Wait for background thread completion (poll up to 3.0s)
        completed_task = None
        for _ in range(30):
            t = runner.store.get_task(task_id)
            if t and t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                completed_task = t
                break
            time.sleep(0.1)

        assert completed_task is not None
        assert completed_task.status == TaskStatus.COMPLETED
        assert completed_task.steps[0].status == StepStatus.COMPLETED
        assert "Cleanup finished" in (completed_task.steps[0].actual_output or "")

    def test_missing_input_gating_and_submission(self, e2e_env):
        """Step requiring user input pauses -> submitting input validates and resumes."""
        client = e2e_env["client"]
        runner = e2e_env["runner"]

        payload = {
            "prompt": "Parameterized API execution",
            "auto_run": False,
            "steps": [
                {
                    "step_id": "input_step",
                    "title": "Call remote service",
                    "tool_name": "parameterized_tool",
                    "tool_args": {},
                    "requires_user_input": True,
                }
            ],
        }
        create_resp = client.post("/api/tasks", json=payload)
        task_id = create_resp.json()["task"]["task_id"]

        # Step marked requires_user_input
        task = runner.store.get_task(task_id)
        task.steps[0].status = StepStatus.WAITING_APPROVAL
        runner.store.save_step(task.steps[0])

        # Submit user arguments via API
        input_resp = client.post(
            f"/api/tasks/{task_id}/input",
            json={"step_id": "input_step", "tool_args": {"api_key": "sec_key_123"}},
        )
        assert input_resp.status_code == 200

        # Step arguments updated and executed
        refreshed = runner.store.get_task(task_id)
        assert refreshed.steps[0].tool_args.get("api_key") == "sec_key_123"

    def test_failure_propagation_and_task_failure_state(self, e2e_env):
        """Step execution failure halts DAG and marks task FAILED."""
        client = e2e_env["client"]
        runner = e2e_env["runner"]

        payload = {
            "prompt": "Task with failing tool",
            "auto_run": False,
            "steps": [
                {
                    "step_id": "fail_step",
                    "title": "Execute faulty tool",
                    "tool_name": "failing_tool",
                    "tool_args": {},
                },
                {
                    "step_id": "never_run",
                    "title": "Downstream step",
                    "tool_name": "safe_calc",
                    "tool_args": {"val": 10},
                    "dependencies": ["fail_step"],
                },
            ],
        }
        create_resp = client.post("/api/tasks", json=payload)
        task_id = create_resp.json()["task"]["task_id"]

        failed_task = runner.run_task(task_id, background=False)
        assert failed_task.status == TaskStatus.FAILED
        assert failed_task.steps[0].status == StepStatus.FAILED
        assert "Underlying service connection refused" in (failed_task.steps[0].error or "")
        assert failed_task.steps[1].status in (StepStatus.PENDING, StepStatus.CANCELLED)

    def test_multi_user_task_access_isolation(self, e2e_env):
        """Non-owner requests return 403 Forbidden under multi-user enforcement."""
        client = e2e_env["client"]
        app = e2e_env["app"]
        runner = e2e_env["runner"]

        # Enable multi_user mode on app state
        app.state.multi_user = True

        task = runner.plan_task(
            prompt="Alice private task",
            metadata={"owner_id": "user_alice"},
        )

        # Alice can access her own task
        alice_resp = client.get(f"/api/tasks/{task.task_id}", headers={"X-Mock-User": "user_alice"})
        assert alice_resp.status_code == 200

        # Bob is blocked with 403 Forbidden
        bob_resp = client.get(f"/api/tasks/{task.task_id}", headers={"X-Mock-User": "user_bob"})
        assert bob_resp.status_code == 403
        assert "Access denied" in bob_resp.json()["detail"]
