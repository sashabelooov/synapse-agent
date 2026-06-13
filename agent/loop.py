from termcolor import colored

from models.base import ModelAdapter
from tools import get_all_tools
from tools.base.tool import ToolDefinition
from agent.context import manage_context
from agent.session import save_session, load_session, list_sessions
from agent.thinking import FALLBACK_INSTRUCTION, split_thinking, render_thinking
from agent.skills import get_skill_manager
from agent.persistent_memory import get_memory_manager


SYSTEM_PROMPT = (
    "You are a helpful assistant with access to tools. "
    "Always use the available tools when they can help answer the user's question. "
    "Never say you cannot do something if a tool exists for it."
)

# In-chat commands (typed by the user, never sent to the model).
COMMANDS = {
    "/save": "save the current conversation: /save [name]",
    "/load": "load a saved conversation: /load <name>",
    "/sessions": "list saved conversations",
    "/reset": "clear the conversation (keeps the system prompt)",
    "/help": "show this help",
    "/quit": "exit",
}


def execute_tool(tool_name: str, tool_args: dict, tools: list[ToolDefinition]) -> str:
    """Find and execute a tool by name."""
    tool = next((t for t in tools if t.name == tool_name), None)
    if tool is None:
        return f"Error: tool '{tool_name}' not found"

    print(colored(f"⚙ {tool_name}({tool_args})", "cyan"))
    try:
        return tool.function(**tool_args)
    except Exception as e:
        return f"Error executing {tool_name}: {e}"


def _render_assistant_text(content: str) -> None:
    if not content:
        return
    print(colored("Model: ", "yellow") + content)


class _StreamPrinter:
    """Manages live printing while streaming: a dim thinking channel, then the
    answer. Tracks which header has been printed so deltas land cleanly."""

    def __init__(self):
        self._thinking_started = False
        self._content_started = False

    def on_thinking(self, delta: str) -> None:
        if not self._thinking_started:
            print(colored("💭 thinking", "blue", attrs=["bold"]))
            self._thinking_started = True
        print(colored(delta, "blue", attrs=["dark"]), end="", flush=True)

    def on_content(self, delta: str) -> None:
        if self._thinking_started and not self._content_started:
            print()  # close the thinking block
        if not self._content_started:
            print(colored("Model: ", "yellow"), end="", flush=True)
            self._content_started = True
        print(delta, end="", flush=True)

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


def _handle_command(raw: str, messages: list[dict]) -> bool | None:
    """Handle an in-chat /command.

    Returns True if a command was handled (skip the model turn),
    None if the input is not a command (proceed normally).
    """
    if not raw.startswith("/"):
        return None

    parts = raw.split(maxsplit=1)
    cmd = parts[0]
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd == "/help":
        for name, desc in COMMANDS.items():
            print(colored(f"  {name}", "cyan") + f" — {desc}")
    elif cmd == "/save":
        path = save_session(messages, arg or None)
        print(colored(f"Saved → {path}", "green"))
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


def chat_with_model(adapter: ModelAdapter, model_name: str) -> None:
    """Run the interactive chat loop using any model adapter."""
    tools = get_all_tools()
    formatted_tools = adapter.format_tools(tools)

    # Native-thinking models reason in their own channel; only fallback models
    # need the prompted <thinking> instruction.
    native_thinking = adapter.uses_native_thinking()
    system_prompt = SYSTEM_PROMPT if native_thinking else SYSTEM_PROMPT + FALLBACK_INSTRUCTION

    # Advertise available skills (empty string when there are none, so nothing
    # is appended — no stray "Available skills" header).
    skills_block = get_skill_manager().prompt_block()
    if skills_block:
        system_prompt += "\n\n" + skills_block

    # Inject frozen memory snapshot — loaded once at session start, never
    # modified mid-session so the LLM prefix cache stays stable.
    memory_block = get_memory_manager().system_prompt_block()
    if memory_block:
        system_prompt += "\n\n" + memory_block

    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    print(colored(f"[DEBUG] Tools loaded: {[t.name for t in tools]}", "magenta"))
    print(colored(f"[DEBUG] Model: {model_name}", "magenta"))
    print(colored(f"[DEBUG] Thinking: {'native' if native_thinking else 'prompted fallback'}", "magenta"))
    print(colored(f"[DEBUG] Streaming: {'on' if adapter.supports_streaming() else 'off'}", "magenta"))
    print("Chat with model (/help for commands, Ctrl+C to quit)\n")

    total_usage = {"input": 0, "output": 0}

    while True:
        try:
            user_input = input(colored("You: ", "green"))

            if not user_input.strip():
                continue

            if _handle_command(user_input.strip(), messages):
                continue

            messages.append({"role": "user", "content": user_input})

            # Inner loop: keep going while the model wants to call tools.
            while True:
                messages[:] = manage_context(messages, adapter, model_name)

                if adapter.supports_streaming():
                    # Stream the response live, printing as tokens arrive.
                    printer = _StreamPrinter()
                    content, tool_calls, thinking, assistant_msg, usage = adapter.stream_chat(
                        model_name, messages, formatted_tools,
                        printer.on_thinking, printer.on_content,
                    )
                    printer.finish()
                    messages.append(assistant_msg)
                else:
                    response = adapter.chat(model_name, messages, formatted_tools)
                    content, tool_calls, thinking = adapter.parse_response(response)
                    usage = adapter.get_usage(response)

                    # Store the provider-native assistant message (preserves
                    # tool-call structure — this was the core v0.2 bug).
                    messages.append(adapter.build_assistant_message(response))

                    # Native thinking comes from the adapter; for fallback models
                    # we split <thinking> tags out of the answer ourselves.
                    if thinking is None:
                        thinking, content = split_thinking(content)

                    render_thinking(thinking)
                    _render_assistant_text(content)

                # Accumulate and show token usage.
                total_usage["input"] += usage["input"]
                total_usage["output"] += usage["output"]
                if usage["input"] or usage["output"]:
                    print(_format_usage(usage, total_usage))

                if not tool_calls:
                    break

                # Feed each tool result back using the adapter's own format.
                for tc in tool_calls:
                    result = execute_tool(tc["name"], tc["arguments"], tools)
                    messages.append(adapter.build_tool_result_message(tc, result))

        except KeyboardInterrupt:
            print("\n")
            return
