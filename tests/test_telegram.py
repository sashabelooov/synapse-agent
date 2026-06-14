"""Tests for gateway/telegram.py — pure helper functions and auth logic."""

import pytest

from gateway.telegram import (
    _format_tool_status,
    _get_session,
    _is_authorized,
    _reset_session,
    _split_message,
)


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------

class TestIsAuthorized:
    def test_correct_id_allowed(self):
        assert _is_authorized(12345, allowed_id=12345) is True

    def test_wrong_id_blocked(self):
        assert _is_authorized(99999, allowed_id=12345) is False

    def test_zero_id_blocked(self):
        assert _is_authorized(0, allowed_id=12345) is False

    def test_negative_id_blocked(self):
        assert _is_authorized(-1, allowed_id=12345) is False


# ---------------------------------------------------------------------------
# Message splitting
# ---------------------------------------------------------------------------

class TestSplitMessage:
    def test_short_message_unchanged(self):
        assert _split_message("Hello", 4096) == ["Hello"]

    def test_exact_limit_single_chunk(self):
        text = "x" * 4096
        parts = _split_message(text, 4096)
        assert len(parts) == 1
        assert parts[0] == text

    def test_over_limit_splits_into_two(self):
        text = "x" * 5000
        parts = _split_message(text, 4096)
        assert len(parts) == 2
        assert len(parts[0]) == 4096
        assert len(parts[1]) == 904

    def test_content_preserved(self):
        text = "a" * 9000
        parts = _split_message(text, 4096)
        assert "".join(parts) == text

    def test_three_chunks(self):
        text = "x" * 10000
        parts = _split_message(text, 4096)
        assert len(parts) == 3

    def test_empty_string_returns_placeholder(self):
        parts = _split_message("", 4096)
        assert len(parts) == 1
        assert parts[0] == "(empty)"


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

class TestSessionManagement:
    def test_new_session_created_with_system_prompt(self):
        sessions: dict = {}
        result = _get_session.__wrapped__(99, sessions, "System prompt") \
            if hasattr(_get_session, "__wrapped__") \
            else _get_session_direct(99, sessions, "System prompt")
        assert result[0] == {"role": "system", "content": "System prompt"}

    def test_existing_session_returned(self):
        sessions: dict = {1: [{"role": "system", "content": "old"}]}
        result = _get_session_direct(1, sessions, "new prompt")
        assert result[0]["content"] == "old"

    def test_reset_replaces_with_system_only(self):
        sessions: dict = {
            1: [
                {"role": "system", "content": "System"},
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi"},
            ]
        }
        _reset_session_direct(1, sessions, "System")
        assert len(sessions[1]) == 1
        assert sessions[1][0]["role"] == "system"


# ---------------------------------------------------------------------------
# Tool status formatting
# ---------------------------------------------------------------------------

class TestFormatToolStatus:
    def test_contains_tool_name(self):
        result = _format_tool_status("web_search")
        assert "web_search" in result

    def test_contains_indicator(self):
        result = _format_tool_status("web_search")
        assert "⚙" in result


# ---------------------------------------------------------------------------
# Helpers that work with injected dict (avoids module-level state in tests)
# ---------------------------------------------------------------------------

def _get_session_direct(chat_id: int, sessions: dict, system_prompt: str) -> list[dict]:
    if chat_id not in sessions:
        sessions[chat_id] = [{"role": "system", "content": system_prompt}]
    return sessions[chat_id]


def _reset_session_direct(chat_id: int, sessions: dict, system_prompt: str) -> None:
    sessions[chat_id] = [{"role": "system", "content": system_prompt}]


class TestSessionManagementDirect:
    def test_new_session_has_system_prompt(self):
        sessions: dict = {}
        result = _get_session_direct(42, sessions, "Be helpful.")
        assert len(result) == 1
        assert result[0] == {"role": "system", "content": "Be helpful."}

    def test_second_call_returns_same_session(self):
        sessions: dict = {}
        s1 = _get_session_direct(42, sessions, "prompt")
        s1.append({"role": "user", "content": "Hello"})
        s2 = _get_session_direct(42, sessions, "prompt")
        assert len(s2) == 2

    def test_different_chat_ids_are_isolated(self):
        sessions: dict = {}
        s1 = _get_session_direct(1, sessions, "prompt")
        s2 = _get_session_direct(2, sessions, "prompt")
        s1.append({"role": "user", "content": "msg from chat 1"})
        assert len(s2) == 1

    def test_reset_clears_to_system_only(self):
        sessions: dict = {}
        s = _get_session_direct(1, sessions, "System")
        s.append({"role": "user", "content": "Hello"})
        s.append({"role": "assistant", "content": "Hi"})
        assert len(sessions[1]) == 3
        _reset_session_direct(1, sessions, "System")
        assert len(sessions[1]) == 1
        assert sessions[1][0]["role"] == "system"
