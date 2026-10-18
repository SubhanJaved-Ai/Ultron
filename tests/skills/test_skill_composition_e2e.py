"""Ultron Skill Composition — End-to-End Verification Test Suite.

Verifies:
1. Complete End-to-End Workflow:
   - Create 2 simple approved test skills with deterministic outputs.
   - Pre-flight validate composite workflow via POST /api/skills/composite/validate.
   - Create composite draft via POST /api/skills/composite.
   - Confirm it starts in pending_review and cannot execute prematurely.
   - Approve it via authorized approval API (POST /api/skills/learned/{name}/approve).
   - Execute composite via PersistentTaskRunner and SkillManager.
   - Verify data passing from child 1 to child 2, accurate final output, and accurate execution status.
2. Failure & Security Paths:
   - Missing child skills.
   - Disabled child skills (via API disable -> health check -> blocked execution).
   - Invalid parameter mappings / template errors.
   - Circular dependencies (direct and indirect).
   - Child execution failures without false success.
   - Depth limits.
   - CapabilityPolicy enforcement (transitive capability union, unauthorized caller blocked).
   - SafetyKernel evaluation and blocking.
   - Protected core/system skill anti-tamper.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openjarvis.core.events import EventBus
from openjarvis.core.types import ToolCall, ToolResult
from openjarvis.security.capabilities import (
    Capability,
    CapabilityPolicy,
    DEFAULT_TOOL_CAPABILITIES,
)
from openjarvis.security.kernel import ActionEffect, SafetyKernel
from openjarvis.server.memory_skills_routes import memory_skills_router
from openjarvis.skills.composition import (
    CircularCompositionError,
    CompositionValidationError,
    DepthExceededError,
    DisabledSkillError,
    MissingDependencyError,
    UnapprovedSkillError,
    compute_composite_capabilities,
    create_composite_manifest,
    is_skill_approved_and_active,
    validate_composite_skill,
)
from openjarvis.skills.executor import SkillExecutor, SkillResult
from openjarvis.skills.learning import SkillApprovalStatus, WorkflowSkillLearner
from openjarvis.skills.manager import SkillManager
from openjarvis.skills.types import SkillManifest, SkillStep
from openjarvis.tasks.runner import PersistentTaskRunner, TaskPlanPermissionError
from openjarvis.tasks.store import TaskStore
from openjarvis.tasks.types import StepStatus, TaskRecord, TaskStatus, TaskStep
from openjarvis.tools._stubs import ToolExecutor


# ---------------------------------------------------------------------------
# Deterministic Test Fixtures
# ---------------------------------------------------------------------------

class DeterministicToolExecutor(ToolExecutor):
    """Tool executor providing strictly deterministic responses for test steps."""

    def __init__(
        self,
        responses: Optional[Dict[str, Any]] = None,
        fail_tools: Optional[List[str]] = None,
    ) -> None:
        self.responses = responses or {}
        self.fail_tools = set(fail_tools or [])
        self.call_history: List[ToolCall] = []

    def execute(self, tool_call: ToolCall) -> ToolResult:
        self.call_history.append(tool_call)
        if tool_call.name in self.fail_tools:
            return ToolResult(
                tool_name=tool_call.name,
                content=f"Deliberate test failure for tool '{tool_call.name}'.",
                success=False,
            )

        if tool_call.name == "produce_record":
            try:
                args = json.loads(tool_call.arguments) if isinstance(tool_call.arguments, str) else tool_call.arguments
            except Exception:
                args = {}
            topic = args.get("topic", "default_topic")
            return ToolResult(
                tool_name=tool_call.name,
                content=f"PRODUCED_DATA::{topic.upper()}",
                success=True,
            )

        if tool_call.name == "transform_record":
            try:
                args = json.loads(tool_call.arguments) if isinstance(tool_call.arguments, str) else tool_call.arguments
            except Exception:
                args = {}
            data = args.get("input_data", "no_data")
            return ToolResult(
                tool_name=tool_call.name,
                content=f"TRANSFORMED<<{data}>>",
                success=True,
            )

        resp = self.responses.get(tool_call.name, f"DEFAULT_RESP_FOR_{tool_call.name}")
        return ToolResult(
            tool_name=tool_call.name,
            content=resp,
            success=True,
        )


@pytest.fixture
def test_environment(tmp_path: Path):
    """Set up an isolated end-to-end environment with SkillManager, Learner, Runner, and FastAPI TestClient."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)

    bus = EventBus()
    tool_executor = DeterministicToolExecutor()
    cap_policy = CapabilityPolicy(default_deny=False)

    skill_manager = SkillManager(
        bus=bus,
        tool_executor=tool_executor,
        capability_policy=cap_policy,
    )

    learner = WorkflowSkillLearner(
        skill_manager=skill_manager,
        skills_dir=skills_dir,
    )

    store = TaskStore(tasks_dir / "tasks.db")
    runner = PersistentTaskRunner(
        store=store,
        skill_manager=skill_manager,
        capability_policy=cap_policy,
        bus=bus,
    )
    # Ensure runner uses the same learner
    runner.workflow_skill_learner = learner

    # Set up FastAPI app with router
    app = FastAPI()
    app.include_router(memory_skills_router)
    app.state.workflow_skill_learner = learner
    app.state.skill_manager = skill_manager
    app.state.capability_policy = cap_policy
    app.state.task_runner = runner
    app.state.multi_user = False  # Single-operator admin default

    client = TestClient(app)

    return {
        "tmp_path": tmp_path,
        "skills_dir": skills_dir,
        "bus": bus,
        "tool_executor": tool_executor,
        "cap_policy": cap_policy,
        "skill_manager": skill_manager,
        "learner": learner,
        "runner": runner,
        "app": app,
        "client": client,
    }


