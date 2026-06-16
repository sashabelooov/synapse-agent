"""Tests for tools/computer_use/computer_use.py.

All pyautogui calls are mocked — no display or hardware needed.
Safety gate (ALLOW_COMPUTER_USE env var) is tested exhaustively.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _call(**kwargs):
    """Import and call _computer_use with the given kwargs."""
    from tools.computer_use.computer_use import _computer_use
    return _computer_use(**kwargs)


def _mock_gui():
    """Return a MagicMock that stands in for the pyautogui module."""
    gui = MagicMock()
    gui.FAILSAFE = True
    gui.PAUSE = 0.05
    return gui


# ---------------------------------------------------------------------------
# Safety gate
# ---------------------------------------------------------------------------

class TestSafetyGate:
    def test_blocked_by_default(self, monkeypatch):
        monkeypatch.delenv("ALLOW_COMPUTER_USE", raising=False)
        result = _call(action="screenshot")
        assert "ALLOW_COMPUTER_USE" in result
        assert "disabled" in result.lower()

    def test_blocked_when_false(self, monkeypatch):
        monkeypatch.setenv("ALLOW_COMPUTER_USE", "false")
        result = _call(action="click", x=100, y=200)
        assert "disabled" in result.lower()

    def test_allowed_true(self, monkeypatch):
        monkeypatch.setenv("ALLOW_COMPUTER_USE", "true")
        with patch("tools.computer_use.computer_use._gui") as mock_get_gui:
            gui = _mock_gui()
            gui.screenshot.return_value = MagicMock()
            gui.screenshot.return_value.save = MagicMock()
            mock_get_gui.return_value = gui
            with patch("tempfile.NamedTemporaryFile") as mock_tmp:
                mock_tmp.return_value.__enter__ = MagicMock(return_value=MagicMock(name="/tmp/test.png"))
                mock_tmp.return_value.__exit__ = MagicMock(return_value=False)
                mock_tmp.return_value.name = "/tmp/synapse_screen_test.png"
                # Just check it doesn't return the gate message
                result = _call(action="screenshot")
                assert "ALLOW_COMPUTER_USE" not in result or "disabled" not in result.lower()

    def test_allowed_1(self, monkeypatch):
        monkeypatch.setenv("ALLOW_COMPUTER_USE", "1")
        with patch("tools.computer_use.computer_use._gui") as mock_get_gui:
            mock_get_gui.return_value = _mock_gui()
            result = _call(action="move", x=0, y=0)
            assert "disabled" not in result.lower()

    def test_allowed_yes(self, monkeypatch):
        monkeypatch.setenv("ALLOW_COMPUTER_USE", "yes")
        with patch("tools.computer_use.computer_use._gui") as mock_get_gui:
            mock_get_gui.return_value = _mock_gui()
            result = _call(action="move", x=0, y=0)
            assert "disabled" not in result.lower()


# ---------------------------------------------------------------------------
# Missing pyautogui
# ---------------------------------------------------------------------------

class TestMissingPyautogui:
    def test_screenshot_no_pyautogui(self, monkeypatch):
        monkeypatch.setenv("ALLOW_COMPUTER_USE", "true")
        with patch("tools.computer_use.computer_use._gui", return_value=None):
            result = _call(action="screenshot")
            assert "not installed" in result.lower()

    def test_click_no_pyautogui(self, monkeypatch):
        monkeypatch.setenv("ALLOW_COMPUTER_USE", "true")
        with patch("tools.computer_use.computer_use._gui", return_value=None):
            result = _call(action="click", x=100, y=200)
            assert "not installed" in result.lower()


# ---------------------------------------------------------------------------
# screenshot
# ---------------------------------------------------------------------------

class TestScreenshot:
    def test_full_screen_saves_png(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ALLOW_COMPUTER_USE", "true")
        fake_img = MagicMock()
        with patch("tools.computer_use.computer_use._gui") as mock_get_gui, \
             patch("tempfile.NamedTemporaryFile") as mock_tmp:
            gui = _mock_gui()
            gui.screenshot.return_value = fake_img
            mock_get_gui.return_value = gui
            png = tmp_path / "screen.png"
            mock_tmp.return_value.name = str(png)
            result = _call(action="screenshot")
            gui.screenshot.assert_called_once_with()
            fake_img.save.assert_called_once_with(str(png))
            assert result == str(png)

    def test_region_screenshot(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ALLOW_COMPUTER_USE", "true")
        fake_img = MagicMock()
        with patch("tools.computer_use.computer_use._gui") as mock_get_gui, \
             patch("tempfile.NamedTemporaryFile") as mock_tmp:
            gui = _mock_gui()
            gui.screenshot.return_value = fake_img
            mock_get_gui.return_value = gui
            mock_tmp.return_value.name = str(tmp_path / "region.png")
            _call(action="screenshot", region=[10, 20, 300, 200])
            gui.screenshot.assert_called_once_with(region=(10, 20, 300, 200))


# ---------------------------------------------------------------------------
# click
# ---------------------------------------------------------------------------

class TestClick:
    def test_left_click(self, monkeypatch):
        monkeypatch.setenv("ALLOW_COMPUTER_USE", "true")
        with patch("tools.computer_use.computer_use._gui") as mock_get_gui:
            gui = _mock_gui()
            mock_get_gui.return_value = gui
            result = _call(action="click", x=500, y=300)
            gui.click.assert_called_once_with(500, 300, button="left", clicks=1, interval=0.1)
            assert "500" in result and "300" in result

    def test_right_click(self, monkeypatch):
        monkeypatch.setenv("ALLOW_COMPUTER_USE", "true")
        with patch("tools.computer_use.computer_use._gui") as mock_get_gui:
            gui = _mock_gui()
            mock_get_gui.return_value = gui
            result = _call(action="click", x=100, y=100, button="right")
            gui.click.assert_called_once_with(100, 100, button="right", clicks=1, interval=0.1)

    def test_double_click(self, monkeypatch):
        monkeypatch.setenv("ALLOW_COMPUTER_USE", "true")
        with patch("tools.computer_use.computer_use._gui") as mock_get_gui:
            gui = _mock_gui()
            mock_get_gui.return_value = gui
            result = _call(action="click", x=200, y=200, clicks=2)
            gui.click.assert_called_once_with(200, 200, button="left", clicks=2, interval=0.1)
            assert "2" in result

    def test_click_missing_coords(self, monkeypatch):
        monkeypatch.setenv("ALLOW_COMPUTER_USE", "true")
        result = _call(action="click")
        assert "requires x and y" in result


# ---------------------------------------------------------------------------
# type_text
# ---------------------------------------------------------------------------

class TestTypeText:
    def test_types_string(self, monkeypatch):
        monkeypatch.setenv("ALLOW_COMPUTER_USE", "true")
        with patch("tools.computer_use.computer_use._gui") as mock_get_gui:
            gui = _mock_gui()
            mock_get_gui.return_value = gui
            result = _call(action="type_text", text="Hello, World!")
            gui.write.assert_called_once_with("Hello, World!", interval=0.02)
            assert "13" in result  # len("Hello, World!")

    def test_type_missing_text(self, monkeypatch):
        monkeypatch.setenv("ALLOW_COMPUTER_USE", "true")
        result = _call(action="type_text")
        assert "requires text" in result


# ---------------------------------------------------------------------------
# key
# ---------------------------------------------------------------------------

class TestKey:
    def test_single_key(self, monkeypatch):
        monkeypatch.setenv("ALLOW_COMPUTER_USE", "true")
        with patch("tools.computer_use.computer_use._gui") as mock_get_gui:
            gui = _mock_gui()
            mock_get_gui.return_value = gui
            result = _call(action="key", combo="enter")
            gui.press.assert_called_once_with("enter")
            assert "enter" in result.lower()

    def test_key_combo(self, monkeypatch):
        monkeypatch.setenv("ALLOW_COMPUTER_USE", "true")
        with patch("tools.computer_use.computer_use._gui") as mock_get_gui:
            gui = _mock_gui()
            mock_get_gui.return_value = gui
            result = _call(action="key", combo="ctrl+c")
            gui.hotkey.assert_called_once_with("ctrl", "c")

    def test_triple_combo(self, monkeypatch):
        monkeypatch.setenv("ALLOW_COMPUTER_USE", "true")
        with patch("tools.computer_use.computer_use._gui") as mock_get_gui:
            gui = _mock_gui()
            mock_get_gui.return_value = gui
            _call(action="key", combo="ctrl+shift+t")
            gui.hotkey.assert_called_once_with("ctrl", "shift", "t")

    def test_key_missing_combo(self, monkeypatch):
        monkeypatch.setenv("ALLOW_COMPUTER_USE", "true")
        result = _call(action="key")
        assert "requires combo" in result


# ---------------------------------------------------------------------------
# scroll
# ---------------------------------------------------------------------------

class TestScroll:
    def test_scroll_down(self, monkeypatch):
        monkeypatch.setenv("ALLOW_COMPUTER_USE", "true")
        with patch("tools.computer_use.computer_use._gui") as mock_get_gui:
            gui = _mock_gui()
            mock_get_gui.return_value = gui
            result = _call(action="scroll", x=400, y=300)
            gui.scroll.assert_called_once_with(-3, x=400, y=300)
            assert "down" in result

    def test_scroll_up(self, monkeypatch):
        monkeypatch.setenv("ALLOW_COMPUTER_USE", "true")
        with patch("tools.computer_use.computer_use._gui") as mock_get_gui:
            gui = _mock_gui()
            mock_get_gui.return_value = gui
            result = _call(action="scroll", x=400, y=300, direction="up", amount=5)
            gui.scroll.assert_called_once_with(5, x=400, y=300)
            assert "up" in result

    def test_scroll_missing_coords(self, monkeypatch):
        monkeypatch.setenv("ALLOW_COMPUTER_USE", "true")
        result = _call(action="scroll")
        assert "requires x and y" in result


# ---------------------------------------------------------------------------
# move
# ---------------------------------------------------------------------------

class TestMove:
    def test_moves_to_coords(self, monkeypatch):
        monkeypatch.setenv("ALLOW_COMPUTER_USE", "true")
        with patch("tools.computer_use.computer_use._gui") as mock_get_gui:
            gui = _mock_gui()
            mock_get_gui.return_value = gui
            result = _call(action="move", x=100, y=200)
            gui.moveTo.assert_called_once_with(100, 200, duration=0.2)
            assert "100" in result and "200" in result

    def test_move_missing_coords(self, monkeypatch):
        monkeypatch.setenv("ALLOW_COMPUTER_USE", "true")
        result = _call(action="move")
        assert "requires x and y" in result


# ---------------------------------------------------------------------------
# drag
# ---------------------------------------------------------------------------

class TestDrag:
    def test_drag_calls_moveTo_and_dragTo(self, monkeypatch):
        monkeypatch.setenv("ALLOW_COMPUTER_USE", "true")
        with patch("tools.computer_use.computer_use._gui") as mock_get_gui:
            gui = _mock_gui()
            mock_get_gui.return_value = gui
            result = _call(action="drag", x=50, y=50, end_x=200, end_y=200)
            gui.moveTo.assert_called_once_with(50, 50, duration=0.2)
            gui.dragTo.assert_called_once_with(200, 200, duration=0.4, button="left")
            assert "50" in result and "200" in result

    def test_drag_missing_end(self, monkeypatch):
        monkeypatch.setenv("ALLOW_COMPUTER_USE", "true")
        result = _call(action="drag", x=50, y=50)
        assert "requires x, y, end_x, and end_y" in result


# ---------------------------------------------------------------------------
# Unknown action
# ---------------------------------------------------------------------------

class TestUnknownAction:
    def test_unknown_action_returns_error(self, monkeypatch):
        monkeypatch.setenv("ALLOW_COMPUTER_USE", "true")
        result = _call(action="fly")
        assert "unknown action" in result.lower()
        assert "fly" in result

    def test_lists_valid_actions(self, monkeypatch):
        monkeypatch.setenv("ALLOW_COMPUTER_USE", "true")
        result = _call(action="hover")
        assert "screenshot" in result


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

class TestToolRegistration:
    def test_tool_is_registered(self):
        from tools.computer_use.computer_use import tool
        assert tool.name == "computer_use"

    def test_tool_has_action_enum(self):
        from tools.computer_use.computer_use import tool
        actions = tool.parameters["properties"]["action"]["enum"]
        assert "screenshot" in actions
        assert "click" in actions
        assert "type_text" in actions
        assert "key" in actions
        assert "scroll" in actions
        assert "move" in actions
        assert "drag" in actions

    def test_action_is_required(self):
        from tools.computer_use.computer_use import tool
        assert "action" in tool.parameters["required"]

    def test_tool_function_is_callable(self):
        from tools.computer_use.computer_use import tool
        assert callable(tool.function)
