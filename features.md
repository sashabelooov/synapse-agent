# Synapse Agent — Feature Log

Living reference of every capability in the agent. Updated with every new feature before a PR is opened.

> **Rule:** a feature is not "done" until it has passing tests AND an entry here.

---

## Multi-provider adapter system

- **Added:** 2026-05-25
- **What it does:** Every model provider (Ollama, OpenAI, Anthropic) implements one `ModelAdapter` interface. The agent loop never knows which provider it talks to — swap providers with one flag or env var.
- **Files:** `models/base.py`, `models/ollama.py`, `models/openai.py`, `models/anthropic.py`, `config.py`
- **How to use:** `uv run python3 main.py --provider anthropic` or set `AGENT_PROVIDER=openai` in `.env`
- **Config / env:** `AGENT_PROVIDER` (ollama/openai/anthropic), `AGENT_MODEL`, `OLLAMA_HOST`, `OLLAMA_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`
- **Status:** ✅ working

---

## Auto-discovery tool registry

- **Added:** 2026-05-25
- **What it does:** Scans `tools/*/` on startup and registers every `ToolDefinition` it finds. Adding a new tool means dropping a folder — no wiring, no imports, no config changes.
- **Files:** `tools/base/registry.py`, `tools/base/tool.py`, `tools/__init__.py`
- **How to use:** Drop a folder `tools/my_tool/my_tool.py` that exports `tool = ToolDefinition(...)`. It appears automatically on next launch.
- **Config / env:** none
- **Status:** ✅ working

---

## Native thinking + prompted fallback

- **Added:** 2026-06-01
- **What it does:** Reasoning is rendered in a separate dim-blue channel, never mixed into the answer. Ollama (gpt-oss) and Anthropic (Claude) return real native reasoning tokens. OpenAI (GPT-4o) uses a prompted `<thinking>` scratchpad as fallback.
- **Files:** `agent/thinking.py`, `models/ollama.py`, `models/anthropic.py`, `models/openai.py`
- **How to use:** Automatic — reasoning appears under `💭 thinking` before the model's reply.
- **Config / env:** none (thinking mode is detected per-provider automatically)
- **Status:** ✅ working

---

## Live streaming + token tracking

- **Added:** 2026-06-01
- **What it does:** Ollama responses stream token-by-token as they generate. Thinking and answer print live, not after the full response. Token usage shown per-call and cumulative: `[tokens: 1267→44 this call | 3048→289 total]`.
- **Files:** `agent/loop.py` (`_StreamPrinter`), `models/ollama.py` (`stream_chat`)
- **How to use:** Automatic when using Ollama provider. Non-streaming providers use the existing batch path.
- **Config / env:** none
- **Status:** ✅ working

---

## 4-layer context management

- **Added:** 2026-06-01
- **What it does:** Keeps the conversation inside the model's 128K window without silently dropping anything. Four layers applied in order: (1) full 128K minus 16K output reserve, (2) RAG offload of large old tool outputs, (3) compaction of old turns into a summary note, (4) hard trim of oldest turns as last resort.
- **Files:** `agent/context.py`
- **How to use:** Automatic — called before every model turn.
- **Config / env:** `CONTEXT_WINDOW` (default 128000), `OUTPUT_RESERVE` (default 16000)
- **Status:** ✅ working

---

## RAG persistent memory

- **Added:** 2026-06-05
- **What it does:** Vector database backed by numpy + JSON (no heavy dependencies). Index any file once with `index_file`; retrieve relevant chunks by meaning with `search_knowledge`. Memory survives restarts — cross-session recall works. Structural chunking (paragraph → line → sentence → word boundaries, with overlap) keeps ideas whole.
- **Files:** `agent/memory.py`, `tools/index_file/`, `tools/search_knowledge/`, `vector_store/`
- **How to use:** "Index this PDF" → `index_file(path)`. "What did the doc say about auth?" → `search_knowledge(query)`.
- **Config / env:** `EMBED_MODEL` (default `nomic-embed-text`), `EMBED_HOST` (default `http://localhost:11434`). Requires local Ollama: `ollama pull nomic-embed-text`.
- **Status:** ✅ working

---

## Session save / load

