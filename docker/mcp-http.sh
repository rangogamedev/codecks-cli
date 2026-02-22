#!/usr/bin/env bash
# Start the MCP server (HTTP on port 8808) inside Docker.
# Press Ctrl+C to stop.
set -e
cd "$(dirname "$0")/.."
docker compose up mcp-http "$@"
