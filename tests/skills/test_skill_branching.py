"""Comprehensive tests for Ultron Skill Composition Conditional Branching.

Verifies:
- Safe condition parser and evaluator (AST-based, no eval/exec)
- Operator support (==, !=, <, <=, >, >=, in, not in, is, is not, contains, and, or, not)
- Branch reachability and sequence validation (if / else sequencing, no duplicate else)
- Selected branch execution; skipped steps must NOT run or be reported as completed work
- Inline else alternative execution (else_skill_name / else_tool_name)
- Missing variable and runtime evaluation failure handling
- Child failure propagation without false success reporting
- Transitive capability calculation across all branches
- Unapproved, disabled, and missing child skill gating in both branches
- Circular dependency and depth limit detection through else branches
- Task plan validation with branching composite skills
- API endpoints for conditional composite validation and creation
"""

import ast
from pathlib import Path
from typing import Any, Dict, List, Optional
import pytest

from openjarvis.core.types import ToolCall, ToolResult
from openjarvis.security.capabilities import (
    AgentPolicy,
    Capability,
    CapabilityGrant,
    CapabilityPolicy,
)
from openjarvis.skills.composition import (
    CircularCompositionError,
    CompositionValidationError,
    ConditionEvaluationError,
    ConditionValidationError,
    DepthExceededError,
    DisabledSkillError,
    MissingDependencyError,
    UnapprovedSkillError,
    compute_composite_capabilities,
    create_composite_manifest,
    evaluate_condition,
    extract_condition_variables,
    normalize_condition_expression,
    validate_composite_skill,
    validate_condition,
)
from openjarvis.skills.executor import SkillExecutor, SkillResult
from openjarvis.skills.learning import SkillApprovalStatus, WorkflowSkillLearner
from openjarvis.skills.manager import SkillManager
from openjarvis.skills.types import SkillManifest, SkillStep
from openjarvis.tasks.runner import PersistentTaskRunner, TaskPlanPermissionError
from openjarvis.tasks.types import TaskRecord, TaskStep, TaskStatus, StepStatus
from openjarvis.tools._stubs import ToolExecutor


# ---------------------------------------------------------------------------
# Test Fixtures & Helpers
# ---------------------------------------------------------------------------

class BranchingMockToolExecutor(ToolExecutor):
    """Mock tool executor that tracks all calls and produces predictable outputs."""

    def __init__(
        self,
        responses: Optional[Dict[str, Any]] = None,
        fail_tools: Optional[List[str]] = None,
    ) -> None:
        self.responses = responses or {}
        self.fail_tools = set(fail_tools or [])
        self.executed_tools: List[str] = []
        self.calls: List[ToolCall] = []

    def execute(self, tool_call: ToolCall) -> ToolResult:
        self.calls.append(tool_call)
        self.executed_tools.append(tool_call.name)
        if tool_call.name in self.fail_tools:
            return ToolResult(
                tool_name=tool_call.name,
                content=f"Tool '{tool_call.name}' failed intentionally.",
                success=False,
            )

        resp = self.responses.get(tool_call.name, f"result_of_{tool_call.name}")
        return ToolResult(
            tool_name=tool_call.name,
            content=resp,
            success=True,
        )


def _make_skill(
    name: str,
    steps: List[SkillStep],
    *,
    caps: Optional[List[str]] = None,
    approved: bool = True,
    disabled: bool = False,
    author: str = "operator",
) -> SkillManifest:
    status = "approved" if approved else "pending_review"
    tags = ["approved"] if approved else ["pending_review"]
    meta = {
        "approved": approved,
        "approval_status": status,
        "disabled": disabled,
    }
    return SkillManifest(
        name=name,
        version="0.1.0",
        description=f"Skill {name}",
        author=author,
        steps=steps,
        required_capabilities=list(caps or []),
        tags=tags,
        metadata=meta,
        user_invocable=approved,
        disable_model_invocation=not approved,
    )


# ===========================================================================
# 1. Safe Condition Parser & Evaluator Tests
# ===========================================================================

