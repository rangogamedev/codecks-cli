# AGENTS.md — codecks-cli

Agent-agnostic project instructions for AI coding agents.
For Claude Code specifics, see `CLAUDE.md`.
For a fast navigation map, see `PROJECT_INDEX.md`.

Python CLI + library for managing Codecks project cards. Zero runtime dependencies (stdlib only).
Public repo (MIT): https://github.com/rangogamedev/codecks-cli

## Environment
- **Python**: `py` (never `python`/`python3`). Requires 3.12+.
- **Run**: `py codecks_api.py` (no args = help). `--version` for version.
- **Test**: `pwsh -File scripts/run-tests.ps1` (1000+ tests, no API calls)
- **Lint**: `py -m ruff check .` | **Format**: `py -m ruff format --check .`
- **Type check**: `py scripts/quality_gate.py --mypy-only` (targets in `scripts/quality_gate.py:MYPY_TARGETS`)
- **CI**: `.github/workflows/test.yml` — ruff, mypy, pytest (matrix: 3.12, 3.14)
- **Docs backup**: `.github/workflows/backup-docs.yml` — auto-syncs all `*.md` files to private `codecks-cli-docs-backup` repo on push to main. Manual trigger via `workflow_dispatch`. Requires `BACKUP_TOKEN` secret.
- **Dev deps**: `py -m pip install .[dev]` (ruff, mypy, pytest-cov in `pyproject.toml`)
- **Version**: `VERSION` in `codecks_cli/config.py` (currently 0.5.0)

## Docker (optional)
Runs the project in a sandboxed Linux container. Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
./docker/build.sh                        # Build image (once, or after dep changes)
./docker/test.sh                         # Run pytest (1000+ tests)
./docker/quality.sh                      # Ruff + mypy + pytest
./docker/cli.sh cards --format table     # Any CLI command
./docker/mcp.sh                          # MCP server (stdio)
./docker/mcp-http.sh                     # MCP server (HTTP :8808)
./docker/shell.sh                        # Interactive bash shell
./docker/dev.sh                          # One-command dev setup (build + shell)
./docker/logs.sh -f                      # Tail MCP HTTP server logs
./docker/claude.sh                       # Run Claude Code in container
```

- `docker compose build` is the canonical build command (auto-builds on first `run` too).
- `PYTHON_VERSION=3.14 ./docker/build.sh` to build with a different Python version.
- `MCP_HTTP_PORT=9000 ./docker/mcp-http.sh` to override the HTTP port.
- Source is volume-mounted — edits reflect instantly, no rebuild needed.
- `.env` is mounted at runtime via `env_file:`, never baked into the image.
- Container runs as non-root user (`codecks`) for AI agent safety.
- `config.py` `load_env()` falls back to `os.environ` for known `CODECKS_*` keys.

### Security hardening
All Docker services inherit these settings from `x-common`:
- **no-new-privileges** — prevents privilege escalation via setuid/setgid
- **cap_drop ALL** — drops all Linux capabilities (none needed for Python CLI)
- **pids_limit 256** — prevents fork bombs; generous for pytest
- **tmpfs /tmp:64M** — writable temp capped at 64MB, cleaned on stop
- DevContainer explicitly sets `containerUser`/`remoteUser` to `codecks` (defense in depth)

## Architecture

```
codecks_api.py          <- CLI entry point (backward-compat wrapper)
codecks_cli/
  cli.py                <- argparse, build_parser(), main() dispatch
  commands.py           <- cmd_*() wrappers: argparse -> CodecksClient -> formatters (+ cards pagination metadata)
  client.py             <- CodecksClient: 33 core methods (the API surface)
  scaffolding.py        <- Feature scaffolding: scaffold_feature(), split_features() + helpers
  cards.py              <- Card CRUD, hand, conversations, enrichment
  api.py                <- HTTP layer: query(), dispatch(), retries, token check
  config.py             <- Env, tokens, constants, runtime state, contract settings
  exceptions.py         <- CliError, SetupError, HTTPError
  _utils.py             <- _get_field(), get_card_tags(), date/multi-value parsers
  types.py              <- TypedDict response shapes (CardRow, CardDetail, etc.)
  models.py             <- ObjectPayload, FeatureSpec, SplitFeaturesSpec dataclasses
  tags.py               <- Tag registry: TagDefinition, TAGS, HERO_TAGS, LANE_TAGS, helpers (standalone, no project imports)
  lanes.py              <- Lane registry: LaneDefinition, LANES, helpers (imports tags.py)
  formatters/           <- JSON/table/CSV output (7 sub-modules)
    __init__.py          re-exports all 24 names
    _table.py            _table(), _trunc(), _sanitize_str()
    _core.py             output(), mutation_response(), pretty_print()
    _cards.py            format_cards_table, format_card_detail, format_cards_csv
    _entities.py         format_decks_table, format_projects_table, format_milestones_table
    _activity.py         format_activity_table, format_activity_diff
    _dashboards.py       format_pm_focus_table, format_standup_table
    _gdd.py              format_gdd_table, format_sync_report
  _content.py           <- Content title/body parsing, serialization, replace helpers
  planning.py           <- File-based planning tools (init, status, update, measure)
  gdd.py                <- Google OAuth2, GDD fetch/parse/sync
  setup_wizard.py       <- Interactive .env bootstrap
  _operations.py        <- Shared operations (CLI + MCP business logic)
  store.py              <- SQLite storage layer (.pm_store.db)
  mcp_server/            <- MCP server package: 52 tools (6 tool modules, stdio transport)
    __init__.py          FastMCP init, register() calls, re-exports
    __main__.py          ``py -m codecks_cli.mcp_server`` entry point
    _core.py             Client caching, _call dispatcher, response contract, UUID validation, snapshot cache
    _security.py         Injection detection, sanitization, input validation
    _repository.py       CardRepository (O(1) indexed lookups by ID/status/deck/owner)
    _tools_read.py       11 query/dashboard tools (cache-aware, summary_only modes)
    _tools_write.py      21 mutation/hand/scaffolding/batch tools
    _tools_comments.py   5 comment CRUD tools
    _tools_local.py      4 session/preference tools (session_start, workflow preferences)
    _tools_team.py       6 team coordination tools (partition_cards merged, playbook removed)
    _tools_admin.py      5 admin tools (Playwright-backed project/deck/milestone/tag CRUD)
  pm_playbook.md        <- Agent-agnostic PM methodology (read by MCP tool)
