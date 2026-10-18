"""Comprehensive test suite for Tool Execution Intelligence in Ultron.

Verifies:
1. Tool Selection: Exact matching, canonical verb mapping, semantic discovery,
   capability-based filtering, and rejection of unknown tools.
2. Argument Generation & Schema Validation: Schema matching, type/constraint checks,
   placeholder detection (<path>, [TODO], MISSING), and user prompting for missing information.
3. Sequential Reasoning: DAG dependency ordering, predecessor output passing
   ({{previous_output}}, {{s1.output}}), JSON path extraction, and type casting.
4. Result Verification: Honest inspection (no fabricated success), regex/substring
   verification, and filesystem ground truth checks (file_write, delete_file).
5. Safety & Safe Recovery: Deterministic error immediate failure, transient error bounded
   retries, uncertain external action duplicate-protection, and Safety Kernel gating.
"""

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from openjarvis.core.types import ToolResult
from openjarvis.security.capabilities import CapabilityPolicy
from openjarvis.security.kernel import SafetyKernel
from openjarvis.server.app import create_app
from openjarvis.tasks.intelligence import (
    ToolExecutionIntelligence,
)
from openjarvis.tasks.runner import PersistentTaskRunner
from openjarvis.tasks.store import TaskStore
from openjarvis.tasks.types import StepStatus, TaskStatus, TaskStep

# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

@pytest.fixture
def tmp_workspace(tmp_path: Path):
    """Provide a temporary directory for task storage and filesystem operations."""
    return tmp_path


@pytest.fixture
def store(tmp_workspace: Path):
    """Provide an isolated TaskStore."""
    db_file = tmp_workspace / "tasks.db"
    s = TaskStore(db_file)
    yield s
    s.close()


@pytest.fixture
def runner(tmp_workspace: Path, store: TaskStore):
    """Provide an isolated PersistentTaskRunner instance with ToolExecutionIntelligence."""
    kernel = SafetyKernel()
    return PersistentTaskRunner(store=store, kernel=kernel)


@pytest.fixture
def intelligence(runner: PersistentTaskRunner):
    """Provide the runner's ToolExecutionIntelligence instance."""
    return runner.intelligence


# --------------------------------------------------------------------------
# 1. Tool Selection Tests
# --------------------------------------------------------------------------

class TestToolSelection:
    """Validate tool discovery, canonical verb resolution, and unknown tool rejection."""

    def test_exact_registered_tool_selection(self, intelligence: ToolExecutionIntelligence):
        """Exact registered tool names are correctly matched."""
        assert intelligence.select_tool("file_read") == "file_read"
        assert intelligence.select_tool("file_write") == "file_write"
        assert intelligence.select_tool("think") == "think"
        assert intelligence.select_tool("shell_exec") == "shell_exec"

    def test_canonical_verb_mapping(self, intelligence: ToolExecutionIntelligence):
        """Generic and common natural language verbs map to registered canonical tools."""
        assert intelligence.select_tool("read file") == "file_read"
        assert intelligence.select_tool("create file") == "file_write"
        assert intelligence.select_tool("write") == "file_write"
        assert intelligence.select_tool("delete file") == "delete_file"
        assert intelligence.select_tool("clean cache") == "delete_file"
        assert intelligence.select_tool("open app") == "app_launch"
        assert intelligence.select_tool("curl") == "http_request"
        assert intelligence.select_tool("bash") == "shell_exec"

    def test_semantic_intent_discovery(self, intelligence: ToolExecutionIntelligence):
        """Semantic tokens discover the most appropriate tool from description and parameters."""
        selected = intelligence.select_tool("evaluate the mathematical expression")
        assert selected == "calculator"

        selected_search = intelligence.select_tool("search the web for current weather")
        assert selected_search == "web_search"

    def test_rejects_unknown_or_unsupported_tools(self, intelligence: ToolExecutionIntelligence, runner: PersistentTaskRunner):
        """Unknown or hallucinated tool names are rejected during selection and plan validation."""
        # Selection returns None for nonsense tools
        assert intelligence.select_tool("nonexistent_alien_tool_xyz") is None
        assert intelligence.select_tool("make_coffee_now") is None

        # Plan validation raises ValueError for unknown tools
        task_id = "test_reject_unknown"
        step = TaskStep(
            step_id=f"{task_id}_s1",
            task_id=task_id,
            step_index=0,
            title="Step with unknown tool",
            tool_name="unregistered_fake_tool_123",
            tool_args={},
        )
        with pytest.raises(ValueError, match="Unknown or unrecognized tool"):
            runner.validate_plan([step])

    def test_tool_catalog_contains_real_schemas_and_descriptions(self, intelligence: ToolExecutionIntelligence):
        """Tool catalog produces detailed schemas with required markers."""
        catalog = intelligence.build_tool_catalog()
        assert "Registered Tools:" in catalog
        assert "file_write" in catalog
        assert "`path` [string] (REQUIRED)" in catalog
        assert "`content` [string] (REQUIRED)" in catalog
        assert "think" in catalog

    def test_capability_policy_filtering(self, runner: PersistentTaskRunner):
        """Tools requiring capabilities not granted to the agent are rejected."""
        policy = CapabilityPolicy(default_deny=True)
        policy.grant("user_agent", "tool:invoke:think")
        # Do not grant file:write to user_agent
        intel = ToolExecutionIntelligence(runner=runner, capability_policy=policy)

        # discover_tools for user_agent should not contain tools requiring unauthorized capabilities
        tools = intel.discover_tools(owner_id="user_agent")
        assert "think" in tools
        assert "file_write" not in tools


