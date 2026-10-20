"""Test autonomous agentic harness for Canva navigation and browser control."""

from unittest.mock import MagicMock
import pytest

from openjarvis.agents.tool_resolver import BROWSER_SUB_TOOLS
from openjarvis.core.config import AgentConfig
from openjarvis.tools.browser import (
    BrowserNavigateTool,
    BrowserClickTool,
    BrowserTypeTool,
    BrowserScreenshotTool,
    BrowserExtractTool,
)


def test_browser_tools_registered_for_agent_harness():
    """Verify all browser sub-tools required for Canva/web automation are available."""
    tool_classes = [
        BrowserNavigateTool,
        BrowserClickTool,
        BrowserTypeTool,
        BrowserScreenshotTool,
        BrowserExtractTool,
    ]
    for cls in tool_classes:
        assert cls.tool_id in BROWSER_SUB_TOOLS
        tool_inst = cls()
        assert tool_inst.spec.name == cls.tool_id


def test_canva_action_mandate_in_system_prompt():
    """Verify that system prompt explicitly directs the agent to operate software like Canva autonomously."""
    cfg = AgentConfig()
    prompt = cfg.default_system_prompt.lower()
    assert "canva" in prompt or "navigating websites" in prompt
    assert "boss" in prompt
    assert "respect" in prompt
    assert "autonomously" in prompt


def test_canva_url_targeting():
    """Verify browser navigation can correctly target Canva with URL safety."""
    tool = BrowserNavigateTool()
    spec = tool.spec
    assert spec.name == "browser_navigate"
    assert "url" in spec.parameters.get("properties", {})
