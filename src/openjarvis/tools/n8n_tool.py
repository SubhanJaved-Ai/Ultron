"""N8NTool — bridge tool for triggering and commanding n8n automation instances.

Enables Jarvis to control external n8n instances: triggering n8n webhooks,
listing available n8n workflows, and executing n8n pipelines via REST API.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec

logger = logging.getLogger(__name__)


@ToolRegistry.register("n8n_manage")
class N8NTool(BaseTool):
    """Bridge tool for triggering and inspecting n8n automations."""

    tool_id = "n8n_manage"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="n8n_manage",
            description=(
                "Interact with external n8n automation instances. "
                "Actions: "
                "'trigger_webhook' (send data payload to an n8n webhook URL), "
                "'list_workflows' (fetch workflows from an n8n instance via API), "
                "'run_workflow' (trigger a workflow via n8n REST API)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["trigger_webhook", "list_workflows", "run_workflow"],
                        "description": "Action to perform with n8n.",
                    },
                    "webhook_url": {
                        "type": "string",
                        "description": "Full n8n webhook URL (for 'trigger_webhook').",
                    },
                    "payload": {
                        "type": "object",
                        "description": "JSON payload object to send to the webhook or workflow.",
                    },
                    "base_url": {
                        "type": "string",
                        "description": "n8n base URL (e.g. 'http://localhost:5678', default: env N8N_BASE_URL).",
                    },
                    "api_key": {
                        "type": "string",
                        "description": "n8n API Key (default: env N8N_API_KEY).",
                    },
                    "workflow_id": {
                        "type": "string",
                        "description": "Target n8n workflow ID (for 'run_workflow').",
                    },
                },
                "required": ["action"],
            },
            category="workflow",
        )

    def execute(self, **params: Any) -> ToolResult:
        action = params.get("action", "trigger_webhook")
        base_url = (
            params.get("base_url")
            or os.environ.get("N8N_BASE_URL")
            or "http://localhost:5678"
        ).rstrip("/")
        api_key = params.get("api_key") or os.environ.get("N8N_API_KEY", "")

        if action == "trigger_webhook":
            webhook_url = params.get("webhook_url", "").strip()
            if not webhook_url:
                return ToolResult(
                    tool_name=self.spec.name,
                    success=False,
                    content="'webhook_url' is required to trigger an n8n webhook.",
                )
            payload = params.get("payload") or {}
            return self._trigger_webhook(webhook_url, payload)

        elif action == "list_workflows":
            return self._list_workflows(base_url, api_key)

        elif action == "run_workflow":
            workflow_id = params.get("workflow_id", "").strip()
            if not workflow_id:
                return ToolResult(
                    tool_name=self.spec.name,
                    success=False,
                    content="'workflow_id' is required for run_workflow.",
                )
            payload = params.get("payload") or {}
            return self._run_workflow(base_url, api_key, workflow_id, payload)

        return ToolResult(
            tool_name=self.spec.name,
            success=False,
            content=f"Unknown action: {action}",
        )

    def _trigger_webhook(self, url: str, payload: Dict[str, Any]) -> ToolResult:
        """Send HTTP POST to an n8n webhook endpoint."""
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Jarvis-2.0-Automation-Bridge",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp_text = resp.read().decode("utf-8")
                return ToolResult(
                    tool_name=self.spec.name,
                    success=True,
                    content=f"Successfully triggered n8n webhook ({resp.status}):\n{resp_text}",
                )
        except urllib.error.HTTPError as e:
            err_text = e.read().decode("utf-8", errors="ignore")
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content=f"n8n webhook HTTP Error {e.code}: {err_text}",
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content=f"Failed to connect to n8n webhook: {e}",
            )

    def _list_workflows(self, base_url: str, api_key: str) -> ToolResult:
        """Fetch list of workflows from n8n REST API."""
        url = f"{base_url}/api/v1/workflows"
        headers = {"User-Agent": "Jarvis-2.0-Automation-Bridge"}
        if api_key:
            headers["X-N8N-API-KEY"] = api_key

        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                workflows = data.get("data", [])
                lines = [f"n8n Workflows ({len(workflows)} found):"]
                for wf in workflows:
                    active = "ACTIVE" if wf.get("active") else "INACTIVE"
                    lines.append(f"- [{wf.get('id')}] {wf.get('name')} ({active})")
                return ToolResult(
                    tool_name=self.spec.name,
                    success=True,
                    content="\n".join(lines),
                )
        except Exception as e:
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content=f"Error connecting to n8n API at {url}: {e}",
            )

    def _run_workflow(
        self,
        base_url: str,
        api_key: str,
        workflow_id: str,
        payload: Dict[str, Any],
    ) -> ToolResult:
        """Trigger workflow execution via n8n API."""
        url = f"{base_url}/api/v1/workflows/{workflow_id}/run"
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Jarvis-2.0-Automation-Bridge",
        }
        if api_key:
            headers["X-N8N-API-KEY"] = api_key

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data_bytes, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp_text = resp.read().decode("utf-8")
                return ToolResult(
                    tool_name=self.spec.name,
                    success=True,
                    content=f"n8n workflow {workflow_id} executed successfully:\n{resp_text}",
                )
        except Exception as e:
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content=f"Error triggering n8n workflow {workflow_id}: {e}",
            )
