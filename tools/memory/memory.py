"""Memory tool — read and update the agent's persistent cross-session memory.

Two stores:
  memory — agent notes, decisions, and useful facts (max 2200 chars)
  user   — user profile: name, preferences, working style (max 1375 chars)

Entries are §-delimited and stored in ~/.synapse/MEMORY.md and USER.md.
They persist across all sessions. The snapshot already injected into the
system prompt is frozen; writes here take effect from the NEXT session.
"""

from tools.base.tool import ToolDefinition
from agent.persistent_memory import get_memory_manager


def _memory(store: str, action: str, content: str = "", old_text: str = "") -> str:
    return get_memory_manager().dispatch(store, action, content, old_text)


tool = ToolDefinition(
    name="memory",
    description=(
        "Read or update persistent cross-session memory. "
        "Use 'memory' store for agent notes (facts, decisions, project context). "
        "Use 'user' store for user profile (name, preferences, working style). "
        "Memory survives restarts and is injected into every future session automatically. "
        "Proactively add important facts here so you remember them next session."
    ),
    parameters={
        "type": "object",
        "properties": {
            "store": {
                "type": "string",
                "enum": ["memory", "user"],
                "description": "'memory' for agent notes, 'user' for user profile.",
            },
            "action": {
                "type": "string",
                "enum": ["add", "replace", "remove", "read"],
                "description": (
                    "add: append a new entry. "
                    "replace: find entry by old_text substring and replace with content. "
                    "remove: delete all entries containing content as substring. "
                    "read: view current entries and usage."
                ),
            },
            "content": {
                "type": "string",
                "description": (
                    "For add: the entry text to add. "
                    "For replace: the new entry text. "
                    "For remove: substring to match entries for deletion."
                ),
            },
            "old_text": {
                "type": "string",
                "description": "Substring to locate the entry to replace (required for replace).",
            },
        },
        "required": ["store", "action"],
    },
    function=_memory,
)
