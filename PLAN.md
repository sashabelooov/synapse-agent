# Synapse Agent — Professional Reconstruction Plan

**Reference implementation:** [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)
**Strategy:** Evolve existing codebase — keep adapter pattern, registry, MCP client as the base; add Hermes features phase by phase.
**Goal:** A production-grade, self-improving AI agent for coding, research, and DevOps — matching Hermes feature-for-feature.

---

## Ground rules (non-negotiable, always follow)

1. **One feature at a time.** Build → test → document → ship. Then start the next.
2. **Never touch `master` directly.** All agent-built changes go `branch → PR → human merges`. Manual doc fixes on master are fine.
3. **Tests must pass before merge.** Failing tests = stop. Never merge broken code.
4. **No secrets in the repo, ever.** `.env` is gitignored. `.env.example` has placeholders only.
5. **Every feature documented in `features.md`** before the PR is opened. Not done until it's written there.

---

## Status legend

```
✅ Done   🔄 In progress   ⬜ Planned
```

---

## Phase 0 — Core foundation ✅

Multi-provider (Ollama / OpenAI / Anthropic) via adapter pattern. 15 auto-discovered native tools. Native thinking + streaming. 4-layer context management (full window → RAG offload → compaction → hard trim). RAG vector memory (numpy + JSON). Session save/load as JSON. Skills system (`SkillManager`, `use_skill` tool, `code_review` skill). MCP client (stdio, background asyncio loop). GitHub MCP (read-only: repos, issues, pull_requests). Playwright MCP (23 browser tools).

*All Phase 0 deliverables are in `features.md`.*

---

## Phase 1 — Repo polish & documentation ✅ (current)

| Item | Status |
|---|---|
| GitHub repo created (`sashabelooov/synapse-agent`) | ✅ |
| LICENSE (Apache-2.0) | ✅ |
| `.gitignore` | ✅ |
| `README.md` with badges, setup, architecture, roadmap | ✅ |
| `.env.example` with all variables | ✅ |
| `features.md` — living feature log | ✅ |
| `PLAN.md` — this file, updated | ✅ |
| CI workflow (pytest on push) + CI badge | ⬜ optional |

**Exit criterion:** repo is public, readable, and complete for a new contributor.

---

## Phase 2 — Memory & long-session upgrade ⬜

**Goal:** the agent remembers facts about itself and the user across every session — permanently.

Inspired by Hermes `tools/memory_tool.py`.

### Deliverables

**`agent/persistent_memory.py`** — two files on disk:
- `MEMORY.md` — agent's own notes (what it knows, decisions made, useful facts). Max ~2200 chars.
- `USER.md` — user profile (name, preferences, working style, domain). Max ~1375 chars.

Design constraints (copied from Hermes because they are correct):
- Entries delimited by `§` (section sign) — immune to markdown/JSON injection.
- **Frozen snapshot** at session start → injected into system prompt → never modified mid-session. This preserves the LLM prefix cache across all turns.
- Atomic writes: write to temp file → rename. Readers always see complete files.
- **Drift detection**: if file was externally modified since load, back up to `.bak.<timestamp>` before writing — never silently overwrite.
- **Injection scanning**: all entries scanned against threat patterns before entering the system prompt.
- Deduplication: identical entries removed automatically.

**`tools/memory/memory.py`** — `memory` tool exposed to the model. Four actions:
- `add` — append a new entry (content-validated, size-checked)
- `replace` — find by substring, update in place
- `remove` — delete entry by substring
- `read` — view current state (no modification)

**`agent/session.py`** — migrate from JSON → **SQLite** (`sessions.db`):
- Schema: `sessions(id, name, created_at, updated_at)` + `messages(id, session_id, role, content, ts)`
- Enables FTS5 full-text search across all past sessions.

**`tools/search_sessions/search_sessions.py`** — `search_sessions` tool:
- Query: semantic meaning via RAG, or keyword via SQLite FTS5.
- Returns matching message excerpts with session name + date.
- Use case: "what did we discuss last week about the auth bug?"