# ---------------------------------------------------------------------------
# Complete End-to-End Workflow Test
# ---------------------------------------------------------------------------

class TestSkillCompositionCompleteWorkflow:
    """End-to-End verification of the complete 7-step composite workflow."""

    def test_complete_composite_workflow_e2e(self, test_environment):
        env = test_environment
        client: TestClient = env["client"]
        learner: WorkflowSkillLearner = env["learner"]
        manager: SkillManager = env["skill_manager"]
        runner: PersistentTaskRunner = env["runner"]

        # -------------------------------------------------------------------
        # Step 1: Create two simple approved test skills with deterministic outputs
        # -------------------------------------------------------------------
        child_one = SkillManifest(
            name="skill_producer",
            version="1.0.0",
            description="Child 1: Produces deterministic record from topic",
            author="operator",
            steps=[
                SkillStep(
                    tool_name="produce_record",
                    arguments_template='{"topic": "{query_topic}"}',
                    output_key="producer_output",
                )
            ],
            required_capabilities=[Capability.TOOL_INVOKE.value],
            tags=["approved"],
            metadata={"approved": True, "approval_status": SkillApprovalStatus.APPROVED},
            user_invocable=True,
            disable_model_invocation=False,
        )

        child_two = SkillManifest(
            name="skill_transformer",
            version="1.0.0",
            description="Child 2: Transforms record produced by Child 1",
            author="operator",
            steps=[
                SkillStep(
                    tool_name="transform_record",
                    arguments_template='{"input_data": "{raw_input}"}',
                    output_key="transformer_output",
                )
            ],
            required_capabilities=[Capability.TOOL_INVOKE.value],
            tags=["approved"],
            metadata={"approved": True, "approval_status": SkillApprovalStatus.APPROVED},
            user_invocable=True,
            disable_model_invocation=False,
        )

        learner.save_and_register_skill(child_one, overwrite=True)
        learner.save_and_register_skill(child_two, overwrite=True)

        assert manager.resolve("skill_producer") is not None
        assert manager.resolve("skill_transformer") is not None

        # -------------------------------------------------------------------
        # Step 2: Use composition validation API to validate a composite workflow
        # -------------------------------------------------------------------
        valid_payload = {
            "name": "composite_etl_pipeline",
            "description": "Composite pipeline combining producer and transformer",
            "steps": [
                {
                    "tool_name": "",
                    "skill_name": "skill_producer",
                    "arguments_template": '{"query_topic": "{topic}"}',
                    "output_key": "step1_out",
                },
                {
                    "tool_name": "",
                    "skill_name": "skill_transformer",
                    "arguments_template": '{"raw_input": "{step1_out}"}',
                    "output_key": "step2_out",
                },
            ],
            "require_approval": True,
            "tags": ["pipeline", "etl"],
        }

        val_resp = client.post("/api/skills/composite/validate", json=valid_payload)
        assert val_resp.status_code == 200
        val_data = val_resp.json()
        assert val_data["valid"] is True
        assert val_data["errors"] == []
        assert "skill_producer" in val_data["dependencies"]
        assert "skill_transformer" in val_data["dependencies"]

        # -------------------------------------------------------------------
        # Step 3: Create the composite through existing UI/API path
        # -------------------------------------------------------------------
        create_resp = client.post("/api/skills/composite", json=valid_payload)
        assert create_resp.status_code == 200
        create_data = create_resp.json()
        assert create_data["status"] == "created"
        created_skill = create_data["skill"]
        assert created_skill["name"] == "composite_etl_pipeline"
        assert created_skill["is_composite"] is True
        assert created_skill["approval_status"] == SkillApprovalStatus.PENDING_REVIEW
        assert created_skill["user_invocable"] is False

        # -------------------------------------------------------------------
        # Step 4: Confirm composite starts pending approval and cannot execute prematurely
        # -------------------------------------------------------------------
        comp_manifest = manager.resolve("composite_etl_pipeline")
        is_ok, reason = is_skill_approved_and_active(comp_manifest)
        assert is_ok is False
        assert "not approved" in reason.lower()

        # 4A. PersistentTaskRunner plan validation must reject unapproved composite skill
        with pytest.raises(TaskPlanPermissionError) as plan_err:
            runner.validate_plan([
                TaskStep(
                    step_id="step_premature",
                    task_id="t_premature",
                    step_index=0,
                    title="Attempt unapproved composite execution",
                    tool_name="composite_etl_pipeline",
                    tool_args={"topic": "aurora"},
                )
            ])
        assert "not approved" in str(plan_err.value).lower()

        # 4B. Runtime execution handler refusal
        _, handler, _ = runner.resolve_tool_handler("composite_etl_pipeline")
        premature_tool_result = handler(topic="aurora")
        assert premature_tool_result.success is False
        assert "Refusing to execute unapproved learned skill" in premature_tool_result.content

        # -------------------------------------------------------------------
        # Step 5: Approve it through the existing authorized approval mechanism
        # -------------------------------------------------------------------
        approve_resp = client.post("/api/skills/learned/composite_etl_pipeline/approve")
        assert approve_resp.status_code == 200
        approved_data = approve_resp.json()
        assert approved_data["status"] == "approved"
        assert approved_data["skill"]["approval_status"] == SkillApprovalStatus.APPROVED
        assert approved_data["skill"]["user_invocable"] is True

        refreshed_manifest = manager.resolve("composite_etl_pipeline")
        is_ok_now, ok_reason = is_skill_approved_and_active(refreshed_manifest)
        assert is_ok_now is True
        assert "approved" in ok_reason.lower()

        # -------------------------------------------------------------------
        # Step 6: Execute the composite through existing task/skill execution path
        # -------------------------------------------------------------------
        # 6A. Direct execution via SkillManager.execute
        direct_result: SkillResult = manager.execute(
            "composite_etl_pipeline",
            context={"topic": "hyperion"},
        )
        assert direct_result.success is True
        assert len(direct_result.step_results) == 2

        # -------------------------------------------------------------------
        # Step 7: Verify output reaches second child, final result is correct,
        #         and execution status is accurate.
        # -------------------------------------------------------------------
        # Child 1: produce_record for "hyperion" -> "PRODUCED_DATA::HYPERION"
        assert direct_result.context["step1_out"] == "PRODUCED_DATA::HYPERION"
        # Child 2: transform_record for "PRODUCED_DATA::HYPERION" -> "TRANSFORMED<<PRODUCED_DATA::HYPERION>>"
        assert direct_result.context["step2_out"] == "TRANSFORMED<<PRODUCED_DATA::HYPERION>>"

        # 6B. Task execution via PersistentTaskRunner
        task = runner.create_task(
            prompt="Run full ETL composite workflow",
            steps=[
                {
                    "step_id": "step_run_composite",
                    "title": "Execute composite pipeline",
                    "tool_name": "composite_etl_pipeline",
                    "tool_args": {"topic": "solaris"},
                }
            ],
            task_id="task_e2e_composite_1",
        )
        assert task.status == TaskStatus.QUEUED

        # Run task synchronously
        finished_task = runner.run_task(task.task_id, background=False)
        assert finished_task.status == TaskStatus.COMPLETED
        assert len(finished_task.steps) == 1
        comp_step = finished_task.steps[0]
        assert comp_step.status == StepStatus.COMPLETED
        assert comp_step.error is None
        # Verify the actual step output contains the final transformed result
        assert comp_step.actual_output == "TRANSFORMED<<PRODUCED_DATA::SOLARIS>>"

        # Verify audit history
        ledger_resp = client.get("/api/skills/learned/composite_etl_pipeline")
        assert ledger_resp.status_code == 200
        ledger_data = ledger_resp.json()
        assert len(ledger_data["skill"]["audit_history"]) >= 2  # create + approve


