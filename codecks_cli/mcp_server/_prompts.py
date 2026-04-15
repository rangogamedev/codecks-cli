"""MCP prompts — discoverable guides for connected agents.

Agents call prompts/list to see these, then prompts/get to load the full
content.  The pm-session prompt reads pm_playbook.md at call time so it
always reflects the latest version.
"""

from pathlib import Path


def _load_playbook() -> str:
    """Read pm_playbook.md from the package directory."""
    playbook = Path(__file__).resolve().parent.parent / "pm_playbook.md"
    if playbook.is_file():
        return playbook.read_text(encoding="utf-8")
    return "PM playbook not found. Run `codecks-cli agent-init --agent` to get started."


SETUP_GUIDE = """\
# codecks-cli Quick Setup

1. Install: `pip install codecks-cli`
2. Configure tokens: `codecks-cli setup` (interactive wizard in your terminal)
3. Verify: `codecks-cli agent-init --agent`

That's it. Use `codecks-cli <command> --agent` for any PM operation.

## Optional: MCP server

`pip install codecks-cli[mcp]` adds 52 MCP tools with caching and team
coordination. Add to your editor's MCP config:

```json
{"mcpServers": {"codecks": {"command": "codecks-mcp", "args": []}}}
```

## Token guide

| Token | Where to get it |
|-------|-----------------|
| CODECKS_ACCOUNT | Your team subdomain (myteam.codecks.io) |
| CODECKS_TOKEN | Browser DevTools > Cookies > `at` value |
| CODECKS_ACCESS_KEY | Codecks > Settings > Integrations |
| CODECKS_REPORT_TOKEN | `codecks-cli generate-token` |

Tokens go in `.env` (gitignored). Never paste tokens in chat.
"""


def register(mcp):
    """Register MCP prompts on the FastMCP instance."""

    @mcp.prompt("pm-session")
    def pm_session_prompt() -> str:
        """Full PM session guide — CLI-first session flow, execution patterns,
        error recovery, batch ops, and safety rules. Load this at the start of
        any PM session for best results."""
        return _load_playbook()

    @mcp.prompt("setup-guide")
    def setup_guide_prompt() -> str:
        """Quick setup guide — install, configure tokens, verify connection.
        Use when a user asks how to set up codecks-cli or connects for the
        first time."""
        return SETUP_GUIDE
