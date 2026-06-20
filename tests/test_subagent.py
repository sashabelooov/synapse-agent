"""Tests for agent/subagent.py and tools/spawn_agent/spawn_agent.py.

All model adapter calls are mocked — no network or API keys needed.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

from tools.base.tool import ToolDefinition
from agent.subagent import (
    DEFAULT_ALLOWED_TOOLS,
    _MAX_RESULT_CHARS,
    run_subagent,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tool(name: str, result: str = "ok") -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=f"Test tool {name}",
        parameters={"type": "object", "properties": {}, "required": []},
        function=lambda **_: result,
    )


def _make_adapter(content: str = "done", tool_calls: list | None = None):
    """Return a mock adapter whose chat() produces content + optional tool calls."""
    adapter = MagicMock()
    adapter.format_tools.return_value = []
    adapter.uses_native_thinking.return_value = False

    response = MagicMock()
    adapter.chat.return_value = response
    adapter.parse_response.return_value = (content, tool_calls or [], None)
    adapter.get_usage.return_value = {"input": 10, "output": 20}
    adapter.build_assistant_message.return_value = {
        "role": "assistant", "content": content
    }
    adapter.build_tool_result_message.return_value = {
        "role": "tool", "content": "tool result"
    }
    return adapter


# ---------------------------------------------------------------------------
# run_subagent — basic execution
# ---------------------------------------------------------------------------

class TestRunSubagent:
    def test_returns_content_string(self):
        tools = [_make_tool("read_file")]
        adapter = _make_adapter(content="The answer is 42.")

        with patch("agent.subagent.get_adapter", return_value=adapter), \
             patch("agent.subagent.get_model_name", return_value="test-model"):
            result = run_subagent("What is 6x7?", tools)

        assert "42" in result

    def test_returns_string_type(self):
        adapter = _make_adapter(content="result")
        with patch("agent.subagent.get_adapter", return_value=adapter), \
             patch("agent.subagent.get_model_name", return_value="test-model"):
            result = run_subagent("task", [])
        assert isinstance(result, str)

    def test_empty_content_fallback_message(self):
        adapter = _make_adapter(content="")
        with patch("agent.subagent.get_adapter", return_value=adapter), \
             patch("agent.subagent.get_model_name", return_value="test-model"):
            result = run_subagent("task", [])
        assert result  # never empty

    def test_tool_is_called_when_requested(self):
        call_log: list[str] = []

        def my_tool(**_):
            call_log.append("called")
            return "tool output"

        tool = ToolDefinition(
            name="read_file",
            description="read",
            parameters={"type": "object", "properties": {}, "required": []},
            function=my_tool,
        )

        # First turn: returns a tool call. Second turn: returns content (no tools).
        adapter = MagicMock()
        adapter.format_tools.return_value = []
        adapter.uses_native_thinking.return_value = False
        adapter.get_usage.return_value = {"input": 5, "output": 5}
        adapter.build_assistant_message.return_value = {"role": "assistant", "content": ""}
        adapter.build_tool_result_message.return_value = {"role": "tool", "content": "tool output"}

        first_response = MagicMock()
        second_response = MagicMock()
        adapter.chat.side_effect = [first_response, second_response]
        adapter.parse_response.side_effect = [
            ("", [{"name": "read_file", "arguments": {}}], None),
            ("final answer", [], None),
        ]

        with patch("agent.subagent.get_adapter", return_value=adapter), \
             patch("agent.subagent.get_model_name", return_value="test-model"):
            result = run_subagent("Read something", [tool], allowed_tools={"read_file"})

        assert "called" in call_log
        assert "final answer" in result

    def test_unknown_tool_returns_error_message(self):
        adapter = MagicMock()
        adapter.format_tools.return_value = []
        adapter.uses_native_thinking.return_value = False
        adapter.get_usage.return_value = {"input": 5, "output": 5}
        adapter.build_assistant_message.return_value = {"role": "assistant", "content": ""}
        adapter.build_tool_result_message.return_value = {"role": "tool", "content": "err"}

        resp1 = MagicMock()
        resp2 = MagicMock()
        adapter.chat.side_effect = [resp1, resp2]
        adapter.parse_response.side_effect = [
            ("", [{"name": "nonexistent_tool", "arguments": {}}], None),
            ("done", [], None),
        ]

        with patch("agent.subagent.get_adapter", return_value=adapter), \
             patch("agent.subagent.get_model_name", return_value="test-model"):
            result = run_subagent("task", [])

        assert "done" in result


# ---------------------------------------------------------------------------
# Tool isolation — only allowed tools are passed to child
# ---------------------------------------------------------------------------

class TestToolIsolation:
    def test_only_allowed_tools_visible(self):
        safe_tool = _make_tool("read_file")
        unsafe_tool = _make_tool("run_command")
        all_tools = [safe_tool, unsafe_tool]

        captured_tools: list = []

        def fake_execute(task, tools, budget):
            captured_tools.extend(tools)
            return "ok"

        with patch("agent.subagent._execute", side_effect=fake_execute):
            run_subagent("task", all_tools, allowed_tools={"read_file"})

        tool_names = {t.name for t in captured_tools}
        assert "read_file" in tool_names
        assert "run_command" not in tool_names

    def test_spawn_agent_always_excluded(self):
        spawn_tool = _make_tool("spawn_agent")
        all_tools = [spawn_tool, _make_tool("read_file")]

        captured_tools: list = []

        def fake_execute(task, tools, budget):
            captured_tools.extend(tools)
            return "ok"

        with patch("agent.subagent._execute", side_effect=fake_execute):
            # Even if caller explicitly allows spawn_agent, it must be stripped
            run_subagent("task", all_tools, allowed_tools={"read_file", "spawn_agent"})

        assert not any(t.name == "spawn_agent" for t in captured_tools)

    def test_default_allowed_tools_does_not_include_spawn_agent(self):
        assert "spawn_agent" not in DEFAULT_ALLOWED_TOOLS

    def test_default_allowed_tools_does_not_include_run_command(self):
        assert "run_command" not in DEFAULT_ALLOWED_TOOLS


# ---------------------------------------------------------------------------
# Budget enforcement
# ---------------------------------------------------------------------------

class TestBudgetEnforcement:
    def test_stops_when_budget_exceeded(self):
        adapter = MagicMock()
        adapter.format_tools.return_value = []
        adapter.uses_native_thinking.return_value = False
        # Return usage that immediately exceeds budget
        adapter.get_usage.return_value = {"input": 0, "output": 9999}
        adapter.build_assistant_message.return_value = {"role": "assistant", "content": "partial"}
        adapter.build_tool_result_message.return_value = {"role": "tool", "content": ""}

        response = MagicMock()
        adapter.chat.return_value = response
        adapter.parse_response.return_value = (
            "partial result",
            [{"name": "read_file", "arguments": {}}],  # would loop without budget
            None,
        )

        with patch("agent.subagent.get_adapter", return_value=adapter), \
             patch("agent.subagent.get_model_name", return_value="test-model"):
            result = run_subagent("task", [], budget_tokens=100)

        # Should have stopped and appended budget notice
        assert "budget" in result.lower() or "partial" in result.lower()
        # Should NOT have looped indefinitely
        assert adapter.chat.call_count == 1

    def test_result_truncated_to_max_chars(self):
        long_content = "x" * (_MAX_RESULT_CHARS + 500)
        adapter = _make_adapter(content=long_content)

        with patch("agent.subagent.get_adapter", return_value=adapter), \
             patch("agent.subagent.get_model_name", return_value="test-model"):
            result = run_subagent("task", [])

        assert len(result) <= _MAX_RESULT_CHARS + 20  # +20 for [truncated] suffix
        assert "truncated" in result


# ---------------------------------------------------------------------------
# Timeout enforcement
# ---------------------------------------------------------------------------

class TestTimeoutEnforcement:
    def test_timeout_returns_partial_with_notice(self):
        def slow_execute(task, tools, budget):
            time.sleep(5)  # will be cut off
            return "should not appear"

        with patch("agent.subagent._execute", side_effect=slow_execute):
            result = run_subagent("task", [], timeout_s=0.1)

        assert "timed out" in result.lower() or "timeout" in result.lower()

    def test_timeout_does_not_raise(self):
        def slow_execute(task, tools, budget):
            time.sleep(5)
            return "done"

        with patch("agent.subagent._execute", side_effect=slow_execute):
            result = run_subagent("task", [], timeout_s=0.1)

        assert isinstance(result, str)

    def test_fast_task_completes_before_timeout(self):
        adapter = _make_adapter(content="fast answer")
        with patch("agent.subagent.get_adapter", return_value=adapter), \
             patch("agent.subagent.get_model_name", return_value="test-model"):
            result = run_subagent("task", [], timeout_s=10.0)

        assert "fast answer" in result


# ---------------------------------------------------------------------------
# spawn_agent tool
# ---------------------------------------------------------------------------

class TestSpawnAgentTool:
    def _call(self, tasks, **kwargs):
        from tools.spawn_agent.spawn_agent import _spawn
        return _spawn(tasks=tasks, **kwargs)

    def test_empty_tasks_returns_error(self):
        result = self._call([])
        assert "empty" in result.lower()

    def test_too_many_tasks_returns_error(self):
        tasks = [f"task {i}" for i in range(20)]
        result = self._call(tasks)
        assert "too many" in result.lower() or "maximum" in result.lower()

    def test_single_task_returns_result(self):
        with patch("tools.spawn_agent.spawn_agent.run_subagent", return_value="answer A"), \
             patch("tools.spawn_agent.spawn_agent.get_all_tools", return_value=[]):
            result = self._call(["What is 2+2?"])

        assert "answer A" in result
        assert "[Task 1]" in result

    def test_multiple_tasks_numbered(self):
        answers = ["answer A", "answer B", "answer C"]
        call_count = [0]

        def fake_subagent(task, all_tools, allowed, budget, timeout):
            idx = call_count[0]
            call_count[0] += 1
            return answers[idx]

        with patch("tools.spawn_agent.spawn_agent.run_subagent", side_effect=fake_subagent), \
             patch("tools.spawn_agent.spawn_agent.get_all_tools", return_value=[]):
            result = self._call(["task 1", "task 2", "task 3"])

        assert "[Task 1]" in result
        assert "[Task 2]" in result
        assert "[Task 3]" in result
        assert "answer A" in result
        assert "answer B" in result
        assert "answer C" in result

    def test_spawn_agent_excluded_from_child_tools(self):
        captured_allowed: list[set] = []

        def fake_subagent(task, all_tools, allowed, budget, timeout):
            captured_allowed.append(set(allowed))
            return "done"

        spawn_tool = _make_tool("spawn_agent")
        with patch("tools.spawn_agent.spawn_agent.run_subagent", side_effect=fake_subagent), \
             patch("tools.spawn_agent.spawn_agent.get_all_tools", return_value=[spawn_tool]):
            self._call(["task"])

        for allowed in captured_allowed:
            assert "spawn_agent" not in allowed

    def test_tools_override_passed_to_subagent(self):
        captured_allowed: list[set] = []

        def fake_subagent(task, all_tools, allowed, budget, timeout):
            captured_allowed.append(set(allowed))
            return "done"

        with patch("tools.spawn_agent.spawn_agent.run_subagent", side_effect=fake_subagent), \
             patch("tools.spawn_agent.spawn_agent.get_all_tools", return_value=[]):
            self._call(["task"], tools_override="read_file,grep_search")

        assert captured_allowed[0] == {"read_file", "grep_search"}

    def test_budget_forwarded_to_subagent(self):
        captured_budget: list[int] = []

        def fake_subagent(task, all_tools, allowed, budget, timeout):
            captured_budget.append(budget)
            return "done"

        with patch("tools.spawn_agent.spawn_agent.run_subagent", side_effect=fake_subagent), \
             patch("tools.spawn_agent.spawn_agent.get_all_tools", return_value=[]):
            self._call(["task"], budget_tokens=999)

        assert captured_budget[0] == 999

    def test_timeout_forwarded_to_subagent(self):
        captured_timeout: list[float] = []

        def fake_subagent(task, all_tools, allowed, budget, timeout):
            captured_timeout.append(timeout)
            return "done"

        with patch("tools.spawn_agent.spawn_agent.run_subagent", side_effect=fake_subagent), \
             patch("tools.spawn_agent.spawn_agent.get_all_tools", return_value=[]):
            self._call(["task"], timeout_s=30.0)

        assert captured_timeout[0] == 30.0

    def test_subagent_exception_returns_error_in_result(self):
        def failing_subagent(*args, **kwargs):
            raise RuntimeError("model API down")

        with patch("tools.spawn_agent.spawn_agent.run_subagent", side_effect=failing_subagent), \
             patch("tools.spawn_agent.spawn_agent.get_all_tools", return_value=[]):
            result = self._call(["task"])

        assert "[Task 1]" in result
        assert "error" in result.lower()


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

class TestToolRegistration:
    def test_spawn_agent_in_registry(self):
        from tools.base.registry import get_all_tools
        names = {t.name for t in get_all_tools()}
        assert "spawn_agent" in names

    def test_tool_name(self):
        from tools.spawn_agent.spawn_agent import tool
        assert tool.name == "spawn_agent"

    def test_tasks_is_required(self):
        from tools.spawn_agent.spawn_agent import tool
        assert "tasks" in tool.parameters["required"]

    def test_tasks_is_array(self):
        from tools.spawn_agent.spawn_agent import tool
        assert tool.parameters["properties"]["tasks"]["type"] == "array"

    def test_tool_function_callable(self):
        from tools.spawn_agent.spawn_agent import tool
        assert callable(tool.function)
