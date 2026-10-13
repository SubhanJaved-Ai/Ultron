"""Integration tests verifying end-to-end cancellation wiring and security guards.

Covers:
- Strict session ownership & rejection of cross-session cancellation (TSK-P5-01 / 3.A)
- Context listing isolation to prevent tenant enumeration (TSK-P5-01 / 3.A)
- Browser teardown hook and exception surfacing (TSK-P5-01 / 3.B)
- LLM streaming task cancellation and worker cleanup (TSK-P5-01 / 3.C)
- Real agent loop cancellation before tool dispatch (TSK-P5-01 / 3.D)
- Approval queue context-bound cancellation and execution guard (TSK-P5-01 / 3.D)
- Hologram directive registration and cancellation in ActiveExecutionContextStore (TSK-P5-01 / 3.E)
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from openjarvis.agents.native_react import NativeReActAgent
from openjarvis.auth.models import Role, User
from openjarvis.core.events import EventBus
from openjarvis.server.cancellation import (
    CancellationToken,
    get_execution_store,
)
from openjarvis.server.cancellation_routes import cancellation_router
from openjarvis.tools.approval_store import (
    STATUS_APPROVED,
    STATUS_CANCELLED,
    ApprovalStore,
)
from openjarvis.tools.proactive_tools import ExecutePendingActionsTool

# ---------------------------------------------------------------------------
# Fixture: Multi-session mock app
# ---------------------------------------------------------------------------


@pytest.fixture()
def auth_client():
    """FastAPI test app where request.state.user can be set per request header."""
    app = FastAPI()

    @app.middleware("http")
    async def mock_auth_middleware(request: Request, call_next):
        user_header = request.headers.get("X-Mock-User")
        role_header = request.headers.get("X-Mock-Role")
        if user_header:
            role = role_header or (
                Role.ADMIN.value
                if user_header in ("local_admin", "api_admin", "admin")
                else Role.USER.value
            )
            request.state.user = User(
                id=user_header,
                username=user_header,
                role=role,
            )
        else:
            request.state.user = User(
                id="default",
                username="local_admin",
                role=Role.ADMIN.value,
            )
        return await call_next(request)

    app.include_router(cancellation_router)
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Test 1: Cross-session authorization and enumeration isolation
# ---------------------------------------------------------------------------


class TestSessionOwnershipAndIsolation:
    def test_cross_session_cancellation_rejected_without_body_session_id(
        self, auth_client
    ):
        """Attacker omitting session_id in JSON body cannot cancel victim context."""
        store = get_execution_store()
        ctx_id = "ctx-victim-001"
        token = store.register(ctx_id, owner_session_id="user_alice")

        try:
            # Bob attempts to cancel Alice's context without specifying session_id
            resp = auth_client.post(
                "/api/execution/cancel",
                json={"context_id": ctx_id},
                headers={"X-Mock-User": "user_bob"},
            )
            assert resp.status_code == 403
            assert not token.is_cancelled

            # Bob attempts to cancel Alice's context claiming Alice's session_id in body
            resp_spoof = auth_client.post(
                "/api/execution/cancel",
                json={"context_id": ctx_id, "session_id": "user_alice"},
                headers={"X-Mock-User": "user_bob"},
            )
            assert resp_spoof.status_code == 403
            assert not token.is_cancelled

            # Alice successfully cancels her own context
            resp_alice = auth_client.post(
                "/api/execution/cancel",
                json={"context_id": ctx_id},
                headers={"X-Mock-User": "user_alice"},
            )
            assert resp_alice.status_code == 200
            assert token.is_cancelled
        finally:
            store.unregister(ctx_id)

    def test_list_contexts_isolates_by_authenticated_user(self, auth_client):
        """Active contexts of other sessions are not exposed to caller."""
        store = get_execution_store()
        store.register("ctx-alice-job", owner_session_id="user_alice")
        store.register("ctx-bob-job", owner_session_id="user_bob")

        try:
            # Alice sees only her job
            resp_alice = auth_client.get(
                "/api/execution/contexts",
                headers={"X-Mock-User": "user_alice"},
            )
            assert resp_alice.status_code == 200
            alice_contexts = resp_alice.json()["active_contexts"]
            assert "ctx-alice-job" in alice_contexts
            assert "ctx-bob-job" not in alice_contexts

            # Bob sees only his job
            resp_bob = auth_client.get(
                "/api/execution/contexts",
                headers={"X-Mock-User": "user_bob"},
            )
            assert resp_bob.status_code == 200
            bob_contexts = resp_bob.json()["active_contexts"]
            assert "ctx-bob-job" in bob_contexts
            assert "ctx-alice-job" not in bob_contexts
        finally:
            store.unregister("ctx-alice-job")
            store.unregister("ctx-bob-job")


# ---------------------------------------------------------------------------
# Test 2: Browser cleanup callbacks and error surfacing
# ---------------------------------------------------------------------------


class TestBrowserCancellationHooks:
    def test_token_cleanup_callback_invokes_session_close(self):
        token = CancellationToken(context_id="test-browser-hook")
        close_called = False

        def _mock_close():
            nonlocal close_called
            close_called = True

        token.add_cleanup_callback(_mock_close)
        assert not close_called
        token.cancel()
        assert close_called

    def test_cleanup_callback_surfaces_exceptions_without_halting(self):
        token = CancellationToken(context_id="test-cleanup-errors")

        def _bad_cleanup():
            raise RuntimeError("Playwright connection lost")

        token.add_cleanup_callback(_bad_cleanup)
        token.cancel()
        assert token.is_cancelled
        assert len(token.cleanup_errors) == 1
        assert "Playwright connection lost" in str(token.cleanup_errors[0])


# ---------------------------------------------------------------------------
# Test 3: LLM stream worker task cancellation
# ---------------------------------------------------------------------------


class TestStreamTaskCancellation:
    @pytest.mark.asyncio
    async def test_stream_cancels_underlying_agent_task(self):
        from openjarvis.server.models import ChatCompletionRequest, ChatMessage
        from openjarvis.server.stream_bridge import AgentStreamBridge

        token = CancellationToken(context_id="stream-task-cancel")
        bus = EventBus()
        req = ChatCompletionRequest(
            model="mock",
            messages=[ChatMessage(role="user", content="run query")],
        )

        mock_agent = MagicMock()
        mock_agent.run.side_effect = lambda *args, **kwargs: asyncio.sleep(10)

        bridge = AgentStreamBridge(
            agent=mock_agent,
            bus=bus,
            model="mock",
            request=req,
            cancellation_token=token,
        )

        # Cancel immediately
        token.cancel()

        chunks = []
        async for chunk in bridge.stream():
            chunks.append(chunk)

        assert any("[DONE]" in c for c in chunks)


# ---------------------------------------------------------------------------
# Test 4: Agent loop halts before tool dispatch
# ---------------------------------------------------------------------------


class TestAgentLoopCancellation:
    def test_native_react_halts_when_token_cancelled(self):
        token = CancellationToken(context_id="react-cancel-test")
        token.cancel()

        mock_engine = MagicMock()
        mock_engine.generate.return_value = {
            "content": 'Action: shell_exec\nAction Input: {"command": "echo test"}'
        }

        agent = NativeReActAgent(engine=mock_engine, model="mock")
        mock_executor = MagicMock()
        agent._executor = mock_executor

        result = agent.run("execute task", cancellation_token=token)
        assert result.metadata.get("cancelled") is True
        # Executor must NOT have executed any tools
        mock_executor.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Test 5: ApprovalStore & ExecutePendingActionsTool cancellation
# ---------------------------------------------------------------------------


class TestApprovalStoreCancellation:
    def test_cancel_actions_for_context_marks_actions_cancelled(self, tmp_path):
        db_path = str(tmp_path / "test_approvals.db")
        store = ApprovalStore(db_path=db_path)

        action = store.queue_action(
            action_type="shell_exec",
            description="run command",
            payload={"command": "dir", "context_id": "ctx-approval-123"},
            permission_key="shell:dir",
            tier="high",
        )
        store.update_status(action.id, STATUS_APPROVED)

        assert store.get_action(action.id).status == STATUS_APPROVED

        # Cancel actions for this context
        cancelled_count = store.cancel_actions_for_context("ctx-approval-123")
        assert cancelled_count == 1
        assert store.get_action(action.id).status == STATUS_CANCELLED

    def test_execute_pending_actions_skips_cancelled_context(self, tmp_path):
        db_path = str(tmp_path / "test_approvals.db")
        store = ApprovalStore(db_path=db_path)

        action = store.queue_action(
            action_type="shell_exec",
            description="dangerous command",
            payload={"command": "rm -rf", "context_id": "ctx-aborted"},
            permission_key="shell:rm",
            tier="high",
        )
        store.update_status(action.id, STATUS_APPROVED)

        exec_store = get_execution_store()
        ctx_token = exec_store.register("ctx-aborted")
        ctx_token.cancel()

        try:
            tool = ExecutePendingActionsTool(store=store)
            result = tool.execute()
            # Action was safely NOT executed
            assert result.metadata["executed"] == 0
            assert "was cancelled" in result.content
            # Status in store should now be marked cancelled
            assert store.get_action(action.id).status == STATUS_CANCELLED
        finally:
            exec_store.unregister("ctx-aborted")


# ---------------------------------------------------------------------------
# Test 6: Hologram directive cancellation and unregistration
# ---------------------------------------------------------------------------


class TestHologramDirectiveCancellation:
    def test_hologram_directive_aborts_on_pre_cancelled_token(self):
        from openjarvis.server.hologram_routes import hologram_router

        app = FastAPI()
        app.include_router(hologram_router)
        client = TestClient(app)

        store = get_execution_store()
        # Pre-cancel "active"
        tok = store.register("active", owner_session_id="default")
        tok.cancel()

        try:
            resp = client.post(
                "/api/hologram/directive",
                json={"directive": "Deploy the production service"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "cancelled"
            assert "cancelled" in data["reply"].lower()
        finally:
            store.unregister("active")


# ---------------------------------------------------------------------------
# Test 7: Desktop Global Shortcut (Ctrl+Alt+Escape) auth contract & scope
# ---------------------------------------------------------------------------


class TestDesktopShortcutAuthenticationAndContract:
    def test_admin_emergency_stop_cancels_other_session_execution(self, auth_client):
        """Administrator (e.g. api_admin from shortcut) can cancel running execution."""
        store = get_execution_store()
        tok = store.register("ctx-victim-002", owner_session_id="user_alice")
        try:
            resp = auth_client.post(
                "/api/execution/cancel",
                json={"context_id": "ctx-victim-002"},
                headers={"X-Mock-User": "local_admin"},
            )
            assert resp.status_code == 200
            assert tok.is_cancelled
        finally:
            store.unregister("ctx-victim-002")

    def test_admin_broadcast_emergency_stop_cancels_all_active_contexts(
        self, auth_client
    ):
        """Global Emergency Stop without session target cancels all contexts."""
        store = get_execution_store()
        tok_alice = store.register("ctx-active-alice", owner_session_id="user_alice")
        tok_bob = store.register("ctx-active-bob", owner_session_id="user_bob")
        try:
            resp = auth_client.post(
                "/api/execution/cancel",
                json={"context_id": "active"},
                headers={"X-Mock-User": "local_admin"},
            )
            assert resp.status_code == 200
            assert tok_alice.is_cancelled
            assert tok_bob.is_cancelled
        finally:
            store.unregister("ctx-active-alice")
            store.unregister("ctx-active-bob")

    def test_admin_targeted_cancel_scopes_to_target_session(self, auth_client):
        """Admin specifying session_id cancels only the designated tenant's execution."""
        store = get_execution_store()
        tok_alice = store.register("ctx-scoped-alice", owner_session_id="user_alice")
        tok_bob = store.register("ctx-scoped-bob", owner_session_id="user_bob")
        try:
            resp = auth_client.post(
                "/api/execution/cancel",
                json={"context_id": "active", "session_id": "user_alice"},
                headers={"X-Mock-User": "local_admin"},
            )
            assert resp.status_code == 200
            assert tok_alice.is_cancelled
            assert not tok_bob.is_cancelled
        finally:
            store.unregister("ctx-scoped-alice")
            store.unregister("ctx-scoped-bob")

    def test_multi_user_mode_unauthenticated_request_rejected(self):
        """Multi-user mode strictly rejects unauthenticated /api/execution/cancel."""
        from openjarvis.server.auth_middleware import AuthMiddleware

        app = FastAPI()
        app.add_middleware(
            AuthMiddleware, api_key="oj_sk_secret_123", multi_user=True
        )
        app.include_router(cancellation_router)
        client = TestClient(app)

        store = get_execution_store()
        tok = store.register("ctx-multi-user", owner_session_id="user_alice")
        try:
            # Unauthenticated request fails with 401
            resp_no_auth = client.post(
                "/api/execution/cancel",
                json={"context_id": "ctx-multi-user"},
            )
            assert resp_no_auth.status_code == 401
            assert not tok.is_cancelled

            # Invalid key fails with 401
            resp_bad_key = client.post(
                "/api/execution/cancel",
                json={"context_id": "ctx-multi-user"},
                headers={"Authorization": "Bearer wrong_key"},
            )
            assert resp_bad_key.status_code == 401
            assert not tok.is_cancelled

            # Correct API key (as sent by Tauri shortcut) attaches api_admin and cancels
            resp_auth = client.post(
                "/api/execution/cancel",
                json={"context_id": "ctx-multi-user"},
                headers={"Authorization": "Bearer oj_sk_secret_123"},
            )
            assert resp_auth.status_code == 200
            assert tok.is_cancelled
        finally:
            store.unregister("ctx-multi-user")

    def test_single_user_mode_with_api_key_contract(self):
        """Single-user mode with OPENJARVIS_API_KEY enforces auth header."""
        from openjarvis.server.auth_middleware import AuthMiddleware

        app = FastAPI()
        app.add_middleware(
            AuthMiddleware, api_key="oj_sk_desktop_key", multi_user=False
        )
        app.include_router(cancellation_router)
        client = TestClient(app)

        store = get_execution_store()
        tok = store.register("ctx-single-user", owner_session_id="default")
        try:
            # Missing key rejected
            resp = client.post(
                "/api/execution/cancel",
                json={"context_id": "ctx-single-user"},
            )
            assert resp.status_code == 401
            assert not tok.is_cancelled

            # Valid key accepted
            resp_ok = client.post(
                "/api/execution/cancel",
                json={"context_id": "ctx-single-user"},
                headers={"Authorization": "Bearer oj_sk_desktop_key"},
            )
            assert resp_ok.status_code == 200
            assert tok.is_cancelled
        finally:
            store.unregister("ctx-single-user")

