---
name: code_review
description: Review a Python file or module for bugs, design, security, and style, and return a prioritized list of issues with fixes.
---
# Python Code Review skill

Review Python code thoroughly but kindly. Give concrete fixes, not vague advice.

## Steps
1. Read the target file(s) with read_file. Use tree_view/grep_search for context.
2. Review in this priority order:
   - Correctness: bugs, logic errors, bad edge cases, unhandled exceptions.
   - Security: input validation, injection risks, secrets in code, unsafe subprocess/eval.
   - Design: SoC and SOLID (one responsibility each), DRY (no repeated logic).
   - Robustness: fail fast (clear early errors), defensive input checks.
   - Readability: clear names, KISS, type hints.
   - Tests: are there tests? Suggest simple ones (TDD).
   - Performance: only flag real problems; no premature optimization.
3. Do NOT rewrite the whole file unless asked. Point to exact lines.

## Output format
A short summary, then issues grouped by severity:
- Critical (bugs/security) — must fix
- Important (design/robustness) — should fix
- Minor (style/naming) — nice to fix
For each: file:line — what is wrong — suggested fix (short code if helpful).
End with 1-2 things done well.
