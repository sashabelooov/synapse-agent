"""Tests for agent/runner.py — shared agent turn logic."""

from unittest.mock import MagicMock, patch

import pytest

from agent.runner import AgentState, execute_tool, run_agent_turn
from tools.base.tool import ToolDefinition


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tool(name: str, return_value: str = "tool result") -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=f"Test tool {name}",
        parameters={"type": "object", "properties": {}, "required": []},
        function=lambda **_: return_value,
    )


def _make_state(
    streaming: bool = False,
    native_thinking: bool = False,
    tools: list | None = None,
    reply: str = "Hello!",
    tool_calls: list | None = None,
) -> AgentState:
    adapter = MagicMock()
    adapter.uses_native_thinking.return_value = native_thinking
    adapter.supports_streaming.return_value = streaming
    adapter.format_tools.return_value = []

    if streaming:
        adapter.stream_chat.return_value = (
            reply, tool_calls or [], None,
            {"role": "assistant", "content": reply},
            {"input": 10, "output": 5},
        )
    else:
        response = MagicMock()
        adapter.chat.return_value = response
        adapter.parse_response.return_value = (reply, tool_calls or [], None)
        adapter.get_usage.return_value = {"input": 10, "output": 5}
        adapter.build_assistant_message.return_value = {"role": "assistant", "content": reply}

    adapter.build_tool_result_message.side_effect = lambda tc, result: {
        "role": "tool",
        "content": result,
        "tool_call_id": tc.get("id", ""),
    }

    tool_list = tools or []
    return AgentState(
        adapter=adapter,
        model_name="test-model",
        tools=tool_list,
        formatted_tools=[],
        system_prompt="You are helpful.",
        native_thinking=native_thinking,
    )


def _base_messages() -> list[dict]:
    return [{"role": "system", "content": "You are helpful."}]


# ---------------------------------------------------------------------------
# execute_tool
# ---------------------------------------------------------------------------

class TestExecuteTool:
    def test_found_and_called(self):
        tool = _make_tool("ping", "pong")
        result = execute_tool("ping", {}, [tool])
        assert result == "pong"

    def test_not_found_returns_error(self):
        result = execute_tool("ghost", {}, [])
        assert "Error" in result and "ghost" in result

    def test_exception_returns_error(self):
        def boom(**_):
            raise ValueError("kaboom")

        tool = ToolDefinition(
            name="boom",
            description="",
            parameters={"type": "object", "properties": {}},
            function=boom,
        )
        result = execute_tool("boom", {}, [tool])
        assert "Error" in result and "kaboom" in result

    def test_kwargs_passed_correctly(self):
        received: dict = {}

        def capture(**kwargs):
            received.update(kwargs)
            return "ok"

        tool = ToolDefinition(
            name="capture",
            description="",
            parameters={"type": "object", "properties": {}},
            function=capture,
        )
        execute_tool("capture", {"x": 1, "y": 2}, [tool])
        assert received == {"x": 1, "y": 2}


# ---------------------------------------------------------------------------
# run_agent_turn — non-streaming
# ---------------------------------------------------------------------------

class TestRunAgentTurnNonStreaming:
    def test_simple_reply(self):
        state = _make_state(reply="Hello!")
        messages = _base_messages()
        chunks: list[str] = []

        reply, usage = run_agent_turn("Hi", messages, state, on_chunk=chunks.append)

        assert reply == "Hello!"
        assert "Hello!" in "".join(chunks)

    def test_user_message_appended(self):
        state = _make_state()
        messages = _base_messages()

        run_agent_turn("Test message", messages, state)

        roles = [m["role"] for m in messages]
        assert "user" in roles
        assert messages[1]["content"] == "Test message"

    def test_assistant_message_appended(self):
        state = _make_state(reply="My reply")
        messages = _base_messages()

        run_agent_turn("Hi", messages, state)

        roles = [m["role"] for m in messages]
        assert "assistant" in roles

    def test_usage_returned(self):
        state = _make_state()
        messages = _base_messages()

        _, usage = run_agent_turn("Hi", messages, state)

        assert usage["input"] == 10
        assert usage["output"] == 5

    def test_on_chunk_called(self):
        state = _make_state(reply="chunk text")
        messages = _base_messages()
        chunks: list[str] = []

        run_agent_turn("Hi", messages, state, on_chunk=chunks.append)

        assert "".join(chunks) == "chunk text"

    def test_no_callbacks_still_works(self):
        state = _make_state()
        messages = _base_messages()
        reply, _ = run_agent_turn("Hi", messages, state)
        assert reply == "Hello!"


