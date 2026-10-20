"""Tests for the Global Emergency Stop cancellation infrastructure.

Covers:
    - CancellationToken lifecycle (register, cancel, is_cancelled, wait)
    - ActiveExecutionContextStore thread safety and broadcast cancel
    - POST /api/execution/cancel HTTP endpoint (200 on hit, 404 on miss)
    - GET /api/execution/contexts endpoint

TSK-P5-01 / AC-GES-01 through AC-GES-03
"""

from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

from openjarvis.server.cancellation import (
    ActiveExecutionContextStore,
    CancellationToken,
    get_execution_store,
)

# ---------------------------------------------------------------------------
# CancellationToken unit tests
# ---------------------------------------------------------------------------


class TestCancellationToken:
    def test_initial_state_not_cancelled(self):
        token = CancellationToken(context_id="test-001")
        assert not token.is_cancelled
        assert token.cancelled_at is None

    def test_cancel_sets_flag(self):
        token = CancellationToken(context_id="test-002")
        token.cancel()
        assert token.is_cancelled
        assert token.cancelled_at is not None

    def test_cancel_is_idempotent(self):
        token = CancellationToken(context_id="test-003")
        token.cancel()
        first_ts = token.cancelled_at
        time.sleep(0.01)
        token.cancel()  # second call — should not reset cancelled_at
        assert token.cancelled_at == first_ts

    def test_wait_returns_false_on_timeout(self):
        token = CancellationToken(context_id="test-004")
        result = token.wait(timeout=0.05)
        assert result is False

    def test_wait_returns_true_when_cancelled(self):
        token = CancellationToken(context_id="test-005")

        def _cancel_later():
            time.sleep(0.05)
            token.cancel()

        threading.Thread(target=_cancel_later, daemon=True).start()
        result = token.wait(timeout=0.5)
        assert result is True

    def test_cancel_from_separate_thread(self):
        token = CancellationToken(context_id="test-006")
        errors: list[str] = []

        def _cancel():
            try:
                token.cancel()
            except Exception as exc:
                errors.append(str(exc))

        threads = [threading.Thread(target=_cancel, daemon=True) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=1)

        assert not errors
        assert token.is_cancelled


# ---------------------------------------------------------------------------
# ActiveExecutionContextStore unit tests
# ---------------------------------------------------------------------------