docker/                 <- Wrapper scripts (build, test, quality, cli, mcp, mcp-http, shell, dev, logs, claude)
Dockerfile              <- Multi-stage build (Python 3.12-slim, dev+mcp+claude deps)
docker-compose.yml      <- Services: cli, test, quality, lint, typecheck, mcp, mcp-http, shell
```

### Import graph (no circular deps)
```
exceptions.py  <-  config.py  <-  _utils.py  <-  api.py  <-  cards.py  <-  scaffolding.py  <-  client.py
                                                                                                                |
types.py (standalone)    formatters/ <- commands.py <- cli.py                                              models.py
tags.py (standalone) <- lanes.py
```

### Key design patterns
- **Exceptions**: All in `exceptions.py`. `config.py` and `api.py` re-export for backward compat.
- **Utilities**: Pure helpers in `_utils.py`. `cards.py` re-exports them (`# noqa: F401`).
- **Formatters**: Package with `__init__.py` re-exporting all names. Import as `from codecks_cli.formatters import format_cards_table`.
- **CLI dispatch**: `build_parser()` uses `set_defaults(func=cmd_xxx)` per subparser. `main()` calls `ns.func(ns)`.
- **Type annotations**: `client.py` uses `from __future__ import annotations` and `dict[str, Any]` returns. TypedDicts in `types.py` are documentation for consumers.
- **Contracts**: `CONTRACT_SCHEMA_VERSION` (`1.0`) is emitted in CLI JSON errors and MCP contract-aware responses.
- **Pagination contract**: `cards --limit/--offset` applies client-side paging and JSON adds `total_count`, `has_more`, `limit`, `offset`.
- **Mutation contract**: mutation methods return stable `ok` + `per_card` shapes; `update_cards(..., continue_on_error=True)` reports partial failures in `per_card`.

## Programmatic API
```python
from codecks_cli import CodecksClient
client = CodecksClient()  # validates token
cards = client.list_cards(status="started", sort="priority")
```
Methods use keyword-only args, return flat dicts (AI-agent-friendly). Map 1:1 to MCP tools.

