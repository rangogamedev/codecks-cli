#!/usr/bin/env bash
# Tail logs from the MCP HTTP server.
# Usage: ./docker/logs.sh [-f]
set -e
cd "$(dirname "$0")/.."
docker compose logs mcp-http "$@"