class TestConditionParserAndEvaluator:
    """Tests for normalize_condition_expression, extract_condition_variables,
    validate_condition, and evaluate_condition."""

    def test_normalize_expression_placeholders_and_aliases(self):
        assert normalize_condition_expression("{status} == 'ok'") == "status == 'ok'"
        assert normalize_condition_expression("{score} >= 80") == "score >= 80"
        assert normalize_condition_expression("{tags} contains 'urgent'") == "'urgent' in tags"
        assert normalize_condition_expression("true") == "True"
        assert normalize_condition_expression("false") == "False"
        assert normalize_condition_expression("null") == "None"
        assert normalize_condition_expression("else") == "else"

    def test_extract_variables(self):
        vars_found = extract_condition_variables("{status} == 'ok' and {count} > 5")
        assert vars_found == {"status", "count"}

        # Without braces
        vars_found2 = extract_condition_variables("score < 50 or is_flagged == True")
        assert vars_found2 == {"score", "is_flagged"}

        # 'else' has no variables
        assert extract_condition_variables("else") == set()

    def test_validate_condition_supported_constructs(self):
        valid_conditions = [
            "{status} == 'success'",
            "{status} != 'error'",
            "{score} > 80",
            "{score} <= 50",
            "{tags} contains 'critical'",
            "'urgent' in {tags}",
            "{category} in ['bug', 'incident']",
            "not {is_disabled}",
            "{count} > 0 and {retries} < 3",
            "{status} == 'ok' or {force} == True",
            "{item} is None",
            "{item} is not None",
            "True",
        ]
        for cond in valid_conditions:
            is_valid, errors = validate_condition(cond)
            assert is_valid is True, f"Condition failed validation: {cond}, errors: {errors}"
            assert len(errors) == 0

    def test_validate_condition_rejects_disallowed_and_dangerous_constructs(self):
        disallowed = [
            "__import__('os').system('calc')",
            "eval('1 + 1')",
            "obj.__class__.__mro__",
            "[x for x in items]",
            "(lambda x: x > 0)(1)",
            "{'key': 'value'}",
            "foo.bar()",
        ]
        for bad in disallowed:
            is_valid, errors = validate_condition(bad)
            assert is_valid is False, f"Expected disallowed construct to fail: {bad}"
            assert len(errors) > 0

    def test_validate_condition_rejects_unsupported_operators(self):
        unsupported = [
            "a & b",  # bitwise AND
            "a | b",  # bitwise OR
            "a ^ b",  # bitwise XOR
            "a << 2",  # bitwise shift
        ]
        for unsupp in unsupported:
            is_valid, errors = validate_condition(unsupp)
            assert is_valid is False
            assert any("disallowed" in e.lower() or "unsupported" in e.lower() for e in errors)

    def test_validate_condition_detects_static_false(self):
        is_valid, errors = validate_condition("False")
        assert is_valid is False
        assert any("unreachable" in e.lower() for e in errors)

    def test_validate_condition_missing_available_variables(self):
        is_valid, errors = validate_condition(
            "{missing_var} == 'ok'",
            available_vars={"known_var_1", "known_var_2"},
        )
        assert is_valid is False
        assert any("unavailable output" in e.lower() for e in errors)

    def test_evaluate_condition_success_cases(self):
        ctx = {
            "status": "success",
            "count": 10,
            "tags": ["prod", "urgent"],
            "is_flagged": True,
            "empty_val": None,
        }
        assert evaluate_condition("{status} == 'success'", ctx) is True
        assert evaluate_condition("{status} != 'failed'", ctx) is True
        assert evaluate_condition("{count} > 5", ctx) is True
        assert evaluate_condition("{count} <= 10", ctx) is True
        assert evaluate_condition("{tags} contains 'urgent'", ctx) is True
        assert evaluate_condition("'prod' in {tags}", ctx) is True
        assert evaluate_condition("{is_flagged} == True", ctx) is True
        assert evaluate_condition("not {empty_val}", ctx) is True
        assert evaluate_condition("{status} == 'success' and {count} >= 10", ctx) is True
        assert evaluate_condition("{status} == 'failed' or {count} == 10", ctx) is True

    def test_evaluate_condition_numeric_and_bool_coercion(self):
        # Tool outputs are often strings, e.g. "42" or "true"
        ctx = {"str_num": "42", "str_bool": "true"}
        assert evaluate_condition("{str_num} > 10", ctx) is True
        assert evaluate_condition("{str_num} == 42", ctx) is True
        assert evaluate_condition("{str_bool} == True", ctx) is True

    def test_evaluate_condition_missing_variable_raises(self):
        ctx = {"status": "success"}
        with pytest.raises(ConditionEvaluationError) as exc_info:
            evaluate_condition("{unregistered_var} == 'ok'", ctx)
        assert "Variable 'unregistered_var' not found in context" in str(exc_info.value)