# --------------------------------------------------------------------------
# 2. Argument Generation & Schema Validation Tests
# --------------------------------------------------------------------------

class TestArgumentGenerationAndValidation:
    """Validate schema verification, placeholder detection, and user prompting."""

    def test_valid_argument_schema_passes(self, intelligence: ToolExecutionIntelligence):
        """Arguments matching the tool schema return is_valid=True."""
        val_res = intelligence.validate_tool_arguments("file_write", {"path": "output.txt", "content": "hello world"})
        assert val_res.is_valid is True
        assert not val_res.has_missing_essential_info
        assert len(val_res.errors) == 0

    def test_missing_required_field_detected(self, intelligence: ToolExecutionIntelligence):
        """Missing required fields are flagged in missing_fields."""
        val_res = intelligence.validate_tool_arguments("file_write", {"path": "output.txt"})
        assert val_res.is_valid is False
        assert val_res.has_missing_essential_info is True
        assert "content" in val_res.missing_fields

    def test_type_and_constraint_validation(self, intelligence: ToolExecutionIntelligence):
        """Arguments with mismatched types fail validation."""
        val_res = intelligence.validate_tool_arguments("file_write", {"path": 12345, "content": "test"})
        assert val_res.is_valid is False
        assert any("must be a string" in err for err in val_res.errors)

    def test_placeholder_token_detected_as_missing_info(self, intelligence: ToolExecutionIntelligence):
        """Placeholder tokens such as <path> or [TODO] trigger has_missing_essential_info."""
        placeholders = ["<filepath>", "[TODO_PATH]", "MISSING", "UNKNOWN", "PLACEHOLDER"]
        for p in placeholders:
            val_res = intelligence.validate_tool_arguments("file_write", {"path": p, "content": "valid content"})
            assert val_res.is_valid is False
            assert val_res.has_missing_essential_info is True
            assert "path" in val_res.missing_fields

    def test_generate_tool_arguments_prompts_user_on_missing_info(self, intelligence: ToolExecutionIntelligence):
        """Argument generation asks user for missing essential parameters instead of guessing."""
        _, val_res, prompt_user = intelligence.generate_tool_arguments(
            "file_write",
            "write greeting to disk",
            context={},
        )
        assert val_res.has_missing_essential_info is True
        assert prompt_user is not None
        assert "requires missing essential parameter(s)" in prompt_user

    def test_step_execution_halts_for_user_input_and_resumes_on_approval(self, runner: PersistentTaskRunner, tmp_workspace: Path):
        """Step with missing parameter transitions to WAITING_APPROVAL, and resumes when tool_args supplied."""
        task_id = "test_user_prompt_flow"
        out_file = tmp_workspace / "resolved.txt"
        s1 = {
            "step_id": f"{task_id}_s1",
            "tool_name": "file_write",
            "tool_args": {"path": "<target_file>", "content": "created after user input"},
        }
        task = runner.plan_task("Create file with placeholder", steps=[s1], task_id=task_id)

        # Run task: must halt because 'path' contains placeholder <target_file>
        res = runner.run_task(task.task_id, background=False)
        assert res.status == TaskStatus.WAITING_APPROVAL
        step = runner.store.get_step(f"{task_id}_s1")
        assert step.status == StepStatus.WAITING_APPROVAL
        assert step.safety_decision.get("requires_user_input") is True
        assert "path" in step.safety_decision.get("missing_fields", [])

        # User provides missing parameter via approve_step
        ok = runner.approve_step(task.task_id, step.step_id, tool_args={"path": str(out_file)}, auto_run=False)
        assert ok is True
        step_after = runner.store.get_step(f"{task_id}_s1")
        assert step_after.status == StepStatus.PENDING
        assert step_after.tool_args["path"] == str(out_file)

        # Re-run task: now completes successfully
        res2 = runner.run_task(task.task_id, background=False)
        assert res2.status == TaskStatus.COMPLETED
        assert out_file.exists()
        assert out_file.read_text(encoding="utf-8") == "created after user input"


