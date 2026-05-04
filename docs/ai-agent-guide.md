# AI Agent Guide

`codecks-cli` is built so AI agents can manage Codecks with either a lean CLI
workflow or an MCP-connected workflow. The recommended default is CLI first.

## How It Works

All interfaces share the same `CodecksClient` core:

```text
CLI -> commands.py -> CodecksClient -> Codecks API
MCP -> mcp_server/* -> CodecksClient -> Codecks API
```

CLI is smaller in context and easier to compose with shell pipes. MCP adds
snapshot caching, coordination tools, and prompt delivery.

## 3-Minute Setup

1. Install the package:

```bash
py -m pip install codecks-cli
```

2. Run the interactive setup:

```bash
codecks-cli setup
```

3. Verify the connection:

```bash
codecks-cli agent-init --agent
```

## CLI Quick Reference

```bash
codecks-cli agent-init --agent
codecks-cli standup --agent
codecks-cli pm-focus --agent
codecks-cli cards --status started --agent
codecks-cli card <uuid> --agent
codecks-cli update <uuid> --status done --agent
codecks-cli lanes --agent
codecks-cli tags-registry --agent
```

Pipe-friendly patterns:

```bash
codecks-cli cards --status blocked --ids-only | codecks-cli done --stdin --agent
codecks-cli cards --deck Backlog --ids-only | codecks-cli hand --stdin --agent
codecks-cli cards --status started --limit 10 --agent
codecks-cli done @last --agent
```

## CLI vs MCP

### Use CLI When

- you want the lowest token cost
- you can run shell commands directly
- the task is a normal PM workflow
- you want to use pipes, `--stdin`, `--ids-only`, or `@last`

### Use MCP When

- your editor already has the MCP server connected
- you want `session_start()`
- you want `find_and_update()`
- you need snapshot-cached repeated reads
- you need claim/release/delegate coordination
- you want prompts like `pm-session` or `setup-guide`

## MCP Setup

Install the extra:

```bash
py -m pip install "codecks-cli[mcp]"
```

### Claude Code

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

Use the same `command` and `args` values in Cursor's MCP configuration.

### Windsurf

Use the same `command` and `args` values in Windsurf's MCP configuration.

## Security

- Never ask users to paste tokens into chat.
- Prefer `codecks-cli setup` for first-time configuration.
- Keep secrets in `.env`.
- If a token appears in chat, recommend rotating it.

## Customizing

Start from the examples:

- [examples/skills/setup/SKILL.md](../examples/skills/setup/SKILL.md)
- [examples/skills/pm/SKILL.md](../examples/skills/pm/SKILL.md)
- [examples/game-dev-agent.md](../examples/game-dev-agent.md)

Teams often customize:

- project naming conventions
- lane usage rules
- GDD sync workflows
- hand management habits
- when to prefer CLI over MCP

## Troubleshooting

- `[SETUP_NEEDED]`: run `codecks-cli setup`
- `[TOKEN_EXPIRED]`: refresh the browser-session token
- missing deck/project names: verify account and org in `.env`
- CLI works but MCP does not: install the `mcp` extra and confirm editor config

## Next Reads

- [docs/cli-reference.md](cli-reference.md)
- [docs/mcp-reference.md](mcp-reference.md)
- [AGENTS.md](../AGENTS.md)
- [DEVELOPMENT.md](../DEVELOPMENT.md)
