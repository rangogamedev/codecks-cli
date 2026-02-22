#!/usr/bin/env bash
# Run Claude Code inside the Docker dev container.
# Usage: ./docker/claude.sh [claude-args...]
set -e
cd "$(dirname "$0")/.."
docker compose run --rm \
  -e ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY}" \
  shell claude "$@"
