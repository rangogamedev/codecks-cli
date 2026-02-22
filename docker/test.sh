#!/usr/bin/env bash
# Run pytest inside Docker.
set -e
cd "$(dirname "$0")/.."
docker compose run --rm test "$@"