## Tokens (`.env`, never committed)
- `CODECKS_TOKEN` — session cookie (`at`), **expires**. Empty 200 response = expired (not 401).
- `CODECKS_REPORT_TOKEN` — card creation, never expires. URL param `?token=`.
- `CODECKS_ACCESS_KEY` — generates report tokens, never expires.
- `CODECKS_USER_ID` — hand operations. Auto-discovered if unset.
- No-token commands: `setup`, `gdd-auth`, `gdd-revoke`, `generate-token`, `--version`

## API Pitfalls (will cause bugs if ignored)
- Response: snake_case. Query: camelCase. Use `_get_field(d, snake, camel)` (in `_utils.py`) for safe lookups.
- Query cards: `cards({"cardId":"...", "visibility":"default"})` — never `card({"id":...})` (500).
- 500-error fields: `id`/`updatedAt`/`assigneeId`/`parentCardId`/`dueAt`/`creatorId`/`severity`/`isArchived`. Use `assignee` relation instead of `assigneeId` field.
- Archive/unarchive: use `visibility` field (`"archived"`/`"default"`) in dispatch update, NOT `isArchived` (silently ignored).
- Card title = first line of `content` field.
- Rate limit: 40 req / 5 sec. HTTP 429 = specific error message.
- Hand: `queueEntries` (not `handCards`). Add via `handQueue/setCardOrders`, remove via `handQueue/removeCards`.
- Tags: set `masterTags` (syncs `tags`). Setting `tags` alone does NOT sync.
- Owner: `assigneeId` in `cards/update`. Set `null` to unassign.
- **Doc cards**: no priority/effort/status (API 400). Only owner/tags/milestone/deck/title/content/hero.

## Paid-Only (do NOT use)
Due dates (`dueAt`), Dependencies, Time tracking, Runs/Capacity, Guardians, Beast Cards, Vision Board Smart Nodes.
**Never set `dueAt`** on cards. `--stale`/`--updated-after`/`--updated-before` only *read* timestamps.

## Testing
- `conftest.py` autouse fixture isolates all `config.*` globals — no real API calls
- 20 test files mirror source: `test_api.py`, `test_cards.py`, `test_cli.py`, `test_client.py`, `test_commands.py`, `test_config.py`, `test_content.py`, `test_exceptions.py`, `test_formatters.py`, `test_gdd.py`, `test_lanes.py`, `test_models.py`, `test_mcp_cache.py`, `test_mcp_server.py`, `test_planning.py`, `test_repository.py`, `test_scaffolding.py`, `test_setup_wizard.py`, `test_store.py`, `test_tags.py`
- Mocks at module boundary (e.g. `codecks_cli.commands.list_cards`, `codecks_cli.client.list_cards`)

## Known Bugs Fixed (do not reintroduce)
1. `warn_if_empty` only when no server-side filters (false TOKEN_EXPIRED)
2. Sort by effort: tuple key `(0,val)`/`(1,"")` for blanks-last; date sort = newest-first
3. `update_card()` must pass None values through (clear ops: `--priority null` etc.)
4. `_get_field()` uses key-presence check, not truthiness (`False`/`0` preserved)
5. `get_card()` finds requested card by ID match, not first dict iteration result
6. `severity` field causes API 500 — removed from card queries (`list_cards`, `get_card`)
7. Archive uses `visibility: "archived"` not `isArchived: True` (silently ignored by API)
8. `parentCardId` in get_card query causes HTTP 500 for sub-cards — use `{"parentCard": ["title"]}` relation instead
9. Tags in card body text (`#tag`) create deprecated user-style tags — use `masterTags` dispatch field for project tags
10. `update_cards` content-only update duplicated title when content already started with existing title — now auto-detected and skipped
11. Content title/body handling refactored to use `_content.py` helpers (single source of truth). Error responses include `retryable` and `error_code` for agent decision-making. Cache includes `stale_warning` when age > 80% TTL. New `update_card_body` tool for body-only edits.

## MCP Server
- Install: `py -m pip install .[mcp]`
- Run: `py -m codecks_cli.mcp_server` (stdio transport)
- 52 tools registered (down from 55 in v0.4.0, 13 removed but new batch/overview tools added).
- Response mode: `CODECKS_MCP_RESPONSE_MODE=legacy|envelope` (default `legacy`)
  - `legacy`: preserve top-level success shapes, normalize dicts with `ok`/`schema_version`
  - `envelope`: success always returned as `{"ok": true, "schema_version": "1.0", "data": ...}`

