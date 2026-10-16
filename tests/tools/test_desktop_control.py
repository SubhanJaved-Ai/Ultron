"""Unit tests for desktop control tools."""

from __future__ import annotations

import importlib
import sys
import pytest

from openjarvis.core.registry import ToolRegistry
import openjarvis.tools.desktop_control as desktop_control_mod


@pytest.fixture(autouse=True)
def _ensure_desktop_tools_registered():
    importlib.reload(desktop_control_mod)


def test_desktop_tools_registered():
    tools = [
        "desktop_mouse_click",
        "desktop_mouse_move",
        "desktop_keyboard_type",
        "desktop_key_press",
        "desktop_screen_info",
    ]
    for name in tools:
        assert ToolRegistry.contains(name), f"Tool {name} must be registered in ToolRegistry"
        assert ToolRegistry.get(name) is not None


@pytest.mark.skipif(sys.platform != "win32", reason="Requires Windows environment")
def test_desktop_screen_info():
    tool = ToolRegistry.get("desktop_screen_info")()
    result = tool.execute()
    assert result.success is True
    assert "width" in result.metadata
    assert "height" in result.metadata
    assert result.metadata["width"] > 0
    assert result.metadata["height"] > 0


@pytest.mark.skipif(sys.platform != "win32", reason="Requires Windows environment")
def test_desktop_mouse_move_and_click():
    move_tool = ToolRegistry.get("desktop_mouse_move")()
    click_tool = ToolRegistry.get("desktop_mouse_click")()

    move_res = move_tool.execute(x=100, y=100)
    assert move_res.success is True
    assert move_res.metadata["x"] == 100
    assert move_res.metadata["y"] == 100

    click_res = click_tool.execute(button="left", clicks=1)
    assert click_res.success is True
    assert click_res.metadata["clicks"] == 1


@pytest.mark.skipif(sys.platform != "win32", reason="Requires Windows environment")
def test_desktop_key_press():
    tool = ToolRegistry.get("desktop_key_press")()
    res = tool.execute(key="tab")
    assert res.success is True
    assert res.metadata["key"] == "tab"


@pytest.mark.skipif(sys.platform != "win32", reason="Requires Windows environment")
def test_desktop_keyboard_type():
    tool = ToolRegistry.get("desktop_keyboard_type")()
    res = tool.execute(text="test")
    assert res.success is True
    assert res.metadata["char_count"] == 4
