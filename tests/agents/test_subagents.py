"""Tests for OpenClaw-parity Subagent System in Jarvis 2.0."""

from __future__ import annotations

import json
import time

import pytest

from openjarvis.agents.subagents import (
    SubagentManager,
    get_subagent_manager,
    reset_subagent_manager,
)
from openjarvis.tools.agent_tools import (
    SubagentKillTool,
    SubagentListTool,
    SubagentResultTool,
    SubagentSendTool,
    SubagentSpawnTool,
    SubagentStatusTool,
)


class TestSubagentManager:
    def setup_method(self):
        reset_subagent_manager()

    def teardown_method(self):
        reset_subagent_manager()

    def test_spawn_async_basic(self):
        mgr = SubagentManager()
        # Mock runner that finishes quickly
        mgr.set_dependencies(agent_runner=lambda r: f"Report for: {r.task}")

        record = mgr.spawn(
            task="Analyze AI market trends",
            name="MarketAnalyst",
            wait=True,
            timeout=5.0,
        )

        assert record.id.startswith("subagent_")
        assert record.name == "MarketAnalyst"
        assert record.status == "completed"
        assert "Report for: Analyze AI market trends" in record.result
        assert record.started_at is not None
        assert record.completed_at is not None

    def test_spawn_empty_task_raises(self):
        mgr = SubagentManager()
        with pytest.raises(ValueError, match="cannot be empty"):
            mgr.spawn(task="")

    def test_spawn_depth_limiting(self):
        mgr = SubagentManager(max_depth=2)
        mgr.set_dependencies(agent_runner=lambda r: "done")

        # Depth 1: allowed
        r1 = mgr.spawn(task="Top level task", depth=1, wait=True)
        assert r1.status == "completed"

        # Depth 2: allowed
        r2 = mgr.spawn(task="Child subagent task", depth=2, wait=True)
        assert r2.status == "completed"

        # Depth 3: rejected
        with pytest.raises(ValueError, match="nesting depth"):
            mgr.spawn(task="Grandchild subagent task", depth=3)

    def test_list_and_get_subagents(self):
        mgr = SubagentManager()
        mgr.set_dependencies(agent_runner=lambda r: f"Done {r.task}")

        r1 = mgr.spawn(task="Task 1", name="Worker 1", wait=True)
        r2 = mgr.spawn(task="Task 2", name="Worker 2", wait=True)

        all_subs = mgr.list_subagents()
        assert len(all_subs) == 2
        assert {s.id for s in all_subs} == {r1.id, r2.id}

        fetched = mgr.get(r1.id)
        assert fetched is not None
        assert fetched.id == r1.id
        assert fetched.name == "Worker 1"

        filtered = mgr.list_subagents(status="completed")
        assert len(filtered) == 2

    def test_kill_subagent(self):
        mgr = SubagentManager()

        # Runner that simulates a slow job
        def slow_runner(r):
            time.sleep(2.0)
            return "finished"

        mgr.set_dependencies(agent_runner=slow_runner)

        # Spawn non-blocking
        record = mgr.spawn(task="Slow job", wait=False)
        assert record.status in ("pending", "running")

        # Kill
        killed = mgr.kill(record.id)
        assert killed is True
        assert record.status == "stopped"

    def test_send_message_to_subagent(self):
        mgr = SubagentManager()
        r = mgr.spawn(task="Base mission", wait=False)
        success = mgr.send_message(r.id, "Please also include Q3 data")
        assert success is True
        assert "Please also include Q3 data" in r.task

    def test_concurrent_multiple_subagents(self):
        """Test spawning multiple subagents concurrently."""
        mgr = SubagentManager(max_workers=8)

        def runner(r):
            time.sleep(0.05)
            return f"Completed {r.task}"

        mgr.set_dependencies(agent_runner=runner)

        tasks = [f"Sub-task {i}" for i in range(5)]
        records = [mgr.spawn(task=t, wait=False) for t in tasks]

        # Wait for all to complete
        for _ in range(50):
            if all(r.status == "completed" for r in records):
                break
            time.sleep(0.05)

        for r in records:
            assert r.status == "completed"
            assert "Completed Sub-task" in r.result


class TestSubagentTools:
    def setup_method(self):
        reset_subagent_manager()
        mgr = get_subagent_manager()
        mgr.set_dependencies(agent_runner=lambda r: f"Tool result for: {r.task}")

    def teardown_method(self):
        reset_subagent_manager()

    def test_subagent_spawn_tool_sync(self):
        tool = SubagentSpawnTool()
        result = tool.execute(
            task="Find AI security flaws",
            name="SecurityAudit",
            wait=True,
        )
        assert result.success
        data = json.loads(result.content)
        assert data["name"] == "SecurityAudit"
        assert data["status"] == "completed"
        assert "Tool result for: Find AI security flaws" in data["result"]

    def test_subagent_spawn_tool_async(self):
        tool = SubagentSpawnTool()
        result = tool.execute(task="Background indexation", wait=False)
        assert result.success
        data = json.loads(result.content)
        assert data["id"].startswith("subagent_")
        assert data["task"] == "Background indexation"

    def test_subagent_status_tool(self):
        spawn_tool = SubagentSpawnTool()
        spawn_res = spawn_tool.execute(task="Status test", wait=True)
        sub_id = json.loads(spawn_res.content)["id"]

        status_tool = SubagentStatusTool()
        status_res = status_tool.execute(subagent_id=sub_id)
        assert status_res.success
        data = json.loads(status_res.content)
        assert data["id"] == sub_id
        assert data["status"] == "completed"

    def test_subagent_list_tool(self):
        spawn_tool = SubagentSpawnTool()
        spawn_tool.execute(task="Task A", wait=True)
        spawn_tool.execute(task="Task B", wait=True)

        list_tool = SubagentListTool()
        res = list_tool.execute()
        assert res.success
        items = json.loads(res.content)
        assert len(items) >= 2

    def test_subagent_result_tool(self):
        spawn_tool = SubagentSpawnTool()
        spawn_res = spawn_tool.execute(task="Generate summary report", wait=True)
        sub_id = json.loads(spawn_res.content)["id"]

        result_tool = SubagentResultTool()
        res = result_tool.execute(subagent_id=sub_id)
        assert res.success
        assert "Tool result for: Generate summary report" in res.content

    def test_subagent_kill_and_send_tools(self):
        spawn_tool = SubagentSpawnTool()
        spawn_res = spawn_tool.execute(task="Ongoing job", wait=False)
        sub_id = json.loads(spawn_res.content)["id"]

        send_tool = SubagentSendTool()
        send_res = send_tool.execute(subagent_id=sub_id, message="More info")
        assert send_res.success

        kill_tool = SubagentKillTool()
        kill_res = kill_tool.execute(subagent_id=sub_id)
        assert kill_res.success
        assert json.loads(kill_res.content)["status"] == "stopped"

    def test_openclaw_sessions_spawn_alias(self):
        """Verify OpenClaw compatibility alias `sessions_spawn` works."""
        import importlib

        import openjarvis.tools.agent_tools
        from openjarvis.core.registry import ToolRegistry

        importlib.reload(openjarvis.tools.agent_tools)

        assert ToolRegistry.contains("sessions_spawn")
        tool = ToolRegistry.create("sessions_spawn")
        res = tool.execute(task="Run claw task", wait=True)
        assert res.success
        data = json.loads(res.content)
        assert "Tool result for: Run claw task" in data["result"]
