"""Tests for Phase 13 — Supervised self-improvement loop.

Validates:
- Directory structure (research/, plans/)
- self_improve skill file format and content
- Skill loads correctly via SkillManager
- All human gates are documented
- Security constraints are present
- System-prompt block advertises the skill
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL_FILE = ROOT / "skills" / "self_improve" / "SKILL.md"


# ---------------------------------------------------------------------------
# Directory structure
# ---------------------------------------------------------------------------

class TestDirectoryStructure:
    def test_research_dir_exists(self):
        assert (ROOT / "research").is_dir(), "research/ directory missing"

    def test_plans_dir_exists(self):
        assert (ROOT / "plans").is_dir(), "plans/ directory missing"

    def test_self_improve_skill_dir_exists(self):
        assert (ROOT / "skills" / "self_improve").is_dir()

    def test_skill_file_exists(self):
        assert SKILL_FILE.exists(), "skills/self_improve/SKILL.md missing"


# ---------------------------------------------------------------------------
# SKILL.md frontmatter
# ---------------------------------------------------------------------------

class TestSkillFrontmatter:
    def _content(self) -> str:
        return SKILL_FILE.read_text(encoding="utf-8")

    def test_has_frontmatter_delimiters(self):
        lines = self._content().splitlines()
        assert lines[0].strip() == "---", "SKILL.md must start with ---"
        closing = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
        assert closing is not None, "SKILL.md frontmatter has no closing ---"

    def test_name_is_self_improve(self):
        content = self._content()
        assert "name: self_improve" in content

    def test_description_present(self):
        content = self._content()
        assert "description:" in content
        # Description should be non-empty
        for line in content.splitlines():
            if line.startswith("description:"):
                assert len(line.split(":", 1)[1].strip()) > 10
                break

    def test_description_mentions_human_gates(self):
        for line in self._content().splitlines():
            if line.startswith("description:"):
                desc = line.split(":", 1)[1].lower()
                assert "human" in desc or "approval" in desc or "supervised" in desc
                break


# ---------------------------------------------------------------------------
# SKILL.md content — all eight steps present
# ---------------------------------------------------------------------------

class TestSkillSteps:
    def _content(self) -> str:
        return SKILL_FILE.read_text(encoding="utf-8")

    def test_has_research_step(self):
        assert "Research" in self._content()

    def test_has_plan_step(self):
        assert "Plan" in self._content()

    def test_has_branch_step(self):
        assert "Branch" in self._content()

    def test_has_code_step(self):
        assert "Code" in self._content()

    def test_has_test_step(self):
        assert "Test" in self._content()

    def test_has_pr_step(self):
        assert "PR" in self._content() or "pull request" in self._content().lower()

    def test_has_merge_step(self):
        assert "Merge" in self._content() or "merge" in self._content()


# ---------------------------------------------------------------------------
# Human gates — all three must be documented
# ---------------------------------------------------------------------------

class TestHumanGates:
    def _content(self) -> str:
        return SKILL_FILE.read_text(encoding="utf-8")

    def test_gate_1_approval_before_code(self):
        content = self._content()
        # Must tell the agent to stop and ask before writing code
        assert "STOP" in content or "stop" in content.lower()
        assert "go" in content.lower()

    def test_gate_2_tests_must_pass(self):
        content = self._content()
        assert "pytest" in content or "test" in content.lower()
        assert "fail" in content.lower()

    def test_gate_3_human_reviews_pr(self):
        content = self._content()
        assert "review" in content.lower() or "PR" in content

    def test_human_only_merges(self):
        content = self._content()
        assert "only you merge" in content.lower() or "human only" in content.lower() or \
               "do not merge" in content.lower() or "do NOT merge" in content

    def test_max_retry_limit_documented(self):
        content = self._content()
        # The 3-retry rule prevents infinite fix loops
        assert "3" in content and ("retry" in content.lower() or "attempt" in content.lower())


# ---------------------------------------------------------------------------
# Security constraints — all must be documented in the skill
# ---------------------------------------------------------------------------

class TestSecurityConstraints:
    def _content(self) -> str:
        return SKILL_FILE.read_text(encoding="utf-8")

    def test_github_mcp_read_only_constraint(self):
        content = self._content()
        assert "read-only" in content.lower() or "read only" in content.lower()

    def test_no_touch_loop_py_constraint(self):
        content = self._content()
        assert "loop.py" in content

    def test_no_cron_scheduling_cron_constraint(self):
        content = self._content()
        assert "cron" in content.lower()

    def test_no_secrets_in_code_constraint(self):
        content = self._content()
        assert "secret" in content.lower() or "credential" in content.lower()

    def test_computer_use_gate(self):
        content = self._content()
        assert "ALLOW_COMPUTER_USE" in content


# ---------------------------------------------------------------------------
# Plan template — must be present for the agent to know what to write
# ---------------------------------------------------------------------------

class TestPlanTemplate:
    def _content(self) -> str:
        return SKILL_FILE.read_text(encoding="utf-8")

    def test_template_has_goal_section(self):
        assert "Goal" in self._content()

    def test_template_has_scope_section(self):
        assert "Scope" in self._content()

    def test_template_has_files_to_add(self):
        assert "Files to add" in self._content() or "files to add" in self._content().lower()

    def test_template_has_tests_section(self):
        assert "Tests to write" in self._content() or "tests" in self._content().lower()

    def test_template_has_definition_of_done(self):
        assert "Definition of done" in self._content() or "done" in self._content().lower()

    def test_template_references_features_md(self):
        assert "features.md" in self._content()


# ---------------------------------------------------------------------------
# SkillManager integration
# ---------------------------------------------------------------------------

class TestSkillManagerIntegration:
    def test_skill_discovered_by_manager(self):
        from agent.skills import SkillManager
        sm = SkillManager()
        assert "self_improve" in sm.list_skills()

    def test_skill_description_non_empty(self):
        from agent.skills import SkillManager
        sm = SkillManager()
        desc = sm.list_skills()["self_improve"]
        assert len(desc) > 20

    def test_skill_loads_full_content(self):
        from agent.skills import SkillManager
        sm = SkillManager()
        content = sm.load("self_improve")
        assert len(content) > 1000, "Skill content seems too short"

    def test_skill_appears_in_prompt_block(self):
        from agent.skills import SkillManager
        sm = SkillManager()
        block = sm.prompt_block()
        assert "self_improve" in block

    def test_both_skills_present(self):
        from agent.skills import SkillManager
        sm = SkillManager()
        skills = sm.list_skills()
        assert "code_review" in skills
        assert "self_improve" in skills

    def test_loading_unknown_skill_raises(self):
        from agent.skills import SkillManager, SkillError
        sm = SkillManager()
        try:
            sm.load("nonexistent_skill")
            assert False, "Expected SkillError"
        except SkillError:
            pass


# ---------------------------------------------------------------------------
# Quick-reference table — tools needed for the loop must be listed
# ---------------------------------------------------------------------------

class TestToolReferenceTable:
    def _content(self) -> str:
        return SKILL_FILE.read_text(encoding="utf-8")

    def test_references_web_search(self):
        assert "web_search" in self._content()

    def test_references_read_url(self):
        assert "read_url" in self._content()

    def test_references_run_command_for_git(self):
        content = self._content()
        assert "run_command" in content
        assert "git" in content

    def test_references_write_file_for_plans(self):
        assert "write_file" in self._content()

    def test_references_github_hermes_repo(self):
        content = self._content()
        assert "hermes" in content.lower() or "NousResearch" in content
