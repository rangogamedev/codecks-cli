# codecks-cli Docker development environment
# Build:  docker build -t codecks-cli .
# Run:    docker run --rm -v .:/app --env-file .env codecks-cli pytest tests/ -v

FROM python:3.12-slim AS builder

WORKDIR /build

# Install build deps into a venv so we can copy it cleanly
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install third-party dev and MCP deps directly (no project source needed)
RUN pip install --no-cache-dir \
    "mypy>=1.11" \
    "pytest>=8.3" \
    "pytest-cov>=5.0" \
    "ruff>=0.6" \
    "mcp[cli]>=1.6.0"

# --- Runtime stage ---
FROM python:3.12-slim

# Non-root user for safety
RUN groupadd -r codecks && useradd -r -g codecks -m codecks

# Copy venv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Copy project source
COPY . .

# Install in editable mode so entry points work with live code
RUN pip install --no-cache-dir -e ".[dev,mcp]"

# Switch to non-root user
USER codecks

# Default command: show help
CMD ["python", "codecks_api.py"]
