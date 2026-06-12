from typing import Any

from openai import OpenAI

from .base import ModelAdapter
from tools.base.tool import ToolDefinition


class OpenAIAdapter(ModelAdapter):
    """Adapter for OpenAI models (GPT-4o, GPT-4o-mini, etc.)."""

    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)

    def format_tools(self, tools: list[ToolDefinition]) -> list[dict]:
        return [tool.to_provider_format("openai") for tool in tools]

    def chat(self, model_name: str, messages: list[dict], tools: list[dict]) -> Any:
        return self.client.chat.completions.create(
            model=model_name,
            messages=messages,
            tools=tools,
        )

    def parse_response(self, response: Any) -> tuple[str, list[dict], str | None]:
        message = response.choices[0].message
        content = message.content or ""
        tool_calls = []

        if message.tool_calls:
            import json

            for tc in message.tool_calls:
                tool_calls.append(
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": json.loads(tc.function.arguments),
                    }
                )

        # Standard chat models (gpt-4o) don't expose reasoning text, so we
        # return None and rely on the prompted <thinking> fallback.
        return content, tool_calls, None

    def get_usage(self, response: Any) -> dict:
        u = getattr(response, "usage", None)
        if not u:
            return {"input": 0, "output": 0}
        return {"input": u.prompt_tokens or 0, "output": u.completion_tokens or 0}

    def build_assistant_message(self, response: Any) -> dict:
        """Store the assistant message including tool_calls.

        OpenAI requires the assistant message (with tool_calls) to appear
        before the matching tool result messages, linked by tool_call_id.
        model_dump() keeps it JSON-serializable for sessions.
        """
        return response.choices[0].message.model_dump()

    def build_tool_result_message(self, tool_call: dict, result: str) -> dict:
        """Build the tool result message for the next chat turn."""
        return {
            "role": "tool",
            "tool_call_id": tool_call.get("id", ""),
            "content": result,
        }
