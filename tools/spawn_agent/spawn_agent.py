"""spawn_agent tool — run multiple subagents in parallel.

Each subagent gets:
  - Its own isolated message history
  - A restricted, read-only toolset (no spawn_agent recursion)
  - A token budget and wall-clock timeout

Results are returned as a numbered list to the parent agent.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from tools.base.tool import ToolDefinition
from tools.base.registry import get_all_tools
from agent.subagent import DEFAULT_ALLOWED_TOOLS, run_subagent

_MAX_PARALLEL = int(os.environ.get("SPAWN_AGENT_MAX_PARALLEL", "5"))


def _spawn(
    tasks: list[str],
    tools_override: str = "",
    budget_tokens: int = 4000,
    timeout_s: float = 120.0,
) -> str:
    if not tasks:
        return "Error: tasks list is empty."
    if len(tasks) > _MAX_PARALLEL:
        return (
            f"Error: too many tasks ({len(tasks)}). "
            f"Maximum is {_MAX_PARALLEL} (set SPAWN_AGENT_MAX_PARALLEL to change)."
        )

    # Resolve toolset
    if tools_override.strip():
        allowed = {t.strip() for t in tools_override.split(",") if t.strip()}
        allowed -= {"spawn_agent"}  # always blocked
    else:
        allowed = set(DEFAULT_ALLOWED_TOOLS)

    all_tools = get_all_tools()

    futures: dict = {}
    with ThreadPoolExecutor(max_workers=min(len(tasks), _MAX_PARALLEL)) as pool:
        for i, task in enumerate(tasks):
            future = pool.submit(
                run_subagent,
                task,
                all_tools,
                allowed,
                budget_tokens,
                timeout_s,
            )
            futures[future] = (i, task)

        ordered: dict[int, str] = {}
        for future in as_completed(futures):
            idx, _ = futures[future]
            try:
                ordered[idx] = future.result()
            except Exception as exc:
                ordered[idx] = f"[Error: {exc}]"

    parts = [f"[Task {i + 1}]: {ordered[i]}" for i in range(len(tasks))]
    return "\n\n".join(parts)


tool = ToolDefinition(
    name="spawn_agent",
    description=(
        "Run one or more tasks in parallel using isolated child agents. "
        "Each child agent gets its own message history and a restricted read-only toolset. "
        "Use this to parallelize independent research, summarization, or analysis tasks. "
        "Returns results as a numbered list once all children complete. "
        "Child agents cannot use spawn_agent themselves (no recursion). "
        "Default tools: read_file, list_files, tree_view, grep_search, "
        "web_search, read_url, search_knowledge, describe_image."
    ),
    parameters={
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "List of task descriptions to run in parallel. "
                    "Each task is a self-contained instruction for one child agent. "
                    f"Maximum {_MAX_PARALLEL} tasks per call."
                ),
            },
            "tools_override": {
                "type": "string",
                "description": (
                    "Comma-separated list of tool names to give child agents. "
                    "Leave empty to use the default read-only set. "
                    "spawn_agent is always excluded regardless of this value."
                ),
            },
            "budget_tokens": {
                "type": "integer",
                "description": (
                    "Approximate output token budget per child agent (default: 4000). "
                    "Child stops and returns partial results when budget is reached."
                ),
            },
            "timeout_s": {
                "type": "number",
                "description": (
                    "Wall-clock timeout in seconds per child agent (default: 120). "
                    "Child is hard-stopped after this time."
                ),
            },
        },
        "required": ["tasks"],
    },
    function=_spawn,
)
