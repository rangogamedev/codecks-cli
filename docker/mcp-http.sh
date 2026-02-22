#!/usr/bin/env bash
# Start the MCP server (HTTP) inside Docker.
# Override port: MCP_HTTP_PORT=9000 ./docker/mcp-http.sh
# Press Ctrl+C to stop.
set -e
cd "$(dirname "$0")/.."
docker compose up --force-recreate mcp-http "$@"
