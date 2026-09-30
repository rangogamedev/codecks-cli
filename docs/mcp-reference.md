# MCP Server Reference

The MCP (Model Context Protocol) server exposes 53 tools for AI agents, enabling full Codecks management from within an AI conversation.

## Setup

### Install and Run

The base `codecks-cli` package has zero runtime dependencies. The MCP server requires one additional package (`mcp`), installed via the `mcp` optional extra:

```bash
# Install CLI + MCP server
py -m pip install .[mcp]

# Run the server (stdio transport)
codecks-mcp
# or: py -m codecks_cli.mcp_server
```

The MCP server wraps the same `CodecksClient` library that powers the CLI, adding caching, guardrails, and team coordination on top.

### Claude Code

Add to `.mcp.json` or MCP settings:

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

### Cursor / Other IDEs

Use the same command (`codecks-mcp`) with your IDE's MCP configuration. The server uses stdio transport.

> **New to codecks-cli?** See [docs/ai-agent-guide.md](ai-agent-guide.md) for the full setup walkthrough and CLI-first patterns. The CLI is the recommended default for AI agents — MCP is an optional enhancement.

## Prompt Surface

The MCP server exposes two prompts that connected clients can discover via `prompts/list`:

- `pm-session` — the full CLI-first PM playbook (session flow, batch ops, error recovery, safety rules)
- `setup-guide` — compact setup and orientation guide for first-time users

Use prompts when your MCP client supports them. Use the CLI directly when you want the smallest possible context footprint.

## Critical: Call session_start() First

**Every session must begin with `session_start()`.** It returns everything an agent needs in a single call:

- Account info and recent standup
- Workflow preferences (persisted across sessions)
- Project context: deck names, tag registry, lane registry
- PM playbook rules
- `removed_tools` migration guide (for agents upgrading from v0.4.0)

This also warms the snapshot cache, making subsequent reads near-instant (<50ms).

## Tool Inventory (53 tools)

| Category | Count | Tools |
|----------|-------|-------|
| **Read** | 11 | `get_account`, `list_cards`, `get_card`, `list_decks`, `list_projects`, `list_milestones`, `list_tags`, `list_activity`, `pm_focus`, `standup`, `quick_overview` |
| **Write** | 13 | `create_card`, `attach_files`, `update_cards`, `update_card_body`, `mark_done`, `mark_started`, `archive_card`, `unarchive_card`, `delete_card`, `scaffold_feature`, `split_features`, `find_and_update`, `tick_checkboxes` |
| **Batch** | 5 | `batch_create_cards`, `batch_archive_cards`, `batch_delete_cards`, `batch_unarchive_cards`, `batch_update_bodies` |
| **Hand** | 3 | `list_hand`, `add_to_hand`, `remove_from_hand` |
| **Comments** | 5 | `create_comment`, `reply_comment`, `close_comment`, `reopen_comment`, `list_conversations` |
| **Session** | 4 | `session_start`, `get_workflow_preferences`, `save_workflow_preferences`, `clear_workflow_preferences` |
| **Team** | 6 | `claim_card`, `release_card`, `delegate_card`, `team_status`, `team_dashboard`, `partition_cards` |
| **Admin** | 5 | `create_project`, `create_deck`, `create_milestone`, `create_tag`, `archive_deck` |
| **Other** | 1 | `undo` |

Notes on individual tools:

