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
If `.env` still has `CODECKS_REPORT_TOKEN` / `CODECKS_ACCESS_KEY`, or a
`CODECKS_TOKEN` that does not start with `cdxut_` / `cdxat_`, this is a 0.5.x
install: follow `docs/migration-0.6.md` (new API token, default deck, delete
the two old lines) — do not read or print the token values.
Otherwise start at Phase 3.

## Phase 2: Install

```bash
pip install "git+https://github.com/rangogamedev/codecks-cli.git"   # CLI only, zero runtime deps
# or
pip install "codecks-cli[mcp] @ git+https://github.com/rangogamedev/codecks-cli.git"   # + MCP server
```

## Phase 3: Configure tokens

Offer the user a choice:

**Option A — "Run the setup wizard" (recommended)**

Run `codecks-cli setup` in the terminal. This is the built-in interactive
wizard that collects the API token in the terminal — not through the chat —
and asks once for the default deck (where new cards go). The agent just starts
the command and waits for it to finish.

Before it runs, tell the user to create the token first: Codecks > Your Profile >
API Tokens > create with Read & write (or Read only for reporting-only use) and
copy it immediately — it is shown once. Organization tokens (`cdxat_`, from
Organization Settings > Integrations > API Tokens) also work.

**Option B — "I'll configure .env myself"**

Copy `.env.example` to `.env` if it does not exist, then print this guide:

| Token | What it does | Where to get it | Expires? |
|-------|-------------|-----------------|----------|
| `CODECKS_ACCOUNT` | Team subdomain | The `myteam` part of `myteam.codecks.io` | Never |
| `CODECKS_TOKEN` | Read + write access | Codecks > Your Profile > API Tokens (`cdxut_...`, shown once) | When revoked or at its optional expiry date |
| `CODECKS_DEFAULT_DECK` | Deck for new cards | Run `codecks-cli default-deck <name>` | — |

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

If it fails, read the message — it names the cause (see the Troubleshooting
table in `docs/migration-0.6.md`): unrecognised/revoked token, expired token,
personal tokens disabled by an admin, `CODECKS_ACCOUNT` not matching the
token's organization, a read-only token trying to write (403 names the missing
permission), or no default deck. An old browser-cookie token shows up as
"did not accept your API token" — create an API token.

Then run security checks silently:

```bash
grep -q ".env" .gitignore          # .env is gitignored?
grep -rn "CODECKS_TOKEN" --include="*.py" --include="*.md"  # leaked?
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
pip install "codecks-cli[mcp] @ git+https://github.com/rangogamedev/codecks-cli.git"
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

If the user's MCP config has an `env` block with Codecks keys, it must hold the
same API token as `.env` and no `CODECKS_REPORT_TOKEN` / `CODECKS_ACCESS_KEY`.

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

Note: "MCP adds 53 tools with caching and team coordination, but loads more
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
