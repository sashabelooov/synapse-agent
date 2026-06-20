---
name: self_improve
description: Research, plan, and implement a new feature for this codebase following the supervised self-improvement loop — with human approval gates before writing any code or opening a PR.
---
# Self-Improvement Skill

This skill guides you through adding a new feature to Synapse Agent safely.
Three human gates prevent runaway changes: **you never write code until the
human says "go", and you never merge anything yourself.**

```
Research → Plan → [HUMAN: go?] → Branch → Code → Test → [HUMAN: review PR] → [HUMAN: merge]
```

---

## Before you start

Read these files to understand the current state:
- `features.md` — what already exists (avoid rebuilding it)
- `PLAN.md` — the roadmap and ground rules
- `plans/` — previously drafted plans (avoid duplicating work)

---

## Step 1 — Research

Goal: understand the feature deeply before touching any code.

1. Use `web_search` and `read_url` to find docs, examples, and prior art for the feature.
2. If the feature has a reference implementation in `NousResearch/hermes-agent`,
   use the GitHub MCP to read relevant files from that repo
   (`get_file_contents`, `search_code`).
3. Read the existing code in this repo that the new feature will touch or extend
   (`read_file`, `tree_view`, `grep_search`).
4. Write a concise research summary to `research/<feature_name>.md`:
   - What the feature does and why it's useful
   - How the reference implementation works (key design decisions)
   - What existing code in this repo it depends on or extends
   - Any gotchas, edge cases, or constraints to watch out for

Keep the summary under 400 words. It is for your own reference, not a user-facing doc.

---

## Step 2 — Plan

Draft a concrete, scoped implementation plan.

Rules:
- **One small feature only.** Resist scope creep. If in doubt, do less.
- Follow the existing patterns: auto-discovery registry, `ToolDefinition`, adapter pattern, SSOT.
- Every new capability needs tests.
- `features.md` must be updated as part of "done".

Write the plan to `plans/<feature_name>.md` using this template:

```markdown
# Plan: <Feature Name>

## Goal
One sentence: what this adds and why.

## Scope (what is IN)
- Bullet list of exactly what will be built

## Out of scope
- Bullet list of what is deliberately excluded

## Files to add
- `path/to/new_file.py` — what it does

## Files to change
- `path/to/existing.py` — what changes and why

## Tests to write
- `tests/test_<name>.py` — what is tested

## Env vars / config
- `VAR_NAME` — purpose, default value

## Implementation notes
Any non-obvious design decisions, edge cases, or constraints.

## Definition of done
- [ ] All tests pass
- [ ] `features.md` updated
- [ ] No secrets in code
- [ ] PR opened for human review
```

---

## Step 3 — STOP. Ask the human.

**Do NOT write any code yet.**

Present the plan to the human:
- Summarise what you found in research (2–3 sentences)
- Show the plan file path and key points
- Ask explicitly: **"Should I proceed with this plan? Say 'go' to start."**

Wait for approval. If the human asks for changes, update `plans/<feature_name>.md`
and ask again. Never skip this gate.

---

## Step 4 — Branch

Once the human says "go":

```bash
run_command("git checkout -b feature/<feature_name>")
```

Branch name must be `feature/<feature_name>`. Never `main` or `master`.
Confirm the branch was created before proceeding.

---

## Step 5 — Code

Implement the plan on the branch. Follow these rules strictly:

- **KISS** — simplest working solution first
- **DRY** — no duplicated logic; reuse existing helpers
- **SSOT** — one place defines each thing (no parallel lists)
- **Fail fast** — validate inputs early; return clear error strings
- **Full type hints** on all new functions and class attributes
- **No secrets in code** — all credentials via env vars
- **No comments** unless the WHY is non-obvious

After each logical piece, commit:
```bash
run_command("git add <files> && git commit -m 'feat(<name>): <what and why>'")
```

Keep commits small and atomic. A good commit is one idea.

---

## Step 6 — Test (automatic gate)

Write tests in `tests/test_<feature_name>.py`. Mock all external calls (APIs,
subprocesses, hardware). Tests must run without network or special hardware.

Run the full suite:
```bash
run_command("python3 -m pytest tests/ -q --tb=short")
```

**Rules:**
- ✅ All tests pass → continue to Step 7
- ❌ Tests fail → fix the code (not the tests). Maximum 3 fix attempts.
  If still failing after 3 attempts, **STOP** and report to the human.
  Never proceed with failing tests.

Also update `features.md` now (before the PR) using the standard entry format.

---

## Step 7 — PR

Push the branch and prepare the PR description:

```bash
run_command("git push -u origin feature/<feature_name>")
```

Then tell the human:
- The branch name and what was implemented
- A diff summary (files changed, tests added)
- Test results (X passed)
- The PR URL on GitHub to open

**Do NOT merge.** Present the PR for human review. Wait.

---

## Step 8 — Merge (human only)

The human reads the diff and merges the PR on GitHub. You delete the branch
after confirmation:

```bash
run_command("git branch -d feature/<feature_name>")
```

Then ask if there is another feature to research next.

---

## Security constraints (always enforced, no exceptions)

| Constraint | Reason |
|---|---|
| GitHub MCP is read-only | Research only — never push via MCP |
| Never modify `agent/loop.py` without explicit human approval | Core loop — highest blast radius |
| Never add cron jobs that schedule more cron jobs | Prevents runaway scheduling loops |
| `ALLOW_COMPUTER_USE=true` required for computer-use actions | Prevents accidental mouse/keyboard control |
| All credentials via env vars, never in code or plans | Secrets must not enter the repo |
| Max 3 test-fix retries before stopping | Prevents infinite fix loops |

---

## Quick reference — useful tools for this skill

| Task | Tool |
|---|---|
| Read existing code | `read_file`, `tree_view`, `grep_search` |
| Research web | `web_search`, `read_url` |
| Read Hermes repo | GitHub MCP: `get_file_contents(repo="NousResearch/hermes-agent", ...)` |
| Write research/plan | `write_file` |
| Git operations | `run_command("git ...")` |
| Run tests | `run_command("python3 -m pytest tests/ -q --tb=short")` |
| Check branch | `run_command("git branch --show-current")` |
