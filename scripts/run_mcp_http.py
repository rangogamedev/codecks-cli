"""Run the Codecks MCP server in streamable-http mode."""

import os

from codecks_cli.mcp_server import mcp

if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host=os.environ.get("MCP_HTTP_HOST", "0.0.0.0"),
        port=int(os.environ.get("MCP_HTTP_PORT", "8808")),
    )
