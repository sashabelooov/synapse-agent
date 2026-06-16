"""Phase 9 — Computer use tool.

Controls the mouse, keyboard, and screen. Requires explicit opt-in:
    ALLOW_COMPUTER_USE=true  in .env

Backend: pyautogui (cross-platform) + Pillow for screenshots.
The screenshot action saves a PNG to a temp file and returns its path
so the agent can pass it to describe_image for visual understanding.

Actions
-------
screenshot      Capture the full screen (or a region) → PNG path
click           Left/right/double click at (x, y)
type_text       Type a string as keyboard events
key             Press a key combo (e.g. "ctrl+c", "enter", "alt+tab")
scroll          Scroll the wheel at (x, y) in a direction
move            Move the mouse cursor to (x, y) without clicking
drag            Click-and-drag from one point to another
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from tools.base.tool import ToolDefinition


# ---------------------------------------------------------------------------
# Safety gate
# ---------------------------------------------------------------------------

def _allowed() -> bool:
    return os.environ.get("ALLOW_COMPUTER_USE", "").lower() in {"1", "true", "yes"}


_GATE_MSG = (
    "Computer use is disabled. Set ALLOW_COMPUTER_USE=true in your .env file "
    "to enable mouse and keyboard control. WARNING: this gives the agent direct "
    "control of your desktop."
)


# ---------------------------------------------------------------------------
# pyautogui helpers — imported lazily so the tool loads even without the lib
# ---------------------------------------------------------------------------

def _gui():
    try:
        import pyautogui
        pyautogui.FAILSAFE = True   # move mouse to top-left corner to abort
        pyautogui.PAUSE = 0.05      # small pause between actions for stability
        return pyautogui
    except ImportError:
        return None


def _pil_image():
    try:
        from PIL import Image
        return Image
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Individual actions
# ---------------------------------------------------------------------------

def _screenshot(region: list[int] | None = None) -> str:
    """Capture screen → save PNG → return path."""
    if not _allowed():
        return _GATE_MSG
    gui = _gui()
    if gui is None:
        return "Error: pyautogui is not installed. Run: uv add pyautogui"
    try:
        if region:
            x, y, w, h = region
            img = gui.screenshot(region=(x, y, w, h))
        else:
            img = gui.screenshot()
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False, prefix="synapse_screen_")
        img.save(tmp.name)
        return tmp.name
    except Exception as e:
        return f"Error taking screenshot: {e}"


def _click(x: int, y: int, button: str = "left", clicks: int = 1) -> str:
    if not _allowed():
        return _GATE_MSG
    gui = _gui()
    if gui is None:
        return "Error: pyautogui is not installed."
    try:
        gui.click(x, y, button=button, clicks=clicks, interval=0.1)
        return f"Clicked ({x}, {y}) with {button} button × {clicks}."
    except Exception as e:
        return f"Error clicking: {e}"


def _type_text(text: str, interval: float = 0.02) -> str:
    if not _allowed():
        return _GATE_MSG
    gui = _gui()
    if gui is None:
        return "Error: pyautogui is not installed."
    try:
        gui.write(text, interval=interval)
        return f"Typed {len(text)} characters."
    except Exception as e:
        return f"Error typing text: {e}"


def _key(combo: str) -> str:
    """Press a key or key combination. Examples: 'enter', 'ctrl+c', 'alt+tab'."""
    if not _allowed():
        return _GATE_MSG
    gui = _gui()
    if gui is None:
        return "Error: pyautogui is not installed."
    try:
        keys = [k.strip() for k in combo.lower().split("+")]
        if len(keys) == 1:
            gui.press(keys[0])
        else:
            gui.hotkey(*keys)
        return f"Pressed: {combo}"
    except Exception as e:
        return f"Error pressing key: {e}"


def _scroll(x: int, y: int, direction: str = "down", amount: int = 3) -> str:
    if not _allowed():
        return _GATE_MSG
    gui = _gui()
    if gui is None:
        return "Error: pyautogui is not installed."
    try:
        clicks = -amount if direction == "down" else amount
        gui.scroll(clicks, x=x, y=y)
        return f"Scrolled {direction} × {amount} at ({x}, {y})."
    except Exception as e:
        return f"Error scrolling: {e}"


def _move(x: int, y: int) -> str:
    if not _allowed():
        return _GATE_MSG
    gui = _gui()
    if gui is None:
        return "Error: pyautogui is not installed."
    try:
        gui.moveTo(x, y, duration=0.2)
        return f"Moved mouse to ({x}, {y})."
    except Exception as e:
        return f"Error moving mouse: {e}"


def _drag(start_x: int, start_y: int, end_x: int, end_y: int) -> str:
    if not _allowed():
        return _GATE_MSG
    gui = _gui()
    if gui is None:
        return "Error: pyautogui is not installed."
    try:
        gui.moveTo(start_x, start_y, duration=0.2)
        gui.dragTo(end_x, end_y, duration=0.4, button="left")
        return f"Dragged from ({start_x}, {start_y}) to ({end_x}, {end_y})."
    except Exception as e:
        return f"Error dragging: {e}"


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def _computer_use(
    action: str,
    x: int | None = None,
    y: int | None = None,
    text: str | None = None,
    combo: str | None = None,
    button: str = "left",
    clicks: int = 1,
    direction: str = "down",
    amount: int = 3,
    region: list | None = None,
    end_x: int | None = None,
    end_y: int | None = None,
) -> str:
    action = action.lower().strip()

    if action == "screenshot":
        return _screenshot(region=region)

    if action == "click":
        if x is None or y is None:
            return "Error: 'click' requires x and y."
        return _click(x, y, button=button, clicks=clicks)

    if action == "type_text":
        if not text:
            return "Error: 'type_text' requires text."
        return _type_text(text)

    if action == "key":
        if not combo:
            return "Error: 'key' requires combo (e.g. 'ctrl+c')."
        return _key(combo)

    if action == "scroll":
        if x is None or y is None:
            return "Error: 'scroll' requires x and y."
        return _scroll(x, y, direction=direction, amount=amount)

    if action == "move":
        if x is None or y is None:
            return "Error: 'move' requires x and y."
        return _move(x, y)

    if action == "drag":
        if None in (x, y, end_x, end_y):
            return "Error: 'drag' requires x, y, end_x, and end_y."
        return _drag(x, y, end_x, end_y)

    return f"Error: unknown action '{action}'. Valid: screenshot, click, type_text, key, scroll, move, drag."


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

tool = ToolDefinition(
    name="computer_use",
    description=(
        "Control the mouse, keyboard, and screen. Use for desktop automation beyond "
        "the browser — clicking UI elements, typing into apps, taking screenshots to "
        "see the current state, pressing keyboard shortcuts, scrolling, and drag-and-drop. "
        "Requires ALLOW_COMPUTER_USE=true in .env.\n\n"
        "Typical workflow: screenshot → describe_image (to see what's on screen) → "
        "click/type/key to interact → screenshot again to verify.\n\n"
        "Actions: screenshot | click | type_text | key | scroll | move | drag"
    ),
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["screenshot", "click", "type_text", "key", "scroll", "move", "drag"],
                "description": "The action to perform.",
            },
            "x": {
                "type": "integer",
                "description": "Screen X coordinate (pixels from left). Required for click, scroll, move, drag.",
            },
            "y": {
                "type": "integer",
                "description": "Screen Y coordinate (pixels from top). Required for click, scroll, move, drag.",
            },
            "end_x": {
                "type": "integer",
                "description": "Drag destination X. Required for drag.",
            },
            "end_y": {
                "type": "integer",
                "description": "Drag destination Y. Required for drag.",
            },
            "text": {
                "type": "string",
                "description": "Text to type. Required for type_text.",
            },
            "combo": {
                "type": "string",
                "description": "Key combo to press, e.g. 'ctrl+c', 'alt+tab', 'enter', 'ctrl+shift+t'. Required for key.",
            },
            "button": {
                "type": "string",
                "enum": ["left", "right", "middle"],
                "description": "Mouse button for click. Default: left.",
            },
            "clicks": {
                "type": "integer",
                "description": "Number of clicks (1 = single, 2 = double). Default: 1.",
            },
            "direction": {
                "type": "string",
                "enum": ["up", "down"],
                "description": "Scroll direction. Default: down.",
            },
            "amount": {
                "type": "integer",
                "description": "Scroll amount in wheel clicks. Default: 3.",
            },
            "region": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Capture region [x, y, width, height] for screenshot. Omit for full screen.",
            },
        },
        "required": ["action"],
    },
    function=_computer_use,
)