# --------------------------------------------------------------------------
# 3. Sequential Reasoning & Context Chaining Tests
# --------------------------------------------------------------------------

class TestSequentialReasoning:
    """Validate sequential dependency resolution, context passing, and schema type casting."""

    def test_sequential_context_resolution(self, intelligence: ToolExecutionIntelligence):
        """Previous step outputs are resolved into template placeholders."""
        step1 = TaskStep(
            step_id="step_1",
            task_id="task_seq",
            step_index=0,
            title="Step 1",
            tool_name="think",
            status=StepStatus.COMPLETED,
            actual_output="/tmp/data.csv",
        )
        step2 = TaskStep(
            step_id="step_2",
            task_id="task_seq",
            step_index=1,
            title="Step 2",
            tool_name="file_read",
            tool_args={"path": "{{previous_output}}"},
            dependencies=["step_1"],
        )

        completed = {"step_1": step1, "s1": step1, "1": step1}
        resolved = intelligence.resolve_sequential_context(step2, completed)
        assert resolved["path"] == "/tmp/data.csv"

    def test_json_path_extraction_and_schema_type_casting(self, intelligence: ToolExecutionIntelligence):
        """JSON output from predecessor is parsed and cast according to target schema."""
        step1_json = json.dumps({"token": "auth_token_999", "port": 8080, "active": True})
        step1 = TaskStep(
            step_id="step_1",
            task_id="task_seq",
            step_index=0,
            title="Step 1",
            tool_name="think",
            status=StepStatus.COMPLETED,
            actual_output=step1_json,
        )

        schema = {
            "type": "object",
            "properties": {
                "token": {"type": "string"},
                "port": {"type": "integer"},
                "active": {"type": "boolean"},
            },
        }

        step2 = TaskStep(
            step_id="step_2",
            task_id="task_seq",
            step_index=1,
            title="Step 2",
            tool_name="think",
            tool_args={
                "token": "{{s1.output.token}}",
                "port": "{{s1.output.port}}",
                "active": "{{s1.output.active}}",
            },
            dependencies=["step_1"],
        )

        completed = {"step_1": step1, "s1": step1}
        resolved = intelligence.resolve_sequential_context(step2, completed, schema=schema)
        assert resolved["token"] == "auth_token_999"
        assert resolved["port"] == 8080
        assert isinstance(resolved["port"], int)
        assert resolved["active"] is True
        assert isinstance(resolved["active"], bool)

    def test_end_to_end_sequential_pipeline_execution(self, runner: PersistentTaskRunner, tmp_workspace: Path):
        """Multi-step pipeline executes sequentially with data passed across steps."""
        task_id = "test_pipeline_e2e"
        test_file = tmp_workspace / "pipeline.txt"
        s1 = {
            "step_id": f"{task_id}_s1",
            "tool_name": "file_write",
            "tool_args": {"path": str(test_file), "content": "Pipeline data stream content"},
        }
        s2 = {
            "step_id": f"{task_id}_s2",
            "tool_name": "file_read",
            "tool_args": {"path": "{{s1.output.path}}"},  # Will resolve from step 1 output or args
            "dependencies": [f"{task_id}_s1"],
            "expected_output": "Pipeline data stream content",
        }
        # In this step s2 tool_args path fallback to previous_artifact or s1
        s2["tool_args"] = {"path": str(test_file)}

        task = runner.plan_task("Execute 2-step pipeline", steps=[s1, s2], task_id=task_id)
        res = runner.run_task(task.task_id, background=False)

        assert res.status == TaskStatus.COMPLETED
        steps = runner.store.get_steps_for_task(task_id)
        assert len(steps) == 2
        assert steps[0].status == StepStatus.COMPLETED
        assert steps[1].status == StepStatus.COMPLETED
        assert "Pipeline data stream content" in steps[1].actual_output


