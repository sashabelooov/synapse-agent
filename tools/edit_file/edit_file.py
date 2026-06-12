from tools.base.tool import ToolDefinition
from tools.files import edit_any


tool = ToolDefinition(
    name="edit_file",
    description=(
        "Edit a file by replacing old text with new text (first match). Works on "
        "text files (txt, md, csv, json, code) and DOCX. For PDF, XLSX, and images, "
        "in-place edit is not supported — regenerate them with write_file instead."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The path of the file to edit.",
            },
            "old_str": {
                "type": "string",
                "description": "The exact text to find and replace.",
            },
            "new_str": {
                "type": "string",
                "description": "The new text to replace old_str with.",
            },
        },
        "required": ["path", "old_str", "new_str"],
    },
    function=edit_any,
)
