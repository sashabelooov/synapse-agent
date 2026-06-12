from tools.base.tool import ToolDefinition
from agent import memory


def _search_knowledge(query: str, k: int = 5) -> str:
    """Search indexed memory for chunks whose meaning matches the query."""
    try:
        results = memory.search(query, k=k)
    except Exception as e:
        return f"Error searching memory: {e}"

    if not results:
        st = memory.stats()
        if st["chunks"] == 0:
            return "Memory is empty. Index a file first with index_file."
        return "No relevant chunks found."

    out = [f"Top {len(results)} matches for: {query!r}\n"]
    for i, r in enumerate(results, 1):
        out.append(
            f"[{i}] {r['source']} (relevance {r['score']:.2f})\n{r['text']}\n"
        )
    return "\n".join(out)


tool = ToolDefinition(
    name="search_knowledge",
    description=(
        "Search long-term memory for information relevant to a query, by meaning "
        "(not keywords). Use this to recall content from files you indexed with "
        "index_file, even across past sessions. Returns the most relevant chunks."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "What you're looking for, in natural language.",
            },
            "k": {
                "type": "integer",
                "description": "How many chunks to return (default 5).",
            },
        },
        "required": ["query"],
    },
    function=_search_knowledge,
)
