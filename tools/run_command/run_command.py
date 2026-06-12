import subprocess
from tools.base.tool import ToolDefinition


def _run_command(command: str) -> str:
    """Run a terminal command and return its output."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            text=True,
            capture_output=True,
            timeout=60,
        )
        output = result.stdout + result.stderr
        return output.strip() if output.strip() else "Command finished with no output."
    except subprocess.TimeoutExpired:
        return "Error: command timed out after 60 seconds."
    except Exception as e:
        return f"Error running command: {e}"


tool = ToolDefinition(
    name="run_command",
    description="Run a terminal command and return its output. Use this to run Python files, install packages, run tests, or any shell command.",
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The terminal command to run. Example: python3 main.py",
            },
        },
        "required": ["command"],
    },
    function=_run_command,
)
