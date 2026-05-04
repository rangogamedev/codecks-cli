# Examples

Starter files for using codecks-cli with AI agents.

## What's here

| File | Purpose |
|------|---------|
| [skills/setup/SKILL.md](skills/setup/SKILL.md) | Interactive setup wizard — install, configure tokens, choose your agent experience |
| [skills/pm/SKILL.md](skills/pm/SKILL.md) | CLI-first PM session skill — standups, card management, feature scaffolding |
| [game-dev-agent.md](game-dev-agent.md) | Real-world example of extending the base workflow for game development |

## Quick start

### Just the tool (any agent)

```bash
pip install codecks-cli
codecks-cli setup               # interactive token wizard
codecks-cli agent-init --agent  # verify connection
```

Any AI agent can now use `codecks-cli <command> --agent` via Bash. No special
prompt needed — the CLI outputs stable JSON with `--agent` mode.

### Plug-and-play PM agent (Claude Code)

```bash
mkdir -p .claude/commands
cp examples/skills/pm/SKILL.md .claude/commands/pm.md
```

Now type `/pm` in Claude Code to start a PM session.

### Full setup with MCP

```bash
pip install codecks-cli[mcp]
```

Add to your editor's MCP config:

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

## Customizing

The base PM skill covers universal patterns. For project-specific additions,
see [game-dev-agent.md](game-dev-agent.md) as an example of how to extend
with custom lanes, sub-card templates, and sync workflows.

Read the full guide at [docs/ai-agent-guide.md](../docs/ai-agent-guide.md).