# ===========================================================================
# 2. Composition Validation & Branch Structure Tests
# ===========================================================================

class TestConditionalBranchingValidation:
    """Tests for branch reachability, dependency checking, and composition validation."""

    def test_first_step_cannot_be_else(self):
        manifest = SkillManifest(
            name="invalid_first_else",
            steps=[
                SkillStep(tool_name="echo", is_else=True),
            ],
        )
        mgr = SkillManager()
        with pytest.raises(ConditionValidationError) as exc:
            validate_composite_skill(manifest, mgr)
        assert "first step cannot be an else branch" in str(exc.value).lower()

    def test_else_must_follow_conditional_step(self):
        manifest = SkillManifest(
            name="invalid_else_seq",
            steps=[
                SkillStep(tool_name="echo"),  # unconditional step
                SkillStep(tool_name="echo2", is_else=True),
            ],
        )
        mgr = SkillManager()
        with pytest.raises(ConditionValidationError) as exc:
            validate_composite_skill(manifest, mgr)
        assert "has no condition" in str(exc.value).lower()

    def test_consecutive_else_steps_rejected(self):
        manifest = SkillManifest(
            name="duplicate_else",
            steps=[
                SkillStep(tool_name="echo", condition="{flag} == True"),
                SkillStep(tool_name="echo_else1", is_else=True),
                SkillStep(tool_name="echo_else2", is_else=True),
            ],
        )
        mgr = SkillManager()
        with pytest.raises(ConditionValidationError) as exc:
            validate_composite_skill(manifest, mgr)
        assert "ambiguous duplicate 'else'" in str(exc.value).lower()

    def test_else_after_inline_else_rejected(self):
        manifest = SkillManifest(
            name="ambiguous_else",
            steps=[
                SkillStep(
                    tool_name="echo_if",
                    condition="{flag} == True",
                    else_tool_name="echo_inline_else",
                ),
                SkillStep(tool_name="echo_step_else", is_else=True),
            ],
        )
        mgr = SkillManager()
        with pytest.raises(ConditionValidationError) as exc:
            validate_composite_skill(manifest, mgr)
        assert "already defined an inline else" in str(exc.value).lower()

    def test_inline_else_without_condition_rejected(self):
        manifest = SkillManifest(
            name="inline_else_no_cond",
            steps=[
                SkillStep(tool_name="echo", else_tool_name="echo_else"),
            ],
        )
        mgr = SkillManager()
        with pytest.raises(ConditionValidationError) as exc:
            validate_composite_skill(manifest, mgr)
        assert "without specifying a condition" in str(exc.value).lower()

    def test_unapproved_child_in_else_branch_blocks_composition(self):
        mgr = SkillManager()
        app_child = _make_skill("app_child", [SkillStep(tool_name="echo")], approved=True)
        unapp_child = _make_skill("unapp_child", [SkillStep(tool_name="echo")], approved=False)
        mgr.register(app_child)
        mgr.register(unapp_child)

        manifest = SkillManifest(
            name="composite_with_unapproved_else",
            steps=[
                SkillStep(
                    skill_name="app_child",
                    condition="{score} > 50",
                    else_skill_name="unapp_child",
                )
            ],
        )
        with pytest.raises(UnapprovedSkillError) as exc:
            validate_composite_skill(manifest, mgr)
        assert "unapproved_child" in str(exc.value).lower() or "unapp_child" in str(exc.value).lower()

    def test_disabled_child_in_else_branch_blocks_composition(self):
        mgr = SkillManager()
        app_child = _make_skill("app_child", [SkillStep(tool_name="echo")], approved=True)
        dis_child = _make_skill("dis_child", [SkillStep(tool_name="echo")], approved=True, disabled=True)
        mgr.register(app_child)
        mgr.register(dis_child)

        manifest = SkillManifest(
            name="composite_with_disabled_else",
            steps=[
                SkillStep(
                    skill_name="app_child",
                    condition="{score} > 50",
                    else_skill_name="dis_child",
                )
            ],
        )
        with pytest.raises(DisabledSkillError) as exc:
            validate_composite_skill(manifest, mgr)
        assert "dis_child" in str(exc.value).lower()

    def test_circular_dependency_in_else_branch_detected(self):
        mgr = SkillManager()
        manifest = SkillManifest(
            name="cyclic_composite",
            steps=[
                SkillStep(
                    tool_name="echo",
                    condition="{score} > 50",
                    else_skill_name="cyclic_composite",
                )
            ],
        )
        mgr.register(manifest)
        with pytest.raises(CircularCompositionError) as exc:
            validate_composite_skill(manifest, mgr)
        assert "circular dependency" in str(exc.value).lower()

    def test_transitive_capabilities_union_includes_both_branches(self):
        mgr = SkillManager()
        skill_if = _make_skill("skill_if", [SkillStep(tool_name="echo")], caps=["network:fetch"])
        skill_else = _make_skill("skill_else", [SkillStep(tool_name="echo")], caps=["filesystem:write"])
        mgr.register(skill_if)
        mgr.register(skill_else)

        manifest = create_composite_manifest(
            name="branch_composite",
            steps=[
                {
                    "skill_name": "skill_if",
                    "condition": "{status} == 'ok'",
                    "else_skill_name": "skill_else",
                }
            ],
            skill_manager=mgr,
            require_approval=False,
        )

        assert "network:fetch" in manifest.required_capabilities
        assert "filesystem:write" in manifest.required_capabilities
        assert set(manifest.depends) == {"skill_else", "skill_if"}


