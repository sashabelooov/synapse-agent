"""CLI interface — the terminal chat loop.

Calls agent/runner.py for the actual model turn so the same logic is shared
with the Telegram gateway and any future interface.
"""

from termcolor import colored

from models.base import ModelAdapter
from agent.runner import AgentState, build_agent_state, run_agent_turn
from agent.session import save_session, load_session, list_sessions
from agent.thinking import render_thinking


# In-chat commands (typed by the user, never sent to the model).
COMMANDS = {
    "/save": "save the current conversation: /save [name]",
    "/load": "load a saved conversation: /load <name>",
    "/sessions": "list saved conversations",
    "/reset": "clear the conversation (keeps the system prompt)",
    "/help": "show this help",
    "/quit": "exit",
}


class _StreamPrinter:
    """Prints thinking and answer live as tokens arrive."""

    def __init__(self) -> None:
        self._thinking_started = False
        self._content_started = False

    def on_thinking(self, delta: str) -> None:
        if not self._thinking_started:
            print(colored("💭 thinking", "blue", attrs=["bold"]))
            self._thinking_started = True
        print(colored(delta, "blue", attrs=["dark"]), end="", flush=True)

    def on_content(self, delta: str) -> None:
        if self._thinking_started and not self._content_started:
            print()
        if not self._content_started:
            print(colored("Model: ", "yellow"), end="", flush=True)
            self._content_started = True
        print(delta, end="", flush=True)

    def on_tool_call(self, name: str, args: dict) -> None:
        print(colored(f"⚙ {name}({args})", "cyan"))

    def finish(self) -> None:
        if self._thinking_started and not self._content_started:
            print()
        if self._content_started:
            print()


def _format_usage(turn: dict, total: dict) -> str:
    return colored(
        f"[tokens: {turn['input']}→{turn['output']} this call | "
        f"{total['input']}→{total['output']} total]",
        "magenta",
        attrs=["dark"],
    )


def _handle_command(raw: str, messages: list[dict], system_prompt: str) -> bool:
    """Handle a /command. Returns True if handled (skip the model turn)."""
    if not raw.startswith("/"):
        return False

    parts = raw.split(maxsplit=1)
    cmd = parts[0]
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd == "/help":
        for name, desc in COMMANDS.items():
            print(colored(f"  {name}", "cyan") + f" — {desc}")
    elif cmd == "/save":
        name = save_session(messages, arg or None)
        print(colored(f"Saved → {name}", "green"))
    elif cmd == "/load":
        if not arg:
            print(colored("Usage: /load <name>", "red"))
        else:
            try:
                loaded = load_session(arg)
                messages.clear()
                messages.extend(loaded)
                print(colored(f"Loaded '{arg}' ({len(loaded)} messages)", "green"))
            except ValueError as e:
                print(colored(str(e), "red"))
    elif cmd == "/sessions":
        names = list_sessions()
        print(colored("Saved sessions: " + (", ".join(names) or "none"), "green"))
    elif cmd == "/reset":
        system = [m for m in messages if m.get("role") == "system"]
        messages.clear()
        messages.extend(system)
        print(colored("Conversation cleared.", "green"))
    elif cmd == "/quit":
        raise KeyboardInterrupt
    else:
        print(colored(f"Unknown command: {cmd} (try /help)", "red"))
    return True


def chat_with_model(
    adapter: ModelAdapter,
    model_name: str,
    state: AgentState | None = None,
) -> None:
    """Run the interactive CLI chat loop."""
    if state is None:
        state = build_agent_state(adapter, model_name)
    messages: list[dict] = [{"role": "system", "content": state.system_prompt}]

    print(colored(f"[DEBUG] Tools loaded: {[t.name for t in state.tools]}", "magenta"))
    print(colored(f"[DEBUG] Model: {model_name}", "magenta"))
    print(colored(f"[DEBUG] Thinking: {'native' if state.native_thinking else 'prompted fallback'}", "magenta"))
    print(colored(f"[DEBUG] Streaming: {'on' if adapter.supports_streaming() else 'off'}", "magenta"))
    print("Chat with Synapse (/help for commands, Ctrl+C to quit)\n")

    total_usage: dict[str, int] = {"input": 0, "output": 0}

    while True:
        try:
            user_input = input(colored("You: ", "green"))
            if not user_input.strip():
                continue
            if _handle_command(user_input.strip(), messages, state.system_prompt):
                continue

            printer = _StreamPrinter()
            reply, usage = run_agent_turn(
                user_input,
                messages,
                state,
                on_chunk=printer.on_content,
                on_tool_call=printer.on_tool_call,
                on_thinking=printer.on_thinking,
            )
            printer.finish()

            total_usage["input"] += usage["input"]
            total_usage["output"] += usage["output"]
            if usage["input"] or usage["output"]:
                print(_format_usage(usage, total_usage))

        except KeyboardInterrupt:
            print("\n")
            return
