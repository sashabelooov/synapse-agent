"""Generic MCP (Model Context Protocol) client support.

This lets the agent use tools hosted by external MCP servers (e.g. the official
GitHub MCP server) exactly like its own native tools. Each remote MCP tool is
wrapped as a `ToolDefinition`, so the registry and the agent loop treat it the
same as a local tool — no changes to agent/loop.py.

The hard part is the sync/async gap: the agent calls tools synchronously and
expects a string back, but the MCP SDK is async and a session must stay open for
the whole run. We solve this with one dedicated asyncio event loop running on a
background thread:

  - Each server connection lives in its own long-lived coroutine that opens the
    stdio + session contexts with `async with`, initializes, lists tools, then
    parks on a stop event. Opening and closing in the SAME task avoids the
    anyio cancel-scope errors you get when async contexts are exited from a
    different task than the one that entered them.
  - Synchronous tool calls hop onto that loop via
    `asyncio.run_coroutine_threadsafe(...).result(timeout)` and block for the
    answer. The agent thread never runs an event loop itself, so nothing leaks.

MCP is optional and defensive: a server that fails to start is reported loudly
and skipped; the agent keeps running with its native tools.
"""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import Future
from typing import Any, Callable

from termcolor import colored

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client, get_default_environment
from mcp.types import TextContent

from tools.base.tool import ToolDefinition

# How long to wait for a server to start / a tool call to return.
_CONNECT_TIMEOUT_S = 60.0
_CALL_TIMEOUT_S = 120.0


class MCPServerError(RuntimeError):
    """Raised when an MCP server cannot be started or connected."""


