"""Tests for Reusable Skill learning, duplicate prevention, tamper protection, and health lifecycle."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from openjarvis.core.events import EventBus
from openjarvis.skills.ledger import SkillLedger
from openjarvis.skills.learning import WorkflowSkillLearner
from openjarvis.skills.manager import SkillManager
from openjarvis.skills.types import SkillManifest, SkillStep
from openjarvis.tasks.types import StepStatus, TaskRecord, TaskStatus, TaskStep


@pytest.fixture
def skills_env(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    bus = EventBus()
    sm = SkillManager(bus=bus, overlay_dir=tmp_path / "overlays")
    ledger = SkillLedger(skills_dir=skills_dir)
    learner = WorkflowSkillLearner(skill_manager=sm, skills_dir=skills_dir, ledger=ledger)
    return sm, ledger, learner, skills_dir


def test_learn_skill_from_verified_task(skills_env):
    sm, ledger, learner, skills_dir = skills_env

    s1 = TaskStep(
        step_id="step_read",
        task_id="task_pipeline_1",
        step_index=0,
        title="Read package.json",
        tool_name="file_read",
        tool_args={"path": "package.json"},
        status=StepStatus.COMPLETED,
        actual_output='{"name": "test"}',
    )
    s2 = TaskStep(
        step_id="step_write",
        task_id="task_pipeline_1",
        step_index=1,
        title="Write version info",
        tool_name="file_write",
        tool_args={"path": "version.txt", "content": "1.0.0"},
        dependencies=["step_read"],
        status=StepStatus.COMPLETED,
        actual_output="version.txt created",
    )

    task = TaskRecord(
        task_id="task_pipeline_1",
        prompt="Sync version from package.json to version.txt",
        status=TaskStatus.COMPLETED,
        steps=[s1, s2],
        created_at=time.time(),
        updated_at=time.time(),
    )

    manifest = learner.learn_skill_from_task(task)
    assert manifest is not None
    assert manifest.name.startswith("learned-")
    assert len(manifest.steps) == 2
    assert manifest.steps[0].tool_name == "file_read"
    assert manifest.steps[1].tool_name == "file_write"

    # Verify registered in SkillManager
    assert manifest.name in sm.skill_names()

    # Verify persisted to disk
    skill_file = skills_dir / manifest.name / "skill.toml"
    assert skill_file.exists()

    # Verify recorded in SkillLedger
    records = ledger.get_history()
    assert len(records) >= 1
    assert records[0].skill_name == manifest.name
    assert records[0].action == "create"


def test_duplicate_prevention_via_fingerprint(skills_env):
    sm, ledger, learner, skills_dir = skills_env

    # Run first task
    s1 = TaskStep(
        step_id="s1",
        task_id="t1",
        step_index=0,
        title="Read input",
        tool_name="file_read",
        tool_args={"path": "input.txt"},
        status=StepStatus.COMPLETED,
        actual_output="data",
    )
    s2 = TaskStep(
        step_id="s2",
        task_id="t1",
        step_index=1,
        title="Write output",
        tool_name="file_write",
        tool_args={"path": "output.txt", "content": "data"},
        dependencies=["s1"],
        status=StepStatus.COMPLETED,
        actual_output="written",
    )
    task1 = TaskRecord(
        task_id="t1",
        prompt="Copy file from input to output",
        status=TaskStatus.COMPLETED,
        steps=[s1, s2],
        created_at=time.time(),
        updated_at=time.time(),
    )

    m1 = learner.learn_skill_from_task(task1)
    assert m1 is not None
    initial_count = m1.metadata.get("execution_count", 1)

    # Run second task with identical structure and tools but different files
    s1_b = TaskStep(
        step_id="s1_b",
        task_id="t2",
        step_index=0,
        title="Read input B",
        tool_name="file_read",
        tool_args={"path": "other.txt"},
        status=StepStatus.COMPLETED,
        actual_output="other",
    )
    s2_b = TaskStep(
        step_id="s2_b",
        task_id="t2",
        step_index=1,
        title="Write output B",
        tool_name="file_write",
        tool_args={"path": "other_out.txt", "content": "other"},
        dependencies=["s1_b"],
        status=StepStatus.COMPLETED,
        actual_output="written",
    )
    task2 = TaskRecord(
        task_id="t2",
        prompt="Copy other file",
        status=TaskStatus.COMPLETED,
        steps=[s1_b, s2_b],
        created_at=time.time(),
        updated_at=time.time(),
    )

    m2 = learner.learn_skill_from_task(task2)
    assert m2 is not None
    # Must NOT create a duplicate skill! Must resolve to the same skill
    assert m2.name == m1.name
    assert m2.metadata.get("execution_count") == initial_count + 1
    assert len(sm.skill_names()) == 1


def test_tamper_protection_guards_system_skills(skills_env):
    sm, ledger, learner, skills_dir = skills_env

    # Seed a protected system skill into SkillManager
    protected_manifest = SkillManifest(
        name="core-system-tool",
        version="1.0.0",
        description="Protected core system skill",
        author="system",
        tags=["system", "trusted"],
        steps=[SkillStep(tool_name="file_read")],
    )
    sm._skills["core-system-tool"] = protected_manifest

    # An untrusted task tries to learn or overwrite "core-system-tool"
    s1 = TaskStep(
        step_id="s1",
        task_id="malicious_task",
        step_index=0,
        title="Inject backdoor",
        tool_name="file_write",
        tool_args={"path": "/etc/shadow", "content": "bad"},
        status=StepStatus.COMPLETED,
        actual_output="ok",
    )
    s2 = TaskStep(
        step_id="s2",
        task_id="malicious_task",
        step_index=1,
        title="Cleanup",
        tool_name="file_read",
        tool_args={"path": "/etc/shadow"},
        dependencies=["s1"],
        status=StepStatus.COMPLETED,
        actual_output="ok",
    )
    task = TaskRecord(
        task_id="malicious_task",
        prompt="Update core-system-tool",
        status=TaskStatus.COMPLETED,
        steps=[s1, s2],
        created_at=time.time(),
        updated_at=time.time(),
    )

    with pytest.raises(PermissionError, match="Security Violation"):
        learner.learn_skill_from_task(task, skill_name="core-system-tool")


def test_health_validation_and_outdated_detection(skills_env):
    sm, ledger, learner, skills_dir = skills_env

    manifest = SkillManifest(
        name="test-health-skill",
        version="0.1.0",
        description="A skill using file_read and shell_exec",
        steps=[
            SkillStep(tool_name="file_read"),
            SkillStep(tool_name="custom_unregistered_tool"),
        ],
    )
    sm._skills["test-health-skill"] = manifest

    # Validate against registered tools: custom_unregistered_tool is missing
    is_healthy, issues = learner.validate_skill_health(
        manifest,
        registered_tools=["file_read", "file_write"],
    )
    assert is_healthy is False
    assert any("custom_unregistered_tool" in iss for iss in issues)

    # Now test repeated execution failure threshold
    learner.mark_skill_execution_result("test-health-skill", success=False, error_reason="Timeout")
    assert manifest.metadata.get("consecutive_failures") == 1
    assert manifest.metadata.get("outdated") is not True

    learner.mark_skill_execution_result("test-health-skill", success=False, error_reason="Timeout")
    assert manifest.metadata.get("consecutive_failures") == 2

    learner.mark_skill_execution_result("test-health-skill", success=False, error_reason="Fatal crash")
    assert manifest.metadata.get("consecutive_failures") == 3
    assert manifest.metadata.get("outdated") is True

    # Validate health now flags the outdated status
    is_healthy_now, issues_now = learner.validate_skill_health(manifest)
    assert is_healthy_now is False
    assert any("outdated" in iss.lower() for iss in issues_now)
