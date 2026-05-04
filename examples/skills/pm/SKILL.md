---
name: pm
description: CLI-first PM session for Codecks — standups, card management, feature scaffolding, sprint health.
---

# PM Session (CLI-First)

Run Codecks PM operations using `codecks-cli` via Bash for the smallest token
footprint. Falls back to MCP tools only for team coordination or batch creates.

## Session Bootstrap

```bash
codecks-cli agent-init --agent
```

If this fails with `[SETUP_NEEDED]` or `[TOKEN_EXPIRED]`, ask the user to run
`codecks-cli setup` or refresh their browser token.

## Common Workflows

**Daily standup:**
```bash
codecks-cli standup --agent
```

**Sprint health check:**
```bash
codecks-cli pm-focus --agent
```

**Aggregate overview (cheapest health check):**
```bash
codecks-cli overview --agent
```

**Find and update cards:**
```bash
codecks-cli cards --status blocked --sort priority --agent
codecks-cli update <uuid> --status in_review --agent
```

**Batch close via pipes:**
```bash
codecks-cli cards --deck Code --status started --ids-only | codecks-cli done --stdin --agent
```

**Chain with @last:**
```bash
codecks-cli cards --deck Backlog --limit 10 --agent
codecks-cli done @last --agent
```

**Scaffold a feature:**
```bash
codecks-cli feature "Feature Name" \
  --hero-deck Features --code-deck Code --design-deck Design \
  --priority b --agent
```

**Hand management:**
```bash
codecks-cli hand --agent                   # current hand
codecks-cli hand <uuid1> <uuid2> --agent   # add cards
codecks-cli unhand <uuid> --agent          # remove card
```

## Error Recovery

| Prefix | Action |
|--------|--------|
| `[SETUP_NEEDED]` | Ask user to run `codecks-cli setup` |
| `[TOKEN_EXPIRED]` | Ask user to refresh browser token |
| `[ERROR]` | Fix arguments, retry once |
| HTTP 429 | Wait 5s, retry once |

Re-read cards before retrying any mutation. For doc cards, never set status,
priority, or effort.

## Safety Rules

- Full 36-char UUIDs for all mutations.
- Never set `dueAt`.
- `--dry-run` to preview mutations.
- Never close a Hero before its sub-cards are done.
- Re-read after mutations; never mutate from stale data.

## When to Use MCP Instead

If MCP tools are available, prefer them for:
- Team coordination (claim/release/delegate)
- Batch creates (up to 20 cards per call)
- Repeated reads with cache (<50ms)
- `find_and_update()` (search + update in one call)

Otherwise, the CLI handles everything a PM session needs.
