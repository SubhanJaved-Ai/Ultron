"""Comprehensive tests for Ultron's Persistent Task Runner.

Covers:
1. Task Planning and DAG Execution
2. State Persistence in SQLite
3. Restart Recovery without repeating completed steps
4. Bounded Retries for recoverable failures
5. Idempotency and Duplicate-Action Prevention
6. Pause, Resume, and Cancellation Controls
7. Step Verification and Honest Reporting
8. Safety Kernel Gating, Approval Handling, and Downstream Abort
9. Task REST API Endpoints
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from openjarvis.core.events import EventBus
from openjarvis.core.types import ToolResult
from openjarvis.security.kernel import ActionEffect, RiskLevel, SafetyKernel
from openjarvis.server.app import create_app
from openjarvis.tasks.runner import PersistentTaskRunner
from openjarvis.tasks.store import TaskStore
from openjarvis.tasks.types import StepStatus, TaskRecord, TaskStatus, TaskStep


@pytest.fixture
def tmp_store(tmp_path):
    """Temporary SQLite task store."""
    db_file = tmp_path / "test_tasks.db"
    store = TaskStore(db_file)
    yield store
    store.close()


@pytest.fixture
def test_kernel(tmp_path):
    """Isolated SafetyKernel instance with clean configuration."""
    from openjarvis.security.kernel import CustomRuleEngine, SafetyCodeManager

    code_file = tmp_path / "safety_code.json"
    rules_file = tmp_path / "custom_rules.json"
    code_mgr = SafetyCodeManager(storage_path=code_file)
    rules_engine = CustomRuleEngine(storage_path=rules_file)
    return SafetyKernel(code_manager=code_mgr, rules_engine=rules_engine)


@pytest.fixture
def runner(tmp_store, test_kernel):
    """PersistentTaskRunner configured with temporary store and kernel."""
    bus = EventBus(record_history=False)
    r = PersistentTaskRunner(store=tmp_store, bus=bus, kernel=test_kernel)
    yield r
    r.join_all(timeout=1.0)


# ===========================================================================
# 1. State Persistence in SQLite
# ===========================================================================

class TestTaskPersistence:
    def test_save_and_retrieve_task_with_steps(self, tmp_store):
        task_id = "task_test_persist_1"
        steps = [
            TaskStep(
                step_id=f"{task_id}_s1",
                task_id=task_id,
                step_index=0,
                title="First Step",
                tool_name="think",
                tool_args={"thought": "step 1"},
                dependencies=[],
                expected_output="done 1",
            ),
            TaskStep(
                step_id=f"{task_id}_s2",
                task_id=task_id,
                step_index=1,
                title="Second Step",
                tool_name="think",
                tool_args={"thought": "step 2"},
                dependencies=[f"{task_id}_s1"],
                expected_output="done 2",
            ),
        ]
        task = TaskRecord(
            task_id=task_id,
            prompt="Build a report",
            status=TaskStatus.QUEUED,
            steps=steps,
            total_steps=2,
            metadata={"priority": "high"},
        )
        tmp_store.save_task(task)

        retrieved = tmp_store.get_task(task_id)
        assert retrieved is not None
        assert retrieved.task_id == task_id
        assert retrieved.prompt == "Build a report"
        assert retrieved.status == TaskStatus.QUEUED
        assert len(retrieved.steps) == 2
        assert retrieved.steps[0].title == "First Step"
        assert retrieved.steps[1].dependencies == [f"{task_id}_s1"]
        assert retrieved.metadata["priority"] == "high"

    def test_list_and_filter_tasks(self, tmp_store):
        t1 = TaskRecord(task_id="t1", prompt="p1", status=TaskStatus.QUEUED)
        t2 = TaskRecord(task_id="t2", prompt="p2", status=TaskStatus.RUNNING)
        t3 = TaskRecord(task_id="t3", prompt="p3", status=TaskStatus.COMPLETED)
        tmp_store.save_task(t1)
        tmp_store.save_task(t2)
        tmp_store.save_task(t3)

        all_tasks = tmp_store.list_tasks()
        assert len(all_tasks) == 3

        queued = tmp_store.list_tasks(status=TaskStatus.QUEUED)
        assert len(queued) == 1
        assert queued[0].task_id == "t1"

        running = tmp_store.list_tasks(status=TaskStatus.RUNNING)
        assert len(running) == 1
        assert running[0].task_id == "t2"

    def test_update_step_state_atomically(self, tmp_store):
        task_id = "task_atomic_1"
        step = TaskStep(
            step_id=f"{task_id}_s1",
            task_id=task_id,
            step_index=0,
            title="Step",
            tool_name="think",
        )
        task = TaskRecord(task_id=task_id, prompt="prompt", steps=[step])
        tmp_store.save_task(task)

        step.status = StepStatus.RUNNING
        step.started_at = 123456.0
        tmp_store.save_step(step)

        saved = tmp_store.get_step(f"{task_id}_s1")
        assert saved is not None
        assert saved.status == StepStatus.RUNNING
        assert saved.started_at == 123456.0


# ===========================================================================
# 2. Task Planning & DAG Execution
# ===========================================================================

class TestTaskPlanningAndExecution:
    def test_plan_task_explicit_steps(self, runner):
        steps_def = [
            {"title": "Download data", "tool_name": "think", "tool_args": {"thought": "download"}},
            {"title": "Process data", "tool_name": "think", "tool_args": {"thought": "process"}, "dependencies": ["s1"]},
        ]
        task = runner.plan_task("Process sales", steps=steps_def)
        assert task.task_id.startswith("task_")
        assert len(task.steps) == 2
        assert task.steps[0].title == "Download data"
        assert task.status == TaskStatus.QUEUED
        assert task.steps[0].idempotency_key != ""

    def test_execute_multi_step_dag(self, runner):
        exec_order = []

        def tool1(**kwargs):
            exec_order.append("step1")
            return ToolResult(tool_name="t1", content="result 1", success=True)

        def tool2(**kwargs):
            exec_order.append("step2")
            return ToolResult(tool_name="t2", content="result 2", success=True)

        def tool3(**kwargs):
            exec_order.append("step3")
            return ToolResult(tool_name="t3", content="result 3", success=True)

        runner.register_custom_tool("t1", tool1)
        runner.register_custom_tool("t2", tool2)
        runner.register_custom_tool("t3", tool3)

        task_id = "dag_task_1"
        s1 = {"step_id": f"{task_id}_s1", "tool_name": "t1", "dependencies": []}
        s2 = {"step_id": f"{task_id}_s2", "tool_name": "t2", "dependencies": [f"{task_id}_s1"]}
        s3 = {"step_id": f"{task_id}_s3", "tool_name": "t3", "dependencies": [f"{task_id}_s2"]}

        task = runner.plan_task("Run 3-step DAG", steps=[s1, s2, s3], task_id=task_id)
        result = runner.run_task(task.task_id, background=False)

        assert result.status == TaskStatus.COMPLETED
        assert exec_order == ["step1", "step2", "step3"]

        # Check progress summary
        progress = result.progress_summary()
        assert progress["total_steps"] == 3
        assert progress["completed_steps"] == 3
        assert progress["percent_complete"] == 100.0
        assert progress["remaining_steps"] == 0


# ===========================================================================
# 3. Persistence & Restart Recovery
# ===========================================================================

class TestRestartRecovery:
    def test_recover_interrupted_task_without_repeating_completed_steps(self, runner, tmp_store):
        call_counts = {"s1": 0, "s2": 0, "s3": 0}

        def step1_tool(**kwargs):
            call_counts["s1"] += 1
            return ToolResult(tool_name="s1", content="done s1", success=True)

        def step2_tool(**kwargs):
            call_counts["s2"] += 1
            return ToolResult(tool_name="s2", content="done s2", success=True)

        def step3_tool(**kwargs):
            call_counts["s3"] += 1
            return ToolResult(tool_name="s3", content="done s3", success=True)

        runner.register_custom_tool("s1", step1_tool)
        runner.register_custom_tool("s2", step2_tool)
        runner.register_custom_tool("s3", step3_tool)

        task_id = "crash_recovery_task"
        s1 = {"step_id": f"{task_id}_s1", "tool_name": "s1", "dependencies": []}
        s2 = {"step_id": f"{task_id}_s2", "tool_name": "s2", "dependencies": [f"{task_id}_s1"]}
        s3 = {"step_id": f"{task_id}_s3", "tool_name": "s3", "dependencies": [f"{task_id}_s2"]}

        task = runner.plan_task("Crash recovery test", steps=[s1, s2, s3], task_id=task_id)

        # Manually complete step 1 as if it finished before a crash
        step1 = tmp_store.get_step(f"{task_id}_s1")
        step1.status = StepStatus.COMPLETED
        step1.actual_output = "Previously completed output"
        tmp_store.save_step(step1)

        # Step 2 was left RUNNING during the crash
        step2 = tmp_store.get_step(f"{task_id}_s2")
        step2.status = StepStatus.RUNNING
        tmp_store.save_step(step2)

        # Overall task was RUNNING
        tmp_store.update_task_status(task_id, TaskStatus.RUNNING)

        # Simulate app restart: initialize new runner on same store
        new_runner = PersistentTaskRunner(store=tmp_store, kernel=runner.kernel)
        new_runner.register_custom_tool("s1", step1_tool)
        new_runner.register_custom_tool("s2", step2_tool)
        new_runner.register_custom_tool("s3", step3_tool)

        recovered = new_runner.recover_interrupted_tasks()
        assert task_id in recovered

        # Wait briefly for background recovery to complete
        time.sleep(0.3)

        final_task = tmp_store.get_task(task_id)
        assert final_task.status == TaskStatus.COMPLETED

        # CRITICAL ASSERTION: Step 1 was NEVER repeated!
        assert call_counts["s1"] == 0
        # Step 2 was resumed and finished
        assert call_counts["s2"] == 1
        # Step 3 was executed
        assert call_counts["s3"] == 1


# ===========================================================================
# 4. Bounded Retries & Honest Failure Reporting
# ===========================================================================

class TestBoundedRetries:
    def test_transient_failure_retries_and_succeeds(self, runner):
        attempts = 0

        def flaky_tool(**kwargs):
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                return ToolResult(tool_name="flaky", content="Network timeout", success=False)
            return ToolResult(tool_name="flaky", content="Success on attempt 3", success=True)

        runner.register_custom_tool("flaky", flaky_tool)

        task_id = "task_flaky_retry"
        s = {"step_id": f"{task_id}_s1", "tool_name": "flaky", "max_retries": 3}
        task = runner.plan_task("Test retry", steps=[s], task_id=task_id)

        res = runner.run_task(task.task_id, background=False)
        assert res.status == TaskStatus.COMPLETED
        assert attempts == 3

        step = res.steps[0]
        assert step.status == StepStatus.COMPLETED
        assert step.retry_count == 2
        assert "Success on attempt 3" in step.actual_output

    def test_exhausted_retries_reports_honest_failure(self, runner):
        def broken_tool(**kwargs):
            return ToolResult(tool_name="broken", content="Hard database connection failure", success=False)

        runner.register_custom_tool("broken", broken_tool)

        task_id = "task_exhausted_retry"
        s1 = {"step_id": f"{task_id}_s1", "tool_name": "broken", "max_retries": 2}
        s2 = {"step_id": f"{task_id}_s2", "tool_name": "broken", "dependencies": [f"{task_id}_s1"]}
        task = runner.plan_task("Test permanent failure", steps=[s1, s2], task_id=task_id)

        res = runner.run_task(task.task_id, background=False)

        # Task and step must fail honestly; never fabricate success
        assert res.status == TaskStatus.FAILED
        step1 = res.steps[0]
        assert step1.status == StepStatus.FAILED
        assert "Hard database connection failure" in step1.error
        assert step1.retry_count > 2

        # Dependent step 2 was NEVER executed!
        step2 = res.steps[1]
        assert step2.status in (StepStatus.PENDING, StepStatus.SKIPPED)


# ===========================================================================
# 5. Idempotency & Reconciliation (Duplicate Side-Effect Prevention)
# ===========================================================================

class TestIdempotencyAndDuplicatePrevention:
    def test_filesystem_reconciliation_skips_duplicate_write(self, runner, tmp_path):
        target_file = tmp_path / "important_contract.txt"
        target_file.write_text("Unique Contract Data", encoding="utf-8")

        write_calls = 0

        def custom_file_writer(**kwargs):
            nonlocal write_calls
            write_calls += 1
            return ToolResult(tool_name="file_write", content="Wrote file", success=True)

        runner.register_custom_tool("file_write", custom_file_writer)

        task_id = "task_idempotency_fs"
        s1 = {
            "step_id": f"{task_id}_s1",
            "tool_name": "file_write",
            "tool_args": {"path": str(target_file), "content": "Unique Contract Data"},
        }
        task = runner.plan_task("Write contract", steps=[s1], task_id=task_id)

        res = runner.run_task(task.task_id, background=False)

        assert res.status == TaskStatus.COMPLETED
        # The file already had the correct content, so runner reconciled without re-writing
        assert write_calls == 0
        step = res.steps[0]
        assert step.status == StepStatus.COMPLETED
        assert "reconcil" in (step.actual_output or "").lower()

    def test_custom_reconciler_prevents_duplicate_submission(self, runner):
        submitted = True
        api_calls = 0

        def send_payment_tool(**kwargs):
            nonlocal api_calls
            api_calls += 1
            return ToolResult(tool_name="send_payment", content="Payment sent", success=True)

        def payment_reconciler(step: TaskStep) -> bool:
            # External verification: check if transaction ID was already processed
            return submitted

        runner.register_custom_tool("send_payment", send_payment_tool)
        runner.register_reconciler("send_payment", payment_reconciler)

        task_id = "task_idempotency_payment"
        s1 = {"step_id": f"{task_id}_s1", "tool_name": "send_payment", "tool_args": {"tx_id": "tx_9988"}}
        task = runner.plan_task("Submit payment", steps=[s1], task_id=task_id)

        res = runner.run_task(task.task_id, background=False)

        assert res.status == TaskStatus.COMPLETED
        assert api_calls == 0  # Duplicate prevented!


# ===========================================================================
# 6. Task Controls: Pause, Resume, Cancellation
# ===========================================================================

class TestTaskControls:
    def test_pause_and_resume_task(self, runner):
        step_log = []

        def step1_tool(**kwargs):
            step_log.append("s1")
            return ToolResult(tool_name="s1", content="done 1", success=True)

        def step2_tool(**kwargs):
            step_log.append("s2")
            return ToolResult(tool_name="s2", content="done 2", success=True)

        runner.register_custom_tool("s1", step1_tool)
        runner.register_custom_tool("s2", step2_tool)

        task_id = "task_pause_resume"
        s1 = {"step_id": f"{task_id}_s1", "tool_name": "s1"}
        s2 = {"step_id": f"{task_id}_s2", "tool_name": "s2", "dependencies": [f"{task_id}_s1"]}
        task = runner.plan_task("Pause resume test", steps=[s1, s2], task_id=task_id)

        # Pause immediately
        runner.pause_task(task_id)
        saved = runner.store.get_task(task_id)
        assert saved.status == TaskStatus.PAUSED

        # Resume execution
        resumed = runner.resume_task(task_id, background=False)
        assert resumed.status == TaskStatus.COMPLETED
        assert step_log == ["s1", "s2"]

    def test_cancel_task_halts_downstream_steps(self, runner):
        step_log = []

        def step1_tool(**kwargs):
            step_log.append("s1")
            # Cancel the task from within step 1
            runner.cancel_task(task_id)
            return ToolResult(tool_name="s1", content="done 1", success=True)

        def step2_tool(**kwargs):
            step_log.append("s2")
            return ToolResult(tool_name="s2", content="done 2", success=True)

        runner.register_custom_tool("s1", step1_tool)
        runner.register_custom_tool("s2", step2_tool)

        task_id = "task_cancel_test"
        s1 = {"step_id": f"{task_id}_s1", "tool_name": "s1"}
        s2 = {"step_id": f"{task_id}_s2", "tool_name": "s2", "dependencies": [f"{task_id}_s1"]}
        task = runner.plan_task("Cancellation test", steps=[s1, s2], task_id=task_id)

        runner.run_task(task_id, background=False)

        final_task = runner.store.get_task(task_id)
        assert final_task.status == TaskStatus.CANCELLED
        # Step 2 was NEVER executed
        assert "s2" not in step_log
        step2 = runner.store.get_step(f"{task_id}_s2")
        assert step2.status == StepStatus.CANCELLED


# ===========================================================================
# 7. Safety Kernel Integration & Approval Handling
# ===========================================================================

class TestSafetyKernelIntegration:
    def test_high_risk_step_triggers_waiting_approval(self, runner, test_kernel):
        task_id = "task_safety_ask"
        # Deleting a file is classified as HIGH risk in Ultron Safety Kernel
        s1 = {
            "step_id": f"{task_id}_s1",
            "title": "Cleanup production cache",
            "tool_name": "delete_cache",
            "tool_args": {"path": "D:/workspace/cache/temp.log"},
        }
        task = runner.plan_task("Clean cache", steps=[s1], task_id=task_id)

        runner.run_task(task_id, background=False)

        task_after = runner.store.get_task(task_id)
        assert task_after.status == TaskStatus.WAITING_APPROVAL
        step = task_after.steps[0]
        assert step.status == StepStatus.WAITING_APPROVAL
        assert step.safety_decision is not None
        assert step.safety_decision["risk_level"] == RiskLevel.HIGH.value

    def test_approve_waiting_step_with_safety_code(self, runner, test_kernel):
        test_kernel.code_mgr.set_safety_code("998877")

        executed = False

        def delete_tool(**kwargs):
            nonlocal executed
            executed = True
            return ToolResult(tool_name="delete_cache", content="Cleaned cache", success=True)

        runner.register_custom_tool("delete_cache", delete_tool)

        task_id = "task_approve_code"
        s1 = {
            "step_id": f"{task_id}_s1",
            "title": "Purge logs",
            "tool_name": "delete_cache",
            "tool_args": {"path": "D:/data/old.log"},
        }
        task = runner.plan_task("Purge logs", steps=[s1], task_id=task_id)
        runner.run_task(task_id, background=False)

        step = runner.store.get_step(f"{task_id}_s1")
        assert step.status == StepStatus.WAITING_APPROVAL
        assert step.requires_code is True

        # Incorrect safety code rejected
        with pytest.raises(ValueError, match="Invalid safety code"):
            runner.approve_step(task_id, step.step_id, safety_code="wrong_code")

        # Correct safety code approved
        approved = runner.approve_step(task_id, step.step_id, safety_code="998877")
        assert approved is True

        # Wait for background completion
        for _ in range(25):
            final_task = runner.store.get_task(task_id)
            if final_task and final_task.status == TaskStatus.COMPLETED:
                break
            time.sleep(0.1)

        final_task = runner.store.get_task(task_id)
        assert final_task.status == TaskStatus.COMPLETED
        assert executed is True

    def test_reject_step_aborts_downstream_dependencies(self, runner):
        task_id = "task_reject_step"
        s1 = {
            "step_id": f"{task_id}_s1",
            "title": "High risk action",
            "tool_name": "delete_cache",
            "tool_args": {"path": "D:/test/file.txt"},
        }
        s2 = {
            "step_id": f"{task_id}_s2",
            "title": "Subsequent dependent action",
            "tool_name": "think",
            "dependencies": [f"{task_id}_s1"],
        }
        task = runner.plan_task("Test rejection", steps=[s1, s2], task_id=task_id)
        runner.run_task(task_id, background=False)

        # Reject authorization
        runner.reject_step(task_id, f"{task_id}_s1", reason="Denied by test administrator")

        final_task = runner.store.get_task(task_id)
        assert final_task.status == TaskStatus.FAILED
        step1 = runner.store.get_step(f"{task_id}_s1")
        assert step1.status == StepStatus.FAILED
        assert "Denied by test administrator" in step1.error

        # Step 2 was never executed
        step2 = runner.store.get_step(f"{task_id}_s2")
        assert step2.status in (StepStatus.PENDING, StepStatus.SKIPPED)


# ===========================================================================
# 8. REST API Endpoints
# ===========================================================================

class TestTaskRoutesApi:
    @pytest.fixture
    def client(self, runner):
        app = create_app()
        app.state.task_runner = runner
        return TestClient(app)

    def test_create_and_get_task_api(self, client):
        resp = client.post(
            "/api/tasks",
            json={
                "prompt": "API test plan",
                "steps": [
                    {"title": "Step 1", "tool_name": "think", "tool_args": {"thought": "api"}}
                ],
                "auto_run": False,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        task_id = data["task"]["task_id"]

        # Detail endpoint
        get_resp = client.get(f"/api/tasks/{task_id}")
        assert get_resp.status_code == 200
        detail = get_resp.json()
        assert detail["task"]["task_id"] == task_id
        assert len(detail["task"]["steps"]) == 1

    def test_list_tasks_api(self, client):
        resp = client.get("/api/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert isinstance(data["tasks"], list)

    def test_pause_and_cancel_api(self, client, runner):
        task = runner.plan_task("Control via API", steps=[{"tool_name": "think"}])
        runner.run_task(task.task_id, background=True)

        pause_resp = client.post(f"/api/tasks/{task.task_id}/pause")
        assert pause_resp.status_code in (200, 400)

        cancel_resp = client.post(f"/api/tasks/{task.task_id}/cancel")
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["status"] == "cancelled"


# ===========================================================================
# 9. Hardening Pass Verification
# ===========================================================================

class TestHardeningPass:
    def test_natural_language_planning_with_agent(self, tmp_store):
        """Verify user prompts convert into ordered executable task steps via agent."""
        mock_agent = MagicMock()
        mock_agent.run.return_value = """
        [
            {
                "title": "Analyze code structure",
                "tool_name": "think",
                "tool_args": {"thought": "Scanning architecture"},
                "dependencies": [],
                "expected_output": "Analysis complete"
            },
            {
                "title": "Write generated report",
                "tool_name": "file_write",
                "tool_args": {"path": "output_report.md", "content": "# Architecture Summary"},
                "dependencies": [1],
                "expected_output": "Report written"
            }
        ]
        """
        runner = PersistentTaskRunner(store=tmp_store, agent=mock_agent)
        task = runner.plan_task("Analyze code and write report")

        assert len(task.steps) == 2
        assert task.steps[0].tool_name == "think"
        assert task.steps[1].tool_name == "file_write"
        assert task.steps[1].dependencies == [task.steps[0].step_id]
        assert task.steps[0].idempotency_key is not None
        assert task.steps[1].idempotency_key is not None
        mock_agent.run.assert_called_once()

    def test_rbac_capability_policy_denial(self, tmp_store):
        """Verify that capability policy denials halt execution with honest failure."""
        from openjarvis.security.capabilities import Capability, CapabilityPolicy

        policy = CapabilityPolicy(default_deny=False)
        policy.deny("restricted_agent", Capability.FILE_WRITE.value)

        runner = PersistentTaskRunner(store=tmp_store, capability_policy=policy)
        task_id = "task_rbac_denial"
        s1 = {
            "step_id": f"{task_id}_s1",
            "tool_name": "file_write",
            "tool_args": {"path": "blocked.txt", "content": "forbidden"},
        }
        # Upfront plan validation rejects unauthorized tools
        with pytest.raises(ValueError, match="Unauthorized tool"):
            runner.plan_task(
                "Write unauthorized file",
                steps=[s1],
                metadata={"owner_id": "restricted_agent"},
                task_id=task_id,
            )

        # If a task bypasses plan_task and is inserted directly into store, run_task rejects it
        record = TaskRecord(
            task_id=task_id,
            prompt="Write unauthorized file",
            status=TaskStatus.QUEUED,
            steps=[
                TaskStep(
                    step_id=f"{task_id}_s1",
                    task_id=task_id,
                    step_index=0,
                    title="Unauthorized write",
                    tool_name="file_write",
                    tool_args={"path": "blocked.txt", "content": "forbidden"},
                )
            ],
            metadata={"owner_id": "restricted_agent"},
        )
        tmp_store.save_task(record)

        res = runner.run_task(task_id, background=False)
        assert res.status == TaskStatus.FAILED

        step = runner.store.get_step(f"{task_id}_s1")
        assert step.status == StepStatus.FAILED
        assert "Capability denied by policy" in step.error or "Unauthorized tool" in (res.error or "")
        assert "restricted_agent" in (step.error or "") or "restricted_agent" in (res.error or "")

    def test_approval_fingerprint_tamper_rejection(self, tmp_store, test_kernel):
        """Verify that modifying action arguments after approval invalidates token."""
        from openjarvis.security.kernel import CustomRule

        test_kernel.rules_engine.add_rule(
            CustomRule(
                id="ask_delete",
                raw_text="Confirm delete operations",
                effect="ASK",
                action_types=["delete"],
                path_pattern="*",
                risk_level="high",
            )
        )

        runner = PersistentTaskRunner(store=tmp_store, kernel=test_kernel)
        task_id = "task_tamper_defense"
        s1 = {
            "step_id": f"{task_id}_s1",
            "tool_name": "delete_file",
            "tool_args": {"path": "harmless_scratch.txt"},
        }
        task = runner.plan_task("Delete file", steps=[s1], task_id=task_id)

        # 1. First run halts at WAITING_APPROVAL
        res = runner.run_task(task_id, background=False)
        assert res.status == TaskStatus.WAITING_APPROVAL
        step = runner.store.get_step(f"{task_id}_s1")
        assert step.status == StepStatus.WAITING_APPROVAL

        # 2. Approve for harmless path without background execution
        ok = runner.approve_step(task_id, step.step_id, auto_run=False)
        assert ok is True
        token = runner.store.get_step(step.step_id).approval_token
        assert token is not None

        # 3. Simulate tamper: modify arguments to a different unauthorized file
        tampered_step = runner.store.get_step(step.step_id)
        tampered_step.tool_args = {"path": "other_unauthorized_folder/private.log"}
        runner.store.save_step(tampered_step)

        # 4. Attempt execution with the old token against tampered arguments
        res_tampered = runner.run_task(task_id, background=False)
        # Token must be rejected because fingerprint does not match new arguments!
        step_after = runner.store.get_step(step.step_id)
        assert step_after.status == StepStatus.WAITING_APPROVAL
        assert res_tampered.status == TaskStatus.WAITING_APPROVAL

        # 5. Verify that passing an invalid/mismatched token to approve_step is rejected
        with pytest.raises(ValueError) as exc_info:
            runner.approve_step(task_id, step.step_id, token="stolen_or_mismatched_token", auto_run=False)
        assert "invalid or does not match" in str(exc_info.value)

    def test_atomic_task_claim_prevents_concurrent_execution(self, tmp_store):
        """Verify that atomic claiming prevents two workers from claiming the same task."""
        record = TaskRecord(
            task_id="task_atomic_claim",
            prompt="Atomic claim test",
            status=TaskStatus.QUEUED,
            steps=[],
            created_at=time.time(),
            updated_at=time.time(),
            current_step_index=0,
            total_steps=0,
        )
        tmp_store.save_task(record)

        # Worker 1 claims
        c1 = tmp_store.claim_task("task_atomic_claim")
        assert c1 is True

        # Worker 2 attempts to claim while already running
        c2 = tmp_store.claim_task("task_atomic_claim")
        assert c2 is False

        # In-memory thread guard on runner
        runner = PersistentTaskRunner(store=tmp_store)
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True
        runner._active_threads["task_atomic_claim"] = mock_thread

        res = runner.run_task("task_atomic_claim", background=False)
        # Does not launch second execution loop
        assert res.task_id == "task_atomic_claim"

    def test_uncertain_external_action_halts_blind_retry(self, tmp_store):
        """Verify that timeout on external actions does not blindly retry without reconciliation."""
        api_call_count = 0

        def failing_channel_tool(**kwargs):
            nonlocal api_call_count
            api_call_count += 1
            raise TimeoutError("504 Gateway Timeout: connection dropped")

        runner = PersistentTaskRunner(store=tmp_store)
        runner.register_custom_tool("channel_send", failing_channel_tool)

        task_id = "task_uncertain_ext"
        s1 = {
            "step_id": f"{task_id}_s1",
            "tool_name": "channel_send",
            "tool_args": {"recipient": "@vip_user", "message": "Execute transfer"},
            "max_retries": 3,
        }
        task = runner.plan_task("Send VIP alert", steps=[s1], task_id=task_id)

        res = runner.run_task(task_id, background=False)

        # Must halt in WAITING_APPROVAL instead of looping 3 retries blindly!
        assert res.status == TaskStatus.WAITING_APPROVAL
        step = runner.store.get_step(f"{task_id}_s1")
        assert step.status == StepStatus.WAITING_APPROVAL
        assert "Uncertain external action outcome" in step.error
        assert api_call_count == 1  # Exactly 1 call, NO blind retries!

    def test_multi_user_tenant_isolation(self, tmp_store):
        """Verify tenant isolation and multi-user authorization on task endpoints."""
        from unittest.mock import MagicMock
        from fastapi import Request
        from starlette.datastructures import State
        from openjarvis.server.task_routes import (
            _check_task_access,
            create_task,
            get_task,
            pause_task,
            cancel_task,
            CreateTaskRequest,
        )

        runner = PersistentTaskRunner(store=tmp_store)
        task = runner.plan_task("Alice private task", metadata={"owner_id": "alice"})

        # Mock Bob's request
        bob_req = MagicMock(spec=Request)
        bob_state = State()
        bob_state.multi_user = True
        bob_req.app = MagicMock()
        bob_req.app.state = bob_state
        bob_req.state = State()
        bob_user = MagicMock()
        bob_user.id = "bob"
        bob_user.username = "bob"
        bob_user.role = "user"
        bob_req.state.user = bob_user

        # Bob accessing Alice's task raises 403 Forbidden
        with pytest.raises(Exception) as exc_info:
            _check_task_access(task, bob_req)
        assert "403" in str(exc_info.value) or exc_info.value.status_code == 403

        # Admin user accessing Alice's task succeeds
        admin_req = MagicMock(spec=Request)
        admin_req.app = MagicMock()
        admin_req.app.state = bob_state
        admin_req.state = State()
        admin_user = MagicMock()
        admin_user.id = "admin_user"
        admin_user.role = "admin"
        admin_req.state.user = admin_user

        # Should not raise
        _check_task_access(task, admin_req)


# ===========================================================================
# 10. Final Hardening: Plan Validation & Safe Uncertain Action Handling
# ===========================================================================

class TestPlanValidationAndUncertainActionsHardening:
    """Rigorous focused tests validating AI-generated plans and safe uncertain action handling."""

    # --- 1. Plan Validation Tests ---

    def test_plan_validation_rejects_unknown_tool(self, runner):
        """AI plans proposing unknown or hallucinated tools must be rejected upfront."""
        s1 = {
            "step_id": "step_unknown",
            "tool_name": "arbitrary_hallucinated_tool_xyz",
            "tool_args": {"arg": "val"},
        }
        with pytest.raises(ValueError, match="Unknown or unrecognized tool"):
            runner.plan_task("Test unknown tool", steps=[s1])

    def test_plan_validation_rejects_malformed_arguments_schema(self, runner):
        """Steps with non-dict or malformed argument schemas must be rejected."""
        s1 = {
            "step_id": "step_bad_args",
            "tool_name": "think",
            "tool_args": ["not", "a", "dict"],
        }
        with pytest.raises(ValueError, match="Invalid argument schema"):
            runner.plan_task("Test bad schema", steps=[s1])

    def test_plan_validation_rejects_missing_required_tool_args(self, runner):
        """Known tools missing required schema fields must be rejected."""
        # file_write missing 'path'
        s_write = {
            "step_id": "step_write",
            "tool_name": "file_write",
            "tool_args": {"content": "data without path"},
        }
        with pytest.raises(ValueError, match="requires non-empty string argument 'path'"):
            runner.plan_task("Test missing path", steps=[s_write])

        # shell_exec missing 'command'
        s_shell = {
            "step_id": "step_shell",
            "tool_name": "shell_exec",
            "tool_args": {"flags": "-v"},
        }
        with pytest.raises(ValueError, match="requires non-empty string argument 'command'"):
            runner.plan_task("Test missing command", steps=[s_shell])

        # http_request missing 'url'
        s_http = {
            "step_id": "step_http",
            "tool_name": "http_request",
            "tool_args": {"method": "GET"},
        }
        with pytest.raises(ValueError, match="requires non-empty string argument 'url'"):
            runner.plan_task("Test missing url", steps=[s_http])

    def test_plan_validation_rejects_unsupported_generic_verbs_and_unknown_handlers(self, runner):
        """Unsupported generic verbs or tools lacking registered handlers must be rejected before execution."""
        unsupported_verbs = [
            "file_flim_flam",
            "exec_warp_core",
            "send_carrier_pigeon",
            "database_quantum_magic",
            "random_hallucinated_handler",
        ]
        for verb in unsupported_verbs:
            step = {
                "step_id": f"step_{verb}",
                "tool_name": verb,
                "tool_args": {"target": "something"},
            }
            with pytest.raises(ValueError, match="Unknown or unrecognized tool"):
                runner.plan_task(f"Test unsupported {verb}", steps=[step])

    def test_plan_validation_validates_argument_types_against_tool_spec(self, runner):
        """Arguments with invalid types according to the registered tool's schema must be rejected."""
        # 1. file_write path must be string, not int
        s1 = {
            "step_id": "s1",
            "tool_name": "file_write",
            "tool_args": {"path": 12345, "content": "hello"},
        }
        with pytest.raises(ValueError, match="argument 'path' must be a string"):
            runner.plan_task("Invalid path type", steps=[s1])

        # 2. shell_exec timeout must be integer, not string
        s2 = {
            "step_id": "s2",
            "tool_name": "shell_exec",
            "tool_args": {"command": "echo 1", "timeout": "not_an_int"},
        }
        with pytest.raises(ValueError, match="argument 'timeout' must be an integer"):
            runner.plan_task("Invalid timeout type", steps=[s2])

        # 3. http_request headers must be dict (object), not list
        s3 = {
            "step_id": "s3",
            "tool_name": "http_request",
            "tool_args": {"url": "https://api.example.com", "headers": ["Authorization", "Bearer xyz"]},
        }
        with pytest.raises(ValueError, match="argument 'headers' must be an object"):
            runner.plan_task("Invalid headers type", steps=[s3])

    def test_generic_verb_mapping_resolution_and_dispatch(self, runner, tmp_path):
        """Generic task verbs (create_file, cmd_exec) map to real handlers and execute cleanly."""
        target_file = tmp_path / "generic_verb_test.txt"
        s_create = {
            "step_id": "s_create",
            "tool_name": "create_file",
            "tool_args": {"path": str(target_file), "content": "Written via create_file generic verb"},
        }
        task = runner.plan_task("Create file with generic verb", steps=[s_create], task_id="task_generic_verb")
        assert len(task.steps) == 1
        res = runner.run_task("task_generic_verb", background=False)
        assert res.status == TaskStatus.COMPLETED
        assert target_file.exists()
        assert target_file.read_text(encoding="utf-8") == "Written via create_file generic verb"

    def test_plan_validation_rejects_self_referencing_dependency(self, runner):
        """A step depending on itself must be rejected immediately as circular."""
        s1 = {
            "step_id": "step_self",
            "tool_name": "think",
            "tool_args": {"thought": "thinking"},
            "dependencies": ["step_self"],
        }
        with pytest.raises(ValueError, match="Self-referencing dependency"):
            runner.plan_task("Test self-dep", steps=[s1])

    def test_plan_validation_rejects_missing_dependency_id(self, runner):
        """A step referencing a non-existent step ID must be rejected."""
        s1 = {
            "step_id": "step_1",
            "tool_name": "think",
            "tool_args": {"thought": "step 1"},
            "dependencies": ["step_99_does_not_exist"],
        }
        with pytest.raises(ValueError, match="depends on non-existent step"):
            runner.plan_task("Test missing dep", steps=[s1])

    def test_plan_validation_rejects_circular_dag_dependencies(self, runner):
        """Multi-step cycles in the DAG must be detected and rejected."""
        # 2-step cycle: s1 -> s2 and s2 -> s1
        s1 = {"step_id": "s1", "tool_name": "think", "dependencies": ["s2"]}
        s2 = {"step_id": "s2", "tool_name": "think", "dependencies": ["s1"]}
        with pytest.raises(ValueError, match="Circular dependency detected in DAG"):
            runner.plan_task("Test 2-step cycle", steps=[s1, s2])

        # 3-step cycle: a -> b -> c -> a
        sa = {"step_id": "sa", "tool_name": "think", "dependencies": ["sc"]}
        sb = {"step_id": "sb", "tool_name": "think", "dependencies": ["sa"]}
        sc = {"step_id": "sc", "tool_name": "think", "dependencies": ["sb"]}
        with pytest.raises(ValueError, match="Circular dependency detected in DAG"):
            runner.plan_task("Test 3-step cycle", steps=[sa, sb, sc])

    def test_plan_validation_rejects_duplicate_step_ids(self, runner):
        """Duplicate step IDs within the same plan must be rejected."""
        s1 = {"step_id": "dup_id", "tool_name": "think"}
        s2 = {"step_id": "dup_id", "tool_name": "think"}
        with pytest.raises(ValueError, match="Duplicate step_id"):
            runner.plan_task("Test duplicate IDs", steps=[s1, s2])

    def test_plan_validation_rejects_safety_kernel_blocked_step(self, runner, test_kernel):
        """Plans containing destructive actions blocked by Safety Kernel must fail validation upfront."""
        # Deleting critical system directory is strictly BLOCK effect by default in Safety Kernel
        s1 = {
            "step_id": "step_danger",
            "tool_name": "delete_file",
            "tool_args": {"path": "C:\\Windows\\System32\\critical_driver.dll"},
        }
        with pytest.raises(ValueError, match="blocked by Safety Kernel"):
            runner.plan_task("Delete critical windows driver", steps=[s1])

    # --- 2. Uncertain External Actions Tests ---

    def test_uncertain_action_provides_clear_duplicate_risk_explanation(self, runner):
        """When an external action times out, the runner halts and provides a clear duplicate-action risk explanation."""
        call_count = 0

        def timeout_webhook(**kwargs):
            nonlocal call_count
            call_count += 1
            raise TimeoutError("504 Gateway Timeout: remote server did not respond in time")

        runner.register_custom_tool("webhook_post", timeout_webhook)
        task_id = "task_uncertain_risk_exp"
        s1 = {
            "step_id": f"{task_id}_s1",
            "tool_name": "webhook_post",
            "tool_args": {"url": "https://api.partner.com/dispatch", "payload": {"charge": 100}},
            "max_retries": 3,
        }
        task = runner.plan_task("Dispatch payment webhook", steps=[s1], task_id=task_id)
        res = runner.run_task(task_id, background=False)

        assert res.status == TaskStatus.WAITING_APPROVAL
        step = runner.store.get_step(f"{task_id}_s1")
        assert step.status == StepStatus.WAITING_APPROVAL
        assert step.safety_decision is not None
        assert step.safety_decision.get("uncertain_external_action") is True
        assert "Duplicate-Action Risk" in step.safety_decision.get("duplicate_action_risk", "")
        assert "duplicate message sends, multiple financial charges, or double webhooks" in step.safety_decision.get("duplicate_action_risk", "")
        assert call_count == 1  # No blind retry

    def test_uncertain_action_blind_approval_prohibited(self, runner):
        """Approving an uncertain external action without resolution must be strictly rejected."""
        def timeout_api(**kwargs):
            raise TimeoutError("Connection reset by peer during webhook dispatch")

        runner.register_custom_tool("channel_send", timeout_api)
        task_id = "task_uncertain_no_blind"
        s1 = {
            "step_id": f"{task_id}_s1",
            "tool_name": "channel_send",
            "tool_args": {"channel": "ops-alerts", "message": "Deploying v2"},
            "max_retries": 3,
        }
        task = runner.plan_task("Send alert", steps=[s1], task_id=task_id)
        runner.run_task(task_id, background=False)

        # Attempt blind approval without resolution
        with pytest.raises(ValueError, match="Blind approval is prohibited"):
            runner.approve_step(task_id, f"{task_id}_s1")

        # Invalid resolution string is also rejected
        with pytest.raises(ValueError, match="Must be 'mark_completed' or 'force_retry'"):
            runner.approve_step(task_id, f"{task_id}_s1", resolution="random_invalid_string")

    def test_uncertain_action_approval_mark_completed_never_repeats_side_effect(self, runner):
        """Approving with resolution='mark_completed' marks step completed without executing tool again."""
        call_count = 0

        def timeout_msg(**kwargs):
            nonlocal call_count
            call_count += 1
            raise TimeoutError("Socket timeout")

        runner.register_custom_tool("send_message", timeout_msg)
        task_id = "task_uncertain_mark_done"
        s1 = {
            "step_id": f"{task_id}_s1",
            "tool_name": "send_message",
            "tool_args": {"user": "alice", "text": "Invoice #101"},
            "max_retries": 3,
        }
        runner.plan_task("Send invoice", steps=[s1], task_id=task_id)
        runner.run_task(task_id, background=False)
        assert call_count == 1

        # User verifies externally that message was delivered, resolves with mark_completed
        ok = runner.approve_step(task_id, f"{task_id}_s1", resolution="mark_completed", auto_run=False)
        assert ok is True

        step = runner.store.get_step(f"{task_id}_s1")
        assert step.status == StepStatus.COMPLETED
        assert step.safety_decision.get("uncertain_resolved") == "mark_completed"
        # Tool was NOT called a second time
        assert call_count == 1

    def test_uncertain_action_approval_force_retry_authorizes_reexecution(self, runner):
        """Approving with resolution='force_retry' requires explicit operator confirmation and safely permits re-executing."""
        call_count = 0

        def flappy_api(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TimeoutError("504 Gateway Timeout")
            return ToolResult(tool_name="http_request", content="HTTP 200 OK: Processed", success=True)

        runner.register_custom_tool("http_request", flappy_api)
        task_id = "task_uncertain_force_retry"
        s1 = {
            "step_id": f"{task_id}_s1",
            "tool_name": "http_request",
            "tool_args": {"url": "https://api.example.com/sync"},
            "max_retries": 3,
        }
        runner.plan_task("Sync data", steps=[s1], task_id=task_id)
        runner.run_task(task_id, background=False)
        assert call_count == 1

        step_waiting = runner.store.get_step(f"{task_id}_s1")
        assert step_waiting.status == StepStatus.WAITING_APPROVAL
        assert step_waiting.safety_decision.get("uncertain_external_action") is True
        assert "duplicate_action_risk" in step_waiting.safety_decision
        assert "force_retry_warning" in step_waiting.safety_decision

        # 1. Calling force_retry without explicit operator confirmation raises ValueError with duplicate risk warning
        with pytest.raises(ValueError, match="confirm_duplicate_risk=True"):
            runner.approve_step(task_id, f"{task_id}_s1", resolution="force_retry", auto_run=False)

        # 2. Operator confirms duplicate risk and resolves with force_retry
        ok = runner.approve_step(
            task_id,
            f"{task_id}_s1",
            resolution="force_retry",
            confirm_duplicate_risk=True,
            auto_run=False,
        )
        assert ok is True

        step_after = runner.store.get_step(f"{task_id}_s1")
        assert step_after.status == StepStatus.PENDING
        assert step_after.safety_decision.get("force_retry_authorized") is True
        assert step_after.safety_decision.get("operator_confirmed_duplicate_risk") is True

        # Now running the task executes the tool safely
        res = runner.run_task(task_id, background=False)
        assert res.status == TaskStatus.COMPLETED
        assert call_count == 2
        final_step = runner.store.get_step(f"{task_id}_s1")
        assert final_step.status == StepStatus.COMPLETED

    def test_force_retry_warning_preserves_safety_authorization(self, runner, test_kernel):
        """Force-retry requires operator confirmation and preserves existing Safety Kernel / code authorization."""
        from openjarvis.security.kernel import CustomRule

        test_kernel.code_mgr.set_safety_code("998877")
        test_kernel.rules_engine.add_rule(
            CustomRule(
                id="ask_external_sync",
                raw_text="High risk sync requires code",
                effect="ASK",
                action_types=["network"],
                path_pattern="*",
                risk_level="high",
            )
        )

        call_count = 0

        def flappy_external(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TimeoutError("504 Gateway Timeout")
            return ToolResult(tool_name="http_request", content="Success", success=True)

        runner.register_custom_tool("http_request", flappy_external)
        task_id = "task_force_retry_auth"
        s1 = {
            "step_id": f"{task_id}_s1",
            "tool_name": "http_request",
            "tool_args": {"url": "https://bank.example.com/transfer"},
            "max_retries": 1,
        }
        runner.plan_task("Transfer", steps=[s1], task_id=task_id)

        # First approval requires code
        with pytest.raises(ValueError, match="Safety code is required"):
            runner.approve_step(task_id, f"{task_id}_s1")

        # Authorize with valid code
        ok = runner.approve_step(task_id, f"{task_id}_s1", safety_code="998877", auto_run=False)
        assert ok is True

        # Run step -> fails with timeout -> transitions to WAITING_APPROVAL
        res = runner.run_task(task_id, background=False)
        assert res.status == TaskStatus.WAITING_APPROVAL

        # 1. Force retry without confirm_duplicate_risk raises ValueError with warning
        with pytest.raises(ValueError, match="confirm_duplicate_risk=True"):
            runner.approve_step(task_id, f"{task_id}_s1", resolution="force_retry", safety_code="998877")

        # 2. Force retry with confirm_duplicate_risk=True but missing safety code raises ValueError (safety preserved!)
        with pytest.raises(ValueError, match="Safety code is required"):
            runner.approve_step(task_id, f"{task_id}_s1", resolution="force_retry", confirm_duplicate_risk=True)

        # 3. Force retry with both confirm_duplicate_risk=True and valid safety code succeeds
        ok = runner.approve_step(
            task_id,
            f"{task_id}_s1",
            resolution="force_retry",
            confirm_duplicate_risk=True,
            safety_code="998877",
            auto_run=False,
        )
        assert ok is True

        res_after = runner.run_task(task_id, background=False)
        assert res_after.status == TaskStatus.COMPLETED

    def test_uncertain_action_refuses_blind_resumption(self, runner):
        """Calling resume_task on a task with unresolved uncertain external action must be refused."""
        def timeout_webhook(**kwargs):
            raise TimeoutError("Connection reset")

        runner.register_custom_tool("webhook", timeout_webhook)
        task_id = "task_uncertain_no_resume"
        s1 = {
            "step_id": f"{task_id}_s1",
            "tool_name": "webhook",
            "tool_args": {"url": "https://hooks.slack.com/services/xxx"},
            "max_retries": 3,
        }
        runner.plan_task("Post webhook", steps=[s1], task_id=task_id)
        runner.run_task(task_id, background=False)

        # Calling resume_task refuses to blindly resume
        with pytest.raises(ValueError, match="Cannot blindly resume task"):
            runner.resume_task(task_id, background=False)

    def test_routes_api_enforces_uncertain_action_resolution(self, runner):
        """FastAPI endpoints reject blind approval of uncertain actions, require force-retry confirmation, and accept resolution."""
        from fastapi.testclient import TestClient
        from openjarvis.server.app import create_app

        def timeout_call(**kwargs):
            raise TimeoutError("504 Gateway Timeout")

        runner.register_custom_tool("http_request", timeout_call)
        task_id = "task_api_uncertain"
        s1 = {
            "step_id": f"{task_id}_s1",
            "tool_name": "http_request",
            "tool_args": {"url": "https://service.local/api"},
            "max_retries": 2,
        }
        runner.plan_task("API Call", steps=[s1], task_id=task_id)
        runner.run_task(task_id, background=False)

        app = create_app()
        app.state.task_runner = runner
        client = TestClient(app)

        # 1. Blind approval without resolution returns 403 Forbidden
        resp1 = client.post(f"/api/tasks/{task_id}/approve", json={"step_id": f"{task_id}_s1"})
        assert resp1.status_code == 403
        assert "Blind approval is prohibited" in resp1.json()["detail"]

        # 2. Resuming without resolution returns 400 Bad Request
        resp2 = client.post(f"/api/tasks/{task_id}/resume")
        assert resp2.status_code == 400
        assert "Cannot blindly resume task" in resp2.json()["detail"]

        # 3. Force-retry without confirm_duplicate_risk returns 403 Forbidden with warning
        resp_retry_unconfirmed = client.post(
            f"/api/tasks/{task_id}/approve",
            json={"step_id": f"{task_id}_s1", "resolution": "force_retry", "confirm_duplicate_risk": False},
        )
        assert resp_retry_unconfirmed.status_code == 403
        assert "confirm_duplicate_risk=True" in resp_retry_unconfirmed.json()["detail"]

        # 4. Approval with resolution='mark_completed' succeeds
        resp3 = client.post(
            f"/api/tasks/{task_id}/approve",
            json={"step_id": f"{task_id}_s1", "resolution": "mark_completed"},
        )
        assert resp3.status_code == 200
        assert resp3.json()["status"] == "approved"

        final_step = runner.store.get_step(f"{task_id}_s1")
        assert final_step.status == StepStatus.COMPLETED