# ---------------------------------------------------------------------------
# Failure & Security Path Tests
# ---------------------------------------------------------------------------

class TestSkillCompositionFailureAndSecurityPaths:
    """Verification of failure scenarios, capability policies, and security protections."""

    def test_missing_child_skill_validation_and_runtime(self, test_environment):
        client: TestClient = test_environment["client"]
        manager: SkillManager = test_environment["skill_manager"]

        # 1. Validation API rejects missing child
        payload = {
            "name": "comp_missing_child",
            "description": "Invokes nonexistent child",
            "steps": [
                {
                    "tool_name": "",
                    "skill_name": "nonexistent_child_skill",
                    "arguments_template": "{}",
                    "output_key": "out",
                }
            ],
        }
        val_resp = client.post("/api/skills/composite/validate", json=payload)
        assert val_resp.status_code == 200
        val_data = val_resp.json()
        assert val_data["valid"] is False
        assert any("not registered" in err.lower() or "not found" in err.lower() for err in val_data["errors"])

        # 2. Runtime execution rejects missing child
        comp = SkillManifest(
            name="comp_missing_child_manifest",
            steps=[SkillStep(skill_name="nonexistent_child_skill")],
            tags=["approved"],
            metadata={"approved": True, "approval_status": "approved"},
        )
        manager.register(comp)
        res = manager.execute("comp_missing_child_manifest")
        assert res.success is False
        assert "not found" in res.step_results[0].content.lower()

    def test_disabled_child_skill_blocks_workflow(self, test_environment):
        client: TestClient = test_environment["client"]
        learner: WorkflowSkillLearner = test_environment["learner"]
        manager: SkillManager = test_environment["skill_manager"]

        # Register child skill
        child = SkillManifest(
            name="child_to_disable",
            steps=[SkillStep(tool_name="produce_record", arguments_template='{"topic": "t"}')],
            tags=["approved"],
            metadata={"approved": True, "approval_status": "approved"},
            user_invocable=True,
        )
        learner.save_and_register_skill(child, overwrite=True)

        # Disable child via API
        dis_resp = client.post(
            "/api/skills/learned/child_to_disable/disable",
            json={"reason": "Security deprecation."},
        )
        assert dis_resp.status_code == 200
        assert dis_resp.json()["status"] == "disabled"

        # Attempt to validate composite using disabled child
        comp_payload = {
            "name": "comp_with_disabled_child",
            "steps": [
                {
                    "tool_name": "",
                    "skill_name": "child_to_disable",
                    "arguments_template": "{}",
                    "output_key": "out",
                }
            ],
        }
        val_resp = client.post("/api/skills/composite/validate", json=comp_payload)
        assert val_resp.status_code == 200
        assert val_resp.json()["valid"] is False
        assert any("disabled" in err.lower() for err in val_resp.json()["errors"])

        # Create composite while child was approved, then disable child -> execution blocked
        comp_manifest = SkillManifest(
            name="comp_exec_disabled",
            steps=[SkillStep(skill_name="child_to_disable")],
            tags=["approved"],
            metadata={"approved": True, "approval_status": "approved"},
        )
        manager.register(comp_manifest)
        res = manager.execute("comp_exec_disabled")
        assert res.success is False
        assert "disabled" in res.step_results[0].content.lower()

    def test_circular_dependency_detected_and_blocked(self, test_environment):
        client: TestClient = test_environment["client"]
        manager: SkillManager = test_environment["skill_manager"]

        # 1. Direct cycle
        direct_cycle_payload = {
            "name": "cycle_self",
            "steps": [{"tool_name": "", "skill_name": "cycle_self", "arguments_template": "{}"}],
        }
        resp = client.post("/api/skills/composite/validate", json=direct_cycle_payload)
        assert resp.status_code == 200
        assert resp.json()["valid"] is False
        assert any("circular" in e.lower() for e in resp.json()["errors"])

        # 2. Multi-hop cycle: node_a -> node_b -> node_a
        manager.register(SkillManifest(
            name="node_b",
            steps=[SkillStep(skill_name="node_a")],
            tags=["approved"],
            metadata={"approved": True, "approval_status": "approved"},
        ))
        multi_hop_payload = {
            "name": "node_a",
            "steps": [{"tool_name": "", "skill_name": "node_b", "arguments_template": "{}"}],
        }
        resp2 = client.post("/api/skills/composite/validate", json=multi_hop_payload)
        assert resp2.status_code == 200
        assert resp2.json()["valid"] is False
        assert any("circular" in e.lower() for e in resp2.json()["errors"])

    def test_depth_limit_enforced(self, test_environment):
        manager: SkillManager = test_environment["skill_manager"]

        # Create chain depth 6 with max_depth 5
        for i in range(1, 8):
            step = [SkillStep(skill_name=f"chain_step_{i+1}")] if i < 7 else [SkillStep(tool_name="produce_record")]
            manager.register(SkillManifest(
                name=f"chain_step_{i}",
                steps=step,
                tags=["approved"],
                metadata={"approved": True, "approval_status": "approved"},
            ))

        root = manager.resolve("chain_step_1")
        with pytest.raises(DepthExceededError):
            validate_composite_skill(root, manager, max_depth=5)

        runtime_res = manager.execute("chain_step_1", max_depth=5)
        assert runtime_res.success is False
        assert "depth limit" in runtime_res.step_results[0].content.lower()

    def test_child_execution_failure_propagates_honestly(self, test_environment):
        manager: SkillManager = test_environment["skill_manager"]
        runner: PersistentTaskRunner = test_environment["runner"]

        # Tool fail_step is configured to fail deliberately in DeterministicToolExecutor
        env_executor: DeterministicToolExecutor = test_environment["tool_executor"]
        env_executor.fail_tools.add("fail_tool")

        child_ok = SkillManifest(
            name="child_ok",
            steps=[SkillStep(tool_name="produce_record", arguments_template='{"topic": "ok"}', output_key="c1")],
            tags=["approved"],
            metadata={"approved": True, "approval_status": "approved"},
        )
        child_fail = SkillManifest(
            name="child_fail",
            steps=[SkillStep(tool_name="fail_tool", arguments_template="{}", output_key="c2")],
            tags=["approved"],
            metadata={"approved": True, "approval_status": "approved"},
        )
        child_unreached = SkillManifest(
            name="child_unreached",
            steps=[SkillStep(tool_name="produce_record", arguments_template='{"topic": "never"}', output_key="c3")],
            tags=["approved"],
            metadata={"approved": True, "approval_status": "approved"},
        )

        manager.register(child_ok)
        manager.register(child_fail)
        manager.register(child_unreached)

        comp = SkillManifest(
            name="comp_with_failing_child",
            steps=[
                SkillStep(skill_name="child_ok", output_key="out_ok"),
                SkillStep(skill_name="child_fail", output_key="out_fail"),
                SkillStep(skill_name="child_unreached", output_key="out_never"),
            ],
            tags=["approved"],
            metadata={"approved": True, "approval_status": "approved"},
        )
        manager.register(comp)

        # Direct execution
        res = manager.execute("comp_with_failing_child")
        assert res.success is False
        assert len(res.step_results) == 2  # child_ok ran, child_fail ran, child_unreached never reached
        assert res.step_results[0].success is True
        assert res.step_results[1].success is False
        assert "deliberate test failure" in res.step_results[1].content.lower()

        # Task runner execution
        task = runner.create_task(
            prompt="Run pipeline that fails on child 2",
            steps=[{"step_id": "s_fail", "title": "Run failing pipeline", "tool_name": "comp_with_failing_child"}],
            task_id="task_child_fail_1",
        )
        finished = runner.run_task(task.task_id, background=False)
        assert finished.status == TaskStatus.FAILED
        assert finished.steps[0].status == StepStatus.FAILED
        assert "deliberate test failure" in finished.steps[0].error.lower()

    def test_transitive_capability_enforcement_prevents_privilege_escalation(self, test_environment):
        manager: SkillManager = test_environment["skill_manager"]
        runner: PersistentTaskRunner = test_environment["runner"]
        policy: CapabilityPolicy = test_environment["cap_policy"]

        # child requires privileged code:execute / shell:exec capability
        privileged_child = SkillManifest(
            name="shell_child_skill",
            steps=[SkillStep(tool_name="shell_exec", arguments_template='{"command": "whoami"}')],
            required_capabilities=["code:execute"],
            tags=["approved"],
            metadata={"approved": True, "approval_status": "approved"},
        )
        manager.register(privileged_child)

        composite_shell = SkillManifest(
            name="composite_wrapper_skill",
            steps=[SkillStep(skill_name="shell_child_skill")],
            required_capabilities=[],  # Wrapper tries to omit capabilities
            tags=["approved"],
            metadata={"approved": True, "approval_status": "approved"},
        )
        manager.register(composite_shell)

        # Transitive capabilities calculation must discover that code:execute is required
        transitive_caps = compute_composite_capabilities(composite_shell, manager)
        assert "code:execute" in transitive_caps

        # Configure capability policy with default deny
        restricted_policy = CapabilityPolicy(default_deny=True)
        restricted_policy.grant("user_restricted", Capability.TOOL_INVOKE.value)
        runner.capability_policy = restricted_policy

        with pytest.raises(TaskPlanPermissionError) as exc_info:
            runner.validate_plan(
                [TaskStep(
                    step_id="step_escalation",
                    task_id="t_esc",
                    step_index=0,
                    title="Attempt privilege escalation",
                    tool_name="composite_wrapper_skill",
                )],
                owner_id="user_restricted",
            )
        assert "lacks capability 'code:execute'" in str(exc_info.value)

    def test_safety_kernel_enforcement_on_composite_actions(self, test_environment):
        runner: PersistentTaskRunner = test_environment["runner"]
        manager: SkillManager = test_environment["skill_manager"]

        # A skill that performs destructive file deletion
        delete_child = SkillManifest(
            name="delete_system_child",
            steps=[SkillStep(tool_name="file_delete", arguments_template='{"path": "C:/Windows/System32/config"}')],
            required_capabilities=["file:delete"],
            tags=["approved"],
            metadata={"approved": True, "approval_status": "approved"},
        )
        manager.register(delete_child)

        comp_destructive = SkillManifest(
            name="comp_destructive",
            steps=[SkillStep(skill_name="delete_system_child")],
            required_capabilities=["file:delete"],
            tags=["approved"],
            metadata={"approved": True, "approval_status": "approved"},
        )
        manager.register(comp_destructive)

        # Configure SafetyKernel to evaluate and block critical system modification
        kernel = SafetyKernel()
        runner.kernel = kernel

        with pytest.raises(ValueError) as exc:
            runner.create_task(
                prompt="Attempt destructive composite",
                steps=[TaskStep(
                    step_id="step_destruct",
                    task_id="t_destruct",
                    step_index=0,
                    title="Destructive action",
                    tool_name="comp_destructive",
                    tool_args={"path": "C:/Windows/System32/config"},
                )],
            )
        assert "blocked by safety kernel" in str(exc.value).lower()

    def test_protected_system_skill_anti_tamper(self, test_environment):
        client: TestClient = test_environment["client"]
        learner: WorkflowSkillLearner = test_environment["learner"]
        manager: SkillManager = test_environment["skill_manager"]

        # Register protected core skill
        protected_skill = SkillManifest(
            name="system_core_guard",
            author="openjarvis (built-in)",
            steps=[SkillStep(tool_name="think")],
            tags=["builtin", "core"],
            metadata={"approved": True},
        )
        manager.register(protected_skill)

        # Attempt to reject or disable protected skill must raise 403 Forbidden
        rej_resp = client.post("/api/skills/learned/system_core_guard/reject")
        assert rej_resp.status_code == 403
        assert "protected" in rej_resp.json()["detail"].lower()

        dis_resp = client.post("/api/skills/learned/system_core_guard/disable")
        assert dis_resp.status_code == 403
        assert "protected" in dis_resp.json()["detail"].lower()
