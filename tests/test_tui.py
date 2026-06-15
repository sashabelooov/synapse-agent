"""Tests for tui/app.py — Textual TUI using the built-in pilot harness.

asyncio_mode = "auto" is set in pyproject.toml so all async tests run automatically.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from tui.app import SynapseApp, ToolPanel, _ToolCall, _StreamLine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(reply: str = "Hello from agent"):
    from unittest.mock import MagicMock
    state = MagicMock()
    state.system_prompt = "You are Synapse."
    state.tools = []
    state.formatted_tools = []
    state.native_thinking = False

    adapter = MagicMock()
    adapter.supports_streaming.return_value = False
    adapter.uses_native_thinking.return_value = False
    adapter.format_tools.return_value = []
    adapter.chat.return_value = MagicMock()
    adapter.parse_response.return_value = (reply, [], None)
    adapter.get_usage.return_value = {"input": 10, "output": 5}
    adapter.build_assistant_message.return_value = {"role": "assistant", "content": reply}
    state.adapter = adapter
    state.model_name = "test-model"
    return state


def _make_app(reply: str = "Hi!") -> SynapseApp:
    return SynapseApp(
        state=_make_state(reply),
        model_name="test-model",
        provider_name="test",
    )


# ---------------------------------------------------------------------------
# _ToolCall — pure dataclass, no Textual needed
# ---------------------------------------------------------------------------

class TestToolCall:
    def test_not_done_initially(self):
        tc = _ToolCall(name="web_search")
        assert tc.done is False

    def test_done_after_finish(self):
        tc = _ToolCall(name="web_search")
        tc.finished_at = time.time()
        assert tc.done is True

    def test_elapsed_increases_over_time(self):
        tc = _ToolCall(name="web_search")
        time.sleep(0.05)
        assert float(tc.elapsed.replace("s", "")) >= 0.04

    def test_elapsed_frozen_after_finish(self):
        tc = _ToolCall(name="web_search")
        tc.finished_at = time.time()
        e1 = tc.elapsed
        time.sleep(0.05)
        assert tc.elapsed == e1


# ---------------------------------------------------------------------------
# ToolPanel — widget logic without a running app
# ---------------------------------------------------------------------------

class TestToolPanel:
    def test_initial_render_shows_placeholder(self):
        panel = ToolPanel()
        panel._refresh()
        assert "No tools called" in panel.content

    def test_push_adds_tool(self):
        panel = ToolPanel()
        panel.push(_ToolCall(name="grep_search"))
        assert "grep_search" in panel.content

    def test_finish_last_marks_done(self):
        panel = ToolPanel()
        tc = _ToolCall(name="web_search")
        panel.push(tc)
        panel.finish_last()
        assert tc.done is True

    def test_clear_resets_list(self):
        panel = ToolPanel()
        panel.push(_ToolCall(name="read_file"))
        panel.clear_calls()
        assert panel._calls == []

    def test_only_last_ten_shown(self):
        panel = ToolPanel()
        for i in range(15):
            panel.push(_ToolCall(name=f"tool_{i}"))
        # Only last 10 in the reversed display
        assert len(panel._calls) == 15
        assert "tool_14" in panel.content


# ---------------------------------------------------------------------------
# _StreamLine — widget logic without a running app
# ---------------------------------------------------------------------------

class TestStreamLine:
    def test_set_text_stores_content(self):
        s = _StreamLine()
        s.set_text("Hello world")
        assert s._plain_text == "Hello world"

    def test_clear_empties_content(self):
        s = _StreamLine()
        s.set_text("Some text")
        s.clear()
        assert s._plain_text == ""


# ---------------------------------------------------------------------------
# SynapseApp — layout via Textual pilot
# ---------------------------------------------------------------------------

async def test_app_composes():
    app = _make_app()
    async with app.run_test() as pilot:
        assert app.query_one("#chat-log")
        assert app.query_one("#msg-input")
        assert app.query_one("#tool-status")
        assert app.query_one("#thinking-collapsible")
        assert app.query_one("#status-bar")


async def test_input_focused_on_mount():
    app = _make_app()
    async with app.run_test() as pilot:
        inp = app.query_one("#msg-input")
        assert inp.has_focus


async def test_thinking_collapsed_by_default():
    from textual.widgets import Collapsible
    app = _make_app()
    async with app.run_test() as pilot:
        c = app.query_one("#thinking-collapsible", Collapsible)
        assert c.collapsed is True


async def test_toggle_thinking_expands_and_collapses():
    from textual.widgets import Collapsible
    app = _make_app()
    async with app.run_test() as pilot:
        c = app.query_one("#thinking-collapsible", Collapsible)
        assert c.collapsed is True
        await pilot.press("ctrl+t")
        assert c.collapsed is False
        await pilot.press("ctrl+t")
        assert c.collapsed is True


async def test_header_subtitle_shows_provider_model():
    app = _make_app()
    async with app.run_test() as pilot:
        assert app.sub_title == "test / test-model"


async def test_status_bar_shows_unsaved_initially():
    from textual.widgets import Static
    app = _make_app()
    async with app.run_test() as pilot:
        bar = app.query_one("#status-bar", Static)
        assert "unsaved" in str(bar.content)


async def test_input_cleared_after_command():
    app = _make_app()
    async with app.run_test() as pilot:
        await pilot.click("#msg-input")
        for ch in "/help":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause(0.1)
        assert app.query_one("#msg-input").value == ""


async def test_reset_command_clears_messages():
    app = _make_app()
    async with app.run_test() as pilot:
        app._messages.append({"role": "user", "content": "Hello"})
        assert len(app._messages) == 2
        await pilot.click("#msg-input")
        for ch in "/reset":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause(0.1)
        assert len(app._messages) == 1
        assert app._messages[0]["role"] == "system"


async def test_session_name_resets_on_reset():
    app = _make_app()
    async with app.run_test() as pilot:
        app._session_name = "my-session"
        await pilot.click("#msg-input")
        for ch in "/reset":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause(0.1)
        assert app._session_name == "unsaved"


async def test_tool_panel_cleared_on_reset():
    app = _make_app()
    async with app.run_test() as pilot:
        panel = app.query_one("#tool-status", ToolPanel)
        panel.push(_ToolCall(name="web_search"))
        assert len(panel._calls) == 1
        await pilot.click("#msg-input")
        for ch in "/reset":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause(0.1)
        assert len(panel._calls) == 0


async def test_unknown_command_no_crash():
    app = _make_app()
    async with app.run_test() as pilot:
        await pilot.click("#msg-input")
        for ch in "/notacommand":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause(0.1)
        # App still alive
        assert not app._exit_requested


async def test_load_missing_name_no_crash():
    app = _make_app()
    async with app.run_test() as pilot:
        await pilot.click("#msg-input")
        for ch in "/load":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause(0.1)
        assert not app._exit_requested


async def test_save_command_updates_session_name():
    app = _make_app()
    async with app.run_test() as pilot:
        with patch("tui.app.save_session", return_value="saved-name"):
            await pilot.click("#msg-input")
            for ch in "/save":
                await pilot.press(ch)
            await pilot.press("enter")
            await pilot.pause(0.1)
        assert app._session_name == "saved-name"


async def test_sessions_command_no_crash():
    app = _make_app()
    async with app.run_test() as pilot:
        with patch("tui.app.list_sessions", return_value=["session-1", "session-2"]):
            await pilot.click("#msg-input")
            for ch in "/sessions":
                await pilot.press(ch)
            await pilot.press("enter")
            await pilot.pause(0.1)
        assert not app._exit_requested
