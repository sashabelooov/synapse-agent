"""search_sessions tool — full-text search across all past conversation sessions."""

from tools.base.tool import ToolDefinition
from agent.session import search_sessions_db


def _search(query: str, limit: int = 5) -> str:
    results = search_sessions_db(query, limit)
    if not results:
        return f"No sessions matched '{query}'."

    lines = [f"Found {len(results)} result(s) for '{query}':\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. [{r['session']}] {r['date']} ({r['role']})")
        lines.append(f"   {r['excerpt']}")
        lines.append("")
    return "\n".join(lines).strip()


tool = ToolDefinition(
    name="search_sessions",
    description=(
        "Full-text search across all past conversation sessions. "
        "Returns matching message excerpts with session name and date. "
        "Use this to recall what was discussed in a previous session, "
        "find a past decision, or look up earlier work."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Keyword or phrase to search for across all past sessions.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum results to return (default 5, max 20).",
            },
        },
        "required": ["query"],
    },
    function=_search,
)
