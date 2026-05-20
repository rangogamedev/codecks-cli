# codecks-cli Docker development environment
# Build:  docker compose build
# Run:    docker compose run --rm test

# Base image digest-pinned for supply-chain integrity.
# Dependabot updates the tag + digest together when a new python:3.12-slim ships.
FROM python:3.14-slim@sha256:a7185a8e40af01bf891414a4df16ef10fc6000cee460a404a13da9029fe41604 AS builder

WORKDIR /build

# Install build deps into a venv so we can copy it cleanly
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# All third-party deps (dev + MCP) in one layer
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install \
    "mypy>=1.11" \
    "pytest>=9.0.3" \
    "pytest-cov>=7.1.0" \
    "ruff>=0.15.13" \
    "mcp[cli]>=1.27.1"

# --- Runtime stage ---
FROM python:3.14-slim@sha256:a7185a8e40af01bf891414a4df16ef10fc6000cee460a404a13da9029fe41604 AS runtime

# Non-root user for safety
RUN groupadd -r codecks && useradd -r -g codecks -m codecks

# Copy venv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Copy project source
COPY . .

# Entry points only — deps already in venv from builder
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-deps -e .

# Switch to non-root user
USER codecks

# Default command: show help
CMD ["python", "codecks_api.py"]

# --- Optional agent shell stage ---
FROM runtime AS agent

USER root

# Node.js 22 LTS + Claude Code for in-container AI dev.
# NodeSource setup script is downloaded to a file (not piped) so a partial
# transfer or interception cannot inject commands. The script itself is not
# integrity-checked (NodeSource does not publish per-release hashes); the
# `agent` stage is dev-only (profiles: ["dev"]) and never used in CI/runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl && \
    curl -fsSL -o /tmp/nodesource_setup.sh https://deb.nodesource.com/setup_22.x && \
    bash /tmp/nodesource_setup.sh && \
    rm /tmp/nodesource_setup.sh && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*
RUN npm install -g @anthropic-ai/claude-code

# Switch to non-root user
USER codecks
