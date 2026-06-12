from pydantic import BaseModel
from typing import Callable


class ToolDefinition(BaseModel):
    """Definition of a tool that can be used by any model provider."""

    name: str
    description: str
    parameters: dict
    function: Callable

    model_config = {"arbitrary_types_allowed": True}

    def to_provider_format(self, provider: str) -> dict:
        """Convert to the format a specific model provider expects.

        All three providers (Ollama, OpenAI, Anthropic) use similar schemas,
        but wrap them slightly differently.
        """
        if provider == "ollama":
            return self._to_ollama_format()
        elif provider == "openai":
            return self._to_openai_format()
        elif provider == "anthropic":
            return self._to_anthropic_format()
        else:
            raise ValueError(f"Unknown provider: {provider}")

    def _to_ollama_format(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def _to_openai_format(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def _to_anthropic_format(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }
