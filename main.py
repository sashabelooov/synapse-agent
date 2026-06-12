import sys

from dotenv import load_dotenv

from config import get_adapter, get_model_name
from agent import chat_with_model
from agent.mcp_client import setup_mcp

load_dotenv()


def main() -> None:
    # Optional CLI argument: --provider ollama|openai|anthropic
    provider = None
    if "--provider" in sys.argv:
        idx = sys.argv.index("--provider")
        if idx + 1 < len(sys.argv):
            provider = sys.argv[idx + 1]

    adapter = get_adapter(provider)
    model_name = get_model_name(provider)

    # Connect MCP servers (e.g. GitHub) before the loop loads tools. Their tools
    # register into the same registry, so chat_with_model picks them up natively.
    # Non-fatal: a failed server warns loudly and the agent runs without it.
    mcp_manager = setup_mcp()
    try:
        chat_with_model(adapter, model_name)
    finally:
        if mcp_manager is not None:
            mcp_manager.shutdown()


if __name__ == "__main__":
    main()
