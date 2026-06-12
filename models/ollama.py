from typing import Any

from ollama import Client

from .base import ModelAdapter
from tools.base import ToolDefinition


class OllamaAdapter(ModelAdapter):
    def __init__(self, client: Client):
        self.client = client
        # Reasoning models (e.g. gpt-oss) return native thinking when asked.
        # We try it; if a model rejects it, we disable and fall back.
        self._think = True

    def format_tools(self, tools: list[ToolDefinition]) -> list[dict]:
        return [tool.to_provider_format("ollama") for tool in tools]

    def uses_native_thinking(self) -> bool:
        return self._think

    def chat(self, model_name: str, messages: list[dict], tools: list[dict]) -> Any:
        if self._think:
            try:
                return self.client.chat(
                    model=model_name,
                    messages=messages,
                    tools=tools,
                    think=True,
                    stream=False,
                )
            except Exception:
                # Model doesn't support thinking — disable and retry plainly.
                self._think = False

        return self.client.chat(
            model=model_name,
            messages=messages,
            tools=tools,
            stream=False,
        )

    def parse_response(self, response: Any) -> tuple[str, list[dict], str | None]:
        assistant_message = response.message
        content = assistant_message.content or ""
        thinking = getattr(assistant_message, "thinking", None)
        tool_calls = []

        if assistant_message.tool_calls:
            for tool_call in assistant_message.tool_calls:
                tool_calls.append(
                    {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    }
                )

        return content, tool_calls, thinking

    def build_assistant_message(self, response: Any) -> dict:
        """Store the assistant message as a plain dict (preserves tool_calls)."""
        message = response.message
        if hasattr(message, "model_dump"):
            return message.model_dump()
        return message

    def build_tool_result_message(self, tool_call: dict, result: str) -> dict:
        """Ollama feeds tool output back via a 'tool' role message."""
        msg = {"role": "tool", "content": result}
        if tool_call.get("name"):
            msg["tool_name"] = tool_call["name"]
        return msg

    def get_usage(self, response: Any) -> dict:
        return {
            "input": getattr(response, "prompt_eval_count", 0) or 0,
            "output": getattr(response, "eval_count", 0) or 0,
        }

    def supports_streaming(self) -> bool:
        return True

    def stream_chat(self, model_name, messages, tools, on_thinking, on_content):
        """Stream a response, calling on_thinking/on_content with text deltas.

        Returns (content, tool_calls, thinking, assistant_message, usage). The
        assistant_message is a plain dict for history; usage has input/output
        token counts from the final chunk.
        """
        content_parts: list[str] = []
        thinking_parts: list[str] = []
        tool_calls: list[dict] = []
        usage = {"input": 0, "output": 0}

        def run(use_think: bool):
            return self.client.chat(
                model=model_name,
                messages=messages,
                tools=tools,
                think=use_think,
                stream=True,
            )

        try:
            stream = run(self._think)
        except Exception:
            self._think = False
            stream = run(False)

        for chunk in stream:
            msg = getattr(chunk, "message", None)
            if msg is None:
                continue
            think_delta = getattr(msg, "thinking", None)
            if think_delta:
                on_thinking(think_delta)
                thinking_parts.append(think_delta)
            if msg.content:
                on_content(msg.content)
                content_parts.append(msg.content)
            if getattr(msg, "tool_calls", None):
                for tc in msg.tool_calls:
                    tool_calls.append(
                        {"name": tc.function.name, "arguments": tc.function.arguments}
                    )
            if getattr(chunk, "done", False):
                usage["input"] = getattr(chunk, "prompt_eval_count", 0) or 0
                usage["output"] = getattr(chunk, "eval_count", 0) or 0

        content = "".join(content_parts)
        thinking = "".join(thinking_parts) or None

        assistant_message: dict = {"role": "assistant", "content": content}
        if thinking:
            assistant_message["thinking"] = thinking
        if tool_calls:
            assistant_message["tool_calls"] = [
                {"function": {"name": t["name"], "arguments": t["arguments"]}}
                for t in tool_calls
            ]

        return content, tool_calls, thinking, assistant_message, usage
