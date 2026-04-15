# AI Agent Guide

How to use codecks-cli with AI agents — CLI-first for token efficiency, MCP as
an optional enhancement.

## How It Works

```
Agent (Claude, Cursor, Windsurf, etc.)
  │
  ├── CLI: codecks-cli <command> --agent     (Bash, lean JSON, no deps)
  │
  └── MCP: codecks-mcp (52 tools)           (optional, adds caching + teams)
        │
        └── CodecksClient (33 methods)
              │
              └── Codecks HTTP API
```

Both the CLI and MCP server wrap the same `CodecksClient` library. The CLI
outputs compact JSON in `--agent` mode. The MCP server adds snapshot caching,
guardrails, and team coordination on top.

## Why CLI-First?

MCP loads 52 tool schemas into agent context (~5,200 tokens) before any work
happens. The CLI: an agent knows `codecks-cli <command> --agent` plus a
command reference table — about 200 tokens of tool knowledge. That is a 25x
difference in baseline context cost.

Use MCP when you need cache-heavy reads, team coordination, batch creates, or
`find_and_update()`.

## 3-Minute Setup

```bash
pip install codecks-cli          # CLI only, zero runtime deps
codecks-cli setup                # interactive token wizard (runs in terminal)
codecks-cli agent-init --agent   # verify: returns account + project context
```

That's it. Your agent can now use `codecks-cli <command> --agent` via Bash.

## CLI Quick Reference

| Command | Purpose |
|---------|---------|
| `agent-init` | One-call bootstrap: account + overview + decks + tags + lanes |
| `standup` | Done, in-progress, blocked, hand snapshot |
| `pm-focus` | Sprint health: blocked, stale, unassigned, suggested next |
| `overview` | Aggregate counts only (~500 bytes) |
| `cards --status X` | List cards with filters |
| `card <uuid>` | Single card detail |
| `create "Title" --deck X` | Create a card |
| `update <uuid> --status X` | Update card properties |
| `done <uuid>` | Mark done |
| `start <uuid>` | Mark started |
| `feature "Title" --hero-deck X --code-deck Y` | Scaffold Hero + sub-cards |
| `hand` / `unhand` | Manage personal work queue |
| `lanes` | Lane registry (no token needed) |
| `tags-registry` | Tag registry (no token needed) |
| `commands --format json` | Agent self-discovery: all commands + args |

All commands accept `--agent` for JSON output and `--dry-run` for previewing
mutations.

### Pipe Workflows

```bash
codecks-cli cards --status blocked --ids-only | codecks-cli done --stdin --agent
codecks-cli cards --deck Backlog --limit 10 --agent && codecks-cli done @last --agent
```

## Token Architecture

| Token | Purpose | Where to get it | Expires? |
|-------|---------|-----------------|----------|
| `CODECKS_TOKEN` | Read + write | Browser DevTools > Cookies > `at` value | With browser session |
| `CODECKS_REPORT_TOKEN` | Create cards | `codecks-cli generate-token` | Never (until disabled) |
| `CODECKS_ACCESS_KEY` | Generate report tokens | Codecks > Settings > Integrations | Never |

Tokens go in `.env` (gitignored). Never paste tokens in agent chat — use
`codecks-cli setup` or edit `.env` directly.

## MCP Setup (Optional)

```bash
pip install codecks-cli[mcp]
```

### Claude Code

Add to `.claude/settings.json` or project `.mcp.json`:

```json
{
  "mcpServers": {
    "codecks": {
      "command": "codecks-mcp",
      "args": []
    }
  }
}
```

### Cursor

Add to `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "codecks": {
      "command": "codecks-mcp",
      "args": []
    }
  }
}
```

### Windsurf

Add to your Windsurf MCP configuration with the same JSON structure.

### MCP Prompts

The MCP server exposes two prompts that agents can discover via `prompts/list`:

- `pm-session` — the full CLI-first PM playbook
- `setup-guide` — compact setup and orientation guide

## Customizing Your Agent

The base workflow covers any project. To add domain-specific patterns:

1. Start with the PM skill: `examples/skills/pm/SKILL.md`
2. Add project-specific lanes, templates, or sync workflows
3. See `examples/game-dev-agent.md` for a real-world game-dev example

## CLI vs MCP Decision Guide

| Scenario | Use CLI | Use MCP |
|----------|---------|---------|
| Daily standup | `standup --agent` | `session_start()` + `standup()` |
| Batch close 10 cards | `--ids-only \| done --stdin` | `find_and_update()` |
| Create 15 cards | CLI one at a time | `batch_create_cards` |
| Team coordination | `claim`/`release` | `claim_card`/`delegate_card`/`team_dashboard` |
| Repeated reads | Fresh API each call | Cache hit <50ms |
| Token budget | ~200 tokens baseline | ~5,200 tokens baseline |

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `[SETUP_NEEDED]` | Run `codecks-cli setup` |
| `[TOKEN_EXPIRED]` | Refresh `CODECKS_TOKEN` from browser cookies |
| MCP server not found | Run `pip install codecks-cli[mcp]` then `codecks-mcp` |
| `invalid choice` for a command | Ensure you installed the latest version |
| 429 rate limit | Wait 5s, retry. CLI auto-retries reads. |
| Card mutation returns error | Re-read the card first; the UUID may be stale |
