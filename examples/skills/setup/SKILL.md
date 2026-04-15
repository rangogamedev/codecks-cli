---
name: codecks-setup
description: Interactive setup wizard for codecks-cli — installs the tool, configures tokens securely, optionally sets up MCP and the PM agent skill.
---

# codecks-cli Setup Wizard

## Phase 1: Detect current state

Before asking anything, check what is already set up:

```bash
codecks-cli --version 2>/dev/null          # installed?
ls .env 2>/dev/null                        # env file exists?
codecks-cli agent-init --agent 2>/dev/null # tokens work?
```

If `agent-init` succeeds, skip to Phase 5 (choose agent experience).
If the tool is not installed, start at Phase 2.
Otherwise start at Phase 3.

## Phase 2: Install

```bash
pip install codecks-cli        # CLI only, zero runtime deps
# or
pip install codecks-cli[mcp]   # CLI + MCP server (optional)
```

## Phase 3: Configure tokens

Offer the user a choice:

**Option A — "Run the setup wizard" (recommended)**

Run `codecks-cli setup` in the terminal. This is the built-in interactive
wizard that collects tokens in the terminal — not through the chat. The agent
just starts the command and waits for it to finish.

**Option B — "I'll configure .env myself"**

Copy `.env.example` to `.env` if it does not exist, then print this guide:

| Token | What it does | Where to get it | Expires? |
|-------|-------------|-----------------|----------|
| `CODECKS_ACCOUNT` | Team subdomain | The `myteam` part of `myteam.codecks.io` | Never |
| `CODECKS_TOKEN` | Read + write access | Browser DevTools (F12) > Application > Cookies > `at` value | With browser session |
| `CODECKS_ACCESS_KEY` | Generate report tokens | Codecks > Settings > Integrations > User Reporting | Never |
| `CODECKS_REPORT_TOKEN` | Create cards | Run `codecks-cli generate-token` after setting access key | Never (until disabled) |

Tell the user: "Open `.env` in your editor, fill in the values, and let me
know when you're done."

### Security rules

- **NEVER** ask the user to paste tokens in the chat.
- **NEVER** use AskUserQuestion for token or key input.
- If the user accidentally pastes a token in chat, warn them to rotate it.
- Prefer `codecks-cli setup` (terminal wizard) over manual `.env` editing.

## Phase 4: Verify and secure

```bash
codecks-cli agent-init --agent   # test connection
```

If it fails, diagnose: token expired? account name wrong? missing .env?

Then run security checks silently:

```bash
grep -q ".env" .gitignore          # .env is gitignored?
grep -rn "CODECKS_TOKEN\|CODECKS_ACCESS_KEY" --include="*.py" --include="*.md"  # leaked?
```

Warn immediately if any check fails.

## Phase 5: Choose your agent experience

The tool now works. Ask the user what they want:

**Option 1 — "I'll use my own agent"**

Done. The CLI is ready. Any agent can run `codecks-cli <command> --agent` via
Bash. Point them to `AGENTS.md` for API pitfalls and `docs/ai-agent-guide.md`
for the full reference.

**Option 2 — "Give me the PM agent"**

Copy `examples/skills/pm/SKILL.md` to `.claude/commands/pm.md`:

```bash
mkdir -p .claude/commands
cp examples/skills/pm/SKILL.md .claude/commands/pm.md
```

"You now have `/pm` — a ready-to-use PM session skill."

For Cursor users, print the key sections for pasting into `.cursorrules`.
For Windsurf users, same for `.windsurfrules`.

**Option 3 — "Set up MCP too"**

Install the MCP extra if not already present:

```bash
pip install codecks-cli[mcp]
```

Then write the MCP config for their editor:

Claude Code (`.claude/settings.json` or project `.mcp.json`):
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

Cursor (`.cursor/mcp.json`):
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

Note: "MCP adds 52 tools with caching and team coordination, but loads more
context tokens. CLI is leaner. Use both — CLI for routine ops, MCP for
advanced features."

## Phase 6: Orientation

Show the user their board:

```bash
codecks-cli standup --agent
codecks-cli overview --agent
```

Suggest next steps based on their choice:
- Option 1: "Try asking your agent to run `codecks-cli standup`."
- Option 2: "Try `/pm` to start a PM session."
- Option 3: "Try asking your agent to call `session_start()`."
