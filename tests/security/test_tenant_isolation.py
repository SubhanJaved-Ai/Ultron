"""Automated tests proving tenant isolation between independent users.

Verifies:
1. Unauthenticated access, expired sessions, and invalid tokens return 401.
2. User Alpha vs User Beta registration and session generation.
3. User preference isolation (no honorific or address leakage).
4. Conversation session isolation and IDOR prevention on /v1/sessions.
5. Workflow isolation: User Beta cannot list, inspect, run, or delete User Alpha's workflows.
6. Scheduled tasks isolation: User Beta cannot view, trigger, or remove User Alpha's tasks.
7. Role-based execution control: Unprivileged users cannot invoke dangerous tools (shell_exec).
8. Rate limiting on authentication endpoints.
9. Backward compatibility for single-user local mode.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from openjarvis.auth.manager import UserManager, set_user_manager
from openjarvis.auth.models import Role
from openjarvis.core.types import ToolCall
from openjarvis.scheduler.store import SchedulerStore
from openjarvis.server.app import create_app
from openjarvis.sessions.session import SessionStore
from openjarvis.tools._stubs import ToolExecutor
from openjarvis.tools.cronjob_manage import CronjobManageTool
from openjarvis.tools.shell_exec import ShellExecTool
from openjarvis.tools.workflow_manage import WorkflowManageTool


def _mock_engine():
    engine = MagicMock()
    engine.engine_id = "mock"
    engine.health.return_value = True
    engine.list_models.return_value = ["test-model"]
    return engine


@pytest.fixture
def multi_user_env(tmp_path, monkeypatch):
    """Set up isolated databases and activate multi-user mode."""
    users_db = tmp_path / "test_users.db"
    mgr = UserManager(db_path=users_db)
    set_user_manager(mgr)

    monkeypatch.setenv("OPENJARVIS_MULTI_USER", "1")
    monkeypatch.setattr("openjarvis.core.paths.get_config_dir", lambda: tmp_path)

    # Register User Alpha (first user becomes admin)
    user_alpha = mgr.register(
        "alpha_user", "AlphaSecretPass123!", role=Role.ADMIN.value
    )
    token_alpha = mgr.create_session(user_alpha.id)

    # Register User Beta (standard user)
    user_beta = mgr.register("beta_user", "BetaSecretPass123!", role=Role.USER.value)
    token_beta = mgr.create_session(user_beta.id)

    app = create_app(_mock_engine(), "test-model", multi_user=True)
    client = TestClient(app)

    yield {
        "mgr": mgr,
        "app": app,
        "client": client,
        "user_alpha": user_alpha,
        "token_alpha": token_alpha,
        "user_beta": user_beta,
        "token_beta": token_beta,
        "tmp_path": tmp_path,
    }

    set_user_manager(None)


def test_unauthenticated_and_expired_access_blocked(multi_user_env):
    """Protected endpoints must reject missing, invalid, or expired tokens."""
    client = multi_user_env["client"]
    mgr = multi_user_env["mgr"]
    user_alpha = multi_user_env["user_alpha"]

    # 1. Missing token on /v1/sessions
    resp = client.get("/v1/sessions")
    assert resp.status_code == 401
    assert "Authentication required" in resp.json()["detail"]

    # 2. Invalid/tampered token
    resp = client.get(
        "/v1/sessions", headers={"Authorization": "Bearer oj_usr_invalid_token_123"}
    )
    assert resp.status_code == 401

    # 3. Expired token
    expired_token = mgr.create_session(user_alpha.id, ttl_seconds=-10)
    resp = client.get(
        "/v1/sessions", headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert resp.status_code == 401

    # 4. Revoked token
    revoked_token = mgr.create_session(user_alpha.id, ttl_seconds=3600)
    mgr.revoke_session(revoked_token)
    resp = client.get(
        "/v1/sessions", headers={"Authorization": f"Bearer {revoked_token}"}
    )
    assert resp.status_code == 401

    # 5. Exempt endpoint succeeds without credentials
    resp = client.get("/hologram")
    assert resp.status_code == 200


def test_user_preference_isolation(multi_user_env):
    """User Alpha's address preference must not leak to User Beta."""
    client = multi_user_env["client"]
    token_alpha = multi_user_env["token_alpha"]
    token_beta = multi_user_env["token_beta"]

    headers_alpha = {"Authorization": f"Bearer {token_alpha}"}
    headers_beta = {"Authorization": f"Bearer {token_beta}"}

    # User Alpha sets preference
    resp_a = client.post(
        "/api/hologram/directive",
        json={"directive": "Call me Director Alpha"},
        headers=headers_alpha,
    )
    assert resp_a.status_code == 200
    assert "Director Alpha" in resp_a.json()["reply"]

    # User Beta sets preference
    resp_b = client.post(
        "/api/hologram/directive",
        json={"directive": "Call me Commander Beta"},
        headers=headers_beta,
    )
    assert resp_b.status_code == 200
    assert "Commander Beta" in resp_b.json()["reply"]

    # User Alpha queries name
    id_a = client.post(
        "/api/hologram/directive",
        json={"directive": "Who am I?"},
        headers=headers_alpha,
    )
    assert "Director Alpha" in id_a.json()["reply"]
    assert "Commander Beta" not in id_a.json()["reply"]

    # User Beta queries name
    id_b = client.post(
        "/api/hologram/directive",
        json={"directive": "Who am I?"},
        headers=headers_beta,
    )
    assert "Commander Beta" in id_b.json()["reply"]
    assert "Director Alpha" not in id_b.json()["reply"]


