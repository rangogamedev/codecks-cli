#!/usr/bin/env bash
# Run full quality gate (ruff + mypy + pytest) inside Docker.
set -e
cd "$(dirname "$0")/.."
docker compose run --rm quality "$@"