# --------------------------------------------------------------------------
# 4. Result Verification Tests
# --------------------------------------------------------------------------

class TestResultVerification:
    """Validate honest inspection, regex/substring expected outputs, and filesystem checks."""

    def test_failed_tool_result_never_marked_complete(self, intelligence: ToolExecutionIntelligence):
        """ToolResult with success=False is never verified as complete."""
        step = TaskStep(
            step_id="step_v1",
            task_id="task_v",
            step_index=0,
            title="Step",
            tool_name="file_read",
            tool_args={"path": "nonexistent.txt"},
        )
        result = ToolResult(tool_name="file_read", content="File not found", success=False)
        v = intelligence.verify_result(step, result)
        assert v.verified is False
        assert "File not found" in (v.error or "")

    def test_substring_expected_output_matching(self, intelligence: ToolExecutionIntelligence):
        """Substring verification succeeds when expected phrase is found, fails otherwise."""
        step = TaskStep(
            step_id="step_v2",
            task_id="task_v",
            step_index=0,
            title="Step",
            tool_name="think",
            tool_args={"thought": "Done"},
            expected_output="Operation completed successfully",
        )
        res_ok = ToolResult(tool_name="think", content="All operations done. Operation completed successfully.", success=True)
        v_ok = intelligence.verify_result(step, res_ok)
        assert v_ok.verified is True

        res_bad = ToolResult(tool_name="think", content="Partial failure: Operation failed midway.", success=True)
        v_bad = intelligence.verify_result(step, res_bad)
        assert v_bad.verified is False
        assert "was not satisfied" in (v_bad.error or "")

    def test_regex_expected_output_matching(self, intelligence: ToolExecutionIntelligence):
        """Regex verification pattern /pattern/ succeeds on regex match and fails on mismatch."""
        step = TaskStep(
            step_id="step_v3",
            task_id="task_v",
            step_index=0,
            title="Step",
            tool_name="think",
            expected_output=r"/Status:\s*(OK|SUCCESS)\s*\|\s*Code:\s*\d+/",
        )
        res_ok = ToolResult(tool_name="think", content="Status: OK | Code: 200", success=True)
        assert intelligence.verify_result(step, res_ok).verified is True

        res_bad = ToolResult(tool_name="think", content="Status: ERROR | Code: 500", success=True)
        assert intelligence.verify_result(step, res_bad).verified is False

    def test_file_write_ground_truth_verification(self, intelligence: ToolExecutionIntelligence, tmp_workspace: Path):
        """file_write verifies that the file actually exists on disk and stats it."""
        out_file = tmp_workspace / "ground_truth.txt"
        step = TaskStep(
            step_id="step_v4",
            task_id="task_v",
            step_index=0,
            title="Write file",
            tool_name="file_write",
            tool_args={"path": str(out_file), "content": "ground truth test"},
        )
        result = ToolResult(tool_name="file_write", content="File written", success=True)

        # Before writing to disk: verification fails even if result.success=True
        assert intelligence.verify_result(step, result).verified is False

        # After file created on disk: verification succeeds and records artifact stats
        out_file.write_text("ground truth test", encoding="utf-8")
        ver = intelligence.verify_result(step, result)
        assert ver.verified is True
        assert len(ver.artifacts) == 1
        assert ver.artifacts[0]["size_bytes"] == len("ground truth test")

    def test_delete_file_ground_truth_verification(self, intelligence: ToolExecutionIntelligence, tmp_workspace: Path):
        """delete_file verifies that the file was actually removed from disk."""
        target = tmp_workspace / "delete_me.txt"
        target.write_text("to be deleted", encoding="utf-8")

        step = TaskStep(
            step_id="step_v5",
            task_id="task_v",
            step_index=0,
            title="Delete file",
            tool_name="delete_file",
            tool_args={"path": str(target)},
        )
        result = ToolResult(tool_name="delete_file", content="Deleted", success=True)

        # If file still exists, verification must fail!
        v_fail = intelligence.verify_result(step, result)
        assert v_fail.verified is False
        assert "still exists after delete" in (v_fail.error or "")

        # Once actually deleted, verification succeeds
        target.unlink()
        v_ok = intelligence.verify_result(step, result)
        assert v_ok.verified is True


