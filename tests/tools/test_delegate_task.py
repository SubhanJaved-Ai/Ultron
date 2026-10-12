"""Tests for DelegateTaskTool: single and parallel batch delegation."""

import time

from openjarvis.tools.delegate_task import DelegateTaskTool


def test_delegate_single_task():
    def mock_worker(task: str, context: str | None) -> str:
        return f"Completed: {task.upper()}"

    tool = DelegateTaskTool(worker_fn=mock_worker)
    res = tool.execute(task="analyze logs", context="from last 1 hour")

    assert res.success is True
    assert "Delegated 1 subagent task(s): 1 completed, 0 failed" in res.content
    assert "Completed: ANALYZE LOGS" in res.content


def test_delegate_batch_parallel_tasks():
    started_times = []

    def mock_worker(task: str, context: str | None) -> str:
        started_times.append(time.time())
        time.sleep(0.05)  # Simulate concurrent work
        return f"Finished: {task}"

    tool = DelegateTaskTool(worker_fn=mock_worker, default_max_concurrency=3)
    tasks = [
        {"id": "t1", "task": "Task One"},
        {"id": "t2", "task": "Task Two"},
        {"id": "t3", "task": "Task Three"},
    ]

    start = time.time()
    res = tool.execute(tasks=tasks)
    duration = time.time() - start

    assert res.success is True
    assert "Delegated 3 subagent task(s): 3 completed, 0 failed" in res.content
    assert "Finished: Task One" in res.content
    assert "Finished: Task Two" in res.content
    assert "Finished: Task Three" in res.content
    # Parallel execution duration should be much less than sequential (3 * 0.05 = 0.15 + overhead)
    assert duration < 0.8


def test_delegate_task_failure_handling():
    def failing_worker(task: str, context: str | None) -> str:
        if "error" in task:
            raise ValueError("Deliberate error in subagent")
        return "OK"

    tool = DelegateTaskTool(worker_fn=failing_worker)
    res = tool.execute(
        tasks=[
            {"task": "safe task"},
            {"task": "error task"},
        ]
    )

    assert res.success is False
    assert "1 completed, 1 failed" in res.content
    assert "Deliberate error in subagent" in res.content
