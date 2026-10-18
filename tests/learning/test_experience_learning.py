"""Tests for Experience Learning: verified vs unverified tasks, fact vs assumption, and failure lessons."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from openjarvis.learning.experience import ExperienceLearner
from openjarvis.memory.store import LocalFactStore
from openjarvis.tasks.types import StepStatus, TaskRecord, TaskStatus, TaskStep


@pytest.fixture
def temp_store(tmp_path: Path) -> LocalFactStore:
    jsonl_path = tmp_path / "memory_facts.jsonl"
    return LocalFactStore(path=jsonl_path)


def test_learn_from_verified_completed_task(temp_store: LocalFactStore):
    learner = ExperienceLearner(memory_store=temp_store)

    s1 = TaskStep(
        step_id="step_1",
        task_id="task_build_1",
        step_index=0,
        title="Analyze build config",
        tool_name="think",
        tool_args={"thought": "Assuming Vite configuration needs base URL set to /app"},
        status=StepStatus.COMPLETED,
        actual_output="Thinking finished",
    )
    s2 = TaskStep(
        step_id="step_2",
        task_id="task_build_1",
        step_index=1,
        title="Write configuration file",
        tool_name="file_write",
        tool_args={"path": "vite.config.ts", "content": "export default {}"},
        status=StepStatus.COMPLETED,
        actual_output="File written",
    )

    task = TaskRecord(
        task_id="task_build_1",
        prompt="Configure Vite build for production",
        status=TaskStatus.COMPLETED,
        steps=[s1, s2],
        created_at=time.time(),
        updated_at=time.time(),
        metadata={"project": "frontend-web"},
    )

    facts = learner.learn_from_task(task, project="frontend-web")
    assert len(facts) >= 2

    # 1. Verify successful workflow fact
    workflows = temp_store.query(category="successful_workflows", project="frontend-web")
    assert len(workflows) == 1
    wf = workflows[0]
    assert "Configure Vite build for production" in wf.text
    assert "file_write" in wf.text
    assert wf.verified is True

    # 2. Verify project context artifact
    ctx = temp_store.query(category="project_context", project="frontend-web")
    assert len(ctx) == 1
    assert "vite.config.ts" in ctx[0].text
    assert ctx[0].verified is True

    # 3. Verify thought is recorded as an assumption with verified=False
    general = temp_store.query(category="general", project="frontend-web")
    assert len(general) == 1
    thought_fact = general[0]
    assert "[Assumption]" in thought_fact.text
    assert "Vite configuration needs base URL" in thought_fact.text
    assert thought_fact.verified is False  # Must NOT be marked as verified fact


def test_refuse_unverified_task_claim(temp_store: LocalFactStore):
    """If a task claims to be COMPLETED but has uncompleted or failed steps, refuse to extract success."""
    learner = ExperienceLearner(memory_store=temp_store)

    s1 = TaskStep(
        step_id="step_1",
        task_id="task_fake_1",
        step_index=0,
        title="Execute critical step",
        tool_name="shell_exec",
        tool_args={"command": "npm run build"},
        status=StepStatus.FAILED,  # Step actually failed!
        error="Process returned exit code 1",
    )

    task = TaskRecord(
        task_id="task_fake_1",
        prompt="Deploy project",
        status=TaskStatus.COMPLETED,  # Model/agent claims task completed
        steps=[s1],
        created_at=time.time(),
        updated_at=time.time(),
        metadata={"project": "web-deploy"},
    )

    facts = learner.learn_from_task(task, project="web-deploy")
    assert len(facts) == 0

    workflows = temp_store.query(category="successful_workflows", project="web-deploy")
    assert len(workflows) == 0  # No bogus successful workflow stored!


def test_learn_from_failed_task(temp_store: LocalFactStore):
    learner = ExperienceLearner(memory_store=temp_store)

    s1 = TaskStep(
        step_id="step_db_1",
        task_id="task_migrate_1",
        step_index=0,
        title="Run database migrations",
        tool_name="shell_exec",
        tool_args={"command": "alembic upgrade head"},
        status=StepStatus.FAILED,
        error="Connection refused to db host:5432",
    )

    task = TaskRecord(
        task_id="task_migrate_1",
        prompt="Run db migrations on staging",
        status=TaskStatus.FAILED,
        steps=[s1],
        created_at=time.time(),
        updated_at=time.time(),
        metadata={"project": "backend-api"},
        error="Step 'Run database migrations' failed: Connection refused to db host:5432",
    )

    facts = learner.learn_from_task(task, project="backend-api")
    assert len(facts) == 1

    lessons = temp_store.query(category="recurring_failure_lessons", project="backend-api")
    assert len(lessons) == 1
    lesson = lessons[0]
    assert "Recurring Failure Warning" in lesson.text
    assert "Connection refused" in lesson.text
    assert "shell_exec" in lesson.text
    assert lesson.verified is True


def test_retrieve_planning_context(temp_store: LocalFactStore):
    learner = ExperienceLearner(memory_store=temp_store)

    temp_store.add(
        "User prefers functional programming style with immutable data",
        category="user_preferences",
        project="portal-app",
        verified=True,
    )
    temp_store.add(
        "Avoid using raw eval() in parser",
        category="recurring_failure_lessons",
        project="portal-app",
        verified=True,
    )
    temp_store.add(
        "Successful workflow for 'build parser': 1. file_write(path='parser.py')",
        category="successful_workflows",
        project="portal-app",
        verified=True,
    )

    context = learner.retrieve_planning_context(
        prompt="Build a new JSON parser module",
        project="portal-app",
    )

    markdown = context["markdown"]
    assert "User Preferences:" in markdown
    assert "functional programming style" in markdown
    assert "Failure Lessons & Known Pitfalls" in markdown
    assert "Avoid using raw eval()" in markdown


def test_project_memory_scoping(temp_store: LocalFactStore):
    learner = ExperienceLearner(memory_store=temp_store)

    temp_store.add(
        "Secret project A architecture: microservices",
        category="architecture_decisions",
        project="project-alpha",
        verified=True,
    )
    temp_store.add(
        "Secret project B architecture: monolithic",
        category="architecture_decisions",
        project="project-beta",
        verified=True,
    )

    ctx_alpha = learner.retrieve_planning_context(
        prompt="Architecture review",
        project="project-alpha",
    )
    assert "microservices" in ctx_alpha["markdown"]
    assert "monolithic" not in ctx_alpha["markdown"]

    ctx_beta = learner.retrieve_planning_context(
        prompt="Architecture review",
        project="project-beta",
    )
    assert "monolithic" in ctx_beta["markdown"]
    assert "microservices" not in ctx_beta["markdown"]
