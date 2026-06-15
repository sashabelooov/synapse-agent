import asyncio
import os
import sys
import threading

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


def _start_telegram_background(state) -> None:
    """Launch the Telegram bot in a background daemon thread with its own event loop.

    This lets the CLI and the Telegram gateway share the same AgentState and
    run simultaneously — one command starts everything.
    """
    from gateway.telegram import start_telegram_bot

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(start_telegram_bot(state))
    finally:
        loop.close()


def main() -> None:
    provider, mode = _parse_args()

    adapter = get_adapter(provider)
    model_name = get_model_name(provider)

    mcp_manager = setup_mcp()
    try:
        state = build_agent_state(adapter, model_name)

        # Start cron scheduler as a daemon thread alongside any mode.
        from cron.scheduler import start_scheduler
        start_scheduler(state)

        if mode == "telegram":
            # Telegram-only mode: foreground event loop, no CLI.
            # Use this on servers / when you don't need a terminal.
            from gateway.telegram import start_telegram_bot
            asyncio.run(start_telegram_bot(state))
        else:
            # CLI mode (default): terminal chat in the foreground.
            # Telegram also starts in the background automatically if the
            # token is configured — one command, both interfaces live.
            token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
            allowed = os.environ.get("TELEGRAM_ALLOWED_USER_ID", "").strip()
            if token and allowed:
                t = threading.Thread(
                    target=_start_telegram_background,
                    args=(state,),
                    daemon=True,
                    name="telegram-gateway",
                )
                t.start()
                print("[Telegram] Bot started in background — you can use both CLI and Telegram simultaneously.")

            chat_with_model(adapter, model_name, state=state)
    finally:
        if mcp_manager is not None:
            mcp_manager.shutdown()


if __name__ == "__main__":
    main()
