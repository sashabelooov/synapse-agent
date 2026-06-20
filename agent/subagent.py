"""Lightweight synchronous agent runner for child (sub) agents.

A subagent is a stripped-down agent turn with:
  - Its own isolated message history (no shared state with parent)
  - A restricted toolset (caller decides which tools are allowed)
  - A token budget — hard-stops and returns a truncated result when exceeded
  - A wall-clock timeout — hard-stops after timeout_s seconds
  - No streaming, no session, no memory writes, no skills

Used exclusively by the spawn_agent tool. Subagents cannot spawn further
subagents (the spawn_agent tool is never included in their toolset).
"""

from __future__ import annotations

import threading
from typing import Any

from tools.base.tool import ToolDefinition
from config import get_adapter, get_model_name

# Default read-only toolset for subagents — safe for parallel execution
DEFAULT_ALLOWED_TOOLS = {
    "read_file",
    "list_files",
    "tree_view",
    "grep_search",
    "web_search",
    "read_url",
    "search_knowledge",
    "describe_image",
}

_SUBAGENT_SYSTEM_PROMPT = (
    "You are a focused subagent. Complete the assigned task using the available "
    "tools. Be concise — your entire reply is returned as a string to the parent "
    "agent. Do not ask clarifying questions; do your best with what you have."
)

# Hard cap on the result string returned to the parent
_MAX_RESULT_CHARS = 8000


def run_subagent(
    task: str,
    all_tools: list[ToolDefinition],
    allowed_tools: set[str] | None = None,
    budget_tokens: int = 4000,
    timeout_s: float = 120.0,
) -> str:
    """Run a child agent for `task` and return its result as a string.

    Parameters
    ----------
    task:
        The task description given to the child agent as its first user message.
    all_tools:
        Full tool registry from the parent (filtered down to allowed_tools here).
    allowed_tools:
        Set of tool names the child may use. Defaults to DEFAULT_ALLOWED_TOOLS.
        The `spawn_agent` tool is always excluded regardless of this parameter.
    budget_tokens:
        Approximate output token budget. The loop stops when cumulative output
        tokens exceed this value and returns whatever was produced so far.
    timeout_s:
        Wall-clock timeout in seconds. If the child exceeds this, the current
        result (possibly partial) is returned with a timeout notice appended.

    Returns
    -------
    str
        The child agent's reply, truncated to _MAX_RESULT_CHARS. On timeout or
        budget exhaustion, a notice is appended to the result.
    """
    if allowed_tools is None:
        allowed_tools = DEFAULT_ALLOWED_TOOLS

    # Never allow spawn_agent inside a subagent — prevents recursion
    allowed_tools = allowed_tools - {"spawn_agent"}

    child_tools = [t for t in all_tools if t.name in allowed_tools]

    result_holder: list[str] = [""]
    error_holder: list[str] = [""]

    def _run() -> None:
        try:
            result_holder[0] = _execute(task, child_tools, budget_tokens)
        except Exception as exc:
            error_holder[0] = str(exc)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=timeout_s)

    if thread.is_alive():
        notice = f"\n\n[Subagent timed out after {timeout_s:.0f}s]"
        partial = result_holder[0] or "(no output before timeout)"
        return (partial + notice)[:_MAX_RESULT_CHARS]

    if error_holder[0]:
        return f"[Subagent error: {error_holder[0]}]"

    result = result_holder[0] or "(subagent produced no output)"
    if len(result) > _MAX_RESULT_CHARS:
        result = result[:_MAX_RESULT_CHARS] + "\n\n[truncated]"
    return result


def _execute(
    task: str,
    tools: list[ToolDefinition],
    budget_tokens: int,
) -> str:
    """Inner synchronous execution loop — runs inside the worker thread."""
    adapter = get_adapter()
    model_name = get_model_name()
    formatted_tools = adapter.format_tools(tools)

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _SUBAGENT_SYSTEM_PROMPT},
        {"role": "user", "content": task},
    ]
    reply_parts: list[str] = []
    output_tokens_used = 0

    while True:
        response = adapter.chat(model_name, messages, formatted_tools)
        content, tool_calls, _ = adapter.parse_response(response)
        usage = adapter.get_usage(response)
        output_tokens_used += usage.get("output", 0)

        messages.append(adapter.build_assistant_message(response))

        if content:
            reply_parts.append(content)

        if not tool_calls or output_tokens_used >= budget_tokens:
            if output_tokens_used >= budget_tokens:
                reply_parts.append("\n\n[Budget exhausted — stopping early]")
            break

        for tc in tool_calls:
            tool = next((t for t in tools if t.name == tc["name"]), None)
            if tool is None:
                tool_result = f"Error: tool '{tc['name']}' not available in this subagent."
            else:
                try:
                    tool_result = tool.function(**tc.get("arguments", {}))
                except Exception as exc:
                    tool_result = f"Error: {exc}"
            messages.append(adapter.build_tool_result_message(tc, tool_result))

    return "".join(reply_parts)
