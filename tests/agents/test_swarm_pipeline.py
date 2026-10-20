"""Unit and integration tests for Multi-Subagent Swarm Pipelines & Blackboard."""

from __future__ import annotations

import json

from openjarvis.agents.subagents import (
    SubagentManager,
    SubagentRecord,
    SwarmBlackboard,
    get_subagent_manager,
    reset_subagent_manager,
)
from openjarvis.tools.agent_tools import (
    SubagentBroadcastTool,
    SubagentPipelineTool,
    SubagentQueryTool,
    SubagentShareTool,
)


class TestSwarmBlackboard:
    def test_blackboard_set_and_get(self):
        bb = SwarmBlackboard(swarm_id="swarm_test_1")
        entry = bb.set(
            "findings",
            "AI market growing 30%",
            category="artifact",
            author_subagent_id="sub_1",
        )

        assert entry.key == "findings"
        assert entry.value == "AI market growing 30%"
        assert entry.category == "artifact"
        assert entry.author_subagent_id == "sub_1"

        # Read back value
        val = bb.get("findings")
        assert val == "AI market growing 30%"

        # Read back non-existent key
        assert bb.get("non_existent", "fallback") == "fallback"

    def test_blackboard_list_entries_and_filtering(self):
        bb = SwarmBlackboard(swarm_id="swarm_test_2")
        bb.set("data_1", [1, 2, 3], category="data")
        bb.set("note_1", "Check latency", category="note")
        bb.set("data_2", {"status": "ok"}, category="data")

        all_entries = bb.list_entries()
        assert len(all_entries) == 3

        data_entries = bb.list_entries(category="data")
        assert len(data_entries) == 2
        assert {e.key for e in data_entries} == {"data_1", "data_2"}

        note_entries = bb.list_entries(category="note")
        assert len(note_entries) == 1
        assert note_entries[0].key == "note_1"

    def test_blackboard_to_dict_and_summary(self):
        bb = SwarmBlackboard(swarm_id="swarm_test_3")
        assert bb.to_summary_text() == "(empty blackboard)"

        bb.set("lead_score", 95, category="data")
        bb.set("summary", "Top tier customer", category="artifact")

        as_dict = bb.to_dict()
        assert "lead_score" in as_dict
        assert as_dict["lead_score"]["value"] == 95

        summary_text = bb.to_summary_text()
        assert "lead_score: 95" in summary_text
        assert "summary: Top tier customer" in summary_text


class TestSwarmPipelineExecution:
    def setup_method(self):
        reset_subagent_manager()

    def teardown_method(self):
        reset_subagent_manager()

    def test_execute_pipeline_three_stages_with_templating(self):
        mgr = SubagentManager()

        # Mock runner simulating agent turns that observe templates
        def mock_runner(record: SubagentRecord) -> str:
            if "Researcher" in record.name:
                return "Raw findings: 5 vulnerabilities identified in auth module."
            elif "Analyst" in record.name:
                return f"Analysis based on [{record.task}]: Severity is CRITICAL."
            elif "Reviewer" in record.name:
                return f"Final sign-off on [{record.task}]: Approved for mitigation."
            return f"Done: {record.task}"

        mgr.set_dependencies(agent_runner=mock_runner)

        stages = [
            {
                "name": "Researcher",
                "task": "Audit authentication security issues.",
                "output_key": "raw_audit",
            },
            {
                "name": "Analyst",
                "task": "Evaluate impact of prior results: {previous_result}",
                "output_key": "severity_analysis",
            },
            {
                "name": "Reviewer",
                "task": (
                    "Review recommendations: {previous_result} | "
                    "Reference: {stage:Researcher}"
                ),
                "output_key": "final_approval",
            },
        ]

        result = mgr.execute_pipeline(stages, name="Security Audit Pipeline")

        assert result.status == "completed"
        assert result.stages_completed == 3
        assert result.total_stages == 3
        assert len(result.stage_results) == 3
        assert "Approved for mitigation" in result.final_output

        # Verify blackboard artifacts were recorded
        bb = mgr.get_blackboard(result.swarm_id)
        assert (
            bb.get("raw_audit")
            == "Raw findings: 5 vulnerabilities identified in auth module."
        )
        assert "Severity is CRITICAL" in str(bb.get("severity_analysis"))
        assert "Approved for mitigation" in str(bb.get("final_approval"))

    def test_execute_pipeline_stage_failure_stops_pipeline(self):
        mgr = SubagentManager()

        def failing_runner(record: SubagentRecord) -> str:
            if "Stage-2" in record.name:
                raise RuntimeError("Service timeout connecting to database")
            return "Stage succeeded."

        mgr.set_dependencies(agent_runner=failing_runner)

        stages = [
            {"name": "Stage-1", "task": "Step 1"},
            {"name": "Stage-2", "task": "Step 2", "optional": False},
            {"name": "Stage-3", "task": "Step 3"},
        ]

        result = mgr.execute_pipeline(stages, name="Failure Pipeline")

        assert result.status == "failed"
        assert result.stages_completed == 1
        assert "failed" in (result.error or "").lower()
        # Stage 3 should never have run
        assert len(result.stage_results) == 2

    def test_execute_pipeline_optional_stage_failure_continues(self):
        mgr = SubagentManager()

        def runner_with_optional_fail(record: SubagentRecord) -> str:
            if "OptionalEnricher" in record.name:
                raise ConnectionError("External API rate limited")
            return f"Processed: {record.name}"

        mgr.set_dependencies(agent_runner=runner_with_optional_fail)

        stages = [
            {"name": "Stage-1", "task": "Initial gather"},
            {"name": "OptionalEnricher", "task": "Enrich data", "optional": True},
            {"name": "FinalStage", "task": "Final package"},
        ]

        result = mgr.execute_pipeline(stages, name="Resilient Pipeline")

        assert result.status == "completed"
        assert result.stages_completed == 2
        assert len(result.stage_results) == 3
        assert result.stage_results[1]["status"] == "failed"
        assert result.stage_results[2]["status"] == "completed"

    def test_broadcast_to_swarm(self):
        mgr = SubagentManager()
        # Add mock runner that sleeps to simulate running subagents
        r1 = SubagentRecord(
            id="sub_1",
            name="Worker 1",
            task="Task 1",
            status="running",
            swarm_id="swarm_alpha",
        )
        r2 = SubagentRecord(
            id="sub_2",
            name="Worker 2",
            task="Task 2",
            status="running",
            swarm_id="swarm_alpha",
        )
        r3 = SubagentRecord(
            id="sub_3",
            name="Worker 3",
            task="Task 3",
            status="completed",
            swarm_id="swarm_alpha",
        )
        r4 = SubagentRecord(
            id="sub_4",
            name="Worker 4",
            task="Task 4",
            status="running",
            swarm_id="swarm_beta",
        )

        mgr._subagents = {"sub_1": r1, "sub_2": r2, "sub_3": r3, "sub_4": r4}

        notified = mgr.broadcast_to_swarm(
            "swarm_alpha", "Emergency stop: user revoked permission."
        )
        assert len(notified) == 2
        assert set(notified) == {"sub_1", "sub_2"}
        assert "Update: Emergency stop" in r1.task
        assert "Update: Emergency stop" in r2.task


