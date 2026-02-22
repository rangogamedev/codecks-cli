#!/usr/bin/env bash
# Open an interactive bash shell inside the Docker container.
set -e
cd "$(dirname "$0")/.."
docker compose run --rm shell "$@"
