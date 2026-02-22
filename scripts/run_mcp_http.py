"""Run the Codecks MCP server in streamable-http mode for LobeChat."""

from codecks_cli.mcp_server import mcp

if __name__ == "__main__":
    mcp.settings.host = "127.0.0.1"
    mcp.settings.port = 8808
    mcp.run(transport="streamable-http")
