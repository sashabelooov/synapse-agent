"""Test the skills system: discovery, loading, and error handling.

Run directly:   uv run python3 test_skills.py
Or with pytest: uv run pytest test_skills.py -v
"""

from __future__ import annotations

from agent.skills import SkillManager, SkillError, get_skill_manager


def test_code_review_skill_is_discovered() -> None:
    manager = SkillManager()
    skills = manager.list_skills()

    assert "code_review" in skills, f"code_review not found; got: {list(skills)}"
    assert "review" in skills["code_review"].lower()

    # load() returns the full SKILL.md body, not just frontmatter.
    body = manager.load("code_review")
    assert "# Python Code Review skill" in body
    assert "## Output format" in body
    print(f"Discovered skills: {list(skills)}")


def test_unknown_skill_raises_clear_error() -> None:
    manager = SkillManager()
    try:
        manager.load("does_not_exist")
    except SkillError as e:
        assert "Unknown skill" in str(e)
        assert "Available skills" in str(e)
        print(f"Unknown skill error OK: {e}")
        return
    raise AssertionError("expected SkillError for unknown skill")


def test_prompt_block_lists_code_review() -> None:
    block = get_skill_manager().prompt_block()
    assert "code_review" in block
    assert block.startswith("Available skills")
    print("Prompt block OK.")


if __name__ == "__main__":
    test_code_review_skill_is_discovered()
    test_unknown_skill_raises_clear_error()
    test_prompt_block_lists_code_review()
    print("OK")
