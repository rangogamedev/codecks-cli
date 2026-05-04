# Setup Skill

Use this skill to get `codecks-cli` working for a user without leaking secrets
into chat history. The CLI should work on its own first. MCP is optional.

## Goal

Leave the user with a working `codecks-cli` install and a verified
`codecks-cli agent-init --agent` call.

## Rules

- Never ask the user to paste tokens into chat.
- Prefer `codecks-cli setup` over manual `.env` editing.
- If the user pastes a token into chat, warn them and suggest rotating it.
- Treat MCP as an optional enhancement, not a requirement.

## Phase 1: Detect Current State

Check these in order and skip anything already complete:

1. `codecks-cli --version`
2. Check whether `.env` exists
3. Verify auth with `codecks-cli agent-init --agent`
4. Check whether the user already has MCP configured
5. Check whether they already have a PM skill or prompt file

If `agent-init` succeeds, report that the tool is already set up and move to
orientation.

## Phase 2: Install The Tool

If the CLI is missing:

```bash
py -m pip install codecks-cli
```

If the user also wants MCP:

```bash
py -m pip install "codecks-cli[mcp]"
```

## Phase 3: Configure Tokens

Recommended path:

```bash
codecks-cli setup
```

This keeps token entry inside the terminal instead of the agent conversation.

Manual fallback:

1. Ensure `.env` exists.
2. Tell the user to fill in values locally.
3. Never request the values in chat.

Minimum token guide:

| Token | Purpose |
|---|---|
| `CODECKS_ACCOUNT` | Team/account slug |
| `CODECKS_TOKEN` | Read + write session token |
| `CODECKS_ACCESS_KEY` | Generate report tokens |
| `CODECKS_REPORT_TOKEN` | Stable card creation token |

## Phase 4: Verify

Run:

```bash
codecks-cli agent-init --agent
```

If it works, report:

- account/team context
- total cards
- deck summary

If it fails:

- `[SETUP_NEEDED]` means `.env` is incomplete
- `[TOKEN_EXPIRED]` means the session token needs refresh
- `[ERROR]` means inspect the message and fix the specific configuration issue

## Phase 5: Offer Workflow Options

### Option 1: CLI Only

Tell the user they can use any agent that can run shell commands:

```bash
codecks-cli standup --agent
codecks-cli cards --status started --agent
```

### Option 2: PM Skill

Point them to `examples/skills/pm/SKILL.md` and help them copy or adapt it for
their editor.

### Option 3: MCP Too

If they want richer integrations, add the MCP server config for their editor
after the CLI is already working.

## Phase 6: Orientation

Show them the board:

```bash
codecks-cli standup --agent
codecks-cli overview --agent
```

Then suggest one next step:

- run a daily standup
- start a PM session
- configure MCP if they need caching or coordination