### Startup
**Call `session_start()` first in every session.** Returns account, standup, preferences, project context (deck names, tag/lane registries), playbook rules, and `removed_tools` migration guide. Also warms the snapshot cache.

### Token Efficiency (v0.5.0)
- `list_cards` omits card content by default (only fetched when `search` is set)
- `pm_focus(summary_only=True)` — counts + deck_health only (~2KB vs ~65KB)
- `standup(summary_only=True)` — counts only
- `quick_overview()` — aggregate counts (no card details)
- `_card_summary()` — 7-field card representation used in dashboards
- `include_content=False` / `include_conversations=False` on `get_card` for metadata-only

### Snapshot Cache
- **TTL**: Default 5 minutes. Set `CODECKS_CACHE_TTL_SECONDS=0` to disable.
- **Cache-aware tools**: `get_account`, `list_cards`, `get_card`, `list_decks`, `pm_focus`, `standup`, `list_hand`.
- **Selective invalidation**: Mutations only clear affected keys.
- **Cache warming**: Uses `include_content=False` for smaller API payloads.

### Removed Tools (v0.5.0)
| Removed Tool | Replacement |
|---|---|
| `get_pm_playbook` | `session_start().playbook_rules` |
| `get_team_playbook` | `session_start().playbook_rules` |
| `get_tag_registry` | `session_start().project_context.tag_registry` |
| `get_lane_registry` | `session_start().project_context.lane_registry` |
| `planning_*` (4 tools) | CLI: `py codecks_api.py plan <cmd>` |
| `save/get/clear_cli_feedback` | CLI: `py codecks_api.py feedback <cmd>` |
| `warm_cache` | `session_start()` warms cache |
| `cache_status` | CLI: `py codecks_api.py cache status` |
| `partition_by_lane/owner` | `partition_cards(by='lane'\|'owner')` |
| `tick_all_checkboxes` | `tick_checkboxes(all=True)` |

### Agent Team Coordination (6 tools)
**Claiming** — In-memory claim registry prevents card conflicts:
- `claim_card(card_id, agent_name, reason?)` — Exclusive claim
- `release_card(card_id, agent_name, summary?)` — Release when done
- `delegate_card(card_id, from_agent, to_agent, message?)` — Transfer claim

**Status & Dashboards:**
- `team_status()` — All agents and their active cards
- `team_dashboard(project?)` — Combined health + agent workload + unclaimed in-progress
- `partition_cards(by='lane'|'owner', project?)` — Work distribution with claim annotations

**Lead + Worker pattern:**
1. Lead: `session_start()` → `partition_cards(by='lane')` → assign cards via SendMessage
2. Workers: `claim_card()` → do work → `release_card(summary="...")`
3. Lead: `team_dashboard()` to monitor health

## CLI Feedback (from the PM Agent)

Read `.cli_feedback.json` at session start for PM agent reports. Via CLI: `py codecks_api.py feedback list`.

## Commands
Use `py codecks_api.py <cmd> --help` for flags. Full reference: `/api-ref` skill.
- Common flags have short aliases: `-d` (deck), `-s` (status), `-p` (priority), `-S` (search), `-e` (effort), `-c` (content).
- `cards` supports `--limit <n>` and `--offset <n>` (client-side pagination).
- `card` supports `--no-content` and `--no-conversations` for metadata-only lookups.
- `update` supports `--continue-on-error` for partial batch updates. Effort accepts positive int or `"null"`.
- `create` supports `--parent <id>` for sub-cards.
- `tags` lists project-level tags (masterTags).
- `split-features` batch-splits feature cards into Code/Design/Art/Audio sub-cards (use `--dry-run` first).

## Git
- Commit style: short present tense ("Add X", "Fix Y")
- Never commit `.env`, `.gdd_tokens.json`, `.gdd_cache.md`

## Maintenance
When adding new modules, commands, tests, or fixing bugs:
- Update the Architecture section and test count in this file and `CLAUDE.md`
- Update `MYPY_TARGETS` in `scripts/quality_gate.py` if new modules need type checking
- Add new bug patterns to "Known Bugs Fixed" so they aren't reintroduced