# ===========================================================================
# 3. Execution & Skipped Step Isolation Tests
# ===========================================================================

class TestConditionalBranchingExecution:
    """Tests for runtime step execution, skipped step isolation, and failure handling."""

    def test_sequential_if_branch_taken_and_else_step_skipped(self):
        mock_exec = BranchingMockToolExecutor(
            responses={"check_tool": "pass", "if_tool": "if_done", "else_tool": "else_done"}
        )
        executor = SkillExecutor(mock_exec)

        manifest = SkillManifest(
            name="test_workflow",
            steps=[
                SkillStep(tool_name="check_tool", output_key="result"),
                SkillStep(
                    tool_name="if_tool",
                    condition="{result} == 'pass'",
                    output_key="if_out",
                ),
                SkillStep(
                    tool_name="else_tool",
                    is_else=True,
                    output_key="else_out",
                ),
            ],
        )

        res = executor.run(manifest)
        assert res.success is True
        # Executed tools should be check_tool and if_tool only
        assert mock_exec.executed_tools == ["check_tool", "if_tool"]
        # Step results must ONLY contain results for executed steps (Requirement 3)
        assert len(res.step_results) == 2
        assert res.step_results[0].tool_name == "check_tool"
        assert res.step_results[1].tool_name == "if_tool"
        # Context must contain if_out, but NOT else_out
        assert res.context.get("if_out") == "if_done"
        assert "else_out" not in res.context

    def test_sequential_else_branch_taken_and_if_step_skipped(self):
        mock_exec = BranchingMockToolExecutor(
            responses={"check_tool": "fail", "if_tool": "if_done", "else_tool": "else_done"}
        )
        executor = SkillExecutor(mock_exec)

        manifest = SkillManifest(
            name="test_workflow",
            steps=[
                SkillStep(tool_name="check_tool", output_key="result"),
                SkillStep(
                    tool_name="if_tool",
                    condition="{result} == 'pass'",
                    output_key="if_out",
                ),
                SkillStep(
                    tool_name="else_tool",
                    is_else=True,
                    output_key="else_out",
                ),
            ],
        )

        res = executor.run(manifest)
        assert res.success is True
        # Executed tools should be check_tool and else_tool only
        assert mock_exec.executed_tools == ["check_tool", "else_tool"]
        # Step results must ONLY contain results for executed steps (Requirement 3)
        assert len(res.step_results) == 2
        assert res.step_results[0].tool_name == "check_tool"
        assert res.step_results[1].tool_name == "else_tool"
        # Context must contain else_out, but NOT if_out
        assert res.context.get("else_out") == "else_done"
        assert "if_out" not in res.context

    def test_inline_else_branch_execution(self):
        mock_exec = BranchingMockToolExecutor(
            responses={"tool_primary": "primary_ok", "tool_alternative": "alt_ok"}
        )
        executor = SkillExecutor(mock_exec)

        manifest = SkillManifest(
            name="inline_branch_workflow",
            steps=[
                SkillStep(
                    tool_name="tool_primary",
                    condition="{score} > 80",
                    output_key="branch_out",
                    else_tool_name="tool_alternative",
                )
            ],
        )

        # Case 1: score <= 80 -> executes tool_alternative
        res1 = executor.run(manifest, initial_context={"score": 50})
        assert res1.success is True
        assert mock_exec.executed_tools == ["tool_alternative"]
        assert res1.context.get("branch_out") == "alt_ok"

        # Case 2: score > 80 -> executes tool_primary
        mock_exec.executed_tools.clear()
        res2 = executor.run(manifest, initial_context={"score": 95})
        assert res2.success is True
        assert mock_exec.executed_tools == ["tool_primary"]
        assert res2.context.get("branch_out") == "primary_ok"

    def test_missing_variable_at_runtime_fails_cleanly(self):
        mock_exec = BranchingMockToolExecutor()
        executor = SkillExecutor(mock_exec)

        manifest = SkillManifest(
            name="missing_var_workflow",
            steps=[
                SkillStep(
                    tool_name="tool_a",
                    condition="{missing_key} == 'test'",
                )
            ],
        )

        res = executor.run(manifest, initial_context={})
        assert res.success is False
        assert len(res.step_results) == 1
        assert "Condition evaluation error in step 1" in res.step_results[0].content
        assert "missing_key" in res.step_results[0].content

    def test_child_failure_in_branch_propagates_without_false_success(self):
        mock_exec = BranchingMockToolExecutor(fail_tools=["failing_branch_tool"])
        executor = SkillExecutor(mock_exec)

        manifest = SkillManifest(
            name="failure_propagation_workflow",
            steps=[
                SkillStep(
                    tool_name="failing_branch_tool",
                    condition="{execute} == True",
                ),
                SkillStep(tool_name="never_reached_tool"),
            ],
        )

        res = executor.run(manifest, initial_context={"execute": True})
        assert res.success is False
        assert mock_exec.executed_tools == ["failing_branch_tool"]
        assert "never_reached_tool" not in mock_exec.executed_tools

    def test_sub_skill_branching_with_resolver(self):
        mgr = SkillManager()
        mock_exec = BranchingMockToolExecutor(
            responses={"success_tool": "success_msg", "fallback_tool": "fallback_msg"}
        )
        mgr.set_tool_executor(mock_exec)

        success_skill = _make_skill("success_skill", [SkillStep(tool_name="success_tool", output_key="res")])
        fallback_skill = _make_skill("fallback_skill", [SkillStep(tool_name="fallback_tool", output_key="res")])
        mgr.register(success_skill)
        mgr.register(fallback_skill)

        composite = create_composite_manifest(
            name="composite_subskills",
            steps=[
                {
                    "skill_name": "success_skill",
                    "condition": "{status} == 'ok'",
                    "else_skill_name": "fallback_skill",
                    "output_key": "final_out",
                }
            ],
            skill_manager=mgr,
            require_approval=False,
        )
        mgr.register(composite)

        # Run with status != 'ok' -> should invoke fallback_skill
        res = mgr.execute("composite_subskills", context={"status": "error"})
        assert res.success is True
        assert mock_exec.executed_tools == ["fallback_tool"]

        # Run with status == 'ok' -> should invoke success_skill
        mock_exec.executed_tools.clear()
        res2 = mgr.execute("composite_subskills", context={"status": "ok"})
        assert res2.success is True
        assert mock_exec.executed_tools == ["success_tool"]