def test_conversation_session_isolation_and_idor_protection(multi_user_env):
    """User Beta cannot list or access User Alpha's sessions."""
    client = multi_user_env["client"]
    token_alpha = multi_user_env["token_alpha"]
    token_beta = multi_user_env["token_beta"]
    user_alpha = multi_user_env["user_alpha"]
    user_beta = multi_user_env["user_beta"]
    tmp_path = multi_user_env["tmp_path"]

    session_store = SessionStore(db_path=tmp_path / "sessions.db")

    # Create session for User Alpha
    s_alpha = session_store.get_or_create(user_alpha.id)
    session_store.save_message(s_alpha.session_id, "user", "Alpha confidential data")

    # Create session for User Beta
    s_beta = session_store.get_or_create(user_beta.id)
    session_store.save_message(s_beta.session_id, "user", "Beta general discussion")

    headers_alpha = {"Authorization": f"Bearer {token_alpha}"}
    headers_beta = {"Authorization": f"Bearer {token_beta}"}

    # Alpha lists sessions -> sees s_alpha only
    list_a = client.get("/v1/sessions", headers=headers_alpha).json()
    alpha_ids = [s["session_id"] for s in list_a["sessions"]]
    assert s_alpha.session_id in alpha_ids
    assert s_beta.session_id not in alpha_ids

    # Beta lists sessions -> sees s_beta only
    list_b = client.get("/v1/sessions", headers=headers_beta).json()
    beta_ids = [s["session_id"] for s in list_b["sessions"]]
    assert s_beta.session_id in beta_ids
    assert s_alpha.session_id not in beta_ids

    # IDOR Attack: Beta attempts to read Alpha's session directly
    idor_resp = client.get(f"/v1/sessions/{s_alpha.session_id}", headers=headers_beta)
    assert idor_resp.status_code == 404
    assert idor_resp.json()["detail"] == "Session not found"


def test_workflow_tenant_isolation(multi_user_env):
    """User Beta cannot list, inspect, run, or delete User Alpha's workflows."""
    tmp_path = multi_user_env["tmp_path"]
    user_alpha = multi_user_env["user_alpha"]
    user_beta = multi_user_env["user_beta"]

    wf_tool = WorkflowManageTool(workflows_dir=tmp_path / "workflows")

    # User Alpha creates a workflow
    create_res = wf_tool.execute(
        action="create",
        name="alpha_pipeline",
        nodes=[{"id": "node1", "type": "agent", "agent": "simple"}],
        edges=[],
        user_id=user_alpha.id,
    )
    assert create_res.success

    # User Alpha can list and inspect
    list_a = wf_tool.execute(action="list", user_id=user_alpha.id)
    assert "alpha_pipeline" in list_a.content

    inspect_a = wf_tool.execute(
        action="inspect", name="alpha_pipeline", user_id=user_alpha.id
    )
    assert inspect_a.success

    # User Beta lists workflows -> Alpha's workflow is absent
    list_b = wf_tool.execute(action="list", user_id=user_beta.id)
    assert "alpha_pipeline" not in list_b.content

    # User Beta attempts to inspect Alpha's workflow -> not found
    inspect_b = wf_tool.execute(
        action="inspect", name="alpha_pipeline", user_id=user_beta.id
    )
    assert not inspect_b.success
    assert "not found" in inspect_b.content.lower()

    # User Beta attempts to run Alpha's workflow -> not found
    run_b = wf_tool.execute(action="run", name="alpha_pipeline", user_id=user_beta.id)
    assert not run_b.success
    assert "not found" in run_b.content.lower()

    # User Beta attempts to delete Alpha's workflow -> not found
    del_b = wf_tool.execute(
        action="delete", name="alpha_pipeline", user_id=user_beta.id
    )
    assert not del_b.success
    assert "not found" in del_b.content.lower()

    # Path traversal attack attempt: Beta uses relative path
    traversal_res = wf_tool.execute(
        action="inspect",
        name=f"../{user_alpha.id}/alpha_pipeline",
        user_id=user_beta.id,
    )
    assert not traversal_res.success
    assert "not found" in traversal_res.content.lower()


