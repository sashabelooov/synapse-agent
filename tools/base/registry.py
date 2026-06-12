import importlib
from pathlib import Path

from tools.base.tool import ToolDefinition

# Tools registered at runtime from outside the tools/ folder (e.g. MCP servers).
# get_all_tools() returns auto-discovered tools plus these, so the agent loop
# sees one unified tool list and needs no changes.
_EXTRA_TOOLS: list[ToolDefinition] = []


def register_tools(tools: list[ToolDefinition]) -> None:
    """Register externally-sourced tools (e.g. bridged MCP tools)."""
    _EXTRA_TOOLS.extend(tools)


def clear_extra_tools() -> None:
    """Remove all runtime-registered tools (used on shutdown / in tests)."""
    _EXTRA_TOOLS.clear()


def get_all_tools() -> list[ToolDefinition]:
    """Auto-discover all tools by scanning tools/*/ directories.

    Convention: each tool lives in tools/<name>/<name>.py and must
    export a module-level variable called `tool` of type ToolDefinition.

    Runtime-registered tools (see register_tools) are appended to the result.
    """
    tools_dir = Path(__file__).resolve().parent.parent  # tools/
    discovered: list[ToolDefinition] = []

    for child in sorted(tools_dir.iterdir()):
        # Skip base/ and __pycache__/
        if not child.is_dir() or child.name.startswith(("_", ".")):
            continue
        if child.name == "base":
            continue

        module_file = child / f"{child.name}.py"
        if not module_file.exists():
            continue

        module_path = f"tools.{child.name}.{child.name}"
        try:
            module = importlib.import_module(module_path)
            tool = getattr(module, "tool", None)
            if isinstance(tool, ToolDefinition):
                discovered.append(tool)
        except Exception as e:
            print(f"[WARN] Failed to load tool from {module_path}: {e}")

    return discovered + _EXTRA_TOOLS
