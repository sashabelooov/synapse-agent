# 🧠 Synapse Agent — Final Master Plan

Everything in one place: the **ground rules**, all **phases**, the **self-improvement loop** (each step explained), and the **`features.md`** documentation rule.

---

## 📜 Part 1 — Ground rules (always follow these)

1. 🧩 **One feature at a time.** Build it, test it, ship it, then start the next (KISS + incremental).
2. 🌿 **Never let the agent touch `master`/`main` directly.** Agent changes go on a **branch** → **Pull Request** → **you merge**. (You can still commit your *own* manual work to master if you want — this rule is for *agent-made* changes.)
3. 🧪 **Tests must pass before merge.** If tests fail, fix or stop — never merge broken code (fail fast).
4. 🔑 **No secrets in the repo, ever.** `.env` stays local and gitignored. Use `.env.example` with placeholders.
5. 📝 **Document every feature in `features.md`** (see Part 4). A feature isn't "done" until it's written there.

---

## 🚀 Part 2 — The phases (all, in detail)

Status: ✅ done · 🔄 in progress · ⬜ planned

### ✅ Phase 0 — Core foundation (DONE)
The base agent: multi-provider (Ollama/OpenAI/Anthropic via adapter pattern), 14 native tools, native thinking + streaming, 4-layer context management, RAG memory, session save/load.

### ✅ Phase 1 — MCP client + GitHub (DONE)
A generic MCP client over stdio (reusable for any server). GitHub MCP connected with 21 **read-only** tools.

### ✅ Phase 2 — Skills system (DONE)
`SkillManager` (scan + load), `use_skill` tool, system-prompt injection. First skill: `code_review`.

### ✅ Phase 3 — Browser automation (DONE)
Playwright MCP (23 tools) in **headed** mode so you can watch the browser work live.

### 🔄 Phase 4 — Public repo & polish (IN PROGRESS — now)
- ✅ Repo created + code pushed (`github.com/sashabelooov/synapce-agent`)
- ✅ LICENSE (Apache-2.0) + `.gitignore`
- 🔄 `README.md` with **badges**, features, setup, architecture
- ⬜ `.env.example` (placeholders only)
- ⬜ Rename `synapce-agent` → `synapse-agent` (fix the typo)
- ⬜ *(Optional)* basic CI workflow (pytest on push) → a **real** CI badge
- ⬜ Create `features.md` (Part 4)

### ⬜ Phase 5 — Memory & long-session upgrade (NEXT)
- `MEMORY.md` / `USER.md` — small permanent facts injected every session
- Move sessions from JSON → **SQLite** (queryable, crash-safe)
- **FTS5 session search** → a `search_sessions` tool ("what did we discuss last week?")
- *(Optional)* memory-flush before compaction

### ⬜ Phase 6 — Telegram channel
- Extract a reusable `run_agent_turn(message, session)` (shared by CLI + Telegram)
- `aiogram` bot, **locked to your Telegram user ID only** (mandatory — agent can run shell!)
- One session per `chat_id`; split long replies; `/start`, `/reset`, `/help`

### ⬜ Phase 7 — Voice
- Whisper (speech-to-text) for voice messages
- TTS for spoken replies

### ⬜ Phase 8 — Scheduler / heartbeat (proactive)
- A timer/cron wakes the agent on a schedule
- It checks things and **messages you first**: CI failed, new GitHub issue, daily summary…

### ⬜ Phase 9 — Supervised self-improvement
The agent helps build itself — **safely** (this is the loop in Part 3).

### ⬜ Phase 10 — More MCP servers (as needed)
Context7 (live docs), PostgreSQL (read-only), etc. — just config entries.

---

## 🔁 Part 3 — The self-improvement loop (each step explained)

This is **Phase 9**. The goal: the agent can research and draft improvements to itself, but **humans stay in control** at every risky step.

> ⚙️ **Git note:** keep GitHub MCP **read-only** (for *reading* repos). The agent does branch/commit/push with **local git** via `run_command`, using *your existing* git login — so you don't need to give it any GitHub write token. You still review the PR before merging.

