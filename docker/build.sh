#!/usr/bin/env bash
# Build the codecks-cli Docker image via Compose.
# Run once, or again after changing Dockerfile or pyproject.toml dependencies.
set -e
cd "$(dirname "$0")/.."

docker compose build
echo "Build complete. Run ./docker/test.sh to verify."
