"""End-to-end Integration Tests for Persistent Memory & Experience Learning in Task Runner."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from openjarvis.core.events import EventBus
from openjarvis.memory.store import LocalFactStore
from openjarvis.security.capabilities import Capability, CapabilityPolicy
from openjarvis.security.kernel import SafetyKernel
from openjarvis.skills.manager import SkillManager
from openjarvis.tasks.runner import PersistentTaskRunner
from openjarvis.tasks.store import TaskStore
from openjarvis.tasks.types import StepStatus, TaskRecord, TaskStatus, TaskStep


@pytest.fixture
def integrated_runner(tmp_path: Path):
    store = TaskStore(db_path=tmp_path / "tasks.db")
    bus = EventBus()
    kernel = SafetyKernel()
    policy = CapabilityPolicy(default_deny=True)
    # Grant default agent basic capabilities
    policy.grant("_default", Capability.FILE_WRITE.value, "*")
    policy.grant("_default", Capability.FILE_READ.value, "*")
    policy.grant("_default", Capability.TOOL_INVOKE.value, "*")

    mem_store = LocalFactStore(path=tmp_path / "memory_facts.jsonl")
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    skill_manager = SkillManager(bus=bus, overlay_dir=tmp_path / "overlays")

    runner = PersistentTaskRunner(
        store=store,
        bus=bus,
        kernel=kernel,
        capability_policy=policy,
        memory_store=mem_store,
        skill_manager=skill_manager,
    )
    return runner, mem_store, skill_manager, tmp_path


def test_task_completion_triggers_memory_and_skill_learning(integrated_runner):
    runner, mem_store, sm, tmp_path = integrated_runner
    out_file = tmp_path / "output.txt"

    # Step 1: Write file
    s1 = {
        "step_id": "s1",
        "title": "Write report file",
        "tool_name": "file_write",
        "tool_args": {"path": str(out_file), "content": "Report data v1"},
        "dependencies": [],
        "expected_output": "",
    }
    # Step 2: Read file
    s2 = {
        "step_id": "s2",
        "title": "Verify report file",
        "tool_name": "file_read",
        "tool_args": {"path": str(out_file)},
        "dependencies": ["s1"],
        "expected_output": "Report data v1",
    }

    task = runner.create_task(
        prompt="Generate and verify report file",
        steps=[s1, s2],
        metadata={"project": "reporting-service", "owner_id": "_default"},
    )

    # Run synchronously
    completed_task = runner.run_task(task.task_id, background=False)
    assert completed_task.status == TaskStatus.COMPLETED

    # 1. Verify Persistent Memory Extraction
    wf_memories = mem_store.query(category="successful_workflows", project="reporting-service")
    assert len(wf_memories) == 1
    assert "Generate and verify report file" in wf_memories[0].text
    assert wf_memories[0].verified is True

    ctx_memories = mem_store.query(category="project_context", project="reporting-service")
    assert len(ctx_memories) >= 1
    assert "output.txt" in ctx_memories[0].text

    # 2. Verify Reusable Skill Extraction
    learned_names = [n for n in sm.skill_names() if n.startswith("learned-")]
    assert len(learned_names) == 1
    learned_skill_name = learned_names[0]
    manifest = sm.resolve(learned_skill_name)
    assert len(manifest.steps) == 2
    assert manifest.metadata.get("verified") is True


def test_subsequent_planning_retrieves_memory_context(integrated_runner):
    runner, mem_store, sm, tmp_path = integrated_runner

    # Seed preference and failure lesson
    mem_store.add(
        "Always use UTF-8 encoding for text output",
        category="user_preferences",
        project="reporting-service",
        verified=True,
    )
    mem_store.add(
        "Do not write directly to root directory without permissions",
        category="recurring_failure_lessons",
        project="reporting-service",
        verified=True,
    )

    # Create new task
    task2 = runner.create_task(
        prompt="Generate monthly audit summary",
        metadata={"project": "reporting-service", "owner_id": "_default"},
    )

    # Check that retrieved memories are attached to metadata
    retrieved = task2.metadata.get("retrieved_memories", "")
    assert "User Preferences:" in retrieved
    assert "UTF-8 encoding" in retrieved
    assert "Failure Lessons & Known Pitfalls" in retrieved
    assert "root directory" in retrieved


def test_learned_skill_respects_security_and_capability_policy(integrated_runner):
    runner, mem_store, sm, tmp_path = integrated_runner

    # Create a learned skill that requires admin capabilities
    from openjarvis.skills.types import SkillManifest, SkillStep

    test_skill = SkillManifest(
        name="learned-admin-action",
        description="Admin action",
        steps=[SkillStep(tool_name="delete_file")],
        required_capabilities=["system:admin"],
        metadata={"approval_status": "pending_review", "approved": False},
    )
    sm._skills["learned-admin-action"] = test_skill

    # Attempt to plan a task invoking this learned skill before approval
    step = {
        "step_id": "step_skill",
        "title": "Invoke learned skill",
        "tool_name": "learned-admin-action",
        "tool_args": {},
        "dependencies": [],
    }

    # 1. Before approval: cannot execute unapproved learned skill
    with pytest.raises(PermissionError, match="not approved"):
        runner.create_task(
            prompt="Run admin action",
            steps=[step],
            metadata={"owner_id": "unauthorized_guest"},
        )

    # 2. After approval: still strictly subject to capability policy check
    test_skill.metadata["approved"] = True
    test_skill.metadata["approval_status"] = "approved"

    # Caller 'unauthorized_guest' does not have system:admin
    with pytest.raises(PermissionError, match="not authorized"):
        runner.create_task(
            prompt="Run admin action",
            steps=[step],
            metadata={"owner_id": "unauthorized_guest"},
        )