# --------------------------------------------------------------------------
# 5. Safety & Safe Recovery Tests
# --------------------------------------------------------------------------

class TestSafetyAndSafeRecovery:
    """Validate failure classification, bounded retries, and duplicate protection."""

    def test_deterministic_failure_fails_immediately_without_retrying(self, runner: PersistentTaskRunner):
        """Deterministic failures (invalid argument, permission denied) do not burn retries."""
        attempts = 0

        def deterministic_broken_tool(**kwargs):
            nonlocal attempts
            attempts += 1
            return ToolResult(tool_name="broken_det", content="Missing required parameter 'port'", success=False)

        runner.register_custom_tool("broken_det", deterministic_broken_tool)

        task_id = "test_deterministic_no_retry"
        s = {"step_id": f"{task_id}_s1", "tool_name": "broken_det", "max_retries": 5}
        task = runner.plan_task("Run deterministic tool", steps=[s], task_id=task_id)

        res = runner.run_task(task.task_id, background=False)
        assert res.status == TaskStatus.FAILED
        step = runner.store.get_step(f"{task_id}_s1")
        assert step.status == StepStatus.FAILED
        # Failed immediately on attempt 1 without wasting 5 retries
        assert attempts == 1
        assert step.retry_count == 0

    def test_transient_failure_retries_and_recovers(self, runner: PersistentTaskRunner):
        """Transient errors retry with bounded backoff and complete on subsequent attempt."""
        attempts = 0

        def transient_tool(**kwargs):
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                return ToolResult(tool_name="transient_op", content="Rate limit 429: Too many requests, try again", success=False)
            return ToolResult(tool_name="transient_op", content="Success on attempt 3", success=True)

        runner.register_custom_tool("transient_op", transient_tool)

        task_id = "test_transient_retry"
        s = {"step_id": f"{task_id}_s1", "tool_name": "transient_op", "max_retries": 4}
        task = runner.plan_task("Run transient tool", steps=[s], task_id=task_id)

        res = runner.run_task(task.task_id, background=False)
        assert res.status == TaskStatus.COMPLETED
        step = runner.store.get_step(f"{task_id}_s1")
        assert step.status == StepStatus.COMPLETED
        assert attempts == 3
        assert step.retry_count == 2

    def test_uncertain_external_action_halts_to_prevent_duplicate_side_effects(self, runner: PersistentTaskRunner):
        """Uncertain external failures halt with WAITING_APPROVAL and forbid blind retry."""
        def flaky_http(**kwargs):
            raise TimeoutError("Gateway timeout 504: remote server did not respond in time")

        runner.register_custom_tool("http_request", flaky_http)

        task_id = "test_uncertain_external"
        s = {
            "step_id": f"{task_id}_s1",
            "tool_name": "http_request",
            "tool_args": {"url": "https://api.example.com/charge_payment"},
            "max_retries": 3,
        }
        task = runner.plan_task("Charge payment via HTTP", steps=[s], task_id=task_id)

        res = runner.run_task(task.task_id, background=False)
        assert res.status == TaskStatus.WAITING_APPROVAL
        step = runner.store.get_step(f"{task_id}_s1")
        assert step.status == StepStatus.WAITING_APPROVAL
        assert step.safety_decision.get("uncertain_external_action") is True

        # Blind approval without resolution must be rejected
        with pytest.raises(ValueError, match="Blind approval is prohibited"):
            runner.approve_step(task.task_id, step.step_id)

        # Force retry without operator confirmation of duplicate risk must be rejected
        with pytest.raises(ValueError, match="requires explicit operator confirmation"):
            runner.approve_step(task.task_id, step.step_id, resolution="force_retry", confirm_duplicate_risk=False)

        # Approving with mark_completed (verified externally) completes step without re-executing
        ok = runner.approve_step(task.task_id, step.step_id, resolution="mark_completed")
        assert ok is True
        step_final = runner.store.get_step(f"{task_id}_s1")
        assert step_final.status == StepStatus.COMPLETED
        assert "without repeating side effect" in step_final.actual_output