# ===========================================================================
# 4. Task Runner & Policy Integration Tests
# ===========================================================================

class TestTaskRunnerBranchingIntegration:
    """Verifies that PersistentTaskRunner enforces approval, health, capability policy,
    and DAG validation when plans incorporate branching composite skills."""

    def test_task_runner_blocks_plan_if_branch_child_unapproved(self, tmp_path: Path):
        mock_exec = BranchingMockToolExecutor()
        mgr = SkillManager(tool_executor=mock_exec)

        app_child = _make_skill("app_child", [SkillStep(tool_name="echo")], approved=True)
        unapp_child = _make_skill("unapp_child", [SkillStep(tool_name="echo")], approved=False)
        mgr.register(app_child)
        mgr.register(unapp_child)

        learner = WorkflowSkillLearner(skill_manager=mgr, skills_dir=tmp_path / "skills")

        composite = SkillManifest(
            name="composite_branch",
            steps=[
                SkillStep(skill_name="app_child", condition="{flag} == True", else_skill_name="unapp_child")
            ],
            metadata={"approved": True, "approval_status": "approved"},
        )
        mgr.register(composite)

        runner = PersistentTaskRunner(
            skill_manager=mgr,
        )
        runner.workflow_skill_learner = learner

        plan_steps = [
            TaskStep(
                step_id="s1",
                task_id="t1",
                step_index=0,
                title="Branch Step",
                tool_name="composite_branch",
            )
        ]
        with pytest.raises(TaskPlanPermissionError) as exc:
            runner.validate_plan(plan_steps)
        assert "unapproved" in str(exc.value).lower()

    def test_task_runner_blocks_plan_if_transitive_capability_missing(self, tmp_path: Path):
        mock_exec = BranchingMockToolExecutor()
        mgr = SkillManager(tool_executor=mock_exec)

        skill_primary = _make_skill("skill_primary", [SkillStep(tool_name="echo")], caps=["filesystem:read"])
        skill_else = _make_skill("skill_else", [SkillStep(tool_name="echo")], caps=["shell:execute"])
        mgr.register(skill_primary)
        mgr.register(skill_else)

        composite = create_composite_manifest(
            name="composite_caps",
            steps=[
                {
                    "skill_name": "skill_primary",
                    "condition": "{flag} == True",
                    "else_skill_name": "skill_else",
                }
            ],
            skill_manager=mgr,
            require_approval=False,
        )
        mgr.register(composite)

        # Grant policy only for filesystem:read, NOT shell:execute
        policy_engine = CapabilityPolicy(default_deny=True)
        policy_engine.grant("alice", "filesystem:read")

        runner = PersistentTaskRunner(
            skill_manager=mgr,
            capability_policy=policy_engine,
        )

        plan_steps = [
            TaskStep(
                step_id="s1",
                task_id="t1",
                step_index=0,
                title="Execute Composite",
                tool_name="composite_caps",
            )
        ]

        with pytest.raises(TaskPlanPermissionError) as exc:
            runner.validate_plan(plan_steps, owner_id="alice")
        assert "shell:execute" in str(exc.value)

    def test_branching_nested_skill_approval_cannot_be_bypassed(self, tmp_path: Path):
        """Verifies that approval gating cannot be bypassed via nested skills or alternative branch paths."""
        mock_exec = BranchingMockToolExecutor()
        mgr = SkillManager(tool_executor=mock_exec)

        child_safe = _make_skill("child_safe", [SkillStep(tool_name="echo")], approved=True)
        child_unapproved = _make_skill("child_unapproved", [SkillStep(tool_name="echo")], approved=False)
        mgr.register(child_safe)
        mgr.register(child_unapproved)

        # Nested composite skill containing unapproved child in else branch
        nested_composite = SkillManifest(
            name="nested_composite",
            steps=[
                SkillStep(
                    skill_name="child_safe",
                    condition="{opt} == 'safe'",
                    else_skill_name="child_unapproved",
                )
            ],
            metadata={"approved": True, "approval_status": "approved"},
        )
        mgr.register(nested_composite)

        # Top-level composite pointing to nested_composite
        top_composite = SkillManifest(
            name="top_composite",
            steps=[
                SkillStep(skill_name="nested_composite")
            ],
            metadata={"approved": True, "approval_status": "approved"},
        )
        mgr.register(top_composite)

        learner = WorkflowSkillLearner(skill_manager=mgr, skills_dir=tmp_path / "skills")
        runner = PersistentTaskRunner(skill_manager=mgr)
        runner.workflow_skill_learner = learner

        plan_steps = [
            TaskStep(
                step_id="step_nested",
                task_id="task_nested",
                step_index=0,
                title="Execute Nested Composite",
                tool_name="top_composite",
            )
        ]
        with pytest.raises(TaskPlanPermissionError) as exc:
            runner.validate_plan(plan_steps)
        assert "unapproved" in str(exc.value).lower()


