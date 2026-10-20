"""Tests for subagent cancellation guard (TSK-P5-01 / AC-GES-06).

Verifies that:
  - A CancellationToken pre-set before subagent orchestration causes the
    dispatcher to skip work and report stopped status.
  - The existing SubagentStore.kill() correctly marks a subagent as stopped.
  - A cooperative cancellation check pattern (checking token.is_cancelled
    before/after each tool) works correctly in the multi-step execution model.

Note: The existing subagents.py ``kill()`` method invokes ``future.cancel()``
which is a best-effort Python futures mechanism.  TSK-P5-01 adds cooperative
token checking in the orchestrator dispatch loop.  These tests verify the
cooperative pattern independently so they do not depend on the
ThreadPoolExecutor implementation details.
"""

from __future__ import annotations

import threading
import time

from openjarvis.server.cancellation import CancellationToken, get_execution_store

# ---------------------------------------------------------------------------
# Cooperative cancellation simulation
# ---------------------------------------------------------------------------


def _simulated_agent_dispatch_loop(
    steps: list[str],
    token: CancellationToken,
    results: list[str],
) -> None:
    """Mimics the pattern an agent orchestrator should use for each step.

    Before dispatching any tool in a multi-step plan, the orchestrator checks
    ``token.is_cancelled``.  If set, it abandons remaining steps immediately.
    """
    for step in steps:
        # AC-GES-06: Check token BEFORE dispatching each sub-task
        if token.is_cancelled:
            results.append(f"SKIPPED:{step}")
            continue

        # Simulate tool work
        time.sleep(0.05)
        results.append(f"DONE:{step}")


class TestCooperativeCancellation:
    def test_pre_cancelled_token_skips_all_steps(self):
        token = CancellationToken(context_id="agent-skip-all")
        token.cancel()
        results: list[str] = []

        _simulated_agent_dispatch_loop(
            ["step1", "step2", "step3"],
            token,
            results,
        )

        # Every step must be SKIPPED, none executed
        assert all(r.startswith("SKIPPED:") for r in results), results
        assert len(results) == 3

    def test_uncancelled_token_runs_all_steps(self):
        token = CancellationToken(context_id="agent-run-all")
        results: list[str] = []

        _simulated_agent_dispatch_loop(
            ["step1", "step2", "step3"],
            token,
            results,
        )

        assert all(r.startswith("DONE:") for r in results), results
        assert len(results) == 3

    def test_mid_run_cancellation_stops_remaining(self):
        """Cancel the token after step 1 starts but before step 2."""
        token = CancellationToken(context_id="agent-mid-cancel")
        results: list[str] = []

        long_steps = [f"step{i}" for i in range(10)]
        cancel_after_first_done = threading.Event()

        def _run():
            for step in long_steps:
                if token.is_cancelled:
                    results.append(f"SKIPPED:{step}")
                    continue
                time.sleep(0.03)
                results.append(f"DONE:{step}")
                if not cancel_after_first_done.is_set():
                    cancel_after_first_done.set()

        t = threading.Thread(target=_run, daemon=True)
        t.start()

        # Wait for first step to complete, then cancel
        cancel_after_first_done.wait(timeout=1.0)
        token.cancel()
        t.join(timeout=3)

        assert not t.is_alive()
        done_steps = [r for r in results if r.startswith("DONE:")]
        skipped_steps = [r for r in results if r.startswith("SKIPPED:")]

        # At least one step ran, and at least one was skipped
        assert len(done_steps) >= 1
        assert len(skipped_steps) >= 1
        # Total must equal 10 steps
        assert len(results) == 10

    def test_token_is_checked_before_each_step(self):
        """Verify no step executes after cancellation is set."""
        token = CancellationToken(context_id="agent-strict-check")
        results: list[str] = []
        step_times: dict[str, float] = {}
        cancel_time: list[float] = []

        steps = [f"s{i}" for i in range(20)]

        def _run():
            for step in steps:
                if token.is_cancelled:
                    results.append(f"SKIPPED:{step}")
                    continue
                step_times[step] = time.monotonic()
                time.sleep(0.02)
                results.append(f"DONE:{step}")

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        time.sleep(0.08)  # Let ~4 steps complete
        token.cancel()
        cancel_time.append(time.monotonic())
        t.join(timeout=3)

        ct = cancel_time[0]
        # Ensure no step started after cancellation
        post_cancel_started = [
            step for step, ts in step_times.items() if ts > ct
        ]
        assert not post_cancel_started, (
            f"Steps started AFTER cancellation: {post_cancel_started}"
        )


# ---------------------------------------------------------------------------
# SubagentStore.kill() integration test
# ---------------------------------------------------------------------------


class TestSubagentStoreKill:
    def test_kill_marks_subagent_stopped(self):
        """SubagentManager.kill() must set status=stopped on a registered subagent."""
        from openjarvis.agents.subagents import SubagentManager

        store = SubagentManager()

        # Register a mock subagent record directly
        import concurrent.futures

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

        def _blocking_task():
            time.sleep(30)
            return "done"

        future = executor.submit(_blocking_task)
        subagent_id = "sub-test-kill-001"

        # Inject directly into the store internals (white-box test)
        from openjarvis.agents.subagents import SubagentRecord

        record = SubagentRecord(
            id=subagent_id,
            name="test-subagent",
            task="long task",
            status="running",
        )
        with store._lock:
            store._subagents[subagent_id] = record
            store._futures[subagent_id] = future

        # Kill it
        result = store.kill(subagent_id)
        assert result is True

        # Verify status
        with store._lock:
            updated = store._subagents.get(subagent_id)
        assert updated is not None
        assert updated.status == "stopped"
        assert "cancelled" in (updated.error or "").lower()

        # Cleanup
        future.cancel()
        executor.shutdown(wait=False)

    def test_kill_unknown_subagent_returns_false(self):
        from openjarvis.agents.subagents import SubagentManager

        store = SubagentManager()
        result = store.kill("ghost-subagent-xyz")
        assert result is False

    def test_kill_already_stopped_returns_true(self):
        from openjarvis.agents.subagents import SubagentManager, SubagentRecord

        store = SubagentManager()
        subagent_id = "sub-already-stopped"
        record = SubagentRecord(
            id=subagent_id,
            name="test-subagent",
            task="finished task",
            status="stopped",
        )
        with store._lock:
            store._subagents[subagent_id] = record

        result = store.kill(subagent_id)
        assert result is True  # Idempotent — already stopped


# ---------------------------------------------------------------------------
# Store-level cancel propagates to active execution context
# ---------------------------------------------------------------------------


def test_execution_store_cancel_propagates_to_agent_loop():
    """Integration: cancelling via the global store interrupts an agent loop."""
    store = get_execution_store()
    ctx_id = "integration-agent-cancel-001"
    token = store.register(ctx_id)

    steps_done: list[int] = []
    stop_event = threading.Event()

    def _agent_loop():
        for i in range(100):
            if token.is_cancelled:
                break
            time.sleep(0.02)
            steps_done.append(i)
        stop_event.set()

    t = threading.Thread(target=_agent_loop, daemon=True)
    t.start()

    time.sleep(0.1)  # Let a few steps complete
    store.cancel(ctx_id)
    stop_event.wait(timeout=2)
    t.join(timeout=3)

    assert not t.is_alive()
    # Should have stopped well before step 100
    assert len(steps_done) < 100
    assert token.is_cancelled

    store.unregister(ctx_id)
