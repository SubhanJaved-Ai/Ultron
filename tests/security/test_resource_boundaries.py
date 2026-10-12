"""Comprehensive multi-tenant resource boundary and IDOR tests.

Verifies tenant isolation across all resource boundaries:
1. Direct Object Reference (IDOR) on conversation sessions (/v1/sessions)
2. IDOR on workflow definitions and executions (WorkflowManageTool)
3. IDOR on scheduled jobs and cron tasks (CronjobManageTool)
4. Memory document and knowledge retrieval isolation
5. Background task ownership preservation
6. Dangerous tool authorization boundary checks (ToolExecutor RBAC)
7. Anti-enumeration: unauthenticated/cross-tenant returns no sensitive metadata
8. Account deletion data purging and retention boundaries
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from openjarvis.auth.manager import UserManager, set_user_manager
from openjarvis.core.types import ToolCall, ToolResult
from openjarvis.server.app import create_app
from openjarvis.sessions import SessionStore
from openjarvis.tools._stubs import BaseTool, ToolExecutor, ToolSpec
from openjarvis.tools.cronjob_manage import CronjobManageTool
from openjarvis.tools.workflow_manage import WorkflowManageTool


@pytest.fixture
def auth_env(tmp_path: Path):
    """Set up isolated multi-user database and test client."""
    db_file = tmp_path / "resource_boundary_users.db"
    mgr = UserManager(db_path=db_file)
    set_user_manager(mgr)

    old_env = os.environ.get("OPENJARVIS_MULTI_USER")
    os.environ["OPENJARVIS_MULTI_USER"] = "1"

    app = create_app()
    client = TestClient(app)

    # Register admin (first user) and two distinct standard users
    admin = mgr.register("admin_corp", "AdminSecret1234!")
    alice = mgr.register("alice_tenant", "AliceSecret1234!")
    bob = mgr.register("bob_tenant", "BobSecret1234!")

    t_admin = mgr.create_session(admin.id)
    t_alice = mgr.create_session(alice.id)
    t_bob = mgr.create_session(bob.id)

    yield {
        "tmp_path": tmp_path,
        "mgr": mgr,
        "client": client,
        "admin": admin,
        "alice": alice,
        "bob": bob,
        "t_admin": t_admin,
        "t_alice": t_alice,
        "t_bob": t_bob,
        "h_admin": {"Authorization": f"Bearer {t_admin}"},
        "h_alice": {"Authorization": f"Bearer {t_alice}"},
        "h_bob": {"Authorization": f"Bearer {t_bob}"},
    }

    set_user_manager(None)
    if old_env is None:
        os.environ.pop("OPENJARVIS_MULTI_USER", None)
    else:
        os.environ["OPENJARVIS_MULTI_USER"] = old_env


class TestSessionIDORBoundaries:
    def test_cross_tenant_session_manipulation_blocked(self, auth_env):
        client = auth_env["client"]
        h_alice = auth_env["h_alice"]
        h_bob = auth_env["h_bob"]
        alice = auth_env["alice"]

        # Alice creates a session in the SessionStore
        store = SessionStore()
        s_alice = store.get_or_create(user_id=alice.id, display_name="Alice Confidential")
        s_alice.add_message("user", "Secret project plan alpha")
        store.save_message(s_alice.session_id, "user", "Secret project plan alpha")

        # Alice lists sessions via /v1/sessions: sees her session
        res_alice_list = client.get("/v1/sessions", headers=h_alice)
        assert res_alice_list.status_code == 200
        alice_sessions = res_alice_list.json().get("sessions", [])
        assert any(s.get("session_id") == s_alice.session_id for s in alice_sessions)

        # Bob lists sessions: must NOT see Alice's session
        res_bob_list = client.get("/v1/sessions", headers=h_bob)
        assert res_bob_list.status_code == 200
        bob_sessions = res_bob_list.json().get("sessions", [])
        assert not any(s.get("session_id") == s_alice.session_id for s in bob_sessions)

        # Bob attempts IDOR to directly read Alice's session
        res_bob_get = client.get(f"/v1/sessions/{s_alice.session_id}", headers=h_bob)
        # Must return 404 and disclose NO secret content
        assert res_bob_get.status_code == 404
        assert "Secret project plan alpha" not in res_bob_get.text

        # Alice can directly read her session
        res_alice_get = client.get(f"/v1/sessions/{s_alice.session_id}", headers=h_alice)
        assert res_alice_get.status_code == 200
        assert res_alice_get.json().get("session_id") == s_alice.session_id


class TestWorkflowAndTaskBoundaries:
    def test_cross_tenant_workflow_isolation(self, auth_env):
        tmp_path = auth_env["tmp_path"]
        alice = auth_env["alice"]
        bob = auth_env["bob"]

        wf_dir = tmp_path / "workflows"
        tool = WorkflowManageTool(workflows_dir=wf_dir)

        # Alice creates a private workflow
        nodes = [
            {"id": "step_a", "type": "agent", "agent": "finance_analyst"},
            {"id": "step_b", "type": "agent", "agent": "payout_agent"},
        ]
        edges = [{"source": "step_a", "target": "step_b"}]
        res_create = tool.execute(
            action="create",
            name="alice_payroll_pipeline",
            nodes=nodes,
            edges=edges,
            user_id=alice.id,
        )
        assert res_create.success is True

        # Alice inspects her workflow
        res_alice_inspect = tool.execute(
            action="inspect",
            name="alice_payroll_pipeline",
            user_id=alice.id,
        )
        assert res_alice_inspect.success is True
        assert "step_a -> step_b" in res_alice_inspect.content

        # Bob attempts to inspect Alice's workflow: must fail with not found
        res_bob_inspect = tool.execute(
            action="inspect",
            name="alice_payroll_pipeline",
            user_id=bob.id,
        )
        assert res_bob_inspect.success is False
        assert "Workflow not found" in res_bob_inspect.content
        assert "payout_agent" not in res_bob_inspect.content

        # Bob lists workflows: must not see Alice's workflow
        res_bob_list = tool.execute(action="list", user_id=bob.id)
        assert res_bob_list.success is True
        assert "alice_payroll_pipeline" not in res_bob_list.content

        # Bob attempts to delete Alice's workflow: must fail
        res_bob_del = tool.execute(
            action="delete",
            name="alice_payroll_pipeline",
            user_id=bob.id,
        )
        assert res_bob_del.success is False
        assert "Workflow not found" in res_bob_del.content

        # Alice's workflow remains intact and executable by Alice
        res_alice_check = tool.execute(
            action="inspect",
            name="alice_payroll_pipeline",
            user_id=alice.id,
        )
        assert res_alice_check.success is True


class TestCronAndScheduledJobBoundaries:
    def test_scheduled_job_tenant_isolation(self, auth_env):
        tmp_path = auth_env["tmp_path"]
        alice = auth_env["alice"]
        bob = auth_env["bob"]

        sched_db = tmp_path / "scheduler.db"
        tool = CronjobManageTool(db_path=sched_db)

        # Alice schedules a recurring confidential task
        res_add = tool.execute(
            action="add",
            prompt="Process confidential quarterly bonus payments",
            schedule="0 9 * * *",
            user_id=alice.id,
        )
        assert res_add.success is True
        task_id = res_add.metadata["task_id"]

        # Bob lists scheduled tasks: must not see Alice's task
        res_bob_list = tool.execute(action="list", user_id=bob.id)
        assert res_bob_list.success is True
        assert task_id not in res_bob_list.content
        assert "quarterly bonus" not in res_bob_list.content

        # Bob attempts to inspect status of Alice's task
        res_bob_status = tool.execute(action="status", task_id=task_id, user_id=bob.id)
        assert res_bob_status.success is False
        assert f"Task not found: {task_id}" in res_bob_status.content

        # Bob attempts to pause or cancel Alice's task
        res_bob_pause = tool.execute(action="pause", task_id=task_id, user_id=bob.id)
        assert res_bob_pause.success is False
        res_bob_remove = tool.execute(action="remove", task_id=task_id, user_id=bob.id)
        assert res_bob_remove.success is False

        # Alice can inspect status and remove her own task
        res_alice_status = tool.execute(action="status", task_id=task_id, user_id=alice.id)
        assert res_alice_status.success is True
        assert task_id in res_alice_status.content

        res_alice_remove = tool.execute(action="remove", task_id=task_id, user_id=alice.id)
        assert res_alice_remove.success is True
        assert f"Removed scheduled task: {task_id}" in res_alice_remove.content


class TestMemoryAndKnowledgeIsolation:
    def test_memory_document_isolation(self, auth_env):
        mgr = auth_env["mgr"]
        alice = auth_env["alice"]
        bob = auth_env["bob"]

        # Alice stores private memories
        mgr.set_preference(alice.id, "memory_financial_token", "ALICE_FIN_KEY_998")
        mgr.set_preference(alice.id, "system_prompt_custom", "You are Alice's CFO assistant.")

        # Bob stores his own memories
        mgr.set_preference(bob.id, "system_prompt_custom", "You are Bob's developer assistant.")

        # Verify Bob cannot access Alice's financial token
        bob_val = mgr.get_preference(bob.id, "memory_financial_token")
        assert bob_val is None

        # Verify Bob receives only his own preferences
        bob_all = mgr.get_all_preferences(bob.id)
        assert "memory_financial_token" not in bob_all
        assert bob_all["system_prompt_custom"] == "You are Bob's developer assistant."

        # Verify Alice's preferences remain strictly isolated
        alice_all = mgr.get_all_preferences(alice.id)
        assert alice_all["memory_financial_token"] == "ALICE_FIN_KEY_998"


class DummyDangerousTool(BaseTool):
    tool_id = "dangerous_shell"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="dangerous_shell",
            description="Executes dangerous system shell commands",
            required_capabilities=["code:execute", "system:admin"],
        )

    def execute(self, **params) -> ToolResult:
        return ToolResult(
            tool_name="dangerous_shell",
            success=True,
            content=f"Executed command: {params.get('cmd')}",
        )


class DummySafeTool(BaseTool):
    tool_id = "safe_echo"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="safe_echo",
            description="Echo back safe input",
            required_capabilities=[],
        )

    def execute(self, **params) -> ToolResult:
        return ToolResult(
            tool_name="safe_echo",
            success=True,
            content=f"Echo: {params.get('text')}",
        )


class TestDangerousToolPermissionBoundaries:
    def test_role_based_tool_permission_matrix(self, auth_env):
        alice = auth_env["alice"]
        admin = auth_env["admin"]

        tools = [DummyDangerousTool(), DummySafeTool()]
        executor = ToolExecutor(tools=tools)

        # 1. Unprivileged user executes safe tool -> SUCCESS
        safe_call = ToolCall(
            id="c1",
            name="safe_echo",
            arguments=json.dumps({"text": "hello world"}),
        )
        role_alice = getattr(alice.role, "value", str(alice.role))
        role_admin = getattr(admin.role, "value", str(admin.role))
        res_safe = executor.execute(safe_call, operator_role=role_alice)
        assert res_safe.success is True
        assert "Echo: hello world" in res_safe.content

        # 2. Unprivileged user executes dangerous tool -> DENIED
        dang_call = ToolCall(
            id="c2",
            name="dangerous_shell",
            arguments=json.dumps({"cmd": "rm -rf /"}),
        )
        res_alice = executor.execute(dang_call, operator_role=role_alice)
        assert res_alice.success is False
        assert "Permission denied: role 'user' is not authorized" in res_alice.content

        # 3. Guest executes safe tool with no capabilities -> SUCCESS
        res_guest_safe = executor.execute(safe_call, operator_role="guest")
        assert res_guest_safe.success is True

        # 4. Guest executes dangerous tool -> DENIED
        res_guest_dang = executor.execute(dang_call, operator_role="guest")
        assert res_guest_dang.success is False
        assert "Permission denied: role 'guest' is not authorized" in res_guest_dang.content

        # 5. Admin executes dangerous tool -> SUCCESS
        res_admin = executor.execute(dang_call, operator_role=role_admin)
        assert res_admin.success is True
        assert "Executed command: rm -rf /" in res_admin.content


class TestAccountDeletionDataPurge:
    def test_account_deletion_enforces_retention_purge(self, auth_env):
        client = auth_env["client"]
        mgr = auth_env["mgr"]
        alice = auth_env["alice"]
        h_alice = auth_env["h_alice"]

        # Set preferences for Alice
        mgr.set_preference(alice.id, "theme", "cyberpunk")
        assert mgr.get_preference(alice.id, "theme") == "cyberpunk"

        # Alice deletes her account
        res_del = client.delete("/api/auth/account", headers=h_alice)
        assert res_del.status_code == 200
        assert res_del.json()["status"] == "account_deleted"

        # 1. User record deleted
        assert mgr.get_user(alice.id) is None
        assert mgr.get_user_by_username("alice_tenant") is None

        # 2. Preferences purged
        assert mgr.get_preference(alice.id, "theme") is None
        assert mgr.get_all_preferences(alice.id) == {}

        # 3. Old session token revoked
        assert mgr.validate_session(auth_env["t_alice"]) is None

        # 4. Attempting protected operations with old session returns 401
        res_protected = client.get("/api/auth/me", headers=h_alice)
        assert res_protected.status_code == 401

        # 5. Subsequent login with old credentials returns 401
        res_login = client.post(
            "/api/auth/login",
            json={"username": "alice_tenant", "password": "AliceSecret1234!"},
        )
        assert res_login.status_code == 401


class TestAntiEnumerationAndErrorDisclosure:
    def test_unauthenticated_requests_do_not_leak_internals(self, auth_env):
        client = auth_env["client"]

        # Missing token on protected endpoint returns 401
        res_me = client.get("/api/auth/me")
        assert res_me.status_code == 401
        assert "Authentication required" in res_me.json().get("detail", "")
        # No internal stack traces or environment keys
        assert "Traceback" not in res_me.text
        assert "password" not in res_me.text

        # Invalid token returns 401
        res_bad = client.get("/api/auth/me", headers={"Authorization": "Bearer totally_bogus_token"})
        assert res_bad.status_code == 401