- **Added:** 2026-06-03
- **What it does:** Saves and restores full conversation history to disk as JSON. Each session is a timestamped file in `sessions/`.
- **Files:** `agent/session.py`
- **How to use:** `/save [name]`, `/load <name>`, `/sessions` (list), `/reset` (clear current)
- **Config / env:** none
- **Status:** ✅ working

---

## Native tool — read_file

- **Added:** 2026-06-02
- **What it does:** Reads any supported file format and returns text. Format dispatch by extension: txt/md/json/code → plain text; CSV → formatted rows; Excel (.xlsx) → table; DOCX → paragraphs; PDF → extracted text; images → OCR text.
- **Files:** `tools/read_file/`, `tools/files/dispatch.py`
- **How to use:** "Read budget.xlsx" → `read_file(path="budget.xlsx")`
- **Config / env:** OCR requires `sudo apt install tesseract-ocr`
- **Status:** ✅ working

---

## Native tool — write_file

- **Added:** 2026-06-02
- **What it does:** Creates or overwrites a file. Format chosen by extension. Auto-creates parent directories. Supports txt/md/CSV/Excel/DOCX/PDF.
- **Files:** `tools/write_file/`, `tools/files/dispatch.py`
- **How to use:** "Create a PDF report at reports/summary.pdf" → `write_file(path=..., content=...)`
- **Config / env:** none
- **Status:** ✅ working

---

## Native tool — edit_file

- **Added:** 2026-06-02
- **What it does:** Replaces the first occurrence of old text with new text in a file. Works on text files and DOCX.
- **Files:** `tools/edit_file/`
- **How to use:** "Change 'v1.0' to 'v1.1' in README.md" → `edit_file(path=..., old=..., new=...)`
- **Config / env:** none
- **Status:** ✅ working

---

## Native tool — delete_file

- **Added:** 2026-06-02
- **What it does:** Permanently deletes a file.
- **Files:** `tools/delete_file/`
- **How to use:** `delete_file(path="tmp/old.txt")`
- **Config / env:** none
- **Status:** ✅ working

---

## Native tool — replace_in_file

- **Added:** 2026-06-02
- **What it does:** Find-and-replace using a regex pattern across a file. Use for complex multi-line or pattern-based edits.
- **Files:** `tools/replace_in_file/`
- **How to use:** `replace_in_file(path=..., pattern=..., replacement=...)`
- **Config / env:** none
- **Status:** ✅ working

---

## Native tool — list_files

- **Added:** 2026-06-02
- **What it does:** Lists all files in a directory recursively.
- **Files:** `tools/list_files/`
- **How to use:** `list_files(path="src/")`
- **Config / env:** none
- **Status:** ✅ working

---

## Native tool — tree_view

- **Added:** 2026-06-02
- **What it does:** Renders a visual directory tree — better for understanding project layout than a flat list.
- **Files:** `tools/tree_view/`
- **How to use:** `tree_view(path=".")` 
- **Config / env:** none
- **Status:** ✅ working

---

## Native tool — grep_search

- **Added:** 2026-06-02
- **What it does:** Searches for a text pattern inside all files in a directory recursively. Returns matching lines with file paths and line numbers.
- **Files:** `tools/grep_search/`
- **How to use:** "Find all uses of deprecated_func" → `grep_search(pattern="deprecated_func", path=".")`
- **Config / env:** none
- **Status:** ✅ working

---

## Native tool — web_search

- **Added:** 2026-06-03
- **What it does:** Searches the internet. Uses Tavily if `TAVILY_API_KEY` is set (better results), falls back to DuckDuckGo HTML scraping (keyless, real results — not the near-useless Instant Answers).
- **Files:** `tools/web_search/`
- **How to use:** "Search for the latest Playwright MCP docs" → `web_search(query=...)`
- **Config / env:** `TAVILY_API_KEY` (optional — improves result quality)
- **Status:** ✅ working

---

## Native tool — read_url

- **Added:** 2026-06-03
- **What it does:** Fetches a web page and returns its text content (HTML stripped, markdown-ish output).
- **Files:** `tools/read_url/`
- **How to use:** `read_url(url="https://docs.anthropic.com/...")`
- **Config / env:** none
- **Status:** ✅ working

---

## Native tool — describe_image