class MCPManager:
    """Owns a background asyncio loop and one persistent session per server."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop, name="mcp-loop", daemon=True
        )
        self._thread.start()

        # name -> live session, and name -> the list of tool specs it exposes.
        self._sessions: dict[str, ClientSession] = {}
        self._tools: dict[str, list[Any]] = {}
        # name -> event that, when set, tells the server coroutine to shut down.
        self._stop_events: dict[str, asyncio.Event] = {}

    # -- event loop plumbing -------------------------------------------------

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _submit(self, coro: Any) -> Future:
        """Schedule a coroutine on the background loop from the agent thread."""
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    # -- connection lifecycle ------------------------------------------------

    def connect(self, name: str, command: str, args: list[str], env: dict[str, str]) -> None:
        """Start a server and keep its session open. Raises MCPServerError on failure."""
        # Merge a sane default environment (so PATH is present and `docker`
        # resolves) with the server-specific vars.
        full_env = {**get_default_environment(), **(env or {})}
        params = StdioServerParameters(command=command, args=args, env=full_env)

        ready: Future = Future()
        self._submit(self._serve(name, params, ready))

        try:
            ready.result(timeout=_CONNECT_TIMEOUT_S)
        except Exception as e:  # connection failed or timed out
            raise MCPServerError(f"{name}: {e}") from e

    async def _serve(self, name: str, params: StdioServerParameters, ready: Future) -> None:
        """Long-lived: open contexts, publish the session, park until stopped.

        Both the stdio transport and the ClientSession are entered and exited
        within this single task to keep anyio's cancel scopes happy.
        """
        stop = asyncio.Event()
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = (await session.list_tools()).tools

                    self._sessions[name] = session
                    self._tools[name] = tools
                    self._stop_events[name] = stop

                    if not ready.done():
                        ready.set_result(True)

                    await stop.wait()  # keep the session alive until shutdown
        except Exception as e:
            if not ready.done():
                ready.set_exception(e)
        finally:
            self._sessions.pop(name, None)
            self._stop_events.pop(name, None)

    # -- calling tools -------------------------------------------------------

    def call(self, server: str, tool_name: str, arguments: dict[str, Any]) -> str:
        """Synchronously call an MCP tool and return its text result."""
        session = self._sessions.get(server)
        if session is None:
            return f"Error: MCP server '{server}' is not connected."
        try:
            fut = self._submit(session.call_tool(tool_name, arguments))
            result = fut.result(timeout=_CALL_TIMEOUT_S)
        except Exception as e:
            return f"Error calling MCP tool '{tool_name}': {e}"
        return _result_to_text(result)

    # -- bridging to ToolDefinition ------------------------------------------

    def build_tool_definitions(
        self, server: str, existing_names: set[str]
    ) -> list[ToolDefinition]:
        """Wrap a server's MCP tools as native ToolDefinitions.

        On a name collision with an existing tool, the MCP tool is prefixed
        with '<server>_' and a warning is printed (names stay raw otherwise).
        """
        definitions: list[ToolDefinition] = []
        for spec in self._tools.get(server, []):
            name = spec.name
            if name in existing_names:
                prefixed = f"{server}_{name}"
                print(colored(
                    f"⚠ MCP tool name collision: '{name}' already exists. "
                    f"Exposing it as '{prefixed}'.",
                    "yellow",
                ))
                name = prefixed

            definitions.append(
                ToolDefinition(
                    name=name,
                    description=spec.description or f"{server} MCP tool",
                    parameters=spec.inputSchema or {"type": "object", "properties": {}},
                    function=self._make_caller(server, spec.name),
                )
            )
            existing_names.add(name)
        return definitions

    def _make_caller(self, server: str, tool_name: str) -> Callable[..., str]:
        """Build a sync function that forwards kwargs to the MCP tool."""
        def _call(**kwargs: Any) -> str:
            return self.call(server, tool_name, kwargs)

        return _call

    # -- shutdown ------------------------------------------------------------

    def shutdown(self) -> None:
        """Signal all servers to close, then stop the background loop."""
        for stop in list(self._stop_events.values()):
            self._loop.call_soon_threadsafe(stop.set)
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=10.0)


def setup_mcp() -> MCPManager | None:
    """Connect all configured MCP servers and register their tools.

    Returns the manager (call .shutdown() on exit), or None if no servers are
    configured or none connected. Per-server failures are loud but non-fatal —
    the agent keeps running with its native tools.
    """
    # Imported here to avoid a circular import at module load.
    from config import load_mcp_servers
    from tools.base.registry import get_all_tools, register_tools

    servers = load_mcp_servers()
    if not servers:
        return None

    manager = MCPManager()
    existing_names = {t.name for t in get_all_tools()}
    connected_any = False

    for name, spec in servers.items():
        try:
            manager.connect(name, spec["command"], spec["args"], spec["env"])
        except MCPServerError as e:
            _warn_block(name, str(e))
            continue

        definitions = manager.build_tool_definitions(name, existing_names)
        register_tools(definitions)
        connected_any = True
        print(colored(
            f"✓ MCP '{name}' connected — {len(definitions)} tools "
            f"(read-only): {', '.join(d.name for d in definitions[:8])}"
            f"{'…' if len(definitions) > 8 else ''}",
            "green",
        ))

    if not connected_any:
        manager.shutdown()
        return None
    return manager


def _warn_block(server: str, reason: str) -> None:
    """Print a very visible warning so a failed MCP server is obvious."""
    bar = "!" * 64
    print(colored(bar, "red", attrs=["bold"]))
    print(colored(f"  MCP SERVER '{server.upper()}' FAILED TO START — continuing without it.", "red", attrs=["bold"]))
    print(colored(f"  Reason: {reason}", "red"))
    print(colored("  Check: Docker running? GITHUB_PERSONAL_ACCESS_TOKEN set in .env?", "red"))
    print(colored(f"  The agent will run with NATIVE tools only.", "red"))
    print(colored(bar, "red", attrs=["bold"]))


def _block_to_text(block: Any) -> str:
    """Extract readable text from one MCP content block.

    Handles plain text blocks and embedded resource blocks (e.g. file contents),
    which wrap a TextResourceContents with the actual text one level down.
    """
    if isinstance(block, TextContent):
        return block.text

    # Embedded resource: block.resource is Text/BlobResourceContents.
    resource = getattr(block, "resource", None)
    if resource is not None:
        inner = getattr(resource, "text", None)
        if inner is not None:
            return inner

    return getattr(block, "text", None) or str(block)


def _result_to_text(result: Any) -> str:
    """Flatten an MCP CallToolResult into a plain string for the agent."""
    parts = [_block_to_text(b) for b in (getattr(result, "content", []) or [])]
    text = "\n".join(p for p in parts if p).strip()

    if getattr(result, "isError", False):
        return f"Error from MCP tool: {text or 'unknown error'}"
    return text or "(MCP tool returned no content.)"