**`agent/context.py`** — add memory-flush step: before compaction, write important facts from the current session into `MEMORY.md` so nothing is permanently lost when old turns are trimmed.

### Tests
- `tests/test_persistent_memory.py` — add/replace/remove/read, atomic write, drift detection, injection scan, size limits
- `tests/test_sessions_sqlite.py` — save, load, list, FTS5 search

### Exit criterion
Agent knows your name, preferences, and ongoing projects without being told each session.

---

## Phase 3 — Telegram gateway ⬜

**Goal:** talk to the agent from your phone via Telegram.

Inspired by Hermes `gateway/` + `apps/`.

### Architecture change — extract the agent turn

Before adding Telegram, refactor `agent/loop.py`:

```python
# agent/runner.py — new file
async def run_agent_turn(message: str, session: Session, adapter, model) -> AsyncIterator[str]:
    """Single agent turn: takes a message, yields reply chunks."""
```

This one function is shared by CLI, Telegram, Discord, and any future interface. The loop/gateway just calls it and displays the output in its own way.

### Deliverables

**`gateway/telegram.py`**:
- `aiogram` 3.x bot
- **Locked to your Telegram user ID** (mandatory — agent has shell access)
- One SQLite session per `chat_id`
- Streams reply in real time (edits the message as tokens arrive, Telegram-style)
- Splits replies at 4096-char Telegram limit
- Commands: `/start`, `/reset`, `/sessions`, `/help`, `/quit`
- Tool calls shown as short status messages (e.g. `⚙ running web_search…`)

**`main.py`** — add `--mode telegram` flag:
```bash
uv run python3 main.py --mode telegram
```

### Security (non-negotiable)
- `TELEGRAM_ALLOWED_USER_ID` env var. If incoming `user_id != allowed`, reply "not authorized" and stop. No exceptions.

### Tests
- `tests/test_telegram_gateway.py` — mock `aiogram`, verify auth gate, session routing, reply splitting

### Exit criterion
Send a message on Telegram → agent replies, uses tools, streams output. Unknown user gets blocked.

---

## Phase 4 — Voice ⬜

**Goal:** speak to the agent; it speaks back.

Inspired by Hermes `tools/transcription_tools.py` + `tools/tts_tool.py`.

### Deliverables

**`tools/transcribe/transcribe.py`** — `transcribe_audio` tool:
- Input: audio file path (ogg, mp3, wav, m4a)
- Backend: `faster-whisper` (local, CPU) or OpenAI Whisper API (cloud)
- Returns: transcript text

**`tools/tts/tts.py`** — `text_to_speech` tool:
- Input: text string, optional voice/speed
- Backend: `pyttsx3` (local, offline) or OpenAI TTS API
- Outputs: audio file path

**`gateway/telegram.py`** — wire up voice messages:
- Telegram voice message → download ogg → `transcribe_audio` → pass text to agent turn
- Agent text reply → `text_to_speech` → send as voice note back

### Tests
- `tests/test_voice.py` — mock Whisper, verify transcript → agent → TTS pipeline

### Exit criterion
Send a voice message on Telegram → agent transcribes, replies, speaks back.

---

## Phase 5 — Cron scheduler / heartbeat ⬜

**Goal:** the agent acts proactively — it wakes up on a schedule and messages you first.

Inspired by Hermes `cron/scheduler.py` + `cron/jobs.py`.

### Deliverables

**`cron/scheduler.py`** — background thread, `tick()` every 60 seconds:
- Reads `cron/jobs.json` for due jobs
- File-based lock (one tick at a time across processes)
- Two thread pools: parallel (independent jobs) + sequential (state-mutating jobs)
- Hard-stops jobs that exceed timeout

**`cron/jobs.json`** — job config (user-editable):
```json
{
  "daily_summary": {
    "schedule": "0 9 * * *",
    "prompt": "Check my GitHub issues and summarize anything new.",
    "delivery": "telegram",
    "enabled": true
  }
}
```