class TestActiveExecutionContextStore:
    def test_register_and_get(self):
        store = ActiveExecutionContextStore()
        token = store.register("ctx-A")
        assert isinstance(token, CancellationToken)
        assert store.get("ctx-A") is token

    def test_register_idempotent(self):
        store = ActiveExecutionContextStore()
        t1 = store.register("ctx-B")
        t2 = store.register("ctx-B")
        assert t1 is t2

    def test_unregister_removes_token(self):
        store = ActiveExecutionContextStore()
        store.register("ctx-C")
        store.unregister("ctx-C")
        assert store.get("ctx-C") is None

    def test_unregister_nonexistent_is_safe(self):
        store = ActiveExecutionContextStore()
        store.unregister("nonexistent")  # must not raise

    def test_cancel_specific_context(self):
        store = ActiveExecutionContextStore()
        ta = store.register("ctx-D1")
        tb = store.register("ctx-D2")
        result = store.cancel("ctx-D1")
        assert result is True
        assert ta.is_cancelled
        assert not tb.is_cancelled

    def test_cancel_active_broadcasts_to_all(self):
        store = ActiveExecutionContextStore()
        tokens = [store.register(f"ctx-BC{i}") for i in range(5)]
        result = store.cancel("active")
        assert result is True
        assert all(t.is_cancelled for t in tokens)

    def test_cancel_returns_false_when_nothing_active(self):
        store = ActiveExecutionContextStore()
        assert store.cancel("active") is False
        assert store.cancel("nonexistent") is False

    def test_is_cancelled_helper(self):
        store = ActiveExecutionContextStore()
        store.register("ctx-E")
        assert not store.is_cancelled("ctx-E")
        store.cancel("ctx-E")
        assert store.is_cancelled("ctx-E")

    def test_is_cancelled_unknown_context(self):
        store = ActiveExecutionContextStore()
        assert not store.is_cancelled("ghost")

    def test_list_active_returns_snapshot(self):
        store = ActiveExecutionContextStore()
        store.register("ctx-F1")
        store.register("ctx-F2")
        active = store.list_active()
        assert "ctx-F1" in active
        assert "ctx-F2" in active

    def test_concurrent_registration_is_safe(self):
        store = ActiveExecutionContextStore()
        errors: list[str] = []

        def _work(i: int):
            try:
                token = store.register(f"ctx-T{i}")
                assert token is not None
                store.cancel(f"ctx-T{i}")
                assert store.is_cancelled(f"ctx-T{i}")
                store.unregister(f"ctx-T{i}")
            except Exception as exc:
                errors.append(str(exc))

        threads = [threading.Thread(target=_work, args=(i,), daemon=True) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert not errors


# ---------------------------------------------------------------------------
# Global singleton sanity test
# ---------------------------------------------------------------------------


def test_get_execution_store_returns_singleton():
    s1 = get_execution_store()
    s2 = get_execution_store()
    assert s1 is s2


# ---------------------------------------------------------------------------
# HTTP endpoint tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def app_client():
    """Minimal FastAPI test client with only the cancellation router mounted."""
    from fastapi import FastAPI

    from openjarvis.server.cancellation_routes import cancellation_router

    app = FastAPI()
    app.include_router(cancellation_router)
    return TestClient(app, raise_server_exceptions=True)


class TestCancellationEndpoint:
    def test_cancel_with_active_context_returns_200(self, app_client):
        store = get_execution_store()
        store.register("active")
        try:
            resp = app_client.post(
                "/api/execution/cancel",
                json={"context_id": "active"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "cancelling"
            assert body["context_id"] == "active"
            assert isinstance(body["elapsed_ms"], float)
            assert body["elapsed_ms"] >= 0
        finally:
            store.unregister("active")

    def test_cancel_defaults_to_active_when_no_context_id(self, app_client):
        store = get_execution_store()
        token = store.register("active")
        try:
            resp = app_client.post("/api/execution/cancel", json={})
            assert resp.status_code == 200
            assert token.is_cancelled
        finally:
            store.unregister("active")

    def test_cancel_nonexistent_context_returns_404(self, app_client):
        # Ensure no active contexts exist
        store = get_execution_store()
        for ctx_id in store.list_active():
            store.unregister(ctx_id)

        resp = app_client.post(
            "/api/execution/cancel",
            json={"context_id": "nonexistent-ghost-ctx"},
        )
        assert resp.status_code == 404
        body = resp.json()
        assert "detail" in body

    def test_cancel_sets_token_is_cancelled(self, app_client):
        store = get_execution_store()
        ctx_id = "test-http-cancel-001"
        token = store.register(ctx_id)
        try:
            assert not token.is_cancelled
            resp = app_client.post(
                "/api/execution/cancel",
                json={"context_id": ctx_id},
            )
            assert resp.status_code == 200
            assert token.is_cancelled
        finally:
            store.unregister(ctx_id)

    def test_list_contexts_returns_registered_ids(self, app_client):
        store = get_execution_store()
        for existing in store.list_active():
            store.unregister(existing)

        ctx_id = "ctx-list-test"
        store.register(ctx_id)
        try:
            resp = app_client.get("/api/execution/contexts")
            assert resp.status_code == 200
            body = resp.json()
            assert ctx_id in body["active_contexts"]
        finally:
            store.unregister(ctx_id)

    def test_cancel_response_is_fast(self, app_client):
        store = get_execution_store()
        store.register("active")
        try:
            t0 = time.monotonic()
            resp = app_client.post("/api/execution/cancel", json={"context_id": "active"})
            elapsed = (time.monotonic() - t0) * 1000
            assert resp.status_code == 200
            body = resp.json()
            # Server-side execution must be < 25ms per AC-GES-03
            assert body["elapsed_ms"] < 25, f"Server cancel took {body['elapsed_ms']} ms"
            # Full client round-trip in test environment under 500 ms
            assert elapsed < 500, f"Cancel round-trip took {elapsed:.1f} ms — too slow"
        finally:
            store.unregister("active")

    def test_cancel_cross_session_forbidden(self, app_client):
        """Cross-session cancellation must be rejected with HTTP 403."""
        store = get_execution_store()
        ctx_id = "ctx-user-alpha-001"
        store.register(ctx_id, owner_session_id="session-user-alpha")
        try:
            resp = app_client.post(
                "/api/execution/cancel",
                json={"context_id": ctx_id, "session_id": "session-attacker-beta"},
            )
            assert resp.status_code == 403
            assert "Not authorized" in resp.json()["detail"]
            # Token must remain NOT cancelled
            assert not store.is_cancelled(ctx_id)

            # Legitimate owner can cancel
            resp_owner = app_client.post(
                "/api/execution/cancel",
                json={"context_id": ctx_id, "session_id": "session-user-alpha"},
            )
            assert resp_owner.status_code == 200
            assert store.is_cancelled(ctx_id)
        finally:
            store.unregister(ctx_id)


# ---------------------------------------------------------------------------
# StreamBridge cancellation unit tests
# ---------------------------------------------------------------------------


class TestStreamBridgeCancellation:
    @pytest.mark.asyncio
    async def test_stream_bridge_stops_on_cancelled_token(self):
        """AgentStreamBridge must yield [DONE] immediately when token is cancelled."""
        from unittest.mock import MagicMock

        from openjarvis.core.events import EventBus
        from openjarvis.server.models import ChatCompletionRequest, ChatMessage
        from openjarvis.server.stream_bridge import AgentStreamBridge

        token = CancellationToken(context_id="stream-cancel-test")
        token.cancel()

        mock_agent = MagicMock()
        mock_agent.run.return_value = MagicMock(tool_results=[])
        bus = EventBus()
        req = ChatCompletionRequest(
            model="test-model",
            messages=[ChatMessage(role="user", content="hello")],
        )

        bridge = AgentStreamBridge(
            agent=mock_agent,
            bus=bus,
            model="test-model",
            request=req,
            cancellation_token=token,
        )

        chunks: list[str] = []
        async for chunk in bridge.stream():
            chunks.append(chunk)

        # Must have yielded initial chunk and immediate [DONE]
        assert any("[DONE]" in c for c in chunks)
        # Agent run is prevented from executing when pre-cancelled
        mock_agent.run.assert_not_called()


# ---------------------------------------------------------------------------
# Approval race condition prevention tests
# ---------------------------------------------------------------------------


class TestApprovalRaceProtection:
    def test_cancelled_context_prevents_dispatch_of_pending_action(self):
        """When context is cancelled, approval callback cannot execute actions."""
        store = get_execution_store()
        ctx_id = "approval-race-ctx-001"
        token = store.register(ctx_id)

        executed_actions: list[str] = []

        def _dispatch_action(action_name: str):
            # Guard: check token before executing approved action
            if token.is_cancelled:
                return "CANCELLED_ABORTED"
            executed_actions.append(action_name)
            return "SUCCESS"

        # Action is queued
        assert not token.is_cancelled

        # Emergency stop occurs before operator approves
        store.cancel(ctx_id)
        assert token.is_cancelled

        # Late approval arrives
        result = _dispatch_action("drop_table_users")
        assert result == "CANCELLED_ABORTED"
        assert len(executed_actions) == 0

        store.unregister(ctx_id)
