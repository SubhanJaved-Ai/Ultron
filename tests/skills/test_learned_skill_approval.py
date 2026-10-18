"""Tests for Learned Skill Approval Lifecycle, Validation, Discovery, and Security Preservation."""

from __future__ import annotations

import time
from pathlib import Path
import pytest

from openjarvis.core.events import EventBus
from openjarvis.security.capabilities import Capability, CapabilityPolicy
from openjarvis.security.kernel import ActionEffect, SafetyKernel
from openjarvis.skills.ledger import SkillLedger
from openjarvis.skills.learning import SkillApprovalStatus, WorkflowSkillLearner
from openjarvis.skills.manager import SkillManager
from openjarvis.skills.types import SkillManifest, SkillStep
from openjarvis.tasks.intelligence import ToolExecutionIntelligence
from openjarvis.tasks.runner import PersistentTaskRunner, TaskPlanPermissionError
from openjarvis.tasks.store import TaskStore
from openjarvis.tasks.types import StepStatus, TaskRecord, TaskStatus, TaskStep


@pytest.fixture
def skill_approval_env(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    bus = EventBus()
    kernel = SafetyKernel()
    policy = CapabilityPolicy(default_deny=True)
    # Grant admin full permissions
    policy.grant("admin_user", Capability.SYSTEM_ADMIN.value, "*")
    policy.grant("admin_user", Capability.FILE_WRITE.value, "*")
    policy.grant("admin_user", Capability.FILE_READ.value, "*")
    policy.grant("admin_user", Capability.TOOL_INVOKE.value, "*")

    # Standard agent has basic invoke and read
    policy.grant("standard_user", Capability.TOOL_INVOKE.value, "*")
    policy.grant("standard_user", Capability.FILE_READ.value, "*")

    sm = SkillManager(bus=bus, overlay_dir=tmp_path / "overlays")
    ledger = SkillLedger(skills_dir=skills_dir)
    learner = WorkflowSkillLearner(skill_manager=sm, skills_dir=skills_dir, ledger=ledger)

    store = TaskStore(db_path=tmp_path / "tasks.db")
    runner = PersistentTaskRunner(
        store=store,
        bus=bus,
        kernel=kernel,
        capability_policy=policy,
        skill_manager=sm,
    )
    runner.workflow_skill_learner = learner

    return sm, ledger, learner, runner, policy, kernel, tmp_path


class TestLearnedSkillApproval:
    """Verify approval state machine, discovery isolation, validation, and security preservation."""

    def test_newly_learned_skill_starts_in_pending_review(self, skill_approval_env):
        sm, ledger, learner, runner, policy, kernel, tmp_path = skill_approval_env

        s1 = TaskStep(
            step_id="s1",
            task_id="t_flow",
            step_index=0,
            title="Read source",
            tool_name="file_read",
            tool_args={"path": "src.txt"},
            status=StepStatus.COMPLETED,
            actual_output="data",
        )
        s2 = TaskStep(
            step_id="s2",
            task_id="t_flow",
            step_index=1,
            title="Write target",
            tool_name="file_write",
            tool_args={"path": "target.txt", "content": "data"},
            dependencies=["s1"],
            status=StepStatus.COMPLETED,
            actual_output="written",
        )
        task = TaskRecord(
            task_id="t_flow",
            prompt="Copy source to target",
            status=TaskStatus.COMPLETED,
            steps=[s1, s2],
            created_at=time.time(),
            updated_at=time.time(),
        )

        manifest = learner.learn_skill_from_task(task)
        assert manifest is not None

        # Must default to pending_review
        assert manifest.metadata.get("approval_status") == SkillApprovalStatus.PENDING_REVIEW
        assert manifest.metadata.get("approved") is False
        assert manifest.user_invocable is False
        assert manifest.disable_model_invocation is True
        assert SkillApprovalStatus.PENDING_REVIEW in manifest.tags

        # Must record create in ledger
        assert len(ledger.get_history()) >= 1

    def test_unapproved_skill_hidden_from_normal_tool_discovery(self, skill_approval_env):
        sm, ledger, learner, runner, policy, kernel, tmp_path = skill_approval_env

        unapproved_skill = SkillManifest(
            name="learned-unapproved-workflow",
            description="Should remain hidden",
            steps=[SkillStep(tool_name="file_read")],
            metadata={"approval_status": SkillApprovalStatus.PENDING_REVIEW, "approved": False},
            tags=["learned", SkillApprovalStatus.PENDING_REVIEW],
        )
        sm._skills["learned-unapproved-workflow"] = unapproved_skill

        intel = ToolExecutionIntelligence(runner=runner, capability_policy=policy)
        tools = intel.discover_tools(owner_id="admin_user")

        # Unapproved skill must NOT be discovered!
        assert "learned-unapproved-workflow" not in tools
        catalog = intel.build_tool_catalog(owner_id="admin_user")
        assert "learned-unapproved-workflow" not in catalog

    def test_unapproved_skill_cannot_execute_in_runner_or_plan(self, skill_approval_env):
        sm, ledger, learner, runner, policy, kernel, tmp_path = skill_approval_env

        unapproved_skill = SkillManifest(
            name="learned-draft-skill",
            description="Draft",
            steps=[SkillStep(tool_name="file_read")],
            metadata={"approval_status": SkillApprovalStatus.PENDING_REVIEW, "approved": False},
        )
        sm._skills["learned-draft-skill"] = unapproved_skill

        # 1. Direct handler execution refused
        canonical, handler, schema = runner.resolve_tool_handler("learned-draft-skill")
        assert handler is not None
        result = handler(path="test.txt")
        assert result.success is False
        assert "Refusing to execute unapproved learned skill" in result.content

        # 2. Planning validation rejected
        step = {
            "step_id": "s_draft",
            "title": "Call draft skill",
            "tool_name": "learned-draft-skill",
            "tool_args": {},
            "dependencies": [],
        }
        with pytest.raises(TaskPlanPermissionError, match="not approved"):
            runner.create_task(
                prompt="Run draft skill",
                steps=[step],
                metadata={"owner_id": "admin_user"},
            )

    def test_validate_skill_for_approval_catches_errors(self, skill_approval_env):
        sm, ledger, learner, runner, policy, kernel, tmp_path = skill_approval_env

        # 1. Unknown tool
        bad_tool_skill = SkillManifest(
            name="learned-bad-tool",
            steps=[SkillStep(tool_name="totally_nonexistent_tool_xyz")],
        )
        valid, errors = learner.validate_skill_for_approval(bad_tool_skill)
        assert valid is False
        assert any("unknown or unregistered tool" in e for e in errors)

        # 2. Malformed arguments JSON
        bad_json_skill = SkillManifest(
            name="learned-bad-json",
            steps=[SkillStep(tool_name="file_read", arguments_template="{bad_json: missing_quotes}")],
        )
        valid, errors = learner.validate_skill_for_approval(bad_json_skill)
        assert valid is False
        assert any("invalid JSON" in e for e in errors)

        # 3. Missing forward reference in dependency template
        bad_dep_skill = SkillManifest(
            name="learned-bad-dep",
            steps=[
                SkillStep(tool_name="file_read", arguments_template='{"path": "{{s2_missing_output}}"}'),
            ],
        )
        valid, errors = learner.validate_skill_for_approval(bad_dep_skill)
        assert valid is False
        assert any("references output key 's2_missing_output' before it is produced" in e for e in errors)

        # 4. Under-declared capabilities
        under_declared = SkillManifest(
            name="learned-under-declared",
            steps=[SkillStep(tool_name="file_write", arguments_template='{"path": "x.txt", "content": "1"}')],
            required_capabilities=[],  # Omitted file:write!
        )
        valid, errors = learner.validate_skill_for_approval(under_declared)
        assert valid is False
        assert any("missing from required_capabilities" in e for e in errors)

    def test_approve_skill_lifecycle(self, skill_approval_env):
        sm, ledger, learner, runner, policy, kernel, tmp_path = skill_approval_env

        # Create valid pending skill
        pending_skill = SkillManifest(
            name="learned-valid-pipeline",
            description="Valid pipeline",
            steps=[
                SkillStep(
                    tool_name="file_read",
                    arguments_template='{"path": "input.txt"}',
                    output_key="read_out",
                ),
                SkillStep(
                    tool_name="file_write",
                    arguments_template='{"path": "output.txt", "content": "{{read_out}}"}',
                    output_key="write_out",
                ),
            ],
            required_capabilities=["file:read", "file:write"],
            metadata={"approval_status": SkillApprovalStatus.PENDING_REVIEW, "approved": False},
            tags=["learned", SkillApprovalStatus.PENDING_REVIEW],
        )
        sm._skills["learned-valid-pipeline"] = pending_skill

        # Approver without config:write is denied
        with pytest.raises(PermissionError, match="lacks capability"):
            learner.approve_skill(
                "learned-valid-pipeline",
                approver_id="standard_user",
                capability_policy=policy,
            )

        # Admin with config:write approves skill
        approved_manifest = learner.approve_skill(
            "learned-valid-pipeline",
            approver_id="admin_user",
            capability_policy=policy,
        )

        assert approved_manifest.metadata["approved"] is True
        assert approved_manifest.metadata["approval_status"] == SkillApprovalStatus.APPROVED
        assert approved_manifest.metadata["approved_by"] == "admin_user"
        assert approved_manifest.user_invocable is True
        assert approved_manifest.disable_model_invocation is False
        assert SkillApprovalStatus.APPROVED in approved_manifest.tags

        # Audit ledger recorded 'approve'
        ledger_entries = [e for e in ledger.get_history() if e.action == "approve"]
        assert len(ledger_entries) >= 1
        assert ledger_entries[0].skill_name == "learned-valid-pipeline"

        # Now discoverable in tools
        intel = ToolExecutionIntelligence(runner=runner, capability_policy=policy)
        tools = intel.discover_tools(owner_id="admin_user")
        assert "learned-valid-pipeline" in tools

    def test_approved_skill_still_enforces_capability_policy(self, skill_approval_env):
        sm, ledger, learner, runner, policy, kernel, tmp_path = skill_approval_env

        # An approved skill requires file:write
        approved_skill = SkillManifest(
            name="learned-write-tool",
            description="Writes file",
            steps=[SkillStep(tool_name="file_write", arguments_template='{"path": "f.txt", "content": "c"}')],
            required_capabilities=["file:write"],
            metadata={"approval_status": SkillApprovalStatus.APPROVED, "approved": True},
            tags=["learned", SkillApprovalStatus.APPROVED],
        )
        sm._skills["learned-write-tool"] = approved_skill

        step = {
            "step_id": "s1",
            "title": "Call approved skill",
            "tool_name": "learned-write-tool",
            "tool_args": {},
            "dependencies": [],
        }

        # User 'standard_user' does NOT have file:write capability.
        # Approving the skill must NEVER grant standard_user permission to execute file:write!
        with pytest.raises(PermissionError, match="not authorized"):
            runner.create_task(
                prompt="Invoke write skill",
                steps=[step],
                metadata={"owner_id": "standard_user"},
            )

        # Admin user HAS file:write -> succeeds validation
        task = runner.create_task(
            prompt="Invoke write skill as admin",
            steps=[step],
            metadata={"owner_id": "admin_user"},
        )
        assert task.status == TaskStatus.QUEUED

    def test_approved_skill_still_enforces_safety_kernel(self, skill_approval_env):
        sm, ledger, learner, runner, policy, kernel, tmp_path = skill_approval_env

        # Skill targeting a system protected directory blocked by Safety Kernel
        approved_skill = SkillManifest(
            name="learned-dangerous-skill",
            description="Tries to touch protected path",
            steps=[SkillStep(tool_name="file_write", arguments_template='{"path": "/etc/passwd", "content": "hacked"}')],
            required_capabilities=["file:write"],
            metadata={"approval_status": SkillApprovalStatus.APPROVED, "approved": True},
            tags=["learned", SkillApprovalStatus.APPROVED],
        )
        sm._skills["learned-dangerous-skill"] = approved_skill

        step = {
            "step_id": "s_danger",
            "title": "Call dangerous skill",
            "tool_name": "learned-dangerous-skill",
            "tool_args": {"path": "/etc/passwd", "content": "hacked"},
            "dependencies": [],
        }

        # Even with admin capabilities, SafetyKernel blocks root / system targets
        with pytest.raises(ValueError, match="Safety Kernel"):
            runner.create_task(
                prompt="Modify /etc/passwd",
                steps=[step],
                metadata={"owner_id": "admin_user"},
            )

    def test_reject_skill_lifecycle(self, skill_approval_env):
        sm, ledger, learner, runner, policy, kernel, tmp_path = skill_approval_env

        skill = SkillManifest(
            name="learned-rejected-skill",
            steps=[SkillStep(tool_name="file_read")],
            metadata={"approval_status": SkillApprovalStatus.PENDING_REVIEW, "approved": False},
        )
        sm._skills["learned-rejected-skill"] = skill

        rejected = learner.reject_skill("learned-rejected-skill", reviewer_id="admin_user", reason="Security review failed")
        assert rejected.metadata["approval_status"] == SkillApprovalStatus.REJECTED
        assert rejected.metadata["approved"] is False
        assert rejected.metadata["rejection_reason"] == "Security review failed"

        ledger_records = [r for r in ledger.get_history() if r.action == "reject"]
        assert len(ledger_records) >= 1

    def test_tamper_protection_blocks_mutating_system_skills(self, skill_approval_env):
        sm, ledger, learner, runner, policy, kernel, tmp_path = skill_approval_env

        system_skill = SkillManifest(
            name="system-core-ops",
            author="system",
            tags=["system", "trusted"],
            steps=[SkillStep(tool_name="file_read")],
        )
        sm._skills["system-core-ops"] = system_skill

        # Cannot approve or reject system skills
        with pytest.raises(PermissionError, match="Security Violation"):
            learner.approve_skill("system-core-ops", approver_id="admin_user")

        with pytest.raises(PermissionError, match="Security Violation"):
            learner.reject_skill("system-core-ops", reviewer_id="admin_user")
