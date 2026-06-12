import re
from tools.base.tool import ToolDefinition


def _replace_in_file(path: str, pattern: str, replacement: str) -> str:
    """Find and replace using regex patterns in a file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        new_content, count = re.subn(pattern, replacement, content)

        if count == 0:
            return f"No matches found for pattern: {pattern}"

        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)

        return f"Replaced {count} occurrence(s) in {path}"
    except re.error as e:
        return f"Invalid regex pattern: {e}"
    except Exception as e:
        return f"Error: {e}"


tool = ToolDefinition(
    name="replace_in_file",
    description="Find and replace text in a file using regex patterns. Use this for advanced search-and-replace across a file. For simple literal replacements, use edit_file instead.",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The path of the file to modify.",
            },
            "pattern": {
                "type": "string",
                "description": "The regex pattern to search for.",
            },
            "replacement": {
                "type": "string",
                "description": "The replacement string. Can use regex groups like \\1.",
            },
        },
        "required": ["path", "pattern", "replacement"],
    },
    function=_replace_in_file,
)