# ---------------------------------------------------------------------------
# run_agent_turn — tool calls
# ---------------------------------------------------------------------------

class TestRunAgentTurnWithTools:
    def test_tool_call_executed(self):
        tool = _make_tool("my_tool", "tool output")
        tool_call = {"name": "my_tool", "arguments": {}, "id": "tc1"}

        # First call returns tool_calls, second call returns final reply
        adapter = MagicMock()
        adapter.supports_streaming.return_value = False
        adapter.uses_native_thinking.return_value = False
        adapter.format_tools.return_value = []

        response1, response2 = MagicMock(), MagicMock()
        adapter.chat.side_effect = [response1, response2]
        adapter.parse_response.side_effect = [
            ("", [tool_call], None),
            ("Final answer", [], None),
        ]
        adapter.get_usage.return_value = {"input": 5, "output": 3}
        adapter.build_assistant_message.side_effect = [
            {"role": "assistant", "content": ""},
            {"role": "assistant", "content": "Final answer"},
        ]
        adapter.build_tool_result_message.return_value = {
            "role": "tool", "content": "tool output", "tool_call_id": "tc1"
        }

        state = AgentState(
            adapter=adapter,
            model_name="test",
            tools=[tool],
            formatted_tools=[],
            system_prompt="",
            native_thinking=False,
        )

        messages = _base_messages()
        reply, _ = run_agent_turn("Use my_tool", messages, state)

        assert reply == "Final answer"
        adapter.build_tool_result_message.assert_called_once()

    def test_on_tool_call_callback_fired(self):
        tool = _make_tool("ping", "pong")
        tool_call = {"name": "ping", "arguments": {}, "id": "tc1"}

        adapter = MagicMock()
        adapter.supports_streaming.return_value = False
        adapter.uses_native_thinking.return_value = False
        adapter.format_tools.return_value = []

        r1, r2 = MagicMock(), MagicMock()
        adapter.chat.side_effect = [r1, r2]
        adapter.parse_response.side_effect = [
            ("", [tool_call], None),
            ("Done", [], None),
        ]
        adapter.get_usage.return_value = {"input": 1, "output": 1}
        adapter.build_assistant_message.side_effect = [
            {"role": "assistant", "content": ""},
            {"role": "assistant", "content": "Done"},
        ]
        adapter.build_tool_result_message.return_value = {
            "role": "tool", "content": "pong", "tool_call_id": "tc1"
        }

        state = AgentState(
            adapter=adapter,
            model_name="test",
            tools=[tool],
            formatted_tools=[],
            system_prompt="",
        )

        called_with: list[str] = []
        run_agent_turn(
            "Ping",
            _base_messages(),
            state,
            on_tool_call=lambda name, _: called_with.append(name),
        )

        assert "ping" in called_with


# ---------------------------------------------------------------------------
# run_agent_turn — streaming
# ---------------------------------------------------------------------------

class TestRunAgentTurnStreaming:
    def test_streaming_reply(self):
        state = _make_state(streaming=True, reply="Streamed reply")
        messages = _base_messages()
        chunks: list[str] = []

        reply, _ = run_agent_turn("Hi", messages, state, on_chunk=chunks.append)

        assert reply == "Streamed reply"
