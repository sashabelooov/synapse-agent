from abc import ABC, abstractmethod
from typing import Any, Sequence

from tools.base import ToolDefinition


class ModelAdapter(ABC):
    """Abstract interface for different model providers."""

    @abstractmethod
    def format_tools(self, tools: Sequence[ToolDefinition]) -> Any:
        raise NotImplementedError

    @abstractmethod
    def chat(self, model_name: str, messages: list[dict], tools: Any) -> Any:
        raise NotImplementedError

    @abstractmethod
    def parse_response(self, response: Any) -> tuple[str, list[dict], str | None]:
        """Return (content, tool_calls, thinking).

        thinking is the model's native reasoning if the provider exposes it,
        else None (the loop will try to extract a prompted <thinking> block).
        """
        raise NotImplementedError

    def uses_native_thinking(self) -> bool:
        """True if this provider returns reasoning in a native channel.

        When False, the loop appends the prompted-scratchpad instruction so the
        model produces <thinking> tags we can split out ourselves.
        """
        return False

    def get_usage(self, response: Any) -> dict:
        """Return token usage as {'input': int, 'output': int}.

        Default is zeros; each adapter overrides with its provider's fields.
        """
        return {"input": 0, "output": 0}

    def supports_streaming(self) -> bool:
        """True if this adapter implements stream_chat for live token output."""
        return False

    @abstractmethod
    def build_assistant_message(self, response: Any) -> dict:
        """Convert a raw provider response into a JSON-serializable assistant
        message to append to history.

        Critical: this MUST preserve provider-native tool-call structure
        (OpenAI tool_calls, Anthropic tool_use blocks). Dropping it corrupts
        the next turn. Returning a plain dict also makes sessions serializable.
        """
        raise NotImplementedError

    @abstractmethod
    def build_tool_result_message(self, tool_call: dict, result: str) -> dict:
        """Build the message that feeds a tool's output back to the model.

        Each provider expects a different shape, so the loop must never
        hardcode this.
        """
        raise NotImplementedError
