# codecks-cli Docker development environment
# Build:  docker compose build
# Run:    docker compose run --rm test

ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim AS builder

WORKDIR /build

# Install build deps into a venv so we can copy it cleanly
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# All third-party deps (dev + MCP) in one layer
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install \
    "mypy>=1.11" \
    "pytest>=8.3" \
    "pytest-cov>=5.0" \
    "ruff>=0.6" \
    "mcp[cli]>=1.6.0"

# --- Runtime stage ---
ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim

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

# Node.js + Claude Code for in-container AI dev
RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs npm && rm -rf /var/lib/apt/lists/*
RUN npm install -g @anthropic-ai/claude-code

# Switch to non-root user
USER codecks

# Default command: show help
CMD ["python", "codecks_api.py"]
