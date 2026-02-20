# PM Agent Workflow

A self-updating playbook for AI agents managing Codecks cards. The agent should treat this as a living document — discovering capabilities, composing workflows from primitives, and proposing updates when it finds better patterns.

## How to Use This File

1. **Read on session start** — establishes what the CLI can do right now.
2. **Discover at runtime** — run `py codecks_api.py --help` and subcommand `--help` to find flags not listed here.
3. **Compose workflows** — combine primitives (filters, commands, output formats) to solve novel PM requests.
4. **Propose updates** — if you discover a better pattern or a new flag, suggest appending it to the Learned Patterns section below.

The canonical command/flag reference lives in `CLAUDE.md` and `.claude/commands/api-ref.md`. This file focuses on *how to think* about PM work, not just what commands exist.

---

## Agent Mental Model

### Primitives, Not Recipes

Every PM task decomposes into these primitives:

| Primitive | What it does | Example |
|-----------|-------------|---------|
| **Filter** | Narrow card set | `--status started,blocked --project "Tea Shop"` |
| **Inspect** | Get detail on one card | `card <id> --format json` |
| **Mutate** | Change card state | `update <id> --status done --priority a` |
| **Report** | Summarize for a human | `standup --format table`, `cards --stats` |
| **Verify** | Confirm mutation landed | Re-read the card/list after mutation |

The agent should think: "What set of cards? What action? How to verify?" — not memorize scripts.

### Progressive Disclosure

Start broad, narrow as needed:

```
standup                          # what's the state of the world?
  -> cards --status blocked      # drill into blockers
    -> card <id>                 # what's actually wrong?
      -> update <id> --status started   # unblock it
        -> card <id>             # verify the change
```

### Composability

Filters stack. Every flag on `cards` can combine with every other:

```bash
# These are all valid compositions:
cards --status started --owner none --sort priority
cards --priority a,b --stale 7 --project "Tea Shop"
cards --status started,in_review --updated-before 2026-01-01
cards --deck "Backlog" --sort effort --stats
```

The agent should try novel combinations when the user's request doesn't match a known recipe.

---

## Session Lifecycle

### 1. Bootstrap (every session)

```bash
py codecks_api.py account --format json        # health check + context
py codecks_api.py standup --format json         # quick state snapshot
```

If token fails: stop and ask user to run `setup` or refresh token.

The standup gives four buckets: recently done, in-progress, blocked, hand. Use this to ground the conversation — don't re-scan cards the standup already surfaced.

### 2. Triage (when user asks "what needs attention?")

Escalation ladder — run in order, stop when you have enough to act on:

```bash
py codecks_api.py pm-focus --format table                    # full sprint health
py codecks_api.py cards --status blocked --format table      # stuck cards
py codecks_api.py cards --status started --stale 14          # forgotten work
py codecks_api.py cards --owner none --status not_started    # unassigned backlog
```

### 3. Deep Dive (when user asks about a specific area)

```bash
py codecks_api.py cards --project "X" --status started,blocked --sort priority --format table
py codecks_api.py cards --milestone "MVP" --stats --format table
py codecks_api.py cards --owner "Thomas" --format table
py codecks_api.py cards --hero <hero_id> --format table      # sub-cards of a feature
```

### 4. Act (mutations)

Always: fetch -> confirm target -> mutate -> verify.

```bash
py codecks_api.py update <uuid> --status started --format json
py codecks_api.py card <uuid> --format json                  # verify
```

### 5. Report (end of session)

Present to user in table format. Always state:
- What changed (card IDs + new values)
- What was verified (commands used)
- What's still blocked (needs user input)

---

## Feature Decomposition (No Journey)

The project uses manual Hero/sub-card decomposition, not Codecks Journeys.

### Fast Path

```bash
py codecks_api.py feature "<Title>" \
  --hero-deck "<Hero Deck>" \
  --code-deck "<Code Deck>" \
  --design-deck "<Design Deck>" \
  --art-deck "<Art Deck>" \
  --priority a --effort 5
```

