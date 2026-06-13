"""Tests for agent/session.py — SQLite backend."""

import os
import pytest

from agent.session import (
    _db_path,
    _decode_content,
    _encode_content,
    list_sessions,
    load_session,
    save_session,
    search_sessions_db,
)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Point SYNAPSE_HOME at a temp dir for every test."""
    monkeypatch.setenv("SYNAPSE_HOME", str(tmp_path))
    yield


# ---------------------------------------------------------------------------
# Content encoding helpers
# ---------------------------------------------------------------------------

class TestContentEncoding:
    def test_string_passthrough(self):
        assert _encode_content("hello") == "hello"

    def test_list_encodes_to_json(self):
        encoded = _encode_content([{"type": "text", "text": "hi"}])
        assert encoded.startswith("[")

    def test_decode_string(self):
        assert _decode_content("hello") == "hello"

    def test_decode_json_list(self):
        import json
        raw = json.dumps([{"type": "text", "text": "hi"}])
        result = _decode_content(raw)
        assert isinstance(result, list)

    def test_decode_invalid_json_stays_string(self):
        assert _decode_content("not json {") == "not json {"


# ---------------------------------------------------------------------------
# save / load round-trip
# ---------------------------------------------------------------------------

class TestSaveLoad:
    def test_basic_roundtrip(self):
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        name = save_session(messages, "test-session")
        assert name == "test-session"
        loaded = load_session("test-session")
        assert loaded == messages

    def test_complex_content_roundtrip(self):
        content = [{"type": "text", "text": "complex"}]
        messages = [{"role": "assistant", "content": content}]
        save_session(messages, "complex")
        loaded = load_session("complex")
        assert loaded[0]["content"] == content

    def test_auto_name_generated(self):
        name = save_session([{"role": "user", "content": "hi"}])
        assert name.startswith("session-")

    def test_overwrite_same_name(self):
        save_session([{"role": "user", "content": "v1"}], "mysession")
        save_session([{"role": "user", "content": "v2"}], "mysession")
        loaded = load_session("mysession")
        assert loaded[0]["content"] == "v2"
        assert len(loaded) == 1

    def test_load_missing_raises_value_error(self):
        with pytest.raises(ValueError, match="not found"):
            load_session("does-not-exist")

    def test_system_message_preserved(self):
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello"},
        ]
        save_session(messages, "with-system")
        loaded = load_session("with-system")
        assert loaded[0]["role"] == "system"
        assert loaded[0]["content"] == "You are a helpful assistant."


# ---------------------------------------------------------------------------
# list_sessions
# ---------------------------------------------------------------------------

class TestListSessions:
    def test_empty_initially(self):
        assert list_sessions() == []

    def test_single_session(self):
        save_session([{"role": "user", "content": "hi"}], "alpha")
        assert list_sessions() == ["alpha"]

    def test_multiple_sessions(self):
        save_session([{"role": "user", "content": "a"}], "alpha")
        save_session([{"role": "user", "content": "b"}], "beta")
        names = list_sessions()
        assert "alpha" in names
        assert "beta" in names

    def test_most_recent_first(self):
        save_session([{"role": "user", "content": "a"}], "older")
        save_session([{"role": "user", "content": "b"}], "newer")
        names = list_sessions()
        assert names[0] == "newer"


# ---------------------------------------------------------------------------
# FTS5 search
# ---------------------------------------------------------------------------

class TestSearchSessions:
    def test_basic_search(self):
        messages = [
            {"role": "user", "content": "What is the capital of France?"},
            {"role": "assistant", "content": "The capital of France is Paris."},
        ]
        save_session(messages, "geo-session")
        results = search_sessions_db("France")
        assert len(results) >= 1
        assert any(r["session"] == "geo-session" for r in results)

    def test_no_match_returns_empty(self):
        save_session([{"role": "user", "content": "Python is great"}], "py-session")
        results = search_sessions_db("quantum physics")
        assert results == []

    def test_result_fields(self):
        save_session([{"role": "user", "content": "testing the search feature"}], "s1")
        results = search_sessions_db("testing")
        assert len(results) >= 1
        r = results[0]
        assert "session" in r
        assert "date" in r
        assert "role" in r
        assert "excerpt" in r

    def test_long_content_truncated(self):
        long_content = "keyword " + ("x" * 300)
        save_session([{"role": "user", "content": long_content}], "long-session")
        results = search_sessions_db("keyword")
        assert len(results) >= 1
        assert len(results[0]["excerpt"]) <= 210  # 200 chars + ellipsis

    def test_limit_respected(self):
        for i in range(5):
            save_session(
                [{"role": "user", "content": f"unique_term session {i}"}],
                f"session-{i}",
            )
        results = search_sessions_db("unique_term", limit=3)
        assert len(results) <= 3

    def test_search_across_multiple_sessions(self):
        save_session([{"role": "user", "content": "auth bug discussion"}], "s-auth-1")
        save_session([{"role": "user", "content": "auth token refresh"}], "s-auth-2")
        results = search_sessions_db("auth")
        sessions_found = {r["session"] for r in results}
        assert "s-auth-1" in sessions_found
        assert "s-auth-2" in sessions_found
