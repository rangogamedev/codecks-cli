#!/usr/bin/env bash
# Start the MCP server (stdio transport) inside Docker.
set -e
cd "$(dirname "$0")/.."
docker compose run --rm mcp "$@"
