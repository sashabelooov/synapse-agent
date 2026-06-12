from tools.base.tool import ToolDefinition
from tools.files import read_any


tool = ToolDefinition(
    name="read_file",
    description=(
        "Read a file and return its text. Supports txt, md, csv, json and other "
        "text files, plus PDF (extracts text), DOCX, XLSX (as a table), and "
        "images (.png/.jpg/etc. via OCR). Use this to see what is inside a file."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The path of the file to read.",
            }
        },
        "required": ["path"],
    },
    function=read_any,
)
