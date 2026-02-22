#!/usr/bin/env bash
# One-command Docker dev setup: build if needed, then open interactive shell.
# Usage: ./docker/dev.sh [--build]
set -e
cd "$(dirname "$0")/.."

if [ "$1" = "--build" ] || ! docker image inspect codecks-cli >/dev/null 2>&1; then
  echo "Building codecks-cli image..."
  docker compose build
fi

echo "Starting interactive shell (source is volume-mounted, edits reflect instantly)..."
docker compose run --rm shell
