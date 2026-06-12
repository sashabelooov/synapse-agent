import os
from tools.base.tool import ToolDefinition


def _list_files(path: str = ".") -> str:
    """List all files in a directory recursively."""
    if not path:
        path = "."

    result = []

    for root, dirs, files in os.walk(path):
        # Skip hidden directories and __pycache__
        dirs[:] = [d for d in dirs if not d.startswith((".", "__"))]

        for file in files:
            full_path = os.path.join(root, file)
            result.append(full_path)

    return "\n".join(result) if result else "No files found."


tool = ToolDefinition(
    name="list_files",
    description=(
        "List all files in a directory recursively. "
        "Use this first when you need to find where a file is located. "
        "Defaults to current directory if no path is given."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The directory path to list files from. Defaults to current directory.",
            }
        },
        "required": [],
    },
    function=_list_files,
)
