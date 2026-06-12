from typing import Any

import anthropic

from .base import ModelAdapter
from tools.base.tool import ToolDefinition


class AnthropicAdapter(ModelAdapter):
    """Adapter for Anthropic models (Claude)."""

    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        # Extended thinking. Enabled by default; if a model rejects it we
        # disable and fall back so the working path never breaks.
        self._thinking = True
        self._thinking_budget = 2048
        self._max_tokens = 8192

    def format_tools(self, tools: list[ToolDefinition]) -> list[dict]:
        return [tool.to_provider_format("anthropic") for tool in tools]

    def uses_native_thinking(self) -> bool:
        return self._thinking

    def chat(self, model_name: str, messages: list[dict], tools: list[dict]) -> Any:
        # Anthropic separates system from messages. Multiple system messages
        # (e.g. base prompt + a compaction summary) are concatenated, not
        # overwritten, so none are silently lost.
        system_parts = []
        chat_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_parts.append(msg["content"])
            else:
                chat_messages.append(msg)
        system_prompt = "\n\n".join(system_parts)

        kwargs: dict = {
            "model": model_name,
            "max_tokens": self._max_tokens,
            "system": system_prompt,
            "messages": chat_messages,
            "tools": tools,
        }

        if self._thinking:
            try:
                return self.client.messages.create(
                    **kwargs,
                    thinking={"type": "enabled", "budget_tokens": self._thinking_budget},
                )
            except Exception:
                # Model/config doesn't support extended thinking — disable.
                self._thinking = False

        return self.client.messages.create(max_tokens=4096, **{k: v for k, v in kwargs.items() if k != "max_tokens"})

    def parse_response(self, response: Any) -> tuple[str, list[dict], str | None]:
        content = ""
        thinking = ""
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "thinking":
                thinking += getattr(block, "thinking", "")
            elif block.type == "tool_use":
                tool_calls.append(
                    {
                        "id": block.id,
                        "name": block.name,
                        "arguments": block.input,
                    }
                )

        return content, tool_calls, (thinking or None)

    def get_usage(self, response: Any) -> dict:
        u = getattr(response, "usage", None)
        if not u:
            return {"input": 0, "output": 0}
        return {"input": getattr(u, "input_tokens", 0) or 0, "output": getattr(u, "output_tokens", 0) or 0}

    def build_assistant_message(self, response: Any) -> dict:
        """Store the full content blocks (text + thinking + tool_use) as dicts.

        Anthropic requires both thinking and tool_use blocks to be preserved in
        history or the follow-up tool_result turn will be rejected.
        """
        content = []
        for block in response.content:
            if hasattr(block, "model_dump"):
                content.append(block.model_dump())
            else:
                content.append(block)
        return {"role": "assistant", "content": content}

    def build_tool_result_message(self, tool_call: dict, result: str) -> dict:
        """Build the tool result message for the next chat turn."""
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_call.get("id", ""),
                    "content": result,
                }
            ],
        }