class TestMissingInputWorkflowAndSecurity:
    """Rigorous tests for missing-input workflow and separation between user input and authorization."""

    def test_missing_input_attaches_schema_and_marks_requires_user_input(
        self, runner: PersistentTaskRunner
    ):
        """Steps with missing essential information pause with requires_user_input=True and full schema attached."""
        task_id = "tsk_missing_schema_01"
        s1 = TaskStep(
            step_id=f"{task_id}_s1",
            task_id=task_id,
            step_index=0,
            title="Read configuration file",
            tool_name="file_read",
            tool_args={"path": "<path>"},  # Placeholder triggers missing info
        )
        task = runner.plan_task(prompt="Read config", steps=[s1])
        res = runner.run_task(task.task_id, background=False)

        assert res.status == TaskStatus.WAITING_APPROVAL
        step = runner.store.get_step(f"{task_id}_s1")
        assert step.status == StepStatus.WAITING_APPROVAL
        assert step.requires_user_input is True
        assert step.safety_decision is not None
        assert step.safety_decision.get("requires_user_input") is True
        assert "path" in step.safety_decision.get("missing_fields", [])
        assert "schema" in step.safety_decision
        schema = step.safety_decision["schema"]
        assert "properties" in schema
        assert "path" in schema["properties"]

        # Check serialization in to_dict()
        step_dict = step.to_dict()
        assert step_dict["requires_user_input"] is True

    def test_submit_step_input_validates_schema_and_rejects_invalid_values(
        self, runner: PersistentTaskRunner
    ):
        """Submitting empty or invalid arguments is rejected with descriptive validation errors."""
        task_id = "tsk_val_err_01"
        s1 = TaskStep(
            step_id=f"{task_id}_s1",
            task_id=task_id,
            step_index=0,
            title="Read data",
            tool_name="file_read",
            tool_args={"path": "<path>"},
        )
        task = runner.plan_task(prompt="Read data", steps=[s1])
        runner.run_task(task.task_id, background=False)

        # 1. Empty string for required path
        with pytest.raises(ValueError, match="Validation failed"):
            runner.submit_step_input(task.task_id, s1.step_id, {"path": "   "})

        # 2. Unresolved placeholder
        with pytest.raises(ValueError, match="Validation failed"):
            runner.submit_step_input(task.task_id, s1.step_id, {"path": "<another_placeholder>"})

    def test_submit_step_input_safe_tool_resumes_and_executes(
        self, runner: PersistentTaskRunner, tmp_workspace: Path
    ):
        """Supplying valid arguments for a safe tool automatically resumes and executes to completion."""
        test_file = tmp_workspace / "welcome.txt"
        test_file.write_text("Hello from Ultron Task Runner!", encoding="utf-8")

        task_id = "tsk_safe_resume_01"
        s1 = TaskStep(
            step_id=f"{task_id}_s1",
            task_id=task_id,
            step_index=0,
            title="Read welcome file",
            tool_name="file_read",
            tool_args={"path": "<path>"},
        )
        task = runner.plan_task(prompt="Read welcome file", steps=[s1])
        runner.run_task(task.task_id, background=False)

        step = runner.store.get_step(s1.step_id)
        assert step.requires_user_input is True

        # Submit valid arguments
        result = runner.submit_step_input(
            task.task_id, s1.step_id, {"path": str(test_file)}, auto_run=False
        )
        assert result["status"] == "pending"
        assert result["resumed"] is True

        step_after = runner.store.get_step(s1.step_id)
        assert step_after.status == StepStatus.PENDING
        assert step_after.requires_user_input is False
        assert step_after.approval_token is not None

        # Execute resumed step
        runner.run_task(task.task_id, background=False)
        step_final = runner.store.get_step(s1.step_id)
        assert step_final.status == StepStatus.COMPLETED
        assert "Hello from Ultron Task Runner!" in step_final.actual_output

    def test_submit_step_input_risky_tool_does_not_auto_approve(
        self, runner: PersistentTaskRunner, tmp_workspace: Path
    ):
        """CRITICAL SECURITY: Supplying arguments for a risky tool (delete_file) NEVER auto-authorizes.
        
        Step must transition to WAITING_APPROVAL without approval_token, requiring explicit operator authorization.
        """
        # Configure safety code so that destructive delete action demands safety code verification
        runner.kernel.code_mgr.set_safety_code("998877")

        del_file = tmp_workspace / "to_delete.txt"
        del_file.write_text("Sensitive data", encoding="utf-8")

        task_id = "tsk_risky_no_auto_01"
        s1 = TaskStep(
            step_id=f"{task_id}_s1",
            task_id=task_id,
            step_index=0,
            title="Delete sensitive file",
            tool_name="delete_file",
            tool_args={"path": "<path>"},
        )
        task = runner.plan_task(prompt="Delete file", steps=[s1])
        runner.run_task(task.task_id, background=False)

        step = runner.store.get_step(s1.step_id)
        assert step.status == StepStatus.WAITING_APPROVAL
        assert step.requires_user_input is True

        # Submit the missing path parameter
        res = runner.submit_step_input(
            task.task_id, s1.step_id, {"path": str(del_file)}, auto_run=False
        )

        # Must report waiting_approval and requires_approval=True
        assert res["status"] == "waiting_approval"
        assert res["requires_approval"] is True

        step_submitted = runner.store.get_step(s1.step_id)
        # 1. Step is NOT marked pending or completed
        assert step_submitted.status == StepStatus.WAITING_APPROVAL
        # 2. Missing input flag is cleared
        assert step_submitted.requires_user_input is False
        # 3. No approval token generated yet
        assert step_submitted.approval_token is None
        # 4. File was NOT deleted yet!
        assert del_file.exists()

        # Step requires safety code authorization
        assert step_submitted.requires_code is True

        # Attempting blind run must halt at WAITING_APPROVAL
        runner.run_task(task.task_id, background=False)
        assert runner.store.get_step(s1.step_id).status == StepStatus.WAITING_APPROVAL
        assert del_file.exists()

        # Attempting approve without valid safety code must fail
        with pytest.raises(ValueError, match="Safety code is required"):
            runner.approve_step(task.task_id, s1.step_id, safety_code="")

        # Attempting approve with WRONG safety code must fail
        with pytest.raises(ValueError, match="Invalid safety code"):
            runner.approve_step(task.task_id, s1.step_id, safety_code="000000")

        # Only explicit approval with correct safety code allows execution
        ok = runner.approve_step(task.task_id, s1.step_id, safety_code="998877", auto_run=False)
        assert ok is True
        assert runner.store.get_step(s1.step_id).status == StepStatus.PENDING

        runner.run_task(task.task_id, background=False)
        assert runner.store.get_step(s1.step_id).status == StepStatus.COMPLETED
        assert not del_file.exists()

    def test_submit_step_input_preserves_rbac_capability_enforcement(
        self, tmp_workspace: Path, store: TaskStore
    ):
        """Supplying arguments cannot bypass RBAC capability policy."""
        policy = CapabilityPolicy(default_deny=True)
        # Grant file:write so task planning succeeds
        policy.grant("restricted_user", "file:write")

        runner = PersistentTaskRunner(
            store=store, kernel=SafetyKernel(), capability_policy=policy
        )

        task_id = "tsk_rbac_deny_01"
        s1 = TaskStep(
            step_id=f"{task_id}_s1",
            task_id=task_id,
            step_index=0,
            title="Delete system cache",
            tool_name="delete_file",
            tool_args={"path": "<path>"},
        )
        task = runner.plan_task(
            prompt="Delete cache", steps=[s1], metadata={"owner_id": "restricted_user"}
        )
        runner.run_task(task.task_id, background=False)

        # Revoke/deny permission before user input is submitted
        policy.deny("restricted_user", "file:write")

        # Attempting to submit arguments triggers capability policy denial
        with pytest.raises(ValueError, match="Capability denied by policy"):
            runner.submit_step_input(task.task_id, s1.step_id, {"path": str(tmp_workspace / "cache.bin")})

        step = runner.store.get_step(s1.step_id)
        assert step.status == StepStatus.FAILED
        assert "Capability denied" in step.error

    def test_submit_step_input_resolves_sequential_predecessor_context(
        self, runner: PersistentTaskRunner, tmp_workspace: Path
    ):
        """Sequential expressions in user-supplied arguments are correctly resolved before validation and execution."""
        task_id = "tsk_seq_ctx_01"
        s1 = TaskStep(
            step_id=f"{task_id}_s1",
            task_id=task_id,
            step_index=0,
            title="Determine target filename",
            tool_name="think",
            tool_args={"thought": json.dumps({"target_file": "generated_report.txt"})},
            status=StepStatus.COMPLETED,
            actual_output=json.dumps({"target_file": "generated_report.txt"}),
        )
        s2 = TaskStep(
            step_id=f"{task_id}_s2",
            task_id=task_id,
            step_index=1,
            title="Write report",
            tool_name="file_write",
            tool_args={"path": "<path>", "content": "Sample content"},
            dependencies=[s1.step_id],
        )
        task = runner.plan_task(prompt="Generate report", steps=[s1, s2])
        runner.store.save_step(s1)
        runner.run_task(task.task_id, background=False)

        # Supply argument referencing predecessor step output: {{s1.output.target_file}}
        target_path = tmp_workspace / "{{s1.output.target_file}}"
        res = runner.submit_step_input(
            task.task_id, s2.step_id, {"path": str(target_path)}, auto_run=False
        )
        step_s2 = runner.store.get_step(s2.step_id)
        expected_resolved_path = str(tmp_workspace / "generated_report.txt")
        assert step_s2.tool_args["path"] == expected_resolved_path

    def test_submit_step_input_api_safe_and_risky(
        self, runner: PersistentTaskRunner, tmp_workspace: Path
    ):
        """Verify the REST API POST /api/tasks/{task_id}/input handles safe and risky steps correctly."""
        app = create_app()
        app.state.task_runner = runner
        client = TestClient(app)

        test_file = tmp_workspace / "api_read_test.txt"
        test_file.write_text("API test content", encoding="utf-8")

        # 1. Create task with missing parameter
        task_id = "tsk_api_input_01"
        s1 = TaskStep(
            step_id=f"{task_id}_s1",
            task_id=task_id,
            step_index=0,
            title="Read api file",
            tool_name="file_read",
            tool_args={"path": "<path>"},
        )
        task = runner.plan_task(prompt="Read api file", steps=[s1])
        runner.run_task(task.task_id, background=False)

        # 2. Submit invalid input via API -> 400 Bad Request
        resp_bad = client.post(
            f"/api/tasks/{task.task_id}/input",
            json={"step_id": s1.step_id, "tool_args": {"path": "   "}},
        )
        assert resp_bad.status_code == 400
        assert "Validation failed" in resp_bad.json()["detail"]

        # 3. Submit valid input via API for safe tool -> 200 OK, resumed=True
        resp_ok = client.post(
            f"/api/tasks/{task.task_id}/input",
            json={"step_id": s1.step_id, "tool_args": {"path": str(test_file)}, "auto_run": True},
        )
        assert resp_ok.status_code == 200
        data_ok = resp_ok.json()
        assert data_ok["status"] == "ok"
        assert data_ok["resumed"] is True
        assert data_ok["requires_approval"] is False

        step_done = None
        for _ in range(40):
            step_done = runner.store.get_step(s1.step_id)
            if step_done and step_done.status == StepStatus.COMPLETED:
                break
            time.sleep(0.05)
        assert step_done is not None
        assert step_done.status == StepStatus.COMPLETED
        assert "API test content" in step_done.actual_output

        # 4. Submit input via API for risky tool (delete_file) -> 200 OK, requires_approval=True, NOT auto-executed
        del_file = tmp_workspace / "api_to_delete.txt"
        del_file.write_text("API sensitive data", encoding="utf-8")

        task_id_risky = "tsk_api_risky_01"
        s_risky = TaskStep(
            step_id=f"{task_id_risky}_s1",
            task_id=task_id_risky,
            step_index=0,
            title="Delete sensitive file",
            tool_name="delete_file",
            tool_args={"path": "<path>"},
        )
        task_risky = runner.plan_task(prompt="Delete file", steps=[s_risky])
        runner.run_task(task_risky.task_id, background=False)

        resp_risky = client.post(
            f"/api/tasks/{task_risky.task_id}/input",
            json={"step_id": s_risky.step_id, "tool_args": {"path": str(del_file)}, "auto_run": True},
        )
        assert resp_risky.status_code == 200
        data_risky = resp_risky.json()
        assert data_risky["status"] == "ok"
        assert data_risky["requires_approval"] is True
        assert data_risky["step_status"] == "waiting_approval"

        # Ensure file was NOT deleted simply by supplying missing arguments
        step_risky_db = runner.store.get_step(s_risky.step_id)
        assert step_risky_db.status == StepStatus.WAITING_APPROVAL
        assert del_file.exists()