- `attach_files(card_id, files, dry_run=False)` — paths must resolve inside an allowed root: the project root and the current working directory, plus any directory in `CODECKS_ATTACH_ALLOW_DIRS` (`os.pathsep`-separated; non-absolute, non-existent and filesystem-root entries are ignored with a warning). Dot-prefixed components, credential-looking basenames (`*.pem`, `*.key`, `id_rsa*`, `id_ed25519*`, `*token*`, `*secret*`), `/etc`, `/proc`, `/sys`, and names containing `"`/CR/LF are always refused. `dry_run=True` returns `files: [{path, resolved, size, sha256}]` and uploads nothing. See [cli-reference.md](cli-reference.md#attachments).
- `archive_deck(deck)` — despite the name, this dispatches `decks/delete`: the deck is **deleted and cannot be restored**. Its cards are preserved.
- `create_tag(name, project?)` — takes no color; the `projects/addTag` endpoint has no color field.
- `batch_delete_cards` / `batch_archive_cards` / `batch_unarchive_cards` — `ok` is `false` if any card failed, and `failed` lists `{card_id, error}` for each one.

## Token Efficiency

Minimize token consumption with these patterns:

| Pattern | Saves |
|---------|-------|
| `list_cards` omits content by default | ~60% per card |
| `pm_focus(summary_only=True)` | ~2KB vs ~65KB |
| `standup(summary_only=True)` | Counts only |
| `quick_overview()` | Aggregate counts, no card details |
| `get_card(include_content=False)` | Metadata only |
| `partition_cards(max_cards_per_group=10)` | ~8KB vs ~88KB (default cap, priority-sorted) |
| `team_dashboard(summary_only=True)` | ~2KB vs ~45KB (counts only, no card arrays) |
| `list_activity(limit=5)` | ~2.8KB (strips orphaned entity refs + account key) |
| `_card_summary()` internal format | 7-field compact representation |

## Snapshot Cache

In-memory + disk cache for fast reads.

- **TTL**: 60 seconds (configurable via `CODECKS_CACHE_TTL_SECONDS`, set `0` to disable)
- **Cache-aware tools**: `get_account`, `list_cards`, `get_card`, `list_decks`, `pm_focus`, `standup`, `list_hand`
- **Selective invalidation**: mutations only clear affected cache keys
- **Cache warming**: `session_start()` pre-loads with `include_content=False` for smaller payloads
- **Stale warnings**: returned when cache age exceeds 80% of TTL
- **Cross-process coherence**: mtime-based disk checking

## Error Contract

All error responses include structured fields for agent decision-making:

```json
{
  "ok": false,
  "schema_version": "1.0",
  "error": "[ERROR] Rate limit reached (Codecks allows 40 requests per 5 seconds). Wait 5 seconds and retry.",
  "error_code": "RATE_LIMITED",
  "retryable": true
}
```

| Field | Purpose |
|-------|---------|
| `ok` | `true` on success, `false` on error |
| `schema_version` | Response contract version (`"1.0"`) |
| `error_code` | Machine-readable code (see below) |
| `retryable` | Whether the agent should retry (e.g., `true` for rate limits, `false` for validation errors) |

| `error_code` | Meaning | `retryable` |
|--------------|---------|-------------|
| `TOKEN_EXPIRED` | API token rejected (HTTP 401: invalid, expired, owner disabled, personal tokens off) | no |
| `SETUP_NEEDED` | No configuration, or `CODECKS_ACCOUNT` doesn't match the token's organization | no |
| `PERMISSION_DENIED` | HTTP 403, e.g. `missing_scope` on a read-only token; the message names the required scope | no |
| `RATE_LIMITED` | HTTP 429 after the built-in retries; wait the seconds in the message | yes |
| `INVALID_QUERY` | HTTP 400 graph error; the message has the Codecks code, path and reason | no |
| `HTTP_ERROR` | Any other HTTP error (retryable for 502/503/504) | varies |
| `NETWORK_ERROR` | Timeout or connection failure (reads are retried first); a write may have gone through, so re-read before retrying | no |
| `INVALID_INPUT` / `DOC_CARD_VIOLATION` / `NO_CONTENT` | Rejected by the MCP server before calling Codecks | no |
| `UNKNOWN` | Other MCP-side validation errors (the message says what to fix) | no |
| `SETUP_ERROR` / `CLI_ERROR` / `UNEXPECTED_ERROR` | Other setup, validation or internal errors | no / no / yes |

Before 0.6.0, every API error was `SETUP_ERROR` or `CLI_ERROR`. A rejected token is now `TOKEN_EXPIRED` (was `SETUP_ERROR`), and 403/429/HTTP/network errors have their own codes (were `CLI_ERROR`).

The CLI's JSON errors (`--format json` / `--agent`) carry the same `error_code` and `retryable` fields.

## Response Modes

Set via `CODECKS_MCP_RESPONSE_MODE` environment variable:

| Mode | Behavior |
|------|----------|
| `legacy` (default) | Preserves top-level success shapes, normalizes dicts with `ok`/`schema_version` |
| `envelope` | All responses wrapped: `{"ok": true, "schema_version": "1.0", "data": ...}` |

## Removed Tools (v0.5.0)

13 tools were consolidated. Data is now in `session_start()` or CLI:

| Removed Tool | Replacement |
|---|---|
| `get_pm_playbook` | `session_start().playbook_rules` |
| `get_team_playbook` | `session_start().playbook_rules` |
| `get_tag_registry` | `session_start().project_context.tag_registry` |
| `get_lane_registry` | `session_start().project_context.lane_registry` |
| `planning_*` (4 tools) | Python API: `codecks_cli.planning.init_planning` / `get_planning_status` / `update_planning` / `measure_planning` |
| `save_cli_feedback` | CLI: `py codecks_api.py feedback "<message>" [--category ...]` |
| `get_cli_feedback` / `clear_cli_feedback` | Read/delete `.cli_feedback.json` in the project root (no CLI command) |
| `warm_cache` | `session_start()` warms cache |
| `cache_status` | CLI: `py codecks_api.py cache --show` |
| `partition_by_lane` / `partition_by_owner` | `partition_cards(by='lane'\|'owner')` |
| `tick_all_checkboxes` | `tick_checkboxes(all=True)` |

## Team Coordination (6 tools)

For multi-agent workflows where multiple AI agents work on the same Codecks board.

### Card Claiming

| Tool | Purpose |
|------|---------|
| `claim_card(card_id, agent_name, reason?)` | Exclusive claim on a card |
| `release_card(card_id, agent_name, summary?)` | Release when done |
| `delegate_card(card_id, from_agent, to_agent, message?)` | Transfer to another agent |

### Status and Distribution

| Tool | Purpose |
|------|---------|
| `team_status()` | All agents and their active cards |
| `team_dashboard(project?, summary_only?)` | Combined health + agent workload + unclaimed in-progress. `summary_only=True` for counts only. |
| `partition_cards(by, project?, max_cards_per_group?)` | Divide work with claim annotations. Default cap 10 cards/group (0=unlimited). Priority-sorted. |

### Lead + Worker Pattern

1. **Lead**: `session_start()` > `partition_cards(by='lane')` > assign via SendMessage
2. **Workers**: `claim_card()` > do work > `release_card(summary="...")`
3. **Lead**: `team_dashboard()` to monitor

## Guardrails

Built-in safety checks that prevent common agent mistakes:

- **Doc-card protection**: `update_cards` rejects status/priority/effort on doc cards (`DOC_CARD_VIOLATION`)
- **UUID validation**: suggests full 36-char UUID from cache when agent sends a short ID
- **Deck fuzzy matching**: `resolve_deck_id` suggests closest match ("Did you mean 'X'?") on failure
- **Duplicate detection**: `create_card` blocks exact title matches (override with `allow_duplicate=True`)
- **Default deck**: `create_card` / `batch_create_cards` without `deck` use `CODECKS_DEFAULT_DECK`; if it is unset they fail with a hint instead of creating a private, deck-less card
- **Rate limiting**: every Codecks HTTP request (not every tool call) takes a slot in a shared 35-per-5-seconds window, below Codecks' documented 40 requests / 5 s per IP; a 429 is retried after its `retry-after` wait
- **Prompt injection detection**: sanitizes user content fields