### 1. 📥 Research
The agent reads the **Hermes repo** (via `read_file` on a local clone, or GitHub MCP) and reads **docs on the internet** (`web_search` + `read_url`). It writes a short **summary of findings** — how a specific feature works.
*Why:* understand the idea before copying it.

### 2. 📋 Plan
It drafts a concrete plan for **ONE small feature**: the approach, the files to add/change, and the test. Keep the scope tight (YAGNI).
*Output:* a written plan.

### 3. ✋ APPROVE — ⛔ Gate 1 (human)
**You** read the plan and say **"go"** (or ask for changes). **No code is written until you approve.** This is the most important gate.

### 4. 🌿 Branch
The agent creates a **new git branch** (e.g. `feature/memory-md`) — never `master`. This isolates the change so your main code stays safe.
`git checkout -b feature/<name>`

### 5. ✍️ Code
It implements the feature **on the branch**, following your principles: KISS, DRY, SoC, SSOT, fail fast, defensive checks, full type hints. Small, focused commits.

### 6. 🧪 Test — ⛔ Gate 2 (automatic)
It **writes tests** (TDD) and **runs the suite** (`pytest`).
- ✅ Tests pass → continue.
- ❌ Tests fail → fix (limited retries) or **STOP and report**. Never proceed with failing tests.
- 📝 It also **updates `features.md`** here (part of "done" — see Part 4).

### 7. 👀 Review — ⛔ Gate 3 (human)
It opens a **Pull Request** and **you read the diff**: correctness, security, no secrets, style. Approve or request changes.

### 8. ✅ Merge
**Only you** merge the PR into `master`. Then delete the branch. ↺ Repeat for the next small feature.

```
📥 Research → 📋 Plan → ✋ approve → 🌿 branch → ✍️ code → 🧪 test → 👀 review → ✅ you merge → ↺
                         (human)                          (auto)      (human)
```

---

## 📝 Part 4 — The `features.md` rule

**`features.md`** is a **living log** of everything the agent can do. The agent must **document** every new feature there — automatically, as part of finishing it.

### Why
- 🗂️ One source of truth (SSOT) for the agent's abilities, always up to date.
- 🧠 The agent (and you) can re-read it later to know what already exists (avoids rebuilding things — DRY).
- 📖 Great for your README and for new people reading the repo.

### When
Every time a new **tool, skill, MCP server, or capability** is added — and **before** the PR is opened (it's part of the Definition of Done).

### Format (one entry per feature)
```markdown
## <Feature name>
- **Added:** YYYY-MM-DD
- **What it does:** one or two clear sentences.
- **Files:** the files added or changed.
- **How to use:** an example command or prompt.
- **Config / env:** any new settings or env vars (no real secrets).
- **Status:** ✅ working
```

### Example entry
```markdown
## Skills system (use_skill + code_review)
- **Added:** 2026-06-09
- **What it does:** lets the agent load skill instructions on demand from
  skills/<name>/SKILL.md, so steps don't waste tokens until needed.
- **Files:** agent/skills.py, tools/use_skill/use_skill.py,
  skills/code_review/SKILL.md
- **How to use:** "Use the code_review skill on config.py"
- **Config / env:** none
- **Status:** ✅ working
```

### The rule in one line
> 🔒 **A feature is not "done" until it has tests passing AND an entry in `features.md`.**

---

## ✅ Summary

- **Ground rules:** one feature at a time · branch → PR → you merge · tests pass · no secrets · document in `features.md`.
- **Phases 0–3:** ✅ done. **Phase 4:** 🔄 now. **Phases 5–10:** ⬜ planned.
- **Self-improvement loop:** research → plan → **you approve** → branch → code → **test** → **you review** → **you merge**.
- **`features.md`:** the agent's living feature log — updated with every new feature.

You've already shipped 4 phases of real, working software. Keep going — one small, tested, documented step at a time. 🚀