"""Telegram gateway for Synapse Agent.

Exposes the agent as a Telegram bot. ONLY the configured user ID is allowed —
the agent has shell access so this gate is non-negotiable.

Start with:
    uv run python3 main.py --mode telegram

Required env vars:
    TELEGRAM_BOT_TOKEN         — from @BotFather
    TELEGRAM_ALLOWED_USER_ID   — your numeric Telegram user ID (from @userinfobot)
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message

from agent.runner import AgentState, run_agent_turn
from agent.session import save_session, load_session, list_sessions

router = Router()

# One messages list per chat_id — initialised lazily with the system prompt.
_chat_sessions: dict[int, list[dict]] = {}
# Injected at startup by start_telegram_bot().
_state: AgentState | None = None


# ---------------------------------------------------------------------------
# Pure helpers — easy to test without aiogram
# ---------------------------------------------------------------------------

def _get_allowed_id() -> int:
    val = os.environ.get("TELEGRAM_ALLOWED_USER_ID", "").strip()
    if not val:
        raise RuntimeError(
            "TELEGRAM_ALLOWED_USER_ID is not set in .env. "
            "Get your Telegram user ID from @userinfobot."
        )
    return int(val)


def _is_authorized(user_id: int, allowed_id: int | None = None) -> bool:
    if allowed_id is None:
        allowed_id = _get_allowed_id()
    return user_id == allowed_id


def _split_message(text: str, limit: int = 4096) -> list[str]:
    """Split a string into Telegram-safe chunks of at most `limit` characters."""
    if not text:
        return ["(empty)"]
    return [text[i : i + limit] for i in range(0, len(text), limit)]


def _get_session(chat_id: int, system_prompt: str) -> list[dict]:
    if chat_id not in _chat_sessions:
        _chat_sessions[chat_id] = [{"role": "system", "content": system_prompt}]
    return _chat_sessions[chat_id]


def _reset_session(chat_id: int, system_prompt: str) -> None:
    _chat_sessions[chat_id] = [{"role": "system", "content": system_prompt}]


def _format_tool_status(tool_name: str) -> str:
    return f"⚙ `{tool_name}`…"


# ---------------------------------------------------------------------------
# Auth guard — reused by every handler
# ---------------------------------------------------------------------------

async def _check_auth(message: Message) -> bool:
    """Return True if authorized; reply and return False otherwise."""
    if not _is_authorized(message.from_user.id):
        await message.reply("Not authorized.")
        return False
    return True


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    if not await _check_auth(message):
        return
    await message.reply(
        "Synapse Agent is ready.\n\n"
        "Commands:\n"
        "/reset — clear this conversation\n"
        "/save [name] — save conversation\n"
        "/sessions — list saved conversations\n"
        "/load <name> — restore a conversation\n"
        "/help — show this message\n\n"
        "Just send a message to start."
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    if not await _check_auth(message):
        return
    await message.reply(
        "/start — welcome message\n"
        "/reset — clear this conversation\n"
        "/save [name] — save conversation to memory\n"
        "/sessions — list saved conversations\n"
        "/load <name> — restore a saved conversation\n"
        "/help — this message"
    )


@router.message(Command("reset"))
async def cmd_reset(message: Message) -> None:
    if not await _check_auth(message):
        return
    assert _state is not None
    _reset_session(message.chat.id, _state.system_prompt)
    await message.reply("Conversation cleared.")


@router.message(Command("save"))
async def cmd_save(message: Message) -> None:
    if not await _check_auth(message):
        return
    assert _state is not None
    parts = (message.text or "").split(maxsplit=1)
    name = parts[1].strip() if len(parts) > 1 else None
    session = _get_session(message.chat.id, _state.system_prompt)
    saved_name = save_session(session, name)
    await message.reply(f"Saved as '{saved_name}'.")


@router.message(Command("sessions"))
async def cmd_sessions(message: Message) -> None:
    if not await _check_auth(message):
        return
    names = list_sessions()
    if names:
        lines = "\n".join(f"• {n}" for n in names)
        await message.reply(f"Saved sessions:\n{lines}")
    else:
        await message.reply("No saved sessions yet.")


@router.message(Command("load"))
async def cmd_load(message: Message) -> None:
    if not await _check_auth(message):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("Usage: /load <name>")
        return
    name = parts[1].strip()
    try:
        loaded = load_session(name)
        _chat_sessions[message.chat.id] = loaded
        await message.reply(f"Loaded '{name}' ({len(loaded)} messages).")
    except ValueError as e:
        await message.reply(str(e))


# ---------------------------------------------------------------------------
# Main message handler
# ---------------------------------------------------------------------------

@router.message()
async def handle_message(message: Message) -> None:
    if not await _check_auth(message):
        return
    if not message.text:
        await message.reply("Only text messages are supported for now.")
        return

    assert _state is not None
    session = _get_session(message.chat.id, _state.system_prompt)

    # Placeholder shown while the agent is thinking.
    status_msg = await message.reply("⏳")
    event_loop = asyncio.get_event_loop()

    accumulated: list[str] = []
    last_edit: list[float] = [0.0]  # list so the closure can mutate it

    def on_chunk(text: str) -> None:
        accumulated.append(text)
        # Rate-limit edits to once per second to stay within Telegram limits.
        now = time.time()
        if now - last_edit[0] >= 1.0:
            preview = "".join(accumulated)[:4096]
            asyncio.run_coroutine_threadsafe(
                status_msg.edit_text(preview or "…"),
                event_loop,
            )
            last_edit[0] = now

    def on_tool_call(name: str, _args: dict) -> None:
        asyncio.run_coroutine_threadsafe(
            status_msg.edit_text(_format_tool_status(name)),
            event_loop,
        )

    # Run the synchronous agent turn in a thread-pool executor so the
    # asyncio event loop (and Telegram) stays responsive.
    reply, usage = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: run_agent_turn(
            message.text,
            session,
            _state,
            on_chunk=on_chunk,
            on_tool_call=on_tool_call,
        ),
    )

    # Send the final reply, splitting if it exceeds Telegram's 4096-char limit.
    parts = _split_message(reply or "(no response)")
    try:
        await status_msg.edit_text(parts[0])
    except Exception:
        await message.reply(parts[0])
    for part in parts[1:]:
        await message.reply(part)

    if usage["input"] or usage["output"]:
        await message.reply(
            f"[{usage['input']}→{usage['output']} tokens]",
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def start_telegram_bot(state: AgentState) -> None:
    """Start polling. Blocks until the process is killed."""
    global _state
    _state = state

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not set in .env. "
            "Create a bot with @BotFather to get one."
        )
    allowed_id = _get_allowed_id()

    bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
    dp = Dispatcher()
    dp.include_router(router)

    print(f"Telegram bot starting (allowed user ID: {allowed_id}) …")
    await dp.start_polling(bot)
