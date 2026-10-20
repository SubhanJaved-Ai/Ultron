"""Tests for WorkflowManageTool: DAG synthesis, inspection, execution, and webhooks."""

from pathlib import Path

from openjarvis.tools.workflow_manage import WorkflowManageTool


def test_workflow_manage_lifecycle(tmp_path: Path):
    wf_dir = tmp_path / "workflows"
    tool = WorkflowManageTool(workflows_dir=wf_dir)

    # 1. Create a 2-node pipeline with an edge
    nodes = [
        {"id": "step_a", "type": "agent", "agent": "simple"},
        {"id": "step_b", "type": "agent", "agent": "simple"},
    ]
    edges = [
        {"source": "step_a", "target": "step_b"},
    ]

    res_create = tool.execute(
        action="create",
        name="daily_digest_flow",
        nodes=nodes,
        edges=edges,
    )
    assert res_create.success is True
    assert "Created workflow DAG 'daily_digest_flow'" in res_create.content

    # 2. Inspect workflow
    res_inspect = tool.execute(action="inspect", name="daily_digest_flow")
    assert res_inspect.success is True
    assert "step_a -> step_b" in res_inspect.content

    # 3. List workflows
    res_list = tool.execute(action="list")
    assert res_list.success is True
    assert "daily_digest_flow" in res_list.content

    # 4. Run workflow
    res_run = tool.execute(action="run", name="daily_digest_flow", input="start job")
    assert res_run.success is True
    assert "Execution Trace: daily_digest_flow" in res_run.content
    assert "SUCCESS" in res_run.content

    # 5. Delete workflow
    res_del = tool.execute(action="delete", name="daily_digest_flow")
    assert res_del.success is True
    assert "Deleted workflow" in res_del.content


def test_workflow_manage_invalid_dag(tmp_path: Path):
    wf_dir = tmp_path / "workflows"
    tool = WorkflowManageTool(workflows_dir=wf_dir)

    # Cycle: step_a -> step_b -> step_a
    nodes = [
        {"id": "step_a", "type": "agent"},
        {"id": "step_b", "type": "agent"},
    ]
    edges = [
        {"source": "step_a", "target": "step_b"},
        {"source": "step_b", "target": "step_a"},
    ]

    res = tool.execute(action="create", name="cycle_flow", nodes=nodes, edges=edges)
    assert res.success is False
    assert "Invalid workflow DAG" in res.content
