"""Focused tests for real chat-to-browser tool execution and failure handling."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from openjarvis.agents.orchestrator import OrchestratorAgent
from openjarvis.cli.serve import _DEFAULT_TOOLS, _resolve_allowed_tools
from openjarvis.core.config import JarvisConfig
from openjarvis.core.events import EventBus
from openjarvis.core.types import ToolResult
from openjarvis.engine._base import EngineConnectionError
from openjarvis.server.app import create_app
from openjarvis.tools.browser import BrowserClickTool, BrowserNavigateTool


def _test_config():
    cfg = JarvisConfig()
    cfg.analytics.enabled = False
    cfg.traces.enabled = False
    cfg.security.enabled = False
    return cfg


def _make_mock_engine():
    engine = MagicMock()
    engine.engine_id = "gemini"
    engine.health.return_value = True
    engine.list_models.return_value = ["gemini-3.8-flash"]
    return engine


class TestBrowserToolRegistrationAndDiscovery:
    def test_default_tools_include_browser_automation_suite(self):
        """Browser tools must be permitted by default on the server."""
        expected = {
            "browser_navigate",
            "browser_click",
            "browser_type",
            "browser_screenshot",
            "browser_extract",
        }
        assert expected.issubset(_DEFAULT_TOOLS)

    def test_browser_alias_expands_to_browser_sub_tools(self):
        """When config specifies 'browser', _resolve_allowed_tools must expand it."""
        cfg = JarvisConfig()
        cfg.tools.enabled = "browser,think"
        allowed, explicit = _resolve_allowed_tools(cfg)
        assert explicit is True
        assert "browser" not in allowed
        assert "browser_navigate" in allowed
        assert "browser_click" in allowed
        assert "think" in allowed

    def test_browser_click_schema_is_standard_and_gemini_compatible(self):
        """BrowserClickTool must use standard required array without anyOf."""
        tool = BrowserClickTool()
        spec = tool.to_openai_function()
        func = spec["function"]
        params = func["parameters"]

        assert params["type"] == "object"
        assert "anyOf" not in params
        assert params.get("required") == ["selector"]
        assert "selector" in params["properties"]
        assert "target" in params["properties"]


class TestChatToBrowserToolDispatch:
    def test_streaming_chat_dispatches_gemini_tool_call_to_browser_navigate(self):
        """Incoming chat completion without client tools routes to orchestrator,

        dispatches Gemini tool_calls to BrowserNavigateTool, and returns tool observations.
        """
        engine = _make_mock_engine()

        # Turn 1: Model decides to call browser_navigate
        # Turn 2: Model receives webpage content and responds to the user
        engine.generate.side_effect = [
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_nav_1",
                        "name": "browser_navigate",
                        "arguments": json.dumps({"url": "https://example.com"}),
                    }
                ],
                "finish_reason": "tool_calls",
                "usage": {"prompt_tokens": 15, "completion_tokens": 10},
            },
            {
                "content": "The page title is Example Domain and it describes example web usage.",
                "finish_reason": "stop",
                "usage": {"prompt_tokens": 40, "completion_tokens": 20},
            },
        ]

        executed_urls: list[str] = []

        def mock_navigate_execute(**params):
            executed_urls.append(params.get("url"))
            return ToolResult(
                tool_name="browser_navigate",
                content="Title: Example Domain\n\n<untrusted_web_content url=\"https://example.com\">\nExample Domain text\n</untrusted_web_content>",
                success=True,
                metadata={"url": params.get("url"), "title": "Example Domain"},
            )

        with patch.object(BrowserNavigateTool, "execute", side_effect=mock_navigate_execute):
            nav_tool = BrowserNavigateTool()
            agent = OrchestratorAgent(
                engine,
                "gemini-3.8-flash",
                tools=[nav_tool],
                bus=EventBus(),
                max_turns=3,
                system_prompt="You are Ultron.",
            )
            app = create_app(
                engine,
                "gemini-3.8-flash",
                agent=agent,
                bus=EventBus(),
                config=_test_config(),
            )
            client = TestClient(app)

            resp = client.post(
                "/v1/chat/completions",
                json={
                    "model": "gemini-3.8-flash",
                    "messages": [
                        {"role": "user", "content": "Browse https://example.com and summarize it."}
                    ],
                    "stream": True,
                },
            )

            assert resp.status_code == 200
            content = ""
            for line in resp.text.strip().split("\n"):
                if not line.startswith("data:") or "[DONE]" in line:
                    continue
                data = json.loads(line[5:].strip())
                delta = data.get("choices", [{}])[0].get("delta", {})
                content += delta.get("content") or ""

            assert "Example Domain" in content
            assert executed_urls == ["https://example.com"]
            assert engine.generate.call_count == 2


class TestHTTP503FailureHandling:
    def test_provider_503_fails_cleanly_without_reporting_false_success(self):
        """When inference engine raises EngineConnectionError / 503, the server

        must return a clear error with success=False, never reporting fake success.
        """
        engine = _make_mock_engine()
        engine.generate.side_effect = EngineConnectionError(
            "gemini engine at https://generativelanguage.googleapis.com returned HTTP 503: Model overloaded"
        )

        agent = OrchestratorAgent(
            engine,
            "gemini-3.8-flash",
            tools=[BrowserNavigateTool()],
            bus=EventBus(),
            max_turns=3,
        )
        app = create_app(
            engine,
            "gemini-3.8-flash",
            agent=agent,
            bus=EventBus(),
            config=_test_config(),
        )
        client = TestClient(app)

        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "gemini-3.8-flash",
                "messages": [
                    {"role": "user", "content": "Browse https://example.com"}
                ],
                "stream": True,
            },
        )

        assert resp.status_code == 200
        content = ""
        for line in resp.text.strip().split("\n"):
            if not line.startswith("data:") or "[DONE]" in line:
                continue
            data = json.loads(line[5:].strip())
            delta = data.get("choices", [{}])[0].get("delta", {})
            content += delta.get("content") or ""

        assert "503" in content or "overloaded" in content
        assert "Directive acknowledged" not in content
        assert "All subsystems synchronized" not in content