**`tools/cronjob/cronjob.py`** — `cronjob` tool:
- Actions: `list`, `add`, `enable`, `disable`, `delete`, `run_now`
- Security: cron agents cannot schedule more cron jobs (prevents runaway loops)

**`gateway/telegram.py`** — delivery target: cron results delivered as Telegram messages.

### Example use cases
- 09:00 daily: "Summarize new GitHub issues in synapse-agent repo"
- Every 30 min: "Check if CI is passing; alert me if it fails"
- Weekly: "Generate a progress summary from recent sessions"

### Tests
- `tests/test_scheduler.py` — tick logic, job due-time calculation, lock, timeout, sequential/parallel pools

### Exit criterion
Add a cron job in-chat. It fires at the scheduled time and sends results to Telegram.

---

## Phase 6 — Rich TUI ⬜

**Goal:** replace the plain `input/print` CLI with a proper terminal UI.

Inspired by Hermes `ui-tui/`.

### Deliverables

**`tui/app.py`** — `textual`-based TUI:
- Scrollable chat history panel (left/main)
- Live tool-call status panel (right sidebar): shows active tool, args, elapsed time
- Input box at the bottom (multiline, Ctrl+Enter to send)
- Status bar: current provider, model, token count, memory usage
- Thinking channel rendered in a collapsible panel (dim blue)
- Session name shown in header

**`main.py`** — `--mode tui` flag:
```bash
uv run python3 main.py --mode tui
```

### Tests
- `tests/test_tui.py` — Textual test harness, verify layout renders, input routing

### Exit criterion
`uv run python3 main.py --mode tui` launches a working rich terminal UI.

---

## Phase 7 — Subagent spawning ⬜

**Goal:** the agent can delegate subtasks to isolated child agents running in parallel.

Inspired by Hermes `tools/mixture_of_agents_tool.py`.

### Architecture

```
Main agent
  ├── Subagent A: "research the Playwright MCP API"
  ├── Subagent B: "search GitHub issues for this error"
  └── Subagent C: "summarize this 50-page PDF"
        → results merged back into main agent turn
```

Each subagent:
- Gets its own isolated message history (no shared state)
- Has a restricted toolset (no shell, no memory writes)
- Has a token/time budget — hard-stops when exceeded
- Returns a plain text result to the parent

### Deliverables

**`tools/spawn_agent/spawn_agent.py`** — `spawn_agent` tool:
- Parameters: `task` (string), `tools` (allowed list), `budget_tokens` (int), `timeout_s` (int)
- Runs child agent on a thread pool
- Returns combined output as a string

**`agent/subagent.py`** — lightweight agent runner for subagents (no streaming, no session, no memory writes)

### Tests
- `tests/test_subagent.py` — spawn, budget enforcement, isolation (no memory bleed)

### Exit criterion
"Research X and Y in parallel" → two subagents run simultaneously, results merged in one reply.

---

## Phase 8 — Discord / Slack gateway ⬜

**Goal:** same agent accessible from Discord and Slack workspaces.

Inspired by Hermes `gateway/platforms/`.

### Deliverables

**`gateway/discord.py`** — `discord.py` bot:
- Locked to allowed guild + user IDs
- Uses shared `run_agent_turn()` from Phase 3
- Slash commands: `/chat`, `/reset`, `/sessions`

**`gateway/slack.py`** — Slack Bolt app:
- Locked to allowed workspace + user IDs
- App mentions trigger agent turn
- Slash commands: `/synapse`, `/reset`

**`main.py`** — `--mode discord` / `--mode slack`

### Tests
- `tests/test_discord_gateway.py`
- `tests/test_slack_gateway.py`

### Exit criterion
Message the bot in Discord or Slack → agent responds using full tool set.

---

## Phase 9 — Computer use ⬜

**Goal:** the agent controls the mouse and keyboard — real desktop automation beyond browser.

