"""Desktop mouse and keyboard control tools — native OS human-like input automation."""

from __future__ import annotations

import sys
import time
from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec

# Virtual key codes for common special keys
_VK_MAP = {
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "space": 0x20,
    "backspace": 0x08,
    "escape": 0x1B,
    "esc": 0x1B,
    "win": 0x5B,
    "windows": 0x5B,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "delete": 0x2E,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "shift": 0x10,
}


def _get_windows_screen_and_pos() -> tuple[int, int, int, int]:
    """Return (screen_w, screen_h, cursor_x, cursor_y) via ctypes."""
    import ctypes
    import ctypes.wintypes

    user32 = ctypes.windll.user32
    w = user32.GetSystemMetrics(0)
    h = user32.GetSystemMetrics(1)
    pt = ctypes.wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return w, h, pt.x, pt.y


def _set_cursor_pos(x: int, y: int) -> bool:
    """Move cursor to (x, y)."""
    import ctypes

    return bool(ctypes.windll.user32.SetCursorPos(int(x), int(y)))


def _mouse_click(button: str = "left", clicks: int = 1) -> None:
    """Perform mouse click at current cursor position."""
    import ctypes

    user32 = ctypes.windll.user32
    down_flag = 0x0002
    up_flag = 0x0004
    if button.lower() == "right":
        down_flag, up_flag = 0x0008, 0x0010
    elif button.lower() == "middle":
        down_flag, up_flag = 0x0020, 0x0040

    for _ in range(max(1, clicks)):
        user32.mouse_event(down_flag, 0, 0, 0, 0)
        time.sleep(0.02)
        user32.mouse_event(up_flag, 0, 0, 0, 0)
        if clicks > 1:
            time.sleep(0.08)


def _send_key(vk: int) -> None:
    """Press and release a virtual key code."""
    import ctypes

    user32 = ctypes.windll.user32
    user32.keybd_event(vk, 0, 0, 0)
    time.sleep(0.02)
    user32.keybd_event(vk, 0, 0x0002, 0)  # KEYEVENTF_KEYUP


def _type_text(text: str) -> None:
    """Type string into active focused window via Windows SendInput with unicode."""
    import ctypes
    from ctypes import wintypes

    KEYEVENTF_UNICODE = 0x0004
    KEYEVENTF_KEYUP = 0x0002

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_void_p),
        ]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("ki", KEYBDINPUT), ("padding", ctypes.c_ubyte * 16)]

    user32 = ctypes.windll.user32

    for ch in text:
        if ch == "\n":
            _send_key(0x0D)
            continue
        elif ch == "\t":
            _send_key(0x09)
            continue

        # Down
        inp_down = INPUT()
        inp_down.type = 1  # INPUT_KEYBOARD
        inp_down.ki.wVk = 0
        inp_down.ki.wScan = ord(ch)
        inp_down.ki.dwFlags = KEYEVENTF_UNICODE
        user32.SendInput(1, ctypes.byref(inp_down), ctypes.sizeof(INPUT))

        # Up
        inp_up = INPUT()
        inp_up.type = 1
        inp_up.ki.wVk = 0
        inp_up.ki.wScan = ord(ch)
        inp_up.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
        user32.SendInput(1, ctypes.byref(inp_up), ctypes.sizeof(INPUT))
        time.sleep(0.005)


