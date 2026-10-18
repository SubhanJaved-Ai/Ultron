"""Comprehensive test suite for Ultron Skill Composition.

Verifies:
- Valid composition and data passing between steps and child skills
- Parameter flow and template placeholder resolution
- Circular dependency detection (direct and indirect)
- Maximum composition depth limit enforcement
- Missing, unapproved, rejected, and disabled child skill gating
- Transitive capability union calculation and permission enforcement
- Failure propagation without false success reporting
- Protected core/system skill integrity
- Task DAG and PersistentTaskRunner integration
- API endpoints for composite skill creation and pre-flight validation
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import pytest

from openjarvis.core.types import ToolCall, ToolResult
from openjarvis.security.capabilities import (
    Capability,
    CapabilityPolicy,
)

from openjarvis.skills.composition import (
    CircularCompositionError,
    CompositionValidationError,
    DepthExceededError,
    DisabledSkillError,
    MissingDependencyError,
    ParameterFlowError,
    UnapprovedSkillError,
    compute_composite_capabilities,
    create_composite_manifest,
    is_skill_approved_and_active,
    validate_composite_skill,
    validate_parameter_flow,
)
from openjarvis.skills.executor import SkillExecutor, SkillResult
from openjarvis.skills.learning import SkillApprovalStatus, WorkflowSkillLearner
from openjarvis.skills.manager import SkillManager
from openjarvis.skills.types import SkillManifest, SkillStep
from openjarvis.tasks.runner import PersistentTaskRunner, TaskPlanPermissionError
from openjarvis.tasks.types import TaskRecord, TaskStep, TaskStatus, StepStatus
from openjarvis.tools._stubs import ToolExecutor


# ---------------------------------------------------------------------------
# Test Helpers & Fixtures
# ---------------------------------------------------------------------------

class MockToolExecutor(ToolExecutor):
    """Configurable mock tool executor for deterministic tests."""

    def __init__(self, responses: Optional[Dict[str, Any]] = None, fail_tools: Optional[List[str]] = None) -> None:
        self.responses = responses or {}
        self.fail_tools = set(fail_tools or [])
        self.calls: List[ToolCall] = []

    def execute(self, tool_call: ToolCall) -> ToolResult:
        self.calls.append(tool_call)
        if tool_call.name in self.fail_tools:
            return ToolResult(
                tool_name=tool_call.name,
                content=f"Tool '{tool_call.name}' failed deliberately.",
                success=False,
            )

        resp = self.responses.get(tool_call.name, f"Result of {tool_call.name}")
        return ToolResult(
            tool_name=tool_call.name,
            content=resp,
            success=True,
        )


def _make_approved_skill(
    name: str,
    steps: List[SkillStep],
    caps: Optional[List[str]] = None,
    author: str = "operator",
) -> SkillManifest:
    return SkillManifest(
        name=name,
        version="0.1.0",
        description=f"Approved skill {name}",
        author=author,
        steps=steps,
        required_capabilities=list(caps or []),
        tags=["approved"],
        metadata={"approved": True, "approval_status": "approved"},
        user_invocable=True,
        disable_model_invocation=False,
    )


def _make_unapproved_skill(
    name: str,
    steps: List[SkillStep],
    status: str = "pending_review",
) -> SkillManifest:
    return SkillManifest(
        name=name,
        version="0.1.0",
        description=f"Unapproved skill {name}",
        author="openjarvis (experience-learning)",
        steps=steps,
        required_capabilities=[],
        tags=["learned", status],
        metadata={"approved": False, "approval_status": status},
        user_invocable=False,
        disable_model_invocation=True,
    )


def _make_disabled_skill(name: str, steps: List[SkillStep]) -> SkillManifest:
    return SkillManifest(
        name=name,
        version="0.1.0",
        description=f"Disabled skill {name}",
        author="operator",
        steps=steps,
        required_capabilities=[],
        tags=["approved"],
        metadata={
            "approved": True,
            "approval_status": "approved",
            "disabled": True,
            "disabled_reason": "Maintenance required",
        },
        user_invocable=False,
        disable_model_invocation=True,
    )


def _make_task_step(
    step_id: str,
    tool_name: str,
    tool_args: Optional[Dict[str, Any]] = None,
    deps: Optional[List[str]] = None,
) -> TaskStep:
    return TaskStep(
        step_id=step_id,
        task_id="task-test-1",
        step_index=0,
        title=f"Step {step_id}",
        tool_name=tool_name,
        tool_args=tool_args or {},
        dependencies=list(deps or []),
    )



# ---------------------------------------------------------------------------
# 1. Validation & Pre-Flight Checks
# ---------------------------------------------------------------------------

class TestSkillCompositionValidation:
    """Tests static validation of composite skills."""

    def test_valid_composite_skill_passes(self):
        manager = SkillManager()
        # Register child skills
        child_a = _make_approved_skill(
            "fetch-data",
            [SkillStep(tool_name="http_request", arguments_template='{"url": "{url}"}', output_key="raw_data")],
            caps=["network:fetch"],
        )
        child_b = _make_approved_skill(
            "format-data",
            [SkillStep(tool_name="think", arguments_template='{"thought": "Formatting: {raw_data}"}', output_key="formatted")],
            caps=[],
        )
        manager.register(child_a)
        manager.register(child_b)

        # Composite skill
        comp_steps = [
            SkillStep(skill_name="fetch-data", arguments_template='{"url": "{target_url}"}', output_key="data"),
            SkillStep(skill_name="format-data", arguments_template='{"raw_data": "{data}"}', output_key="result"),
        ]
        composite = create_composite_manifest(
            "etl-pipeline",
            comp_steps,
            skill_manager=manager,
            require_approval=False,
        )

        deps = validate_composite_skill(composite, manager)
        assert "fetch-data" in deps
        assert "format-data" in deps
        assert "network:fetch" in composite.required_capabilities

    def test_direct_circular_dependency_detected(self):
        manager = SkillManager()
        # Self-recursive skill
        steps = [SkillStep(skill_name="recurse-self")]
        manifest = _make_approved_skill("recurse-self", steps)
        manager.register(manifest)

        with pytest.raises(CircularCompositionError) as exc_info:
            validate_composite_skill(manifest, manager)
        assert "Circular dependency detected" in str(exc_info.value)
        assert "recurse-self" in str(exc_info.value)

    def test_multi_hop_circular_dependency_detected(self):
        manager = SkillManager()
        # A -> B -> C -> A
        step_a = [SkillStep(skill_name="skill-b")]
        step_b = [SkillStep(skill_name="skill-c")]
        step_c = [SkillStep(skill_name="skill-a")]

        skill_a = _make_approved_skill("skill-a", step_a)
        skill_b = _make_approved_skill("skill-b", step_b)
        skill_c = _make_approved_skill("skill-c", step_c)

        manager.register(skill_a)
        manager.register(skill_b)
        manager.register(skill_c)

        with pytest.raises(CircularCompositionError) as exc_info:
            validate_composite_skill(skill_a, manager)
        assert "Circular dependency detected" in str(exc_info.value)

    def test_depth_limit_exceeded_raises_error(self):
        manager = SkillManager()
        # Chain depth 6 with max_depth=5
        for i in range(1, 7):
            next_step = [SkillStep(skill_name=f"level-{i+1}")] if i < 6 else [SkillStep(tool_name="think")]
            manager.register(_make_approved_skill(f"level-{i}", next_step))

        root = manager.resolve("level-1")
        with pytest.raises(DepthExceededError) as exc_info:
            validate_composite_skill(root, manager, max_depth=5)
        assert "Composition depth limit (5) exceeded" in str(exc_info.value)

    def test_missing_child_skill_raises_error(self):
        manager = SkillManager()
        comp = _make_approved_skill("orphan-parent", [SkillStep(skill_name="does-not-exist")])

        with pytest.raises(MissingDependencyError) as exc_info:
            validate_composite_skill(comp, manager)
        assert "does-not-exist" in str(exc_info.value)

    def test_unapproved_child_skill_blocks_composition(self):
        manager = SkillManager()
        unapproved = _make_unapproved_skill("draft-child", [SkillStep(tool_name="think")])
        manager.register(unapproved)

        comp = _make_approved_skill("comp-with-unapproved", [SkillStep(skill_name="draft-child")])
        with pytest.raises(UnapprovedSkillError) as exc_info:
            validate_composite_skill(comp, manager)
        assert "is not approved" in str(exc_info.value)

    def test_rejected_child_skill_blocks_composition(self):
        manager = SkillManager()
        rejected = _make_unapproved_skill("bad-child", [SkillStep(tool_name="think")], status="rejected")
        manager.register(rejected)

        comp = _make_approved_skill("comp-with-rejected", [SkillStep(skill_name="bad-child")])
        with pytest.raises(UnapprovedSkillError) as exc_info:
            validate_composite_skill(comp, manager)
        assert "is not approved" in str(exc_info.value)

    def test_disabled_child_skill_blocks_composition(self):
        manager = SkillManager()
        disabled = _make_disabled_skill("inactive-child", [SkillStep(tool_name="think")])
        manager.register(disabled)

        comp = _make_approved_skill("comp-with-disabled", [SkillStep(skill_name="inactive-child")])
        with pytest.raises(DisabledSkillError) as exc_info:
            validate_composite_skill(comp, manager)
        assert "disabled" in str(exc_info.value).lower()

    def test_protected_system_skill_integrity(self):
        # Protected skills are inherently approved and cannot be bypassed
        system_skill = SkillManifest(
            name="system-diagnostics",
            author="system",
            steps=[SkillStep(tool_name="think")],
            tags=["builtin", "system", "core"],
        )
        is_ok, reason = is_skill_approved_and_active(system_skill)
        assert is_ok is True
        assert "core" in reason.lower() or "system" in reason.lower()


# ---------------------------------------------------------------------------
# 2. Execution & Data Passing
# ---------------------------------------------------------------------------

class TestSkillCompositionExecution:
    """Tests runtime execution of composite skills."""

    def test_data_propagation_between_sub_skills(self):
        mock_tools = MockToolExecutor({
            "step_one_tool": "RAW_PAYLOAD",
            "step_two_tool": "ENRICHED_RAW_PAYLOAD",
        })
        manager = SkillManager(tool_executor=mock_tools)

        # Child 1: runs step_one_tool -> outputs 'raw'
        child_1 = _make_approved_skill(
            "ingest",
            [SkillStep(tool_name="step_one_tool", arguments_template='{"src": "{source}"}', output_key="raw")],
        )
        # Child 2: consumes 'raw' -> runs step_two_tool -> outputs 'enriched'
        child_2 = _make_approved_skill(
            "transform",
            [SkillStep(tool_name="step_two_tool", arguments_template='{"data": "{raw}"}', output_key="enriched")],
        )
        manager.register(child_1)
        manager.register(child_2)

        # Composite skill: ingest -> transform
        comp_steps = [
            SkillStep(skill_name="ingest", arguments_template='{"source": "{input_src}"}', output_key="step1_out"),
            SkillStep(skill_name="transform", arguments_template='{"raw": "{step1_out}"}', output_key="step2_out"),
        ]
        composite = _make_approved_skill("full-etl", comp_steps)
        manager.register(composite)

        result = manager.execute("full-etl", context={"input_src": "sensor_feed_alpha"})

        assert result.success is True
        assert len(result.step_results) == 2
        assert result.context["step1_out"] == "RAW_PAYLOAD"
        assert result.context["step2_out"] == "ENRICHED_RAW_PAYLOAD"

    def test_child_failure_stops_pipeline_without_false_success(self):
        mock_tools = MockToolExecutor(fail_tools=["fail_tool"])
        manager = SkillManager(tool_executor=mock_tools)

        child_fail = _make_approved_skill(
            "failing-child",
            [SkillStep(tool_name="fail_tool", arguments_template="{}")],
        )
        child_never_reached = _make_approved_skill(
            "never-reached",
            [SkillStep(tool_name="think", arguments_template="{}")],
        )
        manager.register(child_fail)
        manager.register(child_never_reached)

        comp = _make_approved_skill(
            "pipeline-with-failure",
            [
                SkillStep(skill_name="failing-child", output_key="c1"),
                SkillStep(skill_name="never-reached", output_key="c2"),
            ],
        )
        manager.register(comp)

        result = manager.execute("pipeline-with-failure")
        assert result.success is False
        assert len(result.step_results) == 1  # Never executed second step
        assert "failed" in result.step_results[0].content.lower()

    def test_unapproved_child_blocks_execution(self):
        mock_tools = MockToolExecutor()
        manager = SkillManager(tool_executor=mock_tools)

        unapproved = _make_unapproved_skill("draft-sub", [SkillStep(tool_name="think")])
        manager.register(unapproved)

        comp = _make_approved_skill("caller", [SkillStep(skill_name="draft-sub")])
        manager.register(comp)

        result = manager.execute("caller")
        assert result.success is False
        assert "not approved" in result.step_results[0].content

    def test_disabled_child_blocks_execution(self):
        mock_tools = MockToolExecutor()
        manager = SkillManager(tool_executor=mock_tools)

        disabled = _make_disabled_skill("off-sub", [SkillStep(tool_name="think")])
        manager.register(disabled)

        comp = _make_approved_skill("caller-disabled", [SkillStep(skill_name="off-sub")])
        manager.register(comp)

        result = manager.execute("caller-disabled")
        assert result.success is False
        assert "disabled" in result.step_results[0].content.lower()

    def test_runtime_cycle_detection(self):
        mock_tools = MockToolExecutor()
        manager = SkillManager(tool_executor=mock_tools)

        # Directly registering a cyclic pair into the executor
        step_a = [SkillStep(skill_name="cycle-b")]
        step_b = [SkillStep(skill_name="cycle-a")]
        manager.register(_make_approved_skill("cycle-a", step_a))
        manager.register(_make_approved_skill("cycle-b", step_b))

        result = manager.execute("cycle-a")
        assert result.success is False
        assert "circular dependency" in result.step_results[0].content.lower()

    def test_runtime_depth_limit_enforced(self):
        mock_tools = MockToolExecutor()
        manager = SkillManager(tool_executor=mock_tools)

        # Build recursive chain
        for i in range(1, 8):
            next_step = [SkillStep(skill_name=f"chain-{i+1}")] if i < 7 else [SkillStep(tool_name="think")]
            manager.register(_make_approved_skill(f"chain-{i}", next_step))

        result = manager.execute("chain-1", max_depth=5)
        assert result.success is False
        assert "depth limit" in result.step_results[0].content.lower()

    def test_capability_policy_enforcement_on_child_skills(self):
        mock_tools = MockToolExecutor()
        manager = SkillManager(tool_executor=mock_tools)

        child_net = _make_approved_skill(
            "child-net",
            [SkillStep(tool_name="http_request")],
            caps=["network:fetch"],
        )
        manager.register(child_net)

        comp = _make_approved_skill("comp-net", [SkillStep(skill_name="child-net")])
        manager.register(comp)

        # Execute with only file:read capability (missing network:fetch)
        result = manager.execute("comp-net", allowed_capabilities={"file:read"})
        assert result.success is False
        assert "requires capabilities ['network:fetch']" in result.step_results[0].content


# ---------------------------------------------------------------------------
# 3. PersistentTaskRunner DAG & Plan Integration
# ---------------------------------------------------------------------------

class TestTaskRunnerSkillComposition:
    """Tests PersistentTaskRunner static plan validation and execution with composite skills."""

    def test_runner_validates_plan_with_approved_composite_skill(self):
        manager = SkillManager()
        child = _make_approved_skill("approved-step", [SkillStep(tool_name="think")])
        manager.register(child)

        comp = _make_approved_skill(
            "valid-composite",
            [SkillStep(skill_name="approved-step")],
            caps=[Capability.TOOL_INVOKE.value],
        )
        manager.register(comp)

        runner = PersistentTaskRunner(skill_manager=manager)
        steps = [
            _make_task_step(step_id="s1", tool_name="valid-composite"),
        ]
        # Should not raise
        runner.validate_plan(steps)

    def test_runner_rejects_plan_if_composite_child_unapproved(self):
        manager = SkillManager()
        unapproved_child = _make_unapproved_skill("draft-inner", [SkillStep(tool_name="think")])
        manager.register(unapproved_child)

        comp = _make_approved_skill(
            "flawed-composite",
            [SkillStep(skill_name="draft-inner")],
        )
        manager.register(comp)

        runner = PersistentTaskRunner(skill_manager=manager)
        steps = [_make_task_step(step_id="s1", tool_name="flawed-composite")]

        with pytest.raises(TaskPlanPermissionError) as exc_info:
            runner.validate_plan(steps)
        assert "is not approved" in str(exc_info.value)

    def test_runner_rejects_plan_if_composite_has_cycle(self):
        manager = SkillManager()
        manager.register(_make_approved_skill("cyclic-x", [SkillStep(skill_name="cyclic-y")]))
        manager.register(_make_approved_skill("cyclic-y", [SkillStep(skill_name="cyclic-x")]))

        runner = PersistentTaskRunner(skill_manager=manager)
        steps = [_make_task_step(step_id="s1", tool_name="cyclic-x")]

        with pytest.raises(TaskPlanPermissionError) as exc_info:
            runner.validate_plan(steps)
        assert "circular dependency" in str(exc_info.value).lower()

    def test_runner_rejects_plan_if_transitive_capability_missing(self):
        manager = SkillManager()
        child = _make_approved_skill(
            "priv-child",
            [SkillStep(tool_name="shell_exec")],
            caps=["shell:exec"],
        )
        manager.register(child)

        comp = _make_approved_skill(
            "priv-composite",
            [SkillStep(skill_name="priv-child")],
            caps=["shell:exec"],
        )
        manager.register(comp)

        # Policy grants only tool:invoke to user_alice, NOT shell:exec
        policy = CapabilityPolicy(default_deny=True)
        policy.grant("user_alice", Capability.TOOL_INVOKE.value)

        runner = PersistentTaskRunner(skill_manager=manager, capability_policy=policy)

        steps = [_make_task_step(step_id="s1", tool_name="priv-composite")]

        with pytest.raises(TaskPlanPermissionError) as exc_info:
            runner.validate_plan(steps, owner_id="user_alice")
        assert "lacks capability" in str(exc_info.value)
        assert "code:execute" in str(exc_info.value) or "shell:exec" in str(exc_info.value)




# ---------------------------------------------------------------------------
# 4. Learning & Storage Lifecycle
# ---------------------------------------------------------------------------

class TestWorkflowSkillLearnerComposition:
    """Tests WorkflowSkillLearner composition authoring, ledger auditing, and health checks."""

    def test_compose_skills_persists_and_audits(self, tmp_path):
        manager = SkillManager()
        learner = WorkflowSkillLearner(skill_manager=manager, skills_dir=tmp_path)

        # Register child skills
        c1 = _make_approved_skill("step-alpha", [SkillStep(tool_name="think")])
        c2 = _make_approved_skill("step-beta", [SkillStep(tool_name="think")])
        manager.register(c1)
        manager.register(c2)

        # Compose into a new skill
        composite = learner.compose_skills(
            name="composite-flow",
            steps=[
                SkillStep(skill_name="step-alpha", output_key="out_a"),
                SkillStep(skill_name="step-beta", output_key="out_b"),
            ],
            description="A test composite workflow",
            require_approval=True,
        )

        assert composite.name == "composite-flow"
        assert composite.metadata["composite"] is True
        assert composite.metadata["approval_status"] == SkillApprovalStatus.PENDING_REVIEW
        assert not composite.user_invocable  # Pending review

        # Check ledger record
        history = learner.ledger.get_history("composite-flow")
        assert len(history) >= 1
        assert history[-1].skill_name == "composite-flow"

        # Approval lifecycle
        approved_manifest = learner.approve_skill("composite-flow")
        assert approved_manifest.metadata["approval_status"] == SkillApprovalStatus.APPROVED
        assert approved_manifest.user_invocable is True

    def test_composite_health_reports_disabled_child(self, tmp_path):
        manager = SkillManager()
        learner = WorkflowSkillLearner(skill_manager=manager, skills_dir=tmp_path)

        active = _make_approved_skill("active-child", [SkillStep(tool_name="think")])
        disabled = _make_disabled_skill("disabled-child", [SkillStep(tool_name="think")])
        manager.register(active)
        manager.register(disabled)

        comp = _make_approved_skill(
            "parent-comp",
            [
                SkillStep(skill_name="active-child"),
                SkillStep(skill_name="disabled-child"),
            ],
        )

        is_healthy, issues = learner.validate_skill_health(comp)
        assert is_healthy is False
        assert any("disabled" in issue.lower() for issue in issues)


# ---------------------------------------------------------------------------
# 5. API Endpoints
# ---------------------------------------------------------------------------

class TestSkillCompositionAPI:
    """Tests API routes for composite skills."""

    def test_composite_validation_endpoint(self, tmp_path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from openjarvis.server.memory_skills_routes import memory_skills_router

        app = FastAPI()
        app.include_router(memory_skills_router)

        manager = SkillManager()
        c1 = _make_approved_skill("child-one", [SkillStep(tool_name="think")])
        manager.register(c1)
        learner = WorkflowSkillLearner(skill_manager=manager, skills_dir=tmp_path)
        app.state.workflow_skill_learner = learner

        client = TestClient(app)

        # 1. Valid composition validation request
        payload = {
            "name": "api-composite",
            "description": "Validation test",
            "steps": [
                {
                    "tool_name": "",
                    "skill_name": "child-one",
                    "arguments_template": "{}",
                    "output_key": "step1",
                }
            ],
            "require_approval": True,
        }
        resp = client.post("/api/skills/composite/validate", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert "child-one" in data["dependencies"]

        # 2. Invalid composition (cycle) validation request
        invalid_payload = {
            "name": "cycle-comp",
            "description": "Cycle test",
            "steps": [
                {
                    "tool_name": "",
                    "skill_name": "cycle-comp",
                    "arguments_template": "{}",
                    "output_key": "self",
                }
            ],
            "require_approval": True,
        }
        resp_invalid = client.post(
            "/api/skills/composite/validate", json=invalid_payload
        )
        assert resp_invalid.status_code == 200
        data_inv = resp_invalid.json()
        assert data_inv["valid"] is False
        assert any("circular" in e.lower() for e in data_inv["errors"])

    def test_composite_creation_endpoint(self, tmp_path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from openjarvis.server.memory_skills_routes import memory_skills_router

        app = FastAPI()
        app.include_router(memory_skills_router)

        manager = SkillManager()
        c1 = _make_approved_skill("worker-step", [SkillStep(tool_name="think")])
        manager.register(c1)
        learner = WorkflowSkillLearner(skill_manager=manager, skills_dir=tmp_path)
        app.state.workflow_skill_learner = learner

        client = TestClient(app)

        payload = {
            "name": "created-workflow",
            "description": "Composite created via API",
            "steps": [
                {
                    "tool_name": "",
                    "skill_name": "worker-step",
                    "arguments_template": "{}",
                    "output_key": "out",
                }
            ],
            "require_approval": True,
        }
        resp = client.post("/api/skills/composite", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "created"
        assert data["skill"]["name"] == "created-workflow"
        assert data["skill"]["is_composite"] is True
        assert data["skill"]["approval_status"] == SkillApprovalStatus.PENDING_REVIEW