Inspired by Hermes `tools/computer_use/`.

### Deliverables

**`tools/computer_use/computer_use.py`**:
- `screenshot` — capture screen as image → pass to vision model
- `click(x, y)` — mouse click
- `type_text(text)` — keyboard input
- `key(combo)` — keyboard shortcut (e.g. `Ctrl+C`)
- `scroll(x, y, direction)` — scroll wheel

Backend: `pyautogui` (cross-platform) with `Pillow` for screenshots.

**Safety gate**: every computer-use action requires explicit user confirmation in `.env`:
```
ALLOW_COMPUTER_USE=true
```
If not set, tool returns an error explaining how to enable it.

### Tests
- `tests/test_computer_use.py` — mock pyautogui, verify safety gate

### Exit criterion
"Open terminal and run pytest" → agent takes a screenshot, finds the terminal, clicks, types the command.

---

## Phase 10 — Image & video generation ⬜

**Goal:** the agent generates images and videos on demand.

Inspired by Hermes `tools/image_generation_tool.py` + `tools/video_generation_tool.py`.

### Deliverables

**`tools/generate_image/generate_image.py`** — `generate_image` tool:
- Backend: Stable Diffusion via `diffusers` (local) or DALL-E 3 (OpenAI API)
- Returns: file path to generated image

**`tools/generate_video/generate_video.py`** — `generate_video` tool:
- Backend: RunwayML or Replicate API
- Returns: file path to generated video

Both tools configurable via env vars: `IMAGE_BACKEND`, `VIDEO_BACKEND`.

### Tests
- `tests/test_image_generation.py` — mock backends, verify parameter routing

### 
"Generate an image of X" → image file saved and path returned to the agent.

---

## Phase 11 — Docker packaging ⬜

**Goal:** run the full agent stack with one command.

### Deliverables

**`Dockerfile`**:
- Python 3.12 base
- `uv` for dependency install
- Tesseract + Node.js included
- Non-root user

**`docker-compose.yml`**:
- `synapse` service (the agent)
- Mounts `~/.synapse/` for MEMORY.md, USER.md, sessions.db, vector_store/
- Env from `.env` file
- Optional: `ollama` service (local model server)

**`docs/docker.md`** — setup guide

### Tests
- `tests/test_docker_build.py` — build image, smoke-test import

### Exit criterion
`docker compose up` → agent running, all tools available, memory persisted to host volume.

---

## Phase 12 — More MCP servers ⬜

**Goal:** expand the agent's knowledge sources.

Inspired by Hermes `optional-mcps/`.

| Server | Toolset | Config |
|---|---|---|
| **Context7** | Live library docs (replaces stale training data) | `npx -y @upstash/context7-mcp` |
| **PostgreSQL** | Read-only SQL queries on your databases | `uvx mcp-server-postgres` |
| **Filesystem** | Controlled access to specific directories | `npx -y @modelcontextprotocol/server-filesystem` |
| **Slack** | Read Slack channels (with token) | `npx -y @modelcontextprotocol/server-slack` |

All configured in `mcp_servers.json`. Each is optional and non-fatal on failure.

### Exit criterion
`mcp_servers.json` entry → server connects → tools available in agent. No code changes needed.

---

## Phase 13 — Supervised self-improvement ⬜

**Goal:** the agent researches and drafts improvements to itself. Humans control every risky step.

This is the final phase — it requires all previous phases to be stable.

### The loop

```
Research → Plan → [HUMAN: approve] → Branch → Code → Test → [HUMAN: review PR] → [HUMAN: merge]
```

### Step 1 — Research
Agent reads Hermes repo (via GitHub MCP on `NousResearch/hermes-agent`) and web docs. Writes `research/<feature>.md` summarizing findings.

### Step 2 — Plan
Agent drafts a concrete plan: files to add/change, tests to write, scope (one small feature only). Saves to `plans/<feature>.md`.