@ToolRegistry.register("desktop_mouse_click")
class DesktopMouseClickTool(BaseTool):
    """Click the mouse at specified desktop coordinates or current position."""

    tool_id = "desktop_mouse_click"
    is_local = True

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="desktop_mouse_click",
            description=(
                "Click the mouse on the user's desktop at (x, y) coordinates or current position. "
                "Can single click, double click, right click, or middle click like a real human."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "x": {
                        "type": "integer",
                        "description": "Desktop horizontal coordinate (pixels from left).",
                    },
                    "y": {
                        "type": "integer",
                        "description": "Desktop vertical coordinate (pixels from top).",
                    },
                    "button": {
                        "type": "string",
                        "description": "'left', 'right', or 'middle'. Default: 'left'.",
                    },
                    "clicks": {
                        "type": "integer",
                        "description": "Number of clicks: 1 for single click, 2 for double click. Default: 1.",
                    },
                },
            },
            category="desktop",
            required_capabilities=["system:admin"],
        )

    def execute(self, **params: Any) -> ToolResult:
        if sys.platform != "win32":
            return ToolResult(
                tool_name="desktop_mouse_click",
                content="Desktop mouse control is currently supported on Windows host environments.",
                success=False,
            )

        try:
            x = params.get("x")
            y = params.get("y")
            button = str(params.get("button") or "left")
            clicks = int(params.get("clicks") or 1)

            if x is not None and y is not None:
                _set_cursor_pos(int(x), int(y))
                time.sleep(0.03)

            _mouse_click(button=button, clicks=clicks)
            _, _, cur_x, cur_y = _get_windows_screen_and_pos()
            return ToolResult(
                tool_name="desktop_mouse_click",
                content=f"Successfully clicked {button} button ({clicks}x) at desktop coordinates ({cur_x}, {cur_y}).",
                success=True,
                metadata={"x": cur_x, "y": cur_y, "button": button, "clicks": clicks},
            )
        except Exception as exc:
            return ToolResult(
                tool_name="desktop_mouse_click",
                content=f"Desktop mouse click failed: {exc}",
                success=False,
            )


@ToolRegistry.register("desktop_mouse_move")
class DesktopMouseMoveTool(BaseTool):
    """Move the mouse cursor to desktop (x, y) coordinates."""

    tool_id = "desktop_mouse_move"
    is_local = True

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="desktop_mouse_move",
            description="Move the mouse cursor across the desktop screen to (x, y) coordinates like a human.",
            parameters={
                "type": "object",
                "properties": {
                    "x": {
                        "type": "integer",
                        "description": "Target horizontal coordinate.",
                    },
                    "y": {
                        "type": "integer",
                        "description": "Target vertical coordinate.",
                    },
                },
                "required": ["x", "y"],
            },
            category="desktop",
            required_capabilities=["system:admin"],
        )

    def execute(self, **params: Any) -> ToolResult:
        if sys.platform != "win32":
            return ToolResult(
                tool_name="desktop_mouse_move",
                content="Desktop mouse move is currently supported on Windows host environments.",
                success=False,
            )

        try:
            x = int(params["x"])
            y = int(params["y"])
            _set_cursor_pos(x, y)
            return ToolResult(
                tool_name="desktop_mouse_move",
                content=f"Moved desktop cursor to ({x}, {y}).",
                success=True,
                metadata={"x": x, "y": y},
            )
        except Exception as exc:
            return ToolResult(
                tool_name="desktop_mouse_move",
                content=f"Failed to move desktop cursor: {exc}",
                success=False,
            )


@ToolRegistry.register("desktop_keyboard_type")
class DesktopKeyboardTypeTool(BaseTool):
    """Type text into the currently active desktop window."""

    tool_id = "desktop_keyboard_type"
    is_local = True

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="desktop_keyboard_type",
            description="Type text keystrokes into the active focused desktop application or text field.",
            parameters={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Text to type into the active window.",
                    },
                },
                "required": ["text"],
            },
            category="desktop",
            required_capabilities=["system:admin"],
        )

    def execute(self, **params: Any) -> ToolResult:
        if sys.platform != "win32":
            return ToolResult(
                tool_name="desktop_keyboard_type",
                content="Desktop keyboard typing is currently supported on Windows host environments.",
                success=False,
            )

        text = str(params.get("text") or "")
        if not text:
            return ToolResult(
                tool_name="desktop_keyboard_type",
                content="No text provided to type.",
                success=False,
            )

        try:
            _type_text(text)
            return ToolResult(
                tool_name="desktop_keyboard_type",
                content=f"Successfully typed {len(text)} characters into active window.",
                success=True,
                metadata={"char_count": len(text)},
            )
        except Exception as exc:
            return ToolResult(
                tool_name="desktop_keyboard_type",
                content=f"Failed to type keyboard text: {exc}",
                success=False,
            )


