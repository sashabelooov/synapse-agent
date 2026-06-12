from tools.base.tool import ToolDefinition
from agent.skills import get_skill_manager, SkillError


def _use_skill(name: str) -> str:
    """Load a skill's full instructions by name."""
    try:
        return get_skill_manager().load(name)
    except SkillError as e:
        # Return a clear message (not a crash) so the model can recover.
        return f"Error: {e}"


tool = ToolDefinition(
    name="use_skill",
    description=(
        "Load the full instructions for a named skill, then follow them. Call this "
        "when a task matches one of the available skills listed in your system "
        "prompt. Returns the skill's step-by-step guide."
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "The skill name to load (e.g. 'code_review').",
            }
        },
        "required": ["name"],
    },
    function=_use_skill,
)