### Step 3 — Human approves (Gate 1)
You read the plan. Say "go" or request changes. **No code written until you approve.**

### Step 4 — Branch
```bash
git checkout -b feature/<name>
```
Never `master`.

### Step 5 — Code
Agent implements on the branch. KISS, DRY, SoC, SSOT, fail fast, full type hints. Small atomic commits.

### Step 6 — Test (Gate 2, automatic)
Agent runs `pytest`. Pass → continue. Fail → fix (max 3 retries) → stop and report. Never proceeds with failing tests. Updates `features.md`.

### Step 7 — PR (Gate 3, human)
Agent opens a PR. You read the diff: correctness, security, no secrets. Approve or request changes.

### Step 8 — Merge
**Only you merge.** Delete the branch. Repeat for the next feature.

### Security constraints (always enforced)
- GitHub MCP stays read-only (research only, never push)
- Local git via `run_command` for branch/commit/push
- No self-modification of `agent/loop.py` without explicit human approval
- No cron jobs that schedule more cron jobs
- Computer use requires `ALLOW_COMPUTER_USE=true`

---

## Phase 14 — Subagent spawning ⬜

**Goal:** the agent can delegate subtasks to isolated child agents running in parallel, then merge their results into a single reply.

### Architecture

```
Main agent
  ├── Subagent A: "research the Playwright MCP API"
  ├── Subagent B: "search GitHub issues for this error"
  └── Subagent C: "summarize this 50-page PDF"
        → results merged back into main agent turn
```

Each subagent:
- Gets its own isolated message history (no shared state with parent or siblings)
- Has a restricted toolset (configurable — defaults to read-only: `read_file`, `web_search`, `read_url`, `grep_search`, `tree_view`, `search_knowledge`)
- Has a token budget and wall-clock timeout — hard-stopped when either is exceeded
- Returns a plain text result string to the parent

### Deliverables

**`agent/subagent.py`** — lightweight synchronous agent runner for child agents:
- No streaming, no session persistence, no memory writes
- Accepts: `task`, `tools` (allowed list), `budget_tokens`, `timeout_s`
- Returns: result string (truncated to budget if needed)
- Runs model turns in a loop until the model stops calling tools or budget is hit

**`tools/spawn_agent/spawn_agent.py`** — `spawn_agent` tool exposed to the model:
- Parameters: `tasks` (list of task strings), `tools` (optional override), `budget_tokens`, `timeout_s`
- Runs each task as a child agent on a `ThreadPoolExecutor` (true parallel)
- Returns results as a numbered list: `[Task 1]: <result>\n[Task 2]: <result>…`
- Safety: subagents cannot call `spawn_agent` themselves (no recursion)

### Tests
- `tests/test_subagent.py` — child agent runs task, budget enforcement (truncates), timeout enforcement, tool isolation (only allowed tools available), no recursion (spawn_agent blocked inside subagent), results merged correctly

### Exit criterion
"Research X and Y in parallel" → two child agents run simultaneously → results merged in one reply.

---

## Phase 15 — Code execution sandbox ⬜

**Goal:** let the agent write and run short code snippets safely, without full shell access.

### Why not just `run_command`?

`run_command` is unrestricted shell — it can delete files, make network calls, install packages. It's the right tool for git and pytest. `run_code` is for "evaluate this Python expression" or "test this function" — it needs isolation.

### Deliverables

**`tools/run_code/run_code.py`** — `run_code` tool:
- Executes a Python snippet in a subprocess with:
  - Hard wall-clock timeout (default 10s, max 30s)
  - No network access (`PYTHONPATH` stripped of requests/httpx/etc — via `sys.modules` block in the sandbox preamble)
  - No filesystem writes outside a temp directory
  - Returns: `stdout`, `stderr`, `exit_code`, `truncated` flag
- Language: Python only (v1). Future: JS, bash with similar sandboxing.
- Implementation: `subprocess.run([sys.executable, "-c", code], timeout=timeout, cwd=tmp_dir, env=restricted_env)`

