import asyncio
import sys

from dotenv import load_dotenv

from config import get_adapter, get_model_name
from agent import chat_with_model
from agent.mcp_client import setup_mcp
from agent.runner import build_agent_state

load_dotenv()


def _parse_args() -> tuple[str | None, str]:
    """Parse --provider and --mode from sys.argv. Returns (provider, mode)."""
    provider = None
    mode = "cli"

    if "--provider" in sys.argv:
        idx = sys.argv.index("--provider")
        if idx + 1 < len(sys.argv):
            provider = sys.argv[idx + 1]

    if "--mode" in sys.argv:
        idx = sys.argv.index("--mode")
        if idx + 1 < len(sys.argv):
            mode = sys.argv[idx + 1]

    return provider, mode


def main() -> None:
    provider, mode = _parse_args()

    adapter = get_adapter(provider)
    model_name = get_model_name(provider)

    mcp_manager = setup_mcp()
    try:
        state = build_agent_state(adapter, model_name)

        # Start the cron scheduler as a daemon thread alongside any mode.
        from cron.scheduler import start_scheduler
        start_scheduler(state)

        if mode == "telegram":
            from gateway.telegram import start_telegram_bot
            asyncio.run(start_telegram_bot(state))
        else:
            chat_with_model(adapter, model_name, state=state)
    finally:
        if mcp_manager is not None:
            mcp_manager.shutdown()


if __name__ == "__main__":
    main()
