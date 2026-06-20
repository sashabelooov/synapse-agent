# Running Synapse Agent with Docker

Docker gives you a fully isolated, reproducible environment with Tesseract, Node.js, and all Python dependencies pre-installed. Persistent state (memory, sessions, vector store) lives on a named volume so it survives container restarts.

---

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) 24+
- [Docker Compose](https://docs.docker.com/compose/install/) v2 (bundled with Docker Desktop)
- A `.env` file in the project root (copy from `.env.example`)

---

## Quick start

```bash
# 1. Clone and enter the project
git clone https://github.com/sashabelooov/synapse-agent.git
cd synapse-agent

# 2. Create your .env
cp .env.example .env
# Edit .env — add your ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, etc.

# 3. Build the image
docker compose build

# 4. Run in interactive CLI mode
docker compose run --rm synapse
```

---

## Modes

| Mode | Command |
|---|---|
| Interactive CLI | `docker compose run --rm synapse` |
| Telegram bot (background) | `docker compose up -d synapse` (set `TELEGRAM_BOT_TOKEN` in `.env`) |
| Rich TUI | `docker compose run --rm synapse --mode tui` |

For Telegram mode the container runs as a daemon (`docker compose up -d`). Logs: `docker compose logs -f synapse`.

---

## With local Ollama

Start the full stack including a local Ollama model server:

```bash
docker compose --profile ollama up
```

This starts:
- `synapse` — the agent, pointed at `http://ollama:11434`
- `ollama` — Ollama server on port 11434 (also accessible from your host)

Pull a model into the Ollama container:

```bash
docker compose exec ollama ollama pull qwen3:30b-a3b
docker compose exec ollama ollama pull nomic-embed-text
```

Set in `.env`:
```
AGENT_PROVIDER=ollama
AGENT_MODEL=qwen3:30b-a3b
OLLAMA_HOST=http://ollama:11434
```

---

## Persistent data

All state is stored in the `synapse_data` Docker volume, mounted at `/data/synapse` inside the container:

```
/data/synapse/
  MEMORY.md        — agent's long-term memory
  USER.md          — user profile
  sessions.db      — conversation history (SQLite)
  vector_store/    — RAG embeddings
  cron_jobs.json   — scheduled jobs
```

To inspect or back up the volume from your host:

```bash
# Open a shell in the volume
docker run --rm -it -v synapse_data:/data alpine sh

# Copy the entire volume to a local directory
docker run --rm -v synapse_data:/data -v $(pwd)/backup:/backup alpine \
    cp -r /data/synapse /backup/
```

---

## GPU support (Stable Diffusion / computer-use)

Uncomment the `deploy.resources` block in `docker-compose.yml` under the `synapse` service and ensure the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) is installed on your host.

---

## Building without cache

```bash
docker compose build --no-cache
```

---

## Environment variables

All variables are loaded from `.env`. See `.env.example` for the full list. Key variables for Docker:

| Variable | Purpose |
|---|---|
| `AGENT_PROVIDER` | `ollama`, `openai`, or `anthropic` |
| `ANTHROPIC_API_KEY` | Required for Anthropic provider |
| `OPENAI_API_KEY` | Required for OpenAI provider |
| `OLLAMA_HOST` | Override Ollama URL (auto-set to `http://ollama:11434` in compose) |
| `TELEGRAM_BOT_TOKEN` | Required for Telegram mode |
| `TELEGRAM_ALLOWED_USER_ID` | Your Telegram numeric user ID |
| `SYNAPSE_HOME` | State directory (auto-set to `/data/synapse` in compose) |
