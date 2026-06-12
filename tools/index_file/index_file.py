from tools.base.tool import ToolDefinition
from tools.files import read_any
from agent import memory


def _index_file(path: str) -> str:
    """Read a file (any supported format) and store it in searchable memory."""
    content = read_any(path)
    if content.startswith("Error"):
        return content
    try:
        n = memory.add_text(content, source=path)
    except Exception as e:
        return (
            f"Error indexing {path}: {e}. "
            f"(Is the local embedding model running? Try: ollama pull nomic-embed-text)"
        )
    if n == 0:
        return f"Nothing to index — {path} is empty."
    return f"Indexed {path}: {n} chunks stored in memory. Now searchable with search_knowledge."


tool = ToolDefinition(
    name="index_file",
    description=(
        "Read a file and store it in long-term searchable memory (RAG). Use this for "
        "large documents (PDFs, manuals, datasets) so you can later search them by "
        "meaning instead of loading the whole file into context. Supports all file "
        "formats read_file supports. Re-indexing the same path replaces its old chunks."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path of the file to index into memory.",
            }
        },
        "required": ["path"],
    },
    function=_index_file,
)
