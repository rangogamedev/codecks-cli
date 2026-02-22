#!/usr/bin/env bash
# Build the codecks-cli Docker image.
# Run once, or again after changing pyproject.toml dependencies.
set -e
cd "$(dirname "$0")/.."
docker build -t codecks-cli .
echo "Build complete. Run ./docker/test.sh to verify."