- **Added:** 2026-06-05
- **What it does:** Sends an image to a vision model and returns a description of its visual content — objects, people, scenes, charts. Different from OCR: vision understands visual meaning, not just text. Runs on Ollama Cloud (zero local capacity needed).
- **Files:** `tools/describe_image/`
- **How to use:** "What's in this screenshot?" → `describe_image(path="screenshot.png")`
- **Config / env:** `VISION_MODEL` (default `qwen3-vl:235b-instruct`), `OLLAMA_HOST`, `OLLAMA_API_KEY`
- **Status:** ✅ working

---

## Native tool — run_command

- **Added:** 2026-06-02
- **What it does:** Runs a shell command and returns stdout + stderr. 60-second timeout. Use for git, pytest, npm, docker, or any CLI tool.
- **Files:** `tools/run_command/`
- **How to use:** "Run the tests" → `run_command(command="pytest tests/ -v")`
- **Config / env:** none
- **Status:** ✅ working

---

## Native tool — use_skill

- **Added:** 2026-06-09
- **What it does:** Loads the full instructions of a named skill from `skills/<name>/SKILL.md` and injects them into the current conversation. Skills are only loaded on demand — keeping the system prompt small until needed.
- **Files:** `tools/use_skill/use_skill.py`, `agent/skills.py`
- **How to use:** `use_skill(name="code_review")` — model calls this automatically when a skill is listed in its system prompt.
- **Config / env:** none
- **Status:** ✅ working

---

## Skills system

- **Added:** 2026-06-09
- **What it does:** Discovers `skills/*/SKILL.md` files at startup. Each skill has YAML frontmatter (`name`, `description`). Only frontmatter is read at startup (cheap). Full instructions are loaded on demand via `use_skill`. The model is told what skills exist in the system prompt; it chooses when to load them.
- **Files:** `agent/skills.py`, `skills/code_review/SKILL.md`
- **How to use:** Drop a new folder `skills/my_skill/SKILL.md` with frontmatter. It appears automatically at next launch.
- **Config / env:** none
- **Status:** ✅ working

---

## Skill — code_review

- **Added:** 2026-06-09
- **What it does:** Step-by-step instructions for reviewing a Python file for bugs, design issues, security problems, and style. Produces a prioritized list of findings with suggested fixes.
- **Files:** `skills/code_review/SKILL.md`
- **How to use:** "Use the code_review skill on agent/loop.py"
- **Config / env:** none
- **Status:** ✅ working

---

## MCP client (stdio)

- **Added:** 2026-06-08
- **What it does:** Generic async MCP client that connects to any stdio MCP server. Runs a background asyncio thread so MCP sessions stay open for the agent's lifetime. Remote MCP tools register into the same auto-discovery registry as native tools — the agent loop treats them identically. Non-fatal: a failed server warns loudly and the agent runs without it.
- **Files:** `agent/mcp_client.py`, `mcp_servers.json`, `config.py` (`load_mcp_servers`)
- **How to use:** Add an entry to `mcp_servers.json`. The server connects automatically at startup.
- **Config / env:** Server-specific env vars (e.g. `GITHUB_PERSONAL_ACCESS_TOKEN`). Env vars referenced as `${VAR}` in `mcp_servers.json` — secrets never live in the config file.
- **Status:** ✅ working

---

## GitHub MCP server

- **Added:** 2026-06-08
- **What it does:** Connects the official GitHub MCP server (Docker) with read-only access to repos, issues, and pull requests. Exposes 21 tools: list/get/search repos, list/get/create issues, list/get PRs, search code, get file contents, list branches, and more.
- **Files:** `mcp_servers.json`
- **How to use:** "List open issues in synapse-agent repo" → agent calls GitHub MCP tools automatically.
- **Config / env:** `GITHUB_PERSONAL_ACCESS_TOKEN`, `GITHUB_TOOLSETS` (default: `repos,issues,pull_requests`), `GITHUB_READ_ONLY=1`. Requires: `docker pull ghcr.io/github/github-mcp-server`
- **Status:** ✅ working

---

## Playwright MCP server

- **Added:** 2026-06-09
- **What it does:** Connects the Playwright MCP server (npx) for browser automation. Exposes 23 tools: navigate, click, type, screenshot, select, hover, wait, evaluate JS, and more. Runs in headed mode — you can watch the browser work.
- **Files:** `mcp_servers.json`
- **How to use:** "Open https://github.com and screenshot the page" → agent calls Playwright MCP tools.
- **Config / env:** `DISPLAY`, `XAUTHORITY` (for headed mode on Linux). Requires: `npx playwright install chromium`
- **Status:** ✅ working