# ===========================================================================
# 5. FastAPI Route Endpoints Tests
# ===========================================================================

class TestSkillBranchingAPI:
    """Verifies the /api/skills/composite and /api/skills/composite/validate endpoints."""

    def test_validate_endpoint_with_valid_and_invalid_branches(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from openjarvis.server.memory_skills_routes import memory_skills_router

        app = FastAPI()
        app.include_router(memory_skills_router)

        mock_exec = BranchingMockToolExecutor()
        mgr = SkillManager(tool_executor=mock_exec)

        child_a = _make_skill("child_a", [SkillStep(tool_name="echo")], approved=True)
        child_b = _make_skill("child_b", [SkillStep(tool_name="echo")], approved=True)
        mgr.register(child_a)
        mgr.register(child_b)

        learner = WorkflowSkillLearner(skill_manager=mgr)
        app.state.workflow_skill_learner = learner
        app.state.multi_user = False

        client = TestClient(app)

        # 1. Valid branching workflow
        valid_payload = {
            "name": "api_branching_workflow",
            "description": "Workflow with conditional branching",
            "steps": [
                {
                    "skill_name": "child_a",
                    "output_key": "step1_out",
                },
                {
                    "skill_name": "child_b",
                    "condition": "{step1_out} == 'success'",
                    "output_key": "step2_out",
                },
                {
                    "skill_name": "child_a",
                    "is_else": True,
                    "output_key": "else_out",
                },
            ],
            "require_approval": True,
            "tags": ["workflow"],
        }
        res_valid = client.post("/api/skills/composite/validate", json=valid_payload)
        assert res_valid.status_code == 200
        val_data = res_valid.json()
        assert val_data["valid"] is True
        assert val_data["errors"] == []

        # 2. Invalid condition syntax
        invalid_payload = dict(valid_payload)
        invalid_payload["steps"] = [
            {
                "skill_name": "child_a",
                "condition": "status === 'invalid_syntax_in_python'",
            }
        ]
        res_invalid = client.post("/api/skills/composite/validate", json=invalid_payload)
        assert res_invalid.status_code == 200
        inval_data = res_invalid.json()
        assert inval_data["valid"] is False
        assert any("syntax error" in e.lower() for e in inval_data["errors"])

        # 3. Create composite skill with branching
        res_create = client.post("/api/skills/composite", json=valid_payload)
        assert res_create.status_code == 200
        created = res_create.json()["skill"]
        assert created["name"] == "api_branching_workflow"
        assert created["approval_status"] == "pending_review"
        assert len(created["steps"]) == 3
        assert created["steps"][1]["condition"] == "{step1_out} == 'success'"
        assert created["steps"][2]["is_else"] is True
