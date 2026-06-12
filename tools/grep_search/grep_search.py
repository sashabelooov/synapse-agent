import os
from tools.base.tool import ToolDefinition


def _grep_search(pattern: str, path: str = ".") -> str:
    """Search for a text pattern inside files recursively."""
    if not path:
        path = "."

    results = []

    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if not d.startswith((".", "__"))]

        for file in files:
            file_path = os.path.join(root, file)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    for line_number, line in enumerate(f, start=1):
                        if pattern in line:
                            results.append(
                                f"{file_path}:{line_number}: {line.rstrip()}"
                            )
            except Exception:
                continue

    return "\n".join(results) if results else f"No matches found for: {pattern}"


tool = ToolDefinition(
    name="grep_search",
    description="Search for a word or text pattern inside all files recursively. Use this when you need to find where something is used in the project.",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "The word or text to search for.",
            },
            "path": {
                "type": "string",
                "description": "The directory to search in. Defaults to current directory.",
            },
        },
        "required": ["pattern"],
    },
    function=_grep_search,
)