class TestSwarmTools:
    def setup_method(self):
        reset_subagent_manager()

    def teardown_method(self):
        reset_subagent_manager()

    def test_subagent_share_and_query_tools(self):
        share_tool = SubagentShareTool()
        query_tool = SubagentQueryTool()

        # 1. Share an entry
        res_share = share_tool.execute(
            key="market_forecast",
            value={"2027_growth": "45%", "leader": "Jarvis"},
            swarm_id="swarm_tools_1",
            category="data",
        )
        assert res_share.success is True
        share_data = json.loads(res_share.content)
        assert share_data["key"] == "market_forecast"
        assert share_data["status"] == "shared"

        # 2. Query specific entry
        res_query = query_tool.execute(
            key="market_forecast",
            swarm_id="swarm_tools_1",
        )
        assert res_query.success is True
        query_data = json.loads(res_query.content)
        assert query_data["found"] is True
        assert query_data["entry"]["value"]["2027_growth"] == "45%"

        # 3. Query all entries
        res_query_all = query_tool.execute(swarm_id="swarm_tools_1")
        assert res_query_all.success is True
        all_data = json.loads(res_query_all.content)
        assert all_data["count"] == 1
        assert all_data["entries"][0]["key"] == "market_forecast"

    def test_subagent_pipeline_tool_execution(self):
        mgr = get_subagent_manager()
        mgr.set_dependencies(agent_runner=lambda r: f"Output for {r.name}")

        pipeline_tool = SubagentPipelineTool()
        stages_json = json.dumps(
            [
                {"name": "StageA", "task": "Do part A"},
                {"name": "StageB", "task": "Do part B with {previous_result}"},
            ]
        )

        res = pipeline_tool.execute(stages=stages_json, name="Tool Pipeline")
        assert res.success is True
        data = json.loads(res.content)
        assert data["status"] == "completed"
        assert data["stages_completed"] == 2
        assert len(data["stage_results"]) == 2

    def test_subagent_broadcast_tool(self):
        mgr = get_subagent_manager()
        r = SubagentRecord(
            id="sub_live",
            name="Live Worker",
            task="Work",
            status="running",
            swarm_id="swarm_bc",
        )
        mgr._subagents = {"sub_live": r}

        bc_tool = SubagentBroadcastTool()
        res = bc_tool.execute(swarm_id="swarm_bc", message="Priority update.")
        assert res.success is True
        data = json.loads(res.content)
        assert data["notified_count"] == 1
        assert "sub_live" in data["notified_subagents"]
