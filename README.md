# Synapse Agent

A multi-provider, tool-calling CLI AI agent with persistent memory, MCP integration, and smart context management.

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Ollama](https://img.shields.io/badge/Ollama-local%20%26%20cloud-000000)
![Anthropic](https://img.shields.io/badge/Anthropic-Claude-D97757)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT-412991?logo=openai&logoColor=white)
![MCP](https://img.shields.io/badge/MCP-Model%20Context%20Protocol-1f6feb)
![Playwright](https://img.shields.io/badge/Playwright-browser-2EAD33?logo=playwright&logoColor=white)
![Pydantic](https://img.shields.io/badge/Pydantic-typed-E92063?logo=pydantic&logoColor=white)
![License](https://img.shields.io/badge/License-Apache%202.0-blue)

---

## Features

- **Multi-provider** — Ollama (cloud & local), OpenAI, and Anthropic through one unified adapter interface. Switch with `--provider` or an env var.
- **59 tools** — 15 auto-discovered native tools + GitHub MCP server (repos, issues, pull requests) + Playwright MCP (browser automation).
- **Skills system** — reusable instruction documents in `skills/*/SKILL.md`. Advertised lightly at startup, loaded on demand so the system prompt stays small.
- **RAG memory** — vector store backed by numpy + JSON (no heavy deps). Index files once, retrieve by meaning across sessions via `index_file` / `search_knowledge`.
- **4-layer context management** — full 128K window → RAG offload of large old tool outputs → compaction of old turns → hard trim. The conversation never overflows and nothing is silently dropped.
- **Streaming + thinking** — Ollama responses stream token-by-token. Reasoning rendered in a separate dim-blue channel. Native thinking for Ollama/gpt-oss and Anthropic Claude; prompted `<thinking>` fallback for OpenAI.
- **Multi-format file handling** — read, write, and edit txt/md/CSV/Excel/DOCX/PDF, plus OCR for images, through a single dispatch engine.
- **Session persistence** — save and restore full conversation history with `/save` / `/load`.

---

## Architecture

```
main.py          CLI entry point; --provider dispatch; MCP setup/teardown
config.py        All provider, model, sub-model, and env resolution
agent/
  loop.py        Core conversation loop (streaming, tool routing, commands)
  thinking.py    Native + prompted-fallback reasoning channel
  memory.py      RAG vector store (chunk → embed → cosine search → persist)
  context.py     4-layer context manager (offload, compact, trim)
  session.py     Save/load conversation history as JSON
  skills.py      Skill discovery and on-demand loading
  mcp_client.py  Generic async MCP client with sync bridge
models/
  base.py        ModelAdapter interface
  ollama.py      Ollama adapter (native thinking + streaming)
  openai.py      OpenAI adapter (prompted thinking)
  anthropic.py   Anthropic adapter (extended thinking)
tools/
  base/          Auto-discovery registry + Pydantic ToolDefinition
  files/         Multi-format read/write/edit dispatch engine
  <tool>/        One folder per native tool — drop a folder, get a tool
skills/
  <skill>/       SKILL.md frontmatter + instructions — loaded on demand
vector_store/    Persisted RAG embeddings (gitignored)
sessions/        Saved conversations (gitignored)
```

**Adapter pattern** — every provider implements `ModelAdapter` (`format_tools`, `chat`, `parse_response`, `build_assistant_message`, `build_tool_result_message`, `get_usage`, `stream_chat`, `uses_native_thinking`). The agent loop never knows which provider it is talking to.

**Auto-discovery registry** — `tools/base/registry.py` scans `tools/*/` on startup. Adding a tool means dropping a folder with a `ToolDefinition`; no wiring required.

**Generic MCP client** — `agent/mcp_client.py` bridges the async MCP SDK to the synchronous agent loop via a background asyncio thread. Remote MCP tools register into the same registry as native tools so the loop treats them identically.

**Skills** — `skills/*/SKILL.md` files with YAML frontmatter (`name`, `description`). Only frontmatter is read at startup. Full instructions load on demand when the model calls `use_skill(name)`.

---

## Setup

### Prerequisites

- Python 3.10+
- [uv](https://github.com/astral-sh/uv)
- Docker (for the GitHub MCP server)
- Node.js / npx (for the Playwright MCP server)
- Tesseract (for image OCR): `sudo apt install tesseract-ocr`
- Local Ollama (for embeddings): `ollama pull nomic-embed-text`

### Install

```bash
git clone https://github.com/sashabelooov/synapse-agent.git
cd synapse-agent
uv sync
```

### Configure

```bash
cp .env.example .env
# Edit .env and fill in your keys (see table below)
```

| Variable | Default | Purpose |
|---|---|---|
| `AGENT_PROVIDER` | `ollama` | Provider: `ollama` / `openai` / `anthropic` |
| `AGENT_MODEL` | per-provider | Override the default chat model |
| `OLLAMA_HOST` | `https://ollama.com` | Ollama endpoint (cloud or `http://localhost:11434`) |
| `OLLAMA_API_KEY` | — | Ollama Cloud API key |
| `OPENAI_API_KEY` | — | OpenAI API key |
| `ANTHROPIC_API_KEY` | — | Anthropic API key |
| `GITHUB_PERSONAL_ACCESS_TOKEN` | — | GitHub PAT (for GitHub MCP server) |
| `TAVILY_API_KEY` | — | Tavily web search key (optional; falls back to DuckDuckGo) |
| `VISION_MODEL` | `qwen3-vl:235b-instruct` | Vision model (Ollama Cloud) |
| `EMBED_MODEL` | `nomic-embed-text` | Embedding model for RAG |
| `EMBED_HOST` | `http://localhost:11434` | Ollama host for embeddings |
| `CONTEXT_WINDOW` | `128000` | Model context window in tokens |
| `OUTPUT_RESERVE` | `16000` | Tokens reserved for the model reply |

### MCP servers

```bash
# Playwright MCP (browser automation)
npx playwright install chromium

# GitHub MCP server
docker pull ghcr.io/github/github-mcp-server
```

MCP servers are configured in `mcp_servers.json`. Both are optional — if a server fails to start, the agent runs with native tools only.

---

## Usage

```bash
# Default provider (reads AGENT_PROVIDER from .env, falls back to ollama)
uv run python3 main.py

# Explicit provider
uv run python3 main.py --provider anthropic
uv run python3 main.py --provider openai
uv run python3 main.py --provider ollama
```

### In-chat commands

| Command | Description |
|---|---|
| `/help` | Show available commands |
| `/save [name]` | Save the current conversation |
| `/load <name>` | Restore a saved conversation |
| `/sessions` | List saved conversations |
| `/reset` | Clear the conversation (keeps system prompt) |
| `/quit` | Exit |

---

## Roadmap

| Phase | Status | Description |
|---|---|---|
| 0 — Core rewrite | ✅ Done | Provider-correct tool routing, session save/load, context guard, real web search |
| 1 — Multi-format files | ✅ Done | Read/write/edit across txt/md/CSV/Excel/DOCX/PDF/images via dispatch engine |
| 2 — Structured thinking | ✅ Done | Native reasoning (gpt-oss, Claude) + prompted fallback (GPT-4o), live streaming |
| 2.5 — Multi-modal + RAG | ✅ Done | Vision (Ollama Cloud), cross-session RAG memory, token tracking |
| 3 — Auto-research mode | Planned | Autonomous search-read-synthesize loop with budget controls |
| 4 — Self-build mode | Planned | Agent writes new tools and modifies its own code via the auto-discovery registry |

---

## License

Apache 2.0 — see [LICENSE](LICENSE) for details.
