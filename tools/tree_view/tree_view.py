import os
from tools.base.tool import ToolDefinition


def _tree_view(path: str = ".", max_depth: int = 3) -> str:
    """Generate a visual directory tree."""
    if not path:
        path = "."

    if not os.path.isdir(path):
        return f"Error: {path} is not a directory."

    lines = [path]

    def _build_tree(current_path: str, prefix: str, depth: int) -> None:
        if depth >= max_depth:
            return

        try:
            entries = sorted(os.listdir(current_path))
        except PermissionError:
            return

        # Filter hidden dirs and __pycache__
        entries = [e for e in entries if not e.startswith((".", "__"))]

        for i, entry in enumerate(entries):
            full_path = os.path.join(current_path, entry)
            is_last = i == len(entries) - 1
            connector = "└── " if is_last else "├── "

            if os.path.isdir(full_path):
                lines.append(f"{prefix}{connector}{entry}/")
                extension = "    " if is_last else "│   "
                _build_tree(full_path, prefix + extension, depth + 1)
            else:
                lines.append(f"{prefix}{connector}{entry}")

    _build_tree(path, "", 0)
    return "\n".join(lines)


tool = ToolDefinition(
    name="tree_view",
    description="Show a visual directory tree structure. Better than list_files for understanding project layout at a glance.",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The root directory to show the tree from. Defaults to current directory.",
            },
            "max_depth": {
                "type": "integer",
                "description": "Maximum depth to display. Defaults to 3.",
            },
        },
        "required": [],
    },
    function=_tree_view,
)
