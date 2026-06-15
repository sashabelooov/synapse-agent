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

---

## Native tool — transcribe_audio

- **Added:** 2026-06-15
- **What it does:** Transcribes any supported audio file (ogg, mp3, wav, m4a, webm, mp4, flac) to text. Backend is selectable: OpenAI Whisper API (cloud, default) or faster-whisper (local CPU, requires Python 3.12+). Language can be specified or auto-detected. Falls back to OpenAI API automatically if the local backend is unavailable.
- **Files:** `tools/transcribe/__init__.py`, `tools/transcribe/transcribe.py`
- **How to use:** `transcribe_audio(path="recording.ogg")` or `transcribe_audio(path="interview.mp3", language="en")`
- **Config / env:** `WHISPER_BACKEND` (openai/local), `WHISPER_LOCAL_MODEL` (base/small/medium/large when local)
- **Status:** ✅ working — 12 tests passing

---

## Native tool — text_to_speech

- **Added:** 2026-06-15
- **What it does:** Converts text to speech and saves the audio file (mp3 or wav). Three backends: edge-tts (Microsoft, 300+ neural voices, free, needs internet — default), OpenAI TTS API (cloud, 6 voices), pyttsx3 (fully offline system voice). Voice and backend can be overridden per-call.
- **Files:** `tools/tts/__init__.py`, `tools/tts/tts.py`
- **How to use:** `text_to_speech(text="Hello world")` or `text_to_speech(text="...", voice="ru-RU-SvetlanaNeural", backend="edge")`
- **Config / env:** `TTS_BACKEND` (edge/openai/pyttsx3), `EDGE_TTS_VOICE`, `OPENAI_TTS_VOICE`, `TTS_OUTPUT_DIR`
- **Status:** ✅ working — 16 tests passing

---

## Telegram voice message pipeline

- **Added:** 2026-06-15
- **What it does:** When a user sends a voice message or audio file to the Telegram bot, it is automatically downloaded, transcribed with Whisper, passed to the agent for a response, and replied to with text. If `VOICE_REPLY=true`, the agent's reply is also converted to speech with edge-tts and sent back as a voice message. The transcript is shown above the text reply so the user can verify it was understood correctly.
- **Files:** `gateway/telegram.py` (`_handle_voice`, refactored `handle_message`)
- **How to use:** Send a voice message in Telegram — the bot handles it end-to-end.
- **Config / env:** `VOICE_REPLY` (false/true), plus STT/TTS config above. Requires `WHISPER_BACKEND=openai` + `OPENAI_API_KEY` or `WHISPER_BACKEND=local`.
- **Status:** ✅ working

---

## Cron scheduler

- **Added:** 2026-06-15
- **What it does:** Background daemon thread that runs agent jobs on a cron schedule. Ticks every 60 seconds. Jobs are stored in `~/.synapse/cron_jobs.json` (or `$CRON_JOBS_PATH`). Each job has a standard 5-field cron expression, a prompt the agent runs, a delivery target, and a hard timeout. File-based lock prevents overlapping ticks across processes. Two thread pools: parallel (independent jobs) and sequential (state-mutating jobs marked with `"sequential": true`). Jobs that exceed their timeout are hard-stopped. Scheduler starts automatically as a daemon thread alongside CLI and Telegram modes.
- **Files:** `cron/__init__.py`, `cron/scheduler.py`, `cron/jobs.example.json`
- **How to use:** Automatically starts when you run `uv run python3 main.py`. Manage jobs via the `cronjob` tool or by editing `~/.synapse/cron_jobs.json` directly.
- **Config / env:** `CRON_JOBS_PATH` (default `~/.synapse/cron_jobs.json`), `SYNAPSE_HOME`
- **Status:** ✅ working — 27 tests passing

---

## Native tool — cronjob

- **Added:** 2026-06-15
- **What it does:** Manages scheduled agent jobs. Six actions: `list` (show all jobs with status and next run), `add` (create a job with a cron schedule and prompt), `enable`/`disable` (toggle without deleting), `delete` (remove permanently), `run_now` (execute immediately outside the schedule). Security: `add` and `delete` are blocked inside a running cron job to prevent runaway scheduling loops.
- **Files:** `tools/cronjob/__init__.py`, `tools/cronjob/cronjob.py`
- **How to use:** "Schedule a daily summary at 9am" → `cronjob(action="add", name="daily_summary", schedule="0 9 * * *", prompt="Summarize new GitHub issues.", delivery="telegram")`. See `cron/jobs.example.json` for more examples.
- **Config / env:** none (uses scheduler's config)
- **Security:** `SYNAPSE_CRON_CONTEXT=1` flag is set during cron execution; `add`/`delete` are refused when it's set.
- **Status:** ✅ working — 19 tests passing

---

## Rich TUI (Textual)

- **Added:** 2026-06-15
- **What it does:** Full-featured interactive terminal UI powered by Textual. 4fr chat panel on the left (conversation history in `RichLog`, live streaming line with cursor, collapsible thinking panel) + 24-char tool panel on the right (last 10 tool calls with real-time elapsed timer, ✓/⚙ done/active state). Status bar shows session name and cumulative token counts. Inline slash-command handler — `/save`, `/load`, `/sessions`, `/reset`, `/help` — processed without running the agent. Ctrl+T toggles the thinking panel; Ctrl+S saves; Ctrl+R resets; q or Ctrl+C quits.
- **Files:** `tui/__init__.py`, `tui/app.py`
- **How to use:** `uv run python3 main.py --mode tui` (Telegram also starts in background if credentials are set)
- **Config / env:** none beyond the provider env vars. `TELEGRAM_BOT_TOKEN` + `TELEGRAM_ALLOWED_USER_ID` auto-start Telegram alongside the TUI.
- **Architecture:** Agent runs in a Textual `@work(thread=True)` thread; all UI updates use `call_from_thread()` — no asyncio/sync bridging needed.
- **Status:** ✅ working — 25 tests passing
