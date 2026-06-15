"""Phase 6 — Rich TUI for Synapse Agent (Textual).

Layout:
  ┌─ Header: Synapse Agent | provider/model ──────────────────────────────────┐
  │  ┌─ Chat history (RichLog) ──────────────────┐  ┌─ 🔧 Tools ───────────┐ │
  │  │                                           │  │  ⚙ web_search 2.1s  │ │
  │  │  You: …                                   │  │  ✓ read_url  done   │ │
  │  │  Synapse: …  (streams live)               │  │                     │ │
  │  │                                           │  └─────────────────────┘ │
  │  │  ▶ 💭 Thinking  (Ctrl+T to expand)        │                           │
  │  └───────────────────────────────────────────┘                           │
  │  ┌─ Input ────────────────────────────────────────────────────────────┐  │
  │  │ > _                                                                │  │
  │  └────────────────────────────────────────────────────────────────────┘  │
  └─ Footer: session | tokens | key hints ────────────────────────────────────┘

Key bindings:
  Enter      — send message
  Ctrl+T     — toggle thinking panel
  Ctrl+S     — save session
  Ctrl+R     — reset session
  Ctrl+C / q — quit
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Collapsible,
    Footer,
    Header,
    Input,
    RichLog,
    Static,
)
from textual import work

from agent.runner import AgentState, run_agent_turn
from agent.session import list_sessions, load_session, save_session


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@dataclass
class _ToolCall:
    name: str
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    @property
    def elapsed(self) -> str:
        end = self.finished_at or time.time()
        return f"{end - self.started_at:.1f}s"

    @property
    def done(self) -> bool:
        return self.finished_at is not None


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------

class ToolPanel(Static):
    """Right sidebar: live tool-call status."""

    DEFAULT_CSS = """
    ToolPanel {
        padding: 1 1;
        height: 1fr;
        overflow-y: auto;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__("", markup=True, **kwargs)
        self._calls: list[_ToolCall] = []
        self.content: str = ""  # last rendered text — readable by tests

    def push(self, tc: _ToolCall) -> None:
        self._calls.append(tc)
        self._refresh()

    def finish_last(self) -> None:
        if self._calls and not self._calls[-1].done:
            self._calls[-1].finished_at = time.time()
        self._refresh()

    def clear_calls(self) -> None:
        self._calls.clear()
        self._refresh()

    def _refresh(self) -> None:
        if not self._calls:
            self.content = "No tools called yet."
            self.update("[dim]No tools called yet.[/dim]")
            return
        lines: list[str] = []
        for tc in reversed(self._calls[-10:]):
            icon = "✓" if tc.done else "[blink]⚙[/blink]"
            color = "green" if tc.done else "yellow"
            lines.append(
                f"[{color}]{icon}[/{color}] [bold]{tc.name}[/bold]\n"
                f"  [{color}]{tc.elapsed}[/{color}]"
            )
        self.content = "\n\n".join(lines)
        self.update(self.content)


class _StreamLine(Static):
    """One-line widget that shows the currently-streaming reply token by token."""

    DEFAULT_CSS = """
    _StreamLine {
        height: auto;
        padding: 0 0 1 0;
        color: $text;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__("", markup=True, **kwargs)
        self._plain_text: str = ""  # readable by tests — plain text only

    def set_text(self, text: str) -> None:
        self._plain_text = text
        self.update(f"[bold cyan]Synapse:[/bold cyan] {text}[blink]▍[/blink]")

    def clear(self) -> None:
        self._plain_text = ""
        self.update("")


# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------

class SynapseApp(App):
    """Synapse Agent — Rich TUI (Phase 6)."""

    CSS = """
    Screen {
        background: $surface;
    }

    #main-area {
        height: 1fr;
    }

    #chat-panel {
        width: 4fr;
        border: solid $primary-darken-2;
    }

    #chat-log {
        height: 1fr;
        padding: 0 1;
    }

    #stream-line {
        padding: 0 1;
    }

    #thinking-collapsible {
        border-top: dashed $primary-darken-3;
        height: auto;
        max-height: 12;
    }

    #thinking-log {
        height: auto;
        max-height: 10;
        padding: 0 1;
    }

    #tool-panel {
        width: 24;
        border: solid $primary-darken-2;
    }

    #tool-title {
        background: $primary-darken-3;
        text-align: center;
        padding: 0 1;
        color: $text-muted;
    }

    #input-row {
        height: 3;
        border: solid $primary-darken-2;
        padding: 0 1;
    }

    #msg-input {
        border: none;
        background: transparent;
        width: 1fr;
    }

    #status-bar {
        height: 1;
        background: $primary-darken-3;
        color: $text-muted;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+t", "toggle_thinking", "Thinking"),
        Binding("ctrl+s", "save_session", "Save"),
        Binding("ctrl+r", "reset_session", "Reset"),
        Binding("ctrl+c,q", "quit", "Quit"),
    ]

    def __init__(
        self,
        state: AgentState,
        model_name: str,
        provider_name: str,
    ) -> None:
        super().__init__()
        self._state = state
        self._model_name = model_name
        self._provider_name = provider_name
        self._messages: list[dict] = [
            {"role": "system", "content": state.system_prompt}
        ]
        self._session_name = "unsaved"
        self._total_in = 0
        self._total_out = 0
        self._active_tc: _ToolCall | None = None
        self._exit_requested = False

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main-area"):
            with Vertical(id="chat-panel"):
                yield RichLog(id="chat-log", highlight=True, markup=True, wrap=True)
                yield _StreamLine(id="stream-line")
                with Collapsible(
                    title="💭 Thinking",
                    collapsed=True,
                    id="thinking-collapsible",
                ):
                    yield RichLog(
                        id="thinking-log",
                        highlight=False,
                        markup=True,
                        wrap=True,
                    )
            with Vertical(id="tool-panel"):
                yield Static("🔧 Tools", id="tool-title", markup=True)
                yield ToolPanel(id="tool-status")
        with Horizontal(id="input-row"):
            yield Input(
                placeholder="Message Synapse… (Enter to send, /help for commands)",
                id="msg-input",
            )
        yield Static(self._status_text(), id="status-bar", markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Synapse Agent"
        self.sub_title = f"{self._provider_name} / {self._model_name}"
        log = self.query_one("#chat-log", RichLog)
        log.write(
            "[bold cyan]Synapse Agent[/bold cyan] ready. "
            "Type a message and press [bold]Enter[/bold].\n"
        )
        log.write(
            "[dim]/save [name]  /load <name>  /sessions  /reset  /help[/dim]\n"
        )
        self.query_one("#msg-input", Input).focus()

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        event.input.clear()

        if text.startswith("/"):
            self._handle_command(text)
        else:
            self._send(text)

    def _handle_command(self, text: str) -> None:
        log = self.query_one("#chat-log", RichLog)
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd == "/help":
            log.write(
                "[bold]Commands:[/bold]\n"
                "  /save [name]  — save current session\n"
                "  /load <name>  — load a saved session\n"
                "  /sessions     — list saved sessions\n"
                "  /reset        — clear conversation\n"
                "  /help         — this message\n"
            )
        elif cmd == "/save":
            name = save_session(self._messages, arg or None)
            self._session_name = name
            log.write(f"[green]✓ Saved as '[bold]{name}[/bold]'[/green]\n")
            self._update_status()
        elif cmd == "/load":
            if not arg:
                log.write("[red]Usage: /load <name>[/red]\n")
                return
            try:
                self._messages = load_session(arg)
                self._session_name = arg
                log.write(
                    f"[green]✓ Loaded '[bold]{arg}[/bold]' "
                    f"({len(self._messages)} messages)[/green]\n"
                )
                self._update_status()
            except ValueError as exc:
                log.write(f"[red]{exc}[/red]\n")
        elif cmd == "/sessions":
            names = list_sessions()
            if names:
                log.write(
                    "[bold]Saved sessions:[/bold]\n"
                    + "\n".join(f"  • {n}" for n in names)
                    + "\n"
                )
            else:
                log.write("[dim]No saved sessions yet.[/dim]\n")
        elif cmd == "/reset":
            self._messages = [
                {"role": "system", "content": self._state.system_prompt}
            ]
            self._session_name = "unsaved"
            self.query_one("#tool-status", ToolPanel).clear_calls()
            self.query_one("#thinking-log", RichLog).clear()
            log.write("[yellow]Conversation cleared.[/yellow]\n")
            self._update_status()
        else:
            log.write(f"[red]Unknown command: {cmd}  (try /help)[/red]\n")

    def _send(self, text: str) -> None:
        log = self.query_one("#chat-log", RichLog)
        log.write(f"[bold green]You:[/bold green] {text}\n")
        stream = self.query_one("#stream-line", _StreamLine)
        stream.set_text("…")
        self.query_one("#msg-input", Input).disabled = True
        self._active_tc = None
        self._run_agent(text)

    # ------------------------------------------------------------------
    # Agent worker (background thread via @work)
    # ------------------------------------------------------------------

    @work(thread=True, exclusive=True)
    def _run_agent(self, user_text: str) -> None:
        """Runs in a thread. Uses call_from_thread() to update the UI."""
        buf: list[str] = []

        def on_chunk(chunk: str) -> None:
            buf.append(chunk)
            self.call_from_thread(
                self.query_one("#stream-line", _StreamLine).set_text,
                "".join(buf),
            )

        def on_tool_call(name: str, _args: dict) -> None:
            # Close out the previous tool's timer
            if self._active_tc is not None:
                self._active_tc.finished_at = time.time()
            tc = _ToolCall(name=name)
            self._active_tc = tc
            self.call_from_thread(
                self.query_one("#tool-status", ToolPanel).push, tc
            )

        def on_thinking(text: str) -> None:
            self.call_from_thread(
                self.query_one("#thinking-log", RichLog).write,
                f"[dim]{text}[/dim]",
            )

        try:
            reply, usage = run_agent_turn(
                user_text,
                self._messages,
                self._state,
                on_chunk=on_chunk,
                on_tool_call=on_tool_call,
                on_thinking=on_thinking,
            )
        except Exception as exc:
            reply = f"Error: {exc}"
            usage = {"input": 0, "output": 0}

        # Close out the last tool timer
        if self._active_tc is not None:
            self._active_tc.finished_at = time.time()
            self._active_tc = None

        self._total_in += usage.get("input", 0)
        self._total_out += usage.get("output", 0)
        self.call_from_thread(self._on_done, reply)

    def _on_done(self, reply: str) -> None:
        log = self.query_one("#chat-log", RichLog)
        self.query_one("#stream-line", _StreamLine).clear()
        log.write(f"[bold cyan]Synapse:[/bold cyan] {reply}\n")
        self.query_one("#tool-status", ToolPanel).finish_last()
        inp = self.query_one("#msg-input", Input)
        inp.disabled = False
        inp.focus()
        self._update_status()

    # ------------------------------------------------------------------
    # Status bar & actions
    # ------------------------------------------------------------------

    def _status_text(self) -> str:
        return (
            f" session: [bold]{self._session_name}[/bold]"
            f"  │  tokens: {self._total_in}→{self._total_out}"
            f"  │  Ctrl+T thinking · Ctrl+S save · Ctrl+R reset"
        )

    def _update_status(self) -> None:
        self.query_one("#status-bar", Static).update(self._status_text())

    def action_toggle_thinking(self) -> None:
        c = self.query_one("#thinking-collapsible", Collapsible)
        c.collapsed = not c.collapsed

    def action_save_session(self) -> None:
        self._handle_command("/save")

    def action_reset_session(self) -> None:
        self._handle_command("/reset")
