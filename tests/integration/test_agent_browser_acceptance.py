"""User-level acceptance scenario: autonomous browser task execution from agent workflow.

Validates that an Ultron agent configured with browser tools can resolve them,
dispatch them via ToolExecutor, and accomplish a multi-step web task against
a real browser engine.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Generator

import pytest

from openjarvis.agents.tool_resolver import resolve_agent_tools
from openjarvis.core.types import ToolCall
from openjarvis.tools._stubs import ToolExecutor
from openjarvis.tools.browser import close_active_browser_session


class _AcceptanceHandler(BaseHTTPRequestHandler):
    """Local deterministic fixture server for user acceptance testing."""

    def log_message(self, format: str, *args) -> None:
        pass

    def do_GET(self) -> None:
        if self.path == "/":
            content = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Ultron Agent Portal</title>
</head>
<body>
    <h1>Executive Control Center</h1>
    <p id="portal-status">System Operational</p>

    <!-- Interactive action button -->
    <button id="activate-btn" onclick="document.getElementById('task-state').innerText='Agent Task Active'">
        Activate Workflow
    </button>
    <div id="task-state">Pending Activation</div>

    <!-- Accessible form field with label -->
    <form id="workflow-form">
        <label for="project-input">Project Name</label>
        <input type="text" id="project-input" name="project" placeholder="Enter project name" />
    </form>
</body>
</html>"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content.encode("utf-8"))))
            self.end_headers()
            self.wfile.write(content.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


@pytest.fixture(scope="module")
def portal_server() -> Generator[str, None, None]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _AcceptanceHandler)
    port = server.server_port
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    base_url = f"http://127.0.0.1:{port}"
    try:
        yield base_url
    finally:
        server.shutdown()
        server.server_close()
        close_active_browser_session()


@pytest.fixture(autouse=True)
def _cleanup():
    close_active_browser_session()
    yield
    close_active_browser_session()


def test_agent_browser_workflow_acceptance(
    portal_server: str, monkeypatch: pytest.MonkeyPatch
):
    """Acceptance Scenario: Natural language task completion via resolved browser tools.

    Scenario:
    User requests: "Open the Executive Control Center, set Project Name to 'Project Apollo',
    and click 'Activate Workflow'."
    """
    monkeypatch.setenv("OPENJARVIS_BROWSER_ALLOW_LOCAL_TEST_FIXTURES", "1")

    # 1. Resolve agent tools with "browser"
    agent_record = {
        "id": "agent-browser-acceptance",
        "name": "Web Automator",
        "agent_type": "orchestrator",
        "config": {"tools": ["browser"]},
    }

    resolved = resolve_agent_tools(
        agent_record,
        engine=object(),
        model="gemini-3.8-flash",
    )

    # Confirm all browser sub-tools are resolved
    assert "browser_navigate" in resolved.by_name
    assert "browser_click" in resolved.by_name
    assert "browser_type" in resolved.by_name
    assert "browser_extract" in resolved.by_name
    assert "browser_screenshot" in resolved.by_name

    executor = ToolExecutor(tools=resolved.instances)

    # 2. Step 1: Agent calls browser_navigate
    step1_call = ToolCall(
        id="call-nav-1",
        name="browser_navigate",
        arguments=json.dumps({"url": f"{portal_server}/"}),
    )
    step1_result = executor.execute(step1_call)
    assert step1_result.success is True
    assert "Ultron Agent Portal" in step1_result.content
    assert "<untrusted_web_content" in step1_result.content

    # 3. Step 2: Agent calls browser_type to fill project name
    step2_call = ToolCall(
        id="call-type-2",
        name="browser_type",
        arguments=json.dumps({"label": "Project Name", "text": "Project Apollo"}),
    )
    step2_result = executor.execute(step2_call)
    assert step2_result.success is True
    assert "Typed text into: Project Name" in step2_result.content
    assert step2_result.metadata.get("verified_value") == "Project Apollo"

    # 4. Step 3: Agent calls browser_click to activate workflow
    step3_call = ToolCall(
        id="call-click-3",
        name="browser_click",
        arguments=json.dumps({"text": "Activate Workflow"}),
    )
    step3_result = executor.execute(step3_call)
    assert step3_result.success is True
    assert "Clicked element: Activate Workflow" in step3_result.content

    # 5. Step 4: Agent verifies resulting page state
    step4_call = ToolCall(
        id="call-extract-4",
        name="browser_extract",
        arguments=json.dumps({"selector": "#task-state", "extract_type": "text"}),
    )
    step4_result = executor.execute(step4_call)
    assert step4_result.success is True
    assert "Agent Task Active" in step4_result.content