@ToolRegistry.register("desktop_key_press")
class DesktopKeyPressTool(BaseTool):
    """Press a special key or shortcut in the active desktop window."""

    tool_id = "desktop_key_press"
    is_local = True

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="desktop_key_press",
            description=(
                "Press a special keyboard key like 'enter', 'tab', 'esc', 'space', "
                "'backspace', 'win', 'up', 'down', 'left', 'right', or hotkeys like 'ctrl+c'."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Key name (e.g. 'enter', 'tab', 'esc', 'space', 'win', 'ctrl+c').",
                    },
                },
                "required": ["key"],
            },
            category="desktop",
            required_capabilities=["system:admin"],
        )

    def execute(self, **params: Any) -> ToolResult:
        if sys.platform != "win32":
            return ToolResult(
                tool_name="desktop_key_press",
                content="Desktop key press is currently supported on Windows host environments.",
                success=False,
            )

        key_name = str(params.get("key") or "").strip().lower()
        if not key_name:
            return ToolResult(
                tool_name="desktop_key_press",
                content="No key specified.",
                success=False,
            )

        try:
            import ctypes

            user32 = ctypes.windll.user32

            if "+" in key_name:
                parts = [p.strip() for p in key_name.split("+")]
                vks = [_VK_MAP.get(p, ord(p.upper()) if len(p) == 1 else 0) for p in parts]
                # Press down all in order
                for vk in vks:
                    if vk:
                        user32.keybd_event(vk, 0, 0, 0)
                time.sleep(0.04)
                # Release all in reverse order
                for vk in reversed(vks):
                    if vk:
                        user32.keybd_event(vk, 0, 0x0002, 0)
            else:
                vk = _VK_MAP.get(key_name, ord(key_name.upper()) if len(key_name) == 1 else 0)
                if not vk:
                    return ToolResult(
                        tool_name="desktop_key_press",
                        content=f"Unknown or unsupported key '{key_name}'.",
                        success=False,
                    )
                _send_key(vk)

            return ToolResult(
                tool_name="desktop_key_press",
                content=f"Successfully pressed key '{key_name}'.",
                success=True,
                metadata={"key": key_name},
            )
        except Exception as exc:
            return ToolResult(
                tool_name="desktop_key_press",
                content=f"Failed to press key: {exc}",
                success=False,
            )


@ToolRegistry.register("desktop_screen_info")
class DesktopScreenInfoTool(BaseTool):
    """Retrieve screen resolution and current cursor position."""

    tool_id = "desktop_screen_info"
    is_local = True

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="desktop_screen_info",
            description="Get the screen resolution (width, height in pixels) and current mouse cursor position.",
            parameters={"type": "object", "properties": {}},
            category="desktop",
            required_capabilities=["system:admin"],
        )

    def execute(self, **params: Any) -> ToolResult:
        if sys.platform != "win32":
            return ToolResult(
                tool_name="desktop_screen_info",
                content="Desktop screen info is currently supported on Windows host environments.",
                success=False,
            )

        try:
            w, h, cur_x, cur_y = _get_windows_screen_and_pos()
            return ToolResult(
                tool_name="desktop_screen_info",
                content=f"Screen resolution: {w}x{h} pixels. Current cursor position: ({cur_x}, {cur_y}).",
                success=True,
                metadata={"width": w, "height": h, "cursor_x": cur_x, "cursor_y": cur_y},
            )
        except Exception as exc:
            return ToolResult(
                tool_name="desktop_screen_info",
                content=f"Failed to get screen info: {exc}",
                success=False,
            )