---

## Persistent cross-session memory (MEMORY.md + USER.md)

- **Added:** 2026-06-13
- **What it does:** Two §-delimited flat files in `~/.synapse/` store agent notes (`MEMORY.md`, max 2200 chars) and a user profile (`USER.md`, max 1375 chars). A frozen snapshot is captured at session start and injected into the system prompt — the agent knows what it remembered without being told again. Entries persist across all restarts and sessions.
- **Files:** `agent/persistent_memory.py`
- **How to use:** The agent calls the `memory` tool automatically. You can also say "remember that I prefer short answers" or "note that this project uses FastAPI".
- **Config / env:** `SYNAPSE_HOME` (default `~/.synapse/`)
- **Safety:** Atomic writes (temp → rename), drift detection (backup on external edits), prompt-injection scanning on all entries before system-prompt injection, deduplication.
- **Status:** ✅ working — 31 tests passing

---

## memory tool

- **Added:** 2026-06-13
- **What it does:** Exposes the persistent memory stores to the model. Four actions: `add` (append entry), `replace` (find by substring, update), `remove` (delete by substring), `read` (view current entries and usage).
- **Files:** `tools/memory/memory.py`
- **How to use:** "Add to memory: main language is Python" → `memory(store="memory", action="add", content="Main language is Python.")`
- **Config / env:** none (uses `SYNAPSE_HOME` via `persistent_memory`)
- **Status:** ✅ working

---

## SQLite session storage

- **Added:** 2026-06-13
- **What it does:** Replaces JSON session files with a proper SQLite database (`~/.synapse/sessions.db`). Schema: `sessions` + `messages` tables with WAL mode and foreign keys. FTS5 full-text search index maintained by triggers. Complex message content (Anthropic tool-call blocks etc.) is JSON-serialized and round-tripped correctly.
- **Files:** `agent/session.py` (rewritten)
- **How to use:** `/save`, `/load`, `/sessions` commands work identically to before — SQLite is the new backend.
- **Config / env:** `SYNAPSE_HOME` (default `~/.synapse/`)
- **Status:** ✅ working — 21 tests passing

---

## search_sessions tool

- **Added:** 2026-06-13
- **What it does:** Full-text search across all past conversation sessions using SQLite FTS5. Returns matching message excerpts with session name and date. Use to recall past decisions, find previous work, or look up earlier discussions.
- **Files:** `tools/search_sessions/search_sessions.py`
- **How to use:** "What did we discuss last week about the auth bug?" → `search_sessions(query="auth bug")`
- **Config / env:** none (uses `SYNAPSE_HOME` via `agent/session.py`)
- **Status:** ✅ working

---

## Shared agent runner (agent/runner.py)

- **Added:** 2026-06-14
- **What it does:** Extracts the core agent turn logic (context management, model call, tool execution loop, streaming callbacks) into a single function `run_agent_turn()` shared by CLI, Telegram, and all future gateways. `build_agent_state()` creates the one-time setup (tools, formatted tools, system prompt with memory and skills injected). No I/O — all display is decoupled through callbacks.
- **Files:** `agent/runner.py`, `agent/loop.py` (refactored to use runner)
- **How to use:** Internal — called by loop.py (CLI) and gateway/telegram.py (Telegram).
- **Config / env:** none
- **Status:** ✅ working — 13 tests passing

---

## Telegram gateway

- **Added:** 2026-06-14
- **What it does:** Exposes the full agent as a Telegram bot. The agent uses all tools (file ops, web search, shell, GitHub MCP, Playwright, memory, etc.) and replies via Telegram. Replies stream in real time (the message is edited as tokens arrive). Long replies are split at the 4096-char Telegram limit. One SQLite session per chat ID. Commands: /start, /reset, /save, /load, /sessions, /help.
- **Files:** `gateway/__init__.py`, `gateway/telegram.py`
- **How to use:** `uv run python3 main.py --mode telegram`
- **Config / env:** `TELEGRAM_BOT_TOKEN` (from @BotFather), `TELEGRAM_ALLOWED_USER_ID` (your numeric ID from @userinfobot)
- **Security:** ONLY the configured user ID can interact with the bot. Any other user gets "Not authorized." immediately. No exceptions.
- **Status:** ✅ working — 20 tests passing
