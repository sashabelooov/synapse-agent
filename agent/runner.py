"""Shared agent turn logic — the brain used by every interface (CLI, Telegram, …).

build_agent_state()  — creates the one-time setup (tools, system prompt, memory).
run_agent_turn()     — processes one user message: calls the model, executes tools,
                       streams output via callbacks, returns the full reply text.

No I/O here. All display is decoupled through callbacks so CLI, Telegram, and
future gateways control their own presentation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from models.base import ModelAdapter
from tools.base.tool import ToolDefinition
from agent.context import manage_context
from agent.thinking import FALLBACK_INSTRUCTION, split_thinking

SYSTEM_PROMPT = (
    "You are Synapse, a professional AI agent with access to tools. "
    "Always use the available tools when they can help. "
    "Never say you cannot do something if a tool exists for it. "
    "Be concise and precise."
)


@dataclass
class AgentState:
    """Immutable per-process setup shared across all sessions."""
    adapter: ModelAdapter
    model_name: str
    tools: list[ToolDefinition]
    formatted_tools: list[Any]
    system_prompt: str
    native_thinking: bool = field(default=False)


def build_agent_state(adapter: ModelAdapter, model_name: str) -> AgentState:
    """Build the shared state once at startup. Used by CLI and all gateways."""
    from tools import get_all_tools
    from agent.skills import get_skill_manager
    from agent.persistent_memory import get_memory_manager

    tools = get_all_tools()
    formatted_tools = adapter.format_tools(tools)
    native_thinking = adapter.uses_native_thinking()

    prompt = SYSTEM_PROMPT
    if not native_thinking:
        prompt += FALLBACK_INSTRUCTION

    skills_block = get_skill_manager().prompt_block()
    if skills_block:
        prompt += "\n\n" + skills_block

    memory_block = get_memory_manager().system_prompt_block()
    if memory_block:
        prompt += "\n\n" + memory_block

    return AgentState(
        adapter=adapter,
        model_name=model_name,
        tools=tools,
        formatted_tools=formatted_tools,
        system_prompt=prompt,
        native_thinking=native_thinking,
    )


def execute_tool(name: str, args: dict, tools: list[ToolDefinition]) -> str:
    """Find and call a tool by name. Returns the result string."""
    tool = next((t for t in tools if t.name == name), None)
    if tool is None:
        return f"Error: tool '{name}' not found."
    try:
        return tool.function(**args)
    except Exception as exc:
        return f"Error executing {name}: {exc}"


def run_agent_turn(
    user_message: str,
    messages: list[dict],
    state: AgentState,
    on_chunk: Callable[[str], None] | None = None,
    on_tool_call: Callable[[str, dict], None] | None = None,
    on_thinking: Callable[[str], None] | None = None,
) -> tuple[str, dict]:
    """Process one user turn.

    Appends the user message and all assistant/tool messages to `messages`
    in place. Calls callbacks as tokens and tool calls arrive.

    Returns (reply_text, usage) where usage = {"input": int, "output": int}.
    """
    messages.append({"role": "user", "content": user_message})

    reply_parts: list[str] = []
    total_usage: dict[str, int] = {"input": 0, "output": 0}

    adapter = state.adapter
    model_name = state.model_name
    tools = state.tools
    formatted_tools = state.formatted_tools

    while True:
        messages[:] = manage_context(messages, adapter, model_name)

        if adapter.supports_streaming():
            content, tool_calls, thinking, assistant_msg, usage = adapter.stream_chat(
                model_name,
                messages,
                formatted_tools,
                on_thinking or (lambda _: None),
                on_chunk or (lambda _: None),
            )
            messages.append(assistant_msg)
        else:
            response = adapter.chat(model_name, messages, formatted_tools)
            content, tool_calls, thinking = adapter.parse_response(response)
            usage = adapter.get_usage(response)
            messages.append(adapter.build_assistant_message(response))

            if thinking is None:
                thinking, content = split_thinking(content)

            if thinking and on_thinking:
                on_thinking(thinking)
            if content and on_chunk:
                on_chunk(content)

        if content:
            reply_parts.append(content)

        total_usage["input"] += usage.get("input", 0)
        total_usage["output"] += usage.get("output", 0)

        if not tool_calls:
            break

        for tc in tool_calls:
            if on_tool_call:
                on_tool_call(tc["name"], tc.get("arguments", {}))
            result = execute_tool(tc["name"], tc.get("arguments", {}), tools)
            messages.append(adapter.build_tool_result_message(tc, result))

    return "".join(reply_parts), total_usage