**Safety gate**: `RUN_CODE_ENABLED=true` in `.env` required (disabled by default).

### Tests
- `tests/test_run_code.py` — basic execution, stdout capture, timeout enforcement, syntax error handling, safety gate, output truncation

### Exit criterion
"Write a function that sorts a list by second element and test it" → agent writes + runs code → returns output.

---

## Phase 16 — Structured knowledge graph ⬜

**Goal:** let the agent accumulate and query structured facts (entity → relation → value) that persist across sessions — complementing the existing document-level RAG memory.

### Why not just RAG?

RAG is great for "find chunks of text similar to this query." It's poor for "what framework does project X use?" — a precise relational lookup. A knowledge graph answers that instantly without embedding similarity.

### Deliverables

**`agent/knowledge_graph.py`** — SQLite-backed triple store:
- Schema: `triples(subject TEXT, relation TEXT, value TEXT, confidence REAL, updated_at TEXT)`
- WAL mode, FTS5 index on subject+relation+value for keyword search
- Operations: `add(subject, relation, value)`, `get(subject, relation)`, `search(query)`, `remove(subject, relation)`, `list(subject)`
- Stored at `$SYNAPSE_HOME/knowledge.db`

**`tools/knowledge/knowledge.py`** — `knowledge` tool exposed to the model:
- Actions: `add`, `get`, `search`, `remove`, `list`
- Examples:
  - `knowledge(action="add", subject="synapse-agent", relation="framework", value="FastAPI")` 
  - `knowledge(action="get", subject="synapse-agent", relation="framework")` → "FastAPI"
  - `knowledge(action="search", query="deploy schedule")` → matching triples

**`agent/runner.py`** — inject top-10 most-recently-updated triples into the system prompt (like persistent memory but structured).

### Tests
- `tests/test_knowledge_graph.py` — add/get/search/remove/list, WAL mode, FTS5 search, system-prompt injection

### Exit criterion
"Remember that we deploy on Fridays" → stored as triple. Next session: "when do we deploy?" → answered from knowledge graph without the user repeating it.

---

## Hermes feature coverage tracker

| Hermes feature | Synapse phase | Status |
|---|---|---|
| Multi-provider (Ollama/OpenAI/Anthropic) | Phase 0 | ✅ |
| Native tools (file, web, shell, RAG) | Phase 0 | ✅ |
| Thinking (native + fallback) + streaming | Phase 0 | ✅ |
| 4-layer context management | Phase 0 | ✅ |
| MCP client (stdio) | Phase 0 | ✅ |
| GitHub MCP | Phase 0 | ✅ |
| Playwright MCP | Phase 0 | ✅ |
| Skills system | Phase 0 | ✅ |
| MEMORY.md + USER.md persistent memory | Phase 2 | ⬜ |
| Atomic writes + drift detection | Phase 2 | ⬜ |
| Injection scanning | Phase 2 | ⬜ |
| SQLite sessions + FTS5 search | Phase 2 | ⬜ |
| Telegram gateway | Phase 3 | ⬜ |
| Voice (Whisper + TTS) | Phase 4 | ⬜ |
| Cron scheduler / heartbeat | Phase 5 | ⬜ |
| Rich TUI (Textual) | Phase 6 | ⬜ |
| Subagent spawning | Phase 7 | ⬜ |
| Discord / Slack gateway | Phase 8 | ⬜ |
| Computer use | Phase 9 | ⬜ |
| Image / video generation | Phase 10 | ⬜ |
| Docker packaging | Phase 11 | ⬜ |
| More MCP servers (Context7, PostgreSQL…) | Phase 12 | ⬜ |
| Supervised self-improvement loop | Phase 13 | ⬜ |
| Subagent spawning (parallel tasks) | Phase 14 | ⬜ |
| Code execution sandbox | Phase 15 | ⬜ |
| Structured knowledge graph | Phase 16 | ⬜ |