Use `--skip-art` when visuals are not impacted. Transaction-safe: if creation fails mid-flow, created cards are archived automatically.

### Lane Contract

Every feature must evaluate these lanes:
- **Code** — implementation tasks (always required)
- **Design** — feel, balance, economy, player-facing tuning (always required)
- **Art** — visual/content assets (only when visuals are impacted)

If a lane is skipped, state why in the summary.

### Manual Path (when `feature` command doesn't fit)

1. Create Hero card with `create`
2. Create sub-cards with `create`
3. Link with `update <sub_id> --hero <hero_id> --deck "<Lane Deck>"`
4. Verify with `cards --hero <hero_id> --format table`

---

## Capability Discovery

The agent should not assume this file is complete. When encountering an unfamiliar request:

### Step 1: Check Help

```bash
py codecks_api.py cards --help      # what flags does cards accept?
py codecks_api.py standup --help    # what flags does standup accept?
py codecks_api.py --help            # what commands exist?
```

### Step 2: Check Reference Docs

Read these files for the full picture:
- `CLAUDE.md` — architecture, validation rules, API pitfalls
- `.claude/commands/api-ref.md` — complete flag/command tables
- `.claude/commands/pm.md` — agent-optimized PM session playbook

### Step 3: Experiment Safely

For read-only discovery, any `cards` command with new flag combinations is safe to try. The worst case is an `[ERROR]` with valid options listed.

### Step 4: Propose a Pattern Update

If the agent discovers a useful workflow not documented here, it should tell the user:

> "I found that `cards --priority null --status not_started` is useful for finding deprioritized backlog. Want me to add this to PM_AGENT_WORKFLOW.md?"

---

## Learned Patterns

This section is designed to grow. When the agent or user discovers a useful pattern, add it here with a short label and the command.

| Pattern | Command | When to Use |
|---------|---------|-------------|
| Daily standup | `standup --format table` | Start of every PM session |
| Sprint health | `pm-focus --format table` | Weekly review, sprint planning |
| Stale sweep | `cards --status started --stale 14` | Find forgotten work |
| Stale review items | `cards --status in_review --stale 7` | Find stuck reviews |
| Unassigned work | `cards --owner none --status not_started` | Sprint planning |
| Priority triage | `cards --status started,blocked --sort priority` | Daily triage |
| High-pri focus | `cards --priority a,b --status started` | What matters most right now |
| Workload check | `cards --stats --format table` | Owner/deck/status breakdown |
| Recent completions | `standup --days 7 --format table` | Weekly review |
| Milestone progress | `cards --milestone "MVP" --stats` | Milestone review meeting |
| Deck health | `decks --format table` | See card counts per deck |
| Feature check | `cards --hero <id> --format table` | Verify sub-card coverage |
| Date range audit | `cards --updated-after 2026-01-01 --updated-before 2026-02-01` | Audit period activity |
| No-priority backlog | `cards --priority null --status not_started` | Grooming session |

---

## Safety Rules (Non-Negotiable)

- Always use full UUIDs for mutations (not short 8-char IDs).
- Never mutate from a stale card list — re-fetch first.
- For doc cards: do not set `--status`, `--priority`, or `--effort` (API returns 400).
- `--content` replaces the full content field. Keep title as the first line.
- Bulk updates: batches of ~10, verify between batches.
- Never close a Hero before checking sub-card coverage across Code/Art/Design.
- After every mutation, verify with a re-read.

---

## Version Awareness

This file was last updated for codecks-cli **0.4.0** (280 tests).

If the CLI version has changed since then, the agent should:
1. Run `py codecks_api.py --version` to check.
2. Scan `CHANGELOG.md` for new commands/flags.
3. Update the Learned Patterns table with any new capabilities.
4. Tell the user what's new.
