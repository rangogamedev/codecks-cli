#!/usr/bin/env bash
# Run any codecks-cli command inside Docker.
# Usage: ./docker/cli.sh cards --format table
#        ./docker/cli.sh --version
set -e
cd "$(dirname "$0")/.."
docker compose run --rm cli "$@"
