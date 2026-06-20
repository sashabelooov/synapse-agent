# ── Stage 1: builder ────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency manifests first for layer caching
COPY pyproject.toml uv.lock ./

# Install production deps into an isolated prefix
RUN uv sync --frozen --no-dev --no-install-project

# ── Stage 2: runtime ────────────────────────────────────────────────────────
FROM python:3.12-slim

# System packages: Tesseract (OCR) + Node.js (for npx-based MCP servers) +
# xvfb / xdotool for headless computer-use on Linux
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        curl \
        ca-certificates \
        xvfb \
        xdotool \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install uv in runtime image (used for npx / uvx MCP servers at runtime)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Non-root user
RUN groupadd -r synapse && useradd -r -g synapse -m -d /home/synapse synapse

WORKDIR /app

# Copy installed virtualenv from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application source
COPY --chown=synapse:synapse . .

# Make the venv the active Python
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Synapse home inside a volume-mounted path
    SYNAPSE_HOME=/data/synapse

# Playwright chromium for browser automation (optional — skip if not needed)
# RUN playwright install chromium --with-deps

USER synapse

# /data is the volume mount point for persistent state
VOLUME ["/data/synapse"]

# Default: CLI mode. Override with --mode telegram or --mode tui.
ENTRYPOINT ["python3", "main.py"]
CMD ["--mode", "cli"]
