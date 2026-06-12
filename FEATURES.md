# Agent Features & Tools

A complete reference of everything this AI agent can do, how it's built, and why
each piece exists. This is a multi-provider, multi-modal, tool-calling agent with
persistent memory and smart context management.

---

## Table of contents

1. [What this agent is](#what-this-agent-is)
2. [Architecture](#architecture)
3. [Model providers](#model-providers)
4. [Core capabilities](#core-capabilities)
5. [The 14 tools](#the-14-tools)
6. [Configuration (env vars)](#configuration-env-vars)
7. [How to run](#how-to-run)
8. [Project structure](#project-structure)

---

## What this agent is

A command-line AI agent that:

- Talks to **any of three model providers** (Ollama, OpenAI, Anthropic) through one interface
- **Uses tools** to read/write files, search the web, run commands, see images, and recall memory
- **Sees images** (real vision, not just text extraction)
- **Remembers** across sessions via a vector database (RAG)
- **Thinks out loud** in a separate reasoning channel
- **Streams** its replies live and tracks token usage
- **Manages its own context window** so it never forgets and never overflows

The brain runs on `gpt-oss:120b-cloud` (Ollama Cloud) by default. Specialized
features use dedicated sub-models: vision on Ollama Cloud, embeddings on local
Ollama.

---

## Architecture

Three design decisions shape the whole codebase.

### 1. Provider adapter pattern (`models/`)

Every model provider implements one interface, `ModelAdapter` (`models/base.py`).
The agent loop never knows which provider it's talking to. Adding a new provider
means writing one adapter, nothing else changes.

Each adapter handles:
- `format_tools` — convert tool definitions to that provider's schema
- `chat` — send messages, get a response
- `parse_response` — pull out `(content, tool_calls, thinking)`
- `build_assistant_message` — store the reply in history correctly (preserving
  tool-call structure, which a naive implementation drops)
- `build_tool_result_message` — feed a tool's output back in the provider's format
- `get_usage` — token counts
- `supports_streaming` / `stream_chat` — live token output
- `uses_native_thinking` — whether the model reasons in its own channel

### 2. Auto-discovery tool registry (`tools/base/registry.py`)

Tools are discovered automatically by scanning `tools/*/`. To add a tool, drop a
folder `tools/my_tool/my_tool.py` that exports a `tool = ToolDefinition(...)`.
The registry finds it on next launch. Zero configuration, zero wiring. This is
also the foundation for future self-generated skills (the agent can write a new
tool file and have it picked up automatically).

### 3. Pydantic tool definitions (`tools/base/tool.py`)

Every tool is a typed `ToolDefinition` with a name, description, JSON-schema
parameters, and a function. One definition converts itself to each provider's
format via `to_provider_format()`.

---

## Model providers

| Provider | Adapter | Notes |
|----------|---------|-------|
| **Ollama** | `models/ollama.py` | Default. Cloud (`gpt-oss:120b-cloud`) or local. Native thinking + streaming. |
| **OpenAI** | `models/openai.py` | GPT-4o etc. Prompted-thinking fallback. |
| **Anthropic** | `models/anthropic.py` | Claude. Extended thinking (guarded). |

Switch with `--provider ollama|openai|anthropic` or the `AGENT_PROVIDER` env var.

---

## Core capabilities

### Multi-format file handling

The agent reads and writes **7 file format families** through one set of tools.
A dispatch engine (`tools/files/dispatch.py`) routes by file extension:

| Format | Read | Write/Create | Edit | Library |
|--------|------|--------------|------|---------|
| Text (txt, md, json, code) | ✅ | ✅ | ✅ | stdlib |
| CSV | ✅ | ✅ | ✅ | stdlib `csv` |
| Excel (.xlsx) | ✅ (as table) | ✅ (CSV→cells) | regenerate | `openpyxl` |
| Word (.docx) | ✅ | ✅ | ✅ | `python-docx` |
| PDF | ✅ (clean text) | ✅ (generate) | regenerate | `pdfplumber` + `reportlab` |
| Images | ✅ (OCR) | — | — | `pytesseract` + `pillow` |

Honest limits: PDF and XLSX can't be edited in place (regenerate with `write_file`).
Image OCR is read-only. PDF extraction uses word-boundary reconstruction so text
isn't jammed together.

### Vision (seeing images)

`describe_image` sends an image to a vision model (`qwen3-vl:235b-instruct` on
Ollama Cloud) and returns what it actually shows — objects, people, colors,
scenes, charts. This is different from OCR: OCR only pulls text, vision
understands visual content. Runs entirely on the cloud, zero local capacity used.

### RAG / persistent memory

`agent/memory.py` is a lightweight vector database (numpy + JSON, no heavy deps).

- **`index_file`** chunks a file, embeds each chunk (local `nomic-embed-text`),
  and stores it.
- **`search_knowledge`** finds chunks by *meaning*, not keywords.
- Memory **persists to `vector_store/`**, so it survives restarts and carries
  across sessions.
- **Structural chunking**: splits on paragraph → line → sentence → word
  boundaries (not blind fixed-size), with overlap, so ideas stay whole.

Why RAG matters: a 100-page PDF is ~16K tokens. Without RAG, every question about
it re-sends all 16K. With RAG you index once and retrieve only the relevant few
hundred tokens per question.

### Structured thinking

`agent/thinking.py` gives the model a real reasoning channel, rendered separately
(dim blue) from the answer:

- **Native thinking** for reasoning models (gpt-oss via Ollama returns real
  reasoning tokens; Claude extended thinking). Verified working.
- **Prompted fallback** for models without it (gpt-4o): the model wraps reasoning
  in `<thinking>` tags, which the loop splits out.

### Streaming + token tracking

Ollama responses **stream live** — thinking and answer print token-by-token as
they generate, instead of freezing until done. Token usage shows per-call and
cumulative: `[tokens: 1267→44 this call | 3048→289 total]`.

### Smart context management

`agent/context.py` keeps the conversation inside the model's 128K window while
preserving as much as possible. Four layers, in order:

1. **Full window** — uses 128K minus a 16K output reserve (112K input budget),
   instead of an arbitrary cap.
2. **RAG offload** — big *old* tool outputs (e.g. a 16K PDF dump) get stored in
   the vector store and replaced in history with a tiny pointer. Verified: a
   14,049-token dump shrank to 143 tokens, fully recoverable via search.
3. **Compaction** — if still over 80% of budget, old turns are summarized into
   one note instead of deleted. Memory preserved, tokens reclaimed.
4. **Hard trim** — last-resort drop of oldest turns if all else fails.

### Sessions

`agent/session.py` + in-chat commands save and load conversations to disk as JSON:

- `/save [name]` — save the conversation
- `/load <name>` — restore it
- `/sessions` — list saved ones
- `/reset` — clear (keep the system prompt)
- `/help`, `/quit`

---

## The 14 tools

### File operations

| Tool | What it does |
|------|--------------|
| **read_file** | Read any supported format (text, CSV, Excel, Word, PDF, images via OCR) and return text. |
| **write_file** | Create or overwrite a file; format chosen by extension (text/CSV/XLSX/DOCX/PDF). Auto-creates parent dirs. |
| **edit_file** | Replace old text with new (first match). Works on text files and DOCX. |
| **delete_file** | Delete a file permanently. |
| **replace_in_file** | Find-and-replace using regex patterns (advanced edits). |
| **list_files** | List all files in a directory recursively. |
| **tree_view** | Show a visual directory tree (better for understanding layout). |
| **grep_search** | Search for a text pattern inside all files recursively. |

### Knowledge & web

| Tool | What it does |
|------|--------------|
| **web_search** | Search the internet (Tavily if `TAVILY_API_KEY` set, else DuckDuckGo HTML). |
| **read_url** | Fetch a web page and return its text content. |
| **index_file** | Read a file and store it in searchable long-term memory (RAG). |
| **search_knowledge** | Search memory by meaning to recall indexed content, even across sessions. |

### Multi-modal & system

| Tool | What it does |
|------|--------------|
| **describe_image** | Look at an image and describe its visual content (vision model). |
| **run_command** | Run a terminal command and return its output (60s timeout). |

---

## Configuration (env vars)

Set these in `.env` (never commit it — it's gitignored).

| Variable | Default | Purpose |
|----------|---------|---------|
| `AGENT_PROVIDER` | `ollama` | Which provider: ollama / openai / anthropic |
| `AGENT_MODEL` | per-provider | Main chat model (env wins over defaults) |
| `OLLAMA_HOST` | `https://ollama.com` | Ollama endpoint (cloud or local) |
| `OLLAMA_API_KEY` | — | Ollama Cloud key |
| `OPENAI_API_KEY` | — | OpenAI key |
| `ANTHROPIC_API_KEY` | — | Anthropic key |
| `TAVILY_API_KEY` | — | Better web search (optional) |
| `VISION_MODEL` | `qwen3-vl:235b-instruct` | Vision model (Ollama Cloud) |
| `EMBED_MODEL` | `nomic-embed-text` | Embedding model for RAG |
| `EMBED_HOST` | `http://localhost:11434` | Where embeddings run (local Ollama) |
| `CONTEXT_WINDOW` | `128000` | Model's total context window |
| `OUTPUT_RESERVE` | `16000` | Tokens reserved for the reply |

---

## How to run

```bash
# Install dependencies
uv sync

# Run (uses AGENT_PROVIDER from .env, default ollama)
uv run python3 main.py

# Or pick a provider explicitly
uv run python3 main.py --provider anthropic
```

In-chat: type normally, or use `/help`, `/save`, `/load`, `/sessions`, `/reset`, `/quit`.

**OCR note**: image reading needs the system Tesseract binary:
`sudo apt install tesseract-ocr`

**Embeddings note**: RAG needs the local embedding model:
`ollama pull nomic-embed-text`

---

## Project structure

```
main.py                  CLI entry point, provider dispatch
config.py                Provider/model/sub-model resolution, all env config

agent/
  loop.py                Core conversation loop (tool routing, streaming, commands)
  thinking.py            Structured reasoning (native + prompted fallback)
  memory.py              RAG vector store (chunk, embed, search, persist)
  context.py             Smart context manager (offload, compact, trim)
  session.py             Save/load conversations

models/
  base.py                ModelAdapter interface
  ollama.py              Ollama adapter (native thinking + streaming)
  openai.py              OpenAI adapter
  anthropic.py           Anthropic adapter (extended thinking)

tools/
  base/                  Registry + ToolDefinition
  files/                 Multi-format read/write/edit dispatch engine
  <one folder per tool>  Auto-discovered tools

vector_store/            Persisted RAG memory (gitignored)
sessions/                Saved conversations (gitignored)
```

---

## Capabilities at a glance

✅ Multi-provider (Ollama / OpenAI / Anthropic)
✅ 14 auto-discovered tools
✅ 7 file format families (read/write/edit)
✅ Vision (real image understanding)
✅ OCR (text from images)
✅ RAG persistent memory (cross-session)
✅ Native + prompted thinking
✅ Live streaming + token tracking
✅ Smart context management (offload + compaction)
✅ Session save/load
✅ Web search + URL reading
✅ Shell command execution

See `PLAN.md` for the roadmap and what's next.
