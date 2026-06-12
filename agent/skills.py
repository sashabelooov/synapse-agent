"""Skills system — reusable, on-demand instruction documents.

A "skill" is a folder under skills/ containing a SKILL.md file. The file starts
with YAML-style frontmatter declaring a name and description, followed by the
full instructions:

    ---
    name: code_review
    description: Review a Python file for bugs, design, and style.
    ---
    # ... the actual step-by-step instructions ...

At startup the SkillManager reads ONLY the frontmatter of each skill (cheap), so
the model can be told what skills exist via a one-line summary each. The full
instructions are loaded on demand through the use_skill tool, keeping the system
prompt small until a skill is actually needed.

This mirrors how Claude Code skills work: advertise lightly, load fully on use.

Design notes:
  - Single source of truth: one cached manager (get_skill_manager) shared by the
    use_skill tool and the system-prompt builder, so skills are scanned once.
  - Defensive: folders without a SKILL.md are skipped; a SKILL.md with missing
    or broken frontmatter is skipped with a clear warning; duplicate names warn
    and keep the first; loading an unknown skill raises a clear error.
"""

from __future__ import annotations

from pathlib import Path

from termcolor import colored

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


class SkillError(ValueError):
    """Raised when a requested skill does not exist."""


def _parse_frontmatter(text: str) -> dict[str, str] | None:
    """Parse the leading `--- ... ---` frontmatter into a flat dict.

    Returns None if there is no well-formed frontmatter block. Values are split
    on the first colon only, so descriptions may contain colons.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None

    # Find the closing fence.
    closing = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if closing is None:
        return None

    fields: dict[str, str] = {}
    for line in lines[1:closing]:
        if not line.strip() or ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip().lower()] = value.strip()
    return fields


class SkillManager:
    """Discovers skills and serves their instructions on demand."""

    def __init__(self, skills_dir: Path = SKILLS_DIR) -> None:
        self._skills_dir = skills_dir
        self._paths: dict[str, Path] = {}
        self._descriptions: dict[str, str] = {}
        self._scan()

    def _scan(self) -> None:
        """Scan skills/*/SKILL.md, parsing only frontmatter (name, description)."""
        if not self._skills_dir.is_dir():
            return

        for child in sorted(self._skills_dir.iterdir()):
            if not child.is_dir() or child.name.startswith((".", "_")):
                continue

            skill_file = child / "SKILL.md"
            if not skill_file.exists():
                continue  # not a skill folder — skip silently

            fm = _parse_frontmatter(skill_file.read_text(encoding="utf-8"))
            if not fm or "name" not in fm or "description" not in fm:
                print(colored(
                    f"⚠ Skipping skill '{child.name}': SKILL.md has missing or "
                    f"broken frontmatter (need 'name' and 'description').",
                    "yellow",
                ))
                continue

            name = fm["name"]
            if name in self._paths:
                print(colored(
                    f"⚠ Duplicate skill name '{name}' in {child.name}; keeping the first.",
                    "yellow",
                ))
                continue

            self._paths[name] = skill_file
            self._descriptions[name] = fm["description"]

    def list_skills(self) -> dict[str, str]:
        """Return {name: description} for every discovered skill."""
        return dict(self._descriptions)

    def load(self, name: str) -> str:
        """Return the full SKILL.md text for a skill. Raises SkillError if unknown."""
        path = self._paths.get(name)
        if path is None:
            available = ", ".join(sorted(self._paths)) or "none"
            raise SkillError(f"Unknown skill '{name}'. Available skills: {available}.")
        return path.read_text(encoding="utf-8")

    def prompt_block(self) -> str:
        """Build the 'Available skills' system-prompt block.

        Returns an empty string when there are no skills, so nothing (not even a
        header) is appended to the system prompt.
        """
        if not self._descriptions:
            return ""

        lines = [
            "Available skills (call use_skill(name) to load a skill's full "
            "instructions before doing that kind of task, then follow them):",
        ]
        for name, desc in sorted(self._descriptions.items()):
            lines.append(f"- {name}: {desc}")
        return "\n".join(lines)


_MANAGER: SkillManager | None = None


def get_skill_manager() -> SkillManager:
    """Return the shared SkillManager, scanning skills once and caching it."""
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = SkillManager()
    return _MANAGER
