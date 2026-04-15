# PM Session Playbook (CLI-First)

Agent-agnostic guide for running PM sessions on Codecks with `codecks-cli`.
Use the CLI first for the leanest token footprint. Use MCP as an enhancement
when you need cache-heavy reads, prompt delivery, or team coordination.

## Session Start

Start every session with one composite call:

```bash
codecks-cli agent-init --agent
```

This returns account info, aggregate overview, deck list, tag registry, and
lane registry in a single JSON response (~2 KB).

If the command fails with `[SETUP_NEEDED]` or `[TOKEN_EXPIRED]`, stop and ask
the user to run `codecks-cli setup` or refresh their token.

## Core Execution Loop

For every PM request:

1. **Scope** — filter to the target card set with the smallest useful filter.
2. **Read** — use a compact command first (`cards`, `standup`, `pm-focus`, `overview`).
3. **Mutate** — apply changes only after you have full 36-char UUIDs.
4. **Verify** — re-read affected cards to confirm the expected state.
5. **Report** — summarize what changed, what was verified, and what is blocked.

Never skip verification after mutations.

## Core Commands

```bash
codecks-cli agent-init --agent            # one-call session bootstrap
codecks-cli standup --agent               # done, in-progress, blocked, hand
codecks-cli pm-focus --agent              # sprint health dashboard
codecks-cli overview --agent              # aggregate counts only (~500 B)
codecks-cli cards --status started --agent
codecks-cli card <uuid> --agent
codecks-cli lanes --agent                 # lane registry (no token needed)
codecks-cli tags-registry --agent         # tag registry (no token needed)
```

## Batch Ops Via Pipes

Pipe `--ids-only` output into `--stdin` for batch status changes at ~40 bytes
per card instead of ~2 KB from a full card response.

```bash
codecks-cli cards --status blocked --ids-only | codecks-cli done --stdin --agent
codecks-cli cards --deck Backlog --priority a --ids-only | codecks-cli start --stdin --agent
codecks-cli cards --deck Code --status started --ids-only | codecks-cli update --stdin --status in_review --agent
codecks-cli cards --owner none --priority a --ids-only | codecks-cli hand --stdin --agent
```

## @last Workflow Chains

`@last` reuses the UUIDs from the previous listing command.

```bash
codecks-cli cards --deck Backlog --limit 10 --agent
codecks-cli done @last --agent

codecks-cli cards --status started --owner Alice --agent
codecks-cli hand @last --agent
```

## Feature Decomposition

Every feature starts as one Hero card. Evaluate these lanes:

- **Code** — implementation work
- **Design** — feel, balance, and player-facing tuning
- **Art** — visuals, UI, or assets (add only when genuinely needed)
- **Audio** — sound, music, or feedback (add only when genuinely needed)

```bash
codecks-cli feature "Inventory 2.0" \
  --hero-deck Features \
  --code-deck Code \
  --design-deck Design \
  --art-deck Art \
  --audio-deck Audio \
  --priority b \
  --agent
```

Minimum: Hero + Code + Design. State why a lane was skipped.

## Hand Management

The hand is the user's personal work queue.

```bash
codecks-cli hand --agent                              # see current hand
codecks-cli cards --status not_started --sort priority --agent  # find candidates
codecks-cli hand <uuid1> <uuid2> --agent              # add cards
codecks-cli unhand <uuid1> --agent                    # remove completed
```

## Error Recovery

| Error prefix | Meaning | Action |
|-------------|---------|--------|
| `[SETUP_NEEDED]` | `.env` is missing or incomplete | Ask user to run `codecks-cli setup` |
| `[TOKEN_EXPIRED]` | Browser session cookie is stale | Ask user to refresh token |
| `[ERROR]` | Validation or API failure | Fix arguments, retry once |
| HTTP 429 | Rate limited (40 req/5s) | Wait 5s, retry once |
| Timeout | Network issue | Retry once, then report |

For doc cards, never retry with status, priority, or effort updates. Re-read the card before retrying any mutation.

