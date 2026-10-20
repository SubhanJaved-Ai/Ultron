"""Deterministic integration tests for Multi-Agent Orchestration & Delegated Handoffs.

Validates the complete application-level multi-agent lifecycle:
Request/Task -> Agent/Team Selection -> Delegated Handoff -> Blackboard & Artifact Sharing ->
Result Propagation -> Final Task/Pipeline State.

Note on Limitations:
These tests use deterministic mock/simulated agent runners to verify the orchestration,
handoff, blackboard, timeout, and failure mechanics. They validate system correctness
without requiring live external LLM provider API credentials or live network availability.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List

import pytest

from openjarvis.agents.subagents import (
    SubagentManager,
    SubagentRecord,
    SwarmBlackboard,
    SwarmPipelineResult,
    SwarmPipelineStage,
    get_subagent_manager,
    reset_subagent_manager,
)
from openjarvis.tools.delegate_task import DelegateTaskTool


class TestMultiAgentOrchestrationIntegration:
    """Suite validating multi-agent handoffs, delegation, and blackboard state."""

    def setup_method(self):
        reset_subagent_manager()

    def teardown_method(self):
        reset_subagent_manager()

    def test_multi_agent_pipeline_handoff_success(self):
        """Test sequential multi-agent delegation: ResearchAgent -> AnalysisAgent -> ReviewAgent."""
        mgr = SubagentManager()

        # Simulated agent behavior mimicking LLM-driven team roles
        def agent_team_runner(record: SubagentRecord) -> str:
            if "Researcher" in record.name:
                return "Discovered 3 critical CVEs in dependencies."
            elif "Analyst" in record.name:
                # Must receive the output from the Researcher via template expansion
                assert "Discovered 3 critical CVEs" in record.task
                return "Risk assessment: High exploitability, immediate patch required."
            elif "Reviewer" in record.name:
                # Must receive output from Analyst and reference to Researcher
                assert "Risk assessment" in record.task
                assert "Discovered 3 critical CVEs" in record.task
                return "Final decision: Deploy emergency patch to production."
            return f"Generic completed task: {record.task}"

        mgr.set_dependencies(agent_runner=agent_team_runner)

        stages = [
            {
                "name": "Researcher",
                "task": "Investigate security vulnerabilities in repository dependencies.",
                "output_key": "cve_data",
                "agent_type": "researcher",
            },
            {
                "name": "Analyst",
                "task": "Analyze security implications from: {previous_result}",
                "output_key": "risk_analysis",
                "agent_type": "analyst",
            },
            {
                "name": "Reviewer",
                "task": "Review recommendations: {previous_result} | Initial facts: {stage:Researcher}",
                "output_key": "executive_signoff",
                "agent_type": "reviewer",
            },
        ]

        result = mgr.execute_pipeline(stages, name="Security Team Swarm")

        # Verify pipeline state and handoffs
        assert result.status == "completed"
        assert result.stages_completed == 3
        assert result.total_stages == 3
        assert len(result.stage_results) == 3
        assert "Deploy emergency patch to production" in result.final_output

        # Verify blackboard artifacts and author attribution
        bb = mgr.get_blackboard(result.swarm_id)
        assert bb.get("cve_data") == "Discovered 3 critical CVEs in dependencies."
        assert "High exploitability" in str(bb.get("risk_analysis"))
        assert "Deploy emergency patch" in str(bb.get("executive_signoff"))

        # Verify each stage was attributed to its specific subagent
        cve_entry = bb.get_entry("cve_data")
        assert cve_entry is not None
        assert cve_entry.author_subagent_id is not None
        assert cve_entry.category == "data"

    def test_multi_agent_parallel_batch_delegation(self):
        """Test parallel multi-agent delegation via DelegateTaskTool with isolated contexts."""
        executed_tasks: List[str] = []

        def worker_fn(task: str, context: str | None) -> str:
            executed_tasks.append(task)
            if "frontend" in task.lower():
                return "Frontend audit complete: No XSS vulnerabilities found."
            elif "backend" in task.lower():
                return f"Backend audit complete: Secure endpoints verified for context '{context}'."
            elif "database" in task.lower():
                return "Database audit complete: Parameterized queries in use."
            return "Audit done."

        tool = DelegateTaskTool(worker_fn=worker_fn, default_max_concurrency=4)

        batch = [
            {"id": "agent_fe", "task": "Audit frontend SPA for vulnerabilities", "context": "React 19"},
            {"id": "agent_be", "task": "Audit backend REST endpoints", "context": "FastAPI auth"},
            {"id": "agent_db", "task": "Audit database migration scripts", "context": "PostgreSQL"},
        ]

        result = tool.execute(tasks=batch, max_concurrency=3, timeout=10)

        assert result.success is True
        assert "Delegated 3 subagent task(s): 3 completed, 0 failed/timed out" in result.content
        assert len(executed_tasks) == 3

        metadata = result.metadata or {}
        delegated_results = metadata.get("delegated_results", [])
        assert len(delegated_results) == 3

        statuses = {r["id"]: r["status"] for r in delegated_results}
        assert statuses == {"agent_fe": "completed", "agent_be": "completed", "agent_db": "completed"}

    def test_multi_agent_failure_stops_mandatory_downstream_stages(self):
        """Test failure propagation: mandatory stage failure halts downstream delegation."""
        mgr = SubagentManager()

        def failing_agent_runner(record: SubagentRecord) -> str:
            if "DataIngestion" in record.name:
                return "Ingested 10,000 records."
            elif "DataValidation" in record.name:
                raise ValueError("Corrupted record format at line 452 - schema violation")
            elif "DataModeling" in record.name:
                return "Model built."
            return "Done"

        mgr.set_dependencies(agent_runner=failing_agent_runner)

        stages = [
            {"name": "DataIngestion", "task": "Ingest customer records"},
            {"name": "DataValidation", "task": "Validate schemas", "optional": False},
            {"name": "DataModeling", "task": "Train customer churn model from {previous_result}"},
        ]

        result = mgr.execute_pipeline(stages, name="ETL Machine Learning Swarm")

        assert result.status == "failed"
        assert result.stages_completed == 1
        assert "DataValidation" in (result.error or "")
        assert "schema violation" in (result.error or "")

        # Downstream Modeling stage must never have been spawned
        assert len(result.stage_results) == 2
        assert result.stage_results[0]["status"] == "completed"
        assert result.stage_results[1]["status"] == "failed"

    def test_multi_agent_optional_stage_resilience(self):
        """Test that an optional subagent failure is recorded but does not abort the pipeline."""
        mgr = SubagentManager()

        def resilient_runner(record: SubagentRecord) -> str:
            if "PrimaryWorker" in record.name:
                return "Primary search completed: 42 results."
            elif "OptionalExternalEnricher" in record.name:
                raise TimeoutError("Third-party enrichment API timed out after 5.0s")
            elif "SynthesisWorker" in record.name:
                return f"Final synthesized report generated from: {record.task}"
            return "OK"

        mgr.set_dependencies(agent_runner=resilient_runner)

        stages = [
            {"name": "PrimaryWorker", "task": "Gather internal knowledge"},
            {"name": "OptionalExternalEnricher", "task": "Query external search provider", "optional": True},
            {"name": "SynthesisWorker", "task": "Synthesize summary from: {previous_result}"},
        ]

        result = mgr.execute_pipeline(stages, name="Resilient Search Swarm")

        assert result.status == "completed"
        assert result.stages_completed == 2
        assert result.total_stages == 3
        assert len(result.stage_results) == 3
        assert result.stage_results[1]["status"] == "failed"
        assert result.stage_results[2]["status"] == "completed"
        assert "Final synthesized report" in result.final_output

    def test_multi_agent_swarm_blackboard_isolation(self):
        """Test that separate swarms maintain strict blackboard isolation without data leakage."""
        mgr = SubagentManager()

        bb_security = mgr.get_blackboard("swarm_security_zone")
        bb_marketing = mgr.get_blackboard("swarm_marketing_zone")

        bb_security.set("api_secret_key", "sec_token_999", category="artifact")
        bb_marketing.set("campaign_budget", 50000, category="data")

        # Verify no cross-contamination
        assert bb_security.get("api_secret_key") == "sec_token_999"
        assert bb_security.get("campaign_budget") is None

        assert bb_marketing.get("campaign_budget") == 50000
        assert bb_marketing.get("api_secret_key") is None

    def test_multi_agent_emergency_broadcast_and_cancellation(self):
        """Test broadcasting emergency stop signal to active swarm subagents."""
        mgr = SubagentManager()

        # Create active subagents under a common swarm
        r1 = SubagentRecord(id="sub_worker_1", name="Worker 1", task="Process data chunk 1", status="running", swarm_id="swarm_active")
        r2 = SubagentRecord(id="sub_worker_2", name="Worker 2", task="Process data chunk 2", status="running", swarm_id="swarm_active")
        r3 = SubagentRecord(id="sub_worker_3", name="Worker 3", task="Process data chunk 3", status="completed", swarm_id="swarm_active")

        mgr._subagents = {
            "sub_worker_1": r1,
            "sub_worker_2": r2,
            "sub_worker_3": r3,
        }

        notified = mgr.broadcast_to_swarm("swarm_active", "Emergency Halt: User cancelled task.")
        assert len(notified) == 2
        assert "sub_worker_1" in notified
        assert "sub_worker_2" in notified
        assert "sub_worker_3" not in notified  # Completed agents are not notified

        # Verify task instructions were updated with the emergency notice
        assert "Emergency Halt" in r1.task
        assert "Emergency Halt" in r2.task
