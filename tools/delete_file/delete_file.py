import os
from tools.base.tool import ToolDefinition


def _delete_file(path: str) -> str:
    """Delete a file from the filesystem."""
    try:
        os.remove(path)
        return f"File deleted: {path}"
    except Exception as e:
        return f"Error deleting file: {e}"


tool = ToolDefinition(
    name="delete_file",
    description="Delete a file. Use this when you need to remove a file permanently.",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The path of the file to delete.",
            },
        },
        "required": ["path"],
    },
    function=_delete_file,
)
