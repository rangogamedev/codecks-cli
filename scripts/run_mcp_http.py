"""Run the Codecks MCP server in streamable-http mode."""

import os

from codecks_cli.mcp_server import mcp

if __name__ == "__main__":
    mcp.settings.host = os.environ.get("MCP_HTTP_HOST", "0.0.0.0")
    mcp.settings.port = int(os.environ.get("MCP_HTTP_PORT", "8808"))
    mcp.run(transport="streamable-http")
