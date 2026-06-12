from tools.base.tool import ToolDefinition
from tools.files import write_any


tool = ToolDefinition(
    name="write_file",
    description=(
        "Create or overwrite a file with the given content. The format is chosen "
        "by the file extension: text files (txt/md/json/code) are written as-is; "
        ".csv content is saved as CSV; .xlsx parses CSV-style text into spreadsheet "
        "cells; .docx writes each line as a paragraph; .pdf generates a document "
        "from the text. Creates parent directories automatically. Images cannot be "
        "written (OCR is read-only)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The path of the file to create or overwrite.",
            },
            "content": {
                "type": "string",
                "description": (
                    "The text content. For .xlsx/.csv use comma-separated rows, "
                    "one row per line. For .docx/.pdf use one paragraph per line."
                ),
            },
        },
        "required": ["path", "content"],
    },
    function=write_any,
)