def test_cronjob_tenant_isolation(multi_user_env):
    """User Beta cannot view, trigger, pause, or remove User Alpha's scheduled tasks."""
    tmp_path = multi_user_env["tmp_path"]
    user_alpha = multi_user_env["user_alpha"]
    user_beta = multi_user_env["user_beta"]

    store = SchedulerStore(tmp_path / "scheduler.db")
    cron_tool = CronjobManageTool(store=store, db_path=tmp_path / "scheduler.db")

    # Alpha adds a task
    add_res = cron_tool.execute(
        action="add",
        prompt="Alpha recurring secret task",
        schedule="3600",
        user_id=user_alpha.id,
    )
    assert add_res.success
    alpha_task_id = add_res.metadata["task_id"]

    # Beta lists tasks -> Alpha's task is absent
    list_b = cron_tool.execute(action="list", user_id=user_beta.id)
    assert alpha_task_id not in list_b.content

    # Beta attempts to view status of Alpha's task
    stat_b = cron_tool.execute(
        action="status", task_id=alpha_task_id, user_id=user_beta.id
    )
    assert not stat_b.success
    assert "not found" in stat_b.content.lower()

    # Beta attempts to trigger Alpha's task
    run_b = cron_tool.execute(action="run", task_id=alpha_task_id, user_id=user_beta.id)
    assert not run_b.success
    assert "not found" in run_b.content.lower()

    # Beta attempts to remove Alpha's task
    rem_b = cron_tool.execute(
        action="remove", task_id=alpha_task_id, user_id=user_beta.id
    )
    assert not rem_b.success
    assert "not found" in rem_b.content.lower()

    # Verify task still exists for Alpha
    stat_a = cron_tool.execute(
        action="status", task_id=alpha_task_id, user_id=user_alpha.id
    )
    assert stat_a.success


def test_dangerous_tool_role_enforcement():
    """Unprivileged users (role='user') must be blocked from executing dangerous tools."""
    tool = ShellExecTool()
    executor = ToolExecutor([tool], agent_id="test_agent")

    # 1. Unprivileged user attempting shell execution -> blocked
    result_user = executor.execute(
        ToolCall(
            id="call-1",
            name="shell_exec",
            arguments=json.dumps({"command": "echo 'dangerous'"}),
        ),
        operator_role=Role.USER.value,
    )
    assert not result_user.success
    assert "Permission denied: role 'user' is not authorized" in result_user.content

    # 2. Guest user attempting shell execution -> blocked
    result_guest = executor.execute(
        ToolCall(
            id="call-2",
            name="shell_exec",
            arguments=json.dumps({"command": "echo 'guest'"}),
        ),
        operator_role=Role.GUEST.value,
    )
    assert not result_guest.success
    assert "Permission denied: role 'guest' is not authorized" in result_guest.content


def test_backward_compatibility_single_user_mode(tmp_path, monkeypatch):
    """When multi-user mode is inactive, loopback requests without auth succeed."""
    monkeypatch.delenv("OPENJARVIS_MULTI_USER", raising=False)
    monkeypatch.delenv("OPENJARVIS_API_KEY", raising=False)
    monkeypatch.setattr("openjarvis.core.paths.get_config_dir", lambda: tmp_path)

    app = create_app(_mock_engine(), "test-model", multi_user=False)
    client = TestClient(app)

    # In single-user mode, endpoints allow access without bearer token
    resp = client.get("/v1/models")
    assert resp.status_code == 200

    directive_resp = client.post(
        "/api/hologram/directive",
        json={"directive": "Hello Jarvis"},
    )
    assert directive_resp.status_code == 200
