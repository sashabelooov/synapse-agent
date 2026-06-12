import json
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from models.base import ModelAdapter

load_dotenv()

MCP_SERVERS_FILE = Path(__file__).resolve().parent / "mcp_servers.json"

_ENV_REF = re.compile(r"\$\{([^}]+)\}")


def get_adapter(provider: str | None = None) -> ModelAdapter:
    """Create a ModelAdapter for the given provider.

    Falls back to AGENT_PROVIDER env var, then defaults to 'ollama'.
    """
    provider = provider or os.environ.get("AGENT_PROVIDER", "ollama")

    if provider == "ollama":
        from ollama import Client
        from models.ollama import OllamaAdapter

        host = os.environ.get("OLLAMA_HOST", "https://ollama.com")
        api_key = os.environ.get("OLLAMA_API_KEY", "")
        client = Client(
            host=host,
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
        )
        return OllamaAdapter(client)

    elif provider == "openai":
        from models.openai import OpenAIAdapter

        api_key = os.environ.get("OPENAI_API_KEY", "")
        return OpenAIAdapter(api_key=api_key)

    elif provider == "anthropic":
        from models.anthropic import AnthropicAdapter

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        return AnthropicAdapter(api_key=api_key)

    else:
        raise ValueError(f"Unknown provider: {provider}")


# Sensible fallback model per provider, used only when AGENT_MODEL is unset.
_DEFAULT_MODELS = {
    "ollama": "gpt-oss:120b-cloud",
    "openai": "gpt-4o",
    "anthropic": "claude-sonnet-4-6",
}


def get_model_name(provider: str | None = None) -> str:
    """Get the model name.

    Priority: AGENT_MODEL env var, then a per-provider default.
    """
    env_model = os.environ.get("AGENT_MODEL")
    if env_model:
        return env_model

    provider = provider or os.environ.get("AGENT_PROVIDER", "ollama")
    return _DEFAULT_MODELS.get(provider, "gpt-oss:120b-cloud")


# ---------------------------------------------------------------------------
# Sub-model backends (vision + embeddings).
#
# The main chat agent runs on gpt-oss (text-only). These two helpers power the
# specialized features that gpt-oss can't: seeing images and embedding text.
# Both are Ollama, but split — vision on the cloud, embeddings on local Ollama
# (the cloud plan has no embedding model). All overridable via env.
# ---------------------------------------------------------------------------

def get_ollama_client(host: str | None = None):
    """Build an Ollama client. Defaults to the cloud host + API key from env."""
    from ollama import Client

    host = host or os.environ.get("OLLAMA_HOST", "https://ollama.com")
    api_key = os.environ.get("OLLAMA_API_KEY", "")
    return Client(
        host=host,
        headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
    )


def get_vision_model() -> str:
    """Vision-capable model (sees images). Lives on Ollama cloud."""
    return os.environ.get("VISION_MODEL", "qwen3-vl:235b-instruct")


def get_embed_model() -> str:
    """Embedding model for RAG. Lives on LOCAL Ollama."""
    return os.environ.get("EMBED_MODEL", "nomic-embed-text")


def get_embed_host() -> str:
    """Host for the embedding model. Defaults to local Ollama."""
    return os.environ.get("EMBED_HOST", "http://localhost:11434")


def get_context_window() -> int:
    """The model's total context window in tokens (input + output share it).

    gpt-oss is 128K. Override per model via CONTEXT_WINDOW.
    """
    return int(os.environ.get("CONTEXT_WINDOW", "128000"))


def get_output_reserve() -> int:
    """Tokens reserved for the model's reply, kept free from the input budget."""
    return int(os.environ.get("OUTPUT_RESERVE", "16000"))


# ---------------------------------------------------------------------------
# MCP (Model Context Protocol) server configuration — single source of truth.
#
# Servers are declared in mcp_servers.json. Values may reference environment
# variables with ${VAR} (e.g. the GitHub token), expanded from the process env
# at load time so secrets never live in the config file.
# ---------------------------------------------------------------------------

def _expand_env(value: str) -> str:
    """Replace ${VAR} references with their environment values (empty if unset)."""
    return _ENV_REF.sub(lambda m: os.environ.get(m.group(1), ""), value)


def load_mcp_servers() -> dict[str, dict[str, Any]]:
    """Load and env-expand MCP server definitions from mcp_servers.json.

    Returns a mapping of server name -> {command, args, env}. Returns an empty
    dict if the file is absent (MCP is optional). Raises ValueError on malformed
    JSON so misconfiguration fails loudly rather than silently disabling servers.
    """
    if not MCP_SERVERS_FILE.exists():
        return {}

    try:
        raw = json.loads(MCP_SERVERS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"Malformed {MCP_SERVERS_FILE.name}: {e}") from e

    servers: dict[str, dict[str, Any]] = {}
    for name, spec in raw.items():
        env = {k: _expand_env(str(v)) for k, v in (spec.get("env") or {}).items()}
        servers[name] = {
            "command": spec["command"],
            "args": list(spec.get("args", [])),
            "env": env,
        }
    return servers
