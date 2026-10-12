"""Tests for N8NTool bridge."""

import json
from unittest.mock import MagicMock, patch

from openjarvis.tools.n8n_tool import N8NTool


def test_n8n_trigger_webhook_success():
    tool = N8NTool()

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b'{"message": "Workflow started successfully"}'
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = tool.execute(
            action="trigger_webhook",
            webhook_url="https://n8n.example.com/webhook/test-flow",
            payload={"lead_id": 12345},
        )

    assert res.success is True
    assert "Successfully triggered n8n webhook (200)" in res.content
    assert "Workflow started successfully" in res.content


def test_n8n_list_workflows_success():
    tool = N8NTool()

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps(
        {
            "data": [
                {"id": "wf_1", "name": "Sync Stripe to Slack", "active": True},
                {"id": "wf_2", "name": "GitHub Issue Classifier", "active": False},
            ]
        }
    ).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = tool.execute(
            action="list_workflows",
            base_url="https://n8n.example.com",
            api_key="secret-key",
        )

    assert res.success is True
    assert "Sync Stripe to Slack (ACTIVE)" in res.content
    assert "GitHub Issue Classifier (INACTIVE)" in res.content


def test_n8n_validation():
    tool = N8NTool()
    res = tool.execute(action="trigger_webhook", webhook_url="")
    assert res.success is False
    assert "'webhook_url' is required" in res.content