## Token Efficiency

CLI is 25x leaner in baseline context than MCP (no tool schema overhead):

| Technique | Bytes |
|-----------|-------|
| `--ids-only` pipe | ~40/card |
| `overview` aggregate | ~500 total |
| `card --no-content --no-conversations` | ~200/card |
| `standup` summary | ~2-10 KB |
| Full card with content | ~2-5 KB |

Good defaults:

```bash
codecks-cli overview --agent                                  # cheapest health check
codecks-cli standup --agent                                   # daily snapshot
codecks-cli cards --status started --limit 20 --agent         # bounded list
codecks-cli card <uuid> --no-content --no-conversations --agent  # metadata only
```

## Safety Rules

- Use full 36-character UUIDs for all mutations.
- Never set `dueAt` (paid-only feature).
- Doc cards: no status, priority, or effort changes.
- `content` in `update` replaces the card body (title is auto-preserved).
- Never close a Hero before checking all sub-cards are done.
- Re-read cards after mutation workflows; never mutate from stale data.
- Use `--dry-run` on any mutation to preview without executing.

## When MCP Is Better

Use MCP when you need:

- `session_start()` for one-call cached startup in an MCP-native environment
- `find_and_update()` for search-then-update without manual UUID handling
- Repeated dashboard reads where the snapshot cache matters (<50ms)
- Team coordination: `claim_card`, `release_card`, `delegate_card`, `team_dashboard`
- Batch creates (`batch_create_cards` — up to 20 per call, idempotent)
- Prompt delivery via the MCP prompt surface

Rule of thumb: CLI for everyday work and token efficiency. MCP for coordination, caching, and richer agent integrations.

## Workflow Learning

Observe the user's patterns during sessions and call
`codecks-cli feedback "pattern description" --category improvement` to log them.
Patterns to watch: card selection style, work ordering, hand usage, triage
preferences, communication detail level.

## Recommended Workflows

| Intent | Command |
|--------|---------|
| Daily standup | `standup --agent` |
| Sprint health | `pm-focus --agent` |
| Triage blocked | `cards --status blocked --sort priority --agent` |
| Stale sweep | `cards --status started --stale 14 --agent` |
| Unassigned work | `cards --owner none --status not_started --agent` |
| Milestone review | `cards --milestone MVP --agent` |
| Batch close | `cards --deck Code --status started --ids-only \| done --stdin --agent` |

## Agent Team Coordination

Multi-agent workflows where a lead agent coordinates worker agents.

### Lead Agent Startup

1. Call `session_start()` or `codecks-cli agent-init --agent`
2. Call `partition --by lane --agent` or `partition --by owner --agent`
3. Assign card batches to worker agents (via SendMessage with card UUIDs)
4. Call `team_dashboard()` periodically to monitor health + workload

### Worker Agent Protocol

1. Receive card assignment from lead (list of UUIDs + context)
2. Call `claim_card(card_id, agent_name)` before starting on any card
3. Do your work (`update_cards`, `mark_started`, `create_comment`, etc.)
4. Call `release_card(card_id, agent_name, summary="what you did")` when done
5. If unsure what's available, call `team_status()` to see all claims

### Conflict Resolution

- `claim_card` returns `{ok: false, conflict_agent: "other-agent"}` if already claimed
- Pick a different card — do not retry the same one
- If handoff is needed: lead calls `delegate_card(card_id, from_agent, to_agent)`

### Monitoring (Lead Agent)

| Goal | Tool |
|------|------|
| Full health + workload | `team_dashboard()` |
| Who's doing what | `team_status()` |
| Work by lane | `partition_cards(by='lane')` |
| Work by owner | `partition_cards(by='owner')` |
| Dropped work | Check `unclaimed_in_progress` in `team_dashboard()` |

### Parallel Independent Pattern

When agents work independently without a lead:
1. Each agent calls `session_start()` (skips cache if already warm)
2. Each agent claims cards before working on them
3. Use `team_status()` to avoid conflicts
4. No delegation needed — agents self-coordinate via claims
