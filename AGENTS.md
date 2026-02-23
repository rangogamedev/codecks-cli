# AGENTS.md — codecks-cli

Agent-agnostic project instructions for AI coding agents.
For Claude Code specifics, see `CLAUDE.md`.
For a fast navigation map, see `PROJECT_INDEX.md`.

Python CLI + library for managing Codecks project cards. Zero runtime dependencies (stdlib only).
Public repo (MIT): https://github.com/rangogamedev/codecks-cli

## Environment
- **Python**: `py` (never `python`/`python3`). Requires 3.10+.
- **Run**: `py codecks_api.py` (no args = help). `--version` for version.
- **Test**: `pwsh -File scripts/run-tests.ps1` (711 tests, no API calls)
- **Lint**: `py -m ruff check .` | **Format**: `py -m ruff format --check .`
- **Type check**: `py scripts/quality_gate.py --mypy-only` (targets in `scripts/quality_gate.py:MYPY_TARGETS`)
- **CI**: `.github/workflows/test.yml` — ruff, mypy, pytest (matrix: 3.10, 3.12, 3.14)
- **Docs backup**: `.github/workflows/backup-docs.yml` — auto-syncs all `*.md` files to private `codecks-cli-docs-backup` repo on push to main. Manual trigger via `workflow_dispatch`. Requires `BACKUP_TOKEN` secret.
- **Dev deps**: `py -m pip install .[dev]` (ruff, mypy, pytest-cov in `pyproject.toml`)
- **Version**: `VERSION` in `codecks_cli/config.py` (currently 0.4.0)

## Docker (optional)
Runs the project in a sandboxed Linux container. Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
./docker/build.sh                        # Build image (once, or after dep changes)
./docker/test.sh                         # Run pytest (711 tests)
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
  client.py             <- CodecksClient: 25 core methods + 2 scaffolding stubs (the API surface)
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
  planning.py           <- File-based planning tools (init, status, update, measure)
  gdd.py                <- Google OAuth2, GDD fetch/parse/sync
  setup_wizard.py       <- Interactive .env bootstrap
  mcp_server/            <- MCP server package: 38 tools wrapping CodecksClient (stdio, legacy/envelope modes)
    __init__.py          FastMCP init, register() calls, re-exports
    __main__.py          ``py -m codecks_cli.mcp_server`` entry point
    _core.py             Client caching, _call dispatcher, response contract, UUID validation
    _security.py         Injection detection, sanitization, input validation
    _tools_read.py       10 query/dashboard tools
    _tools_write.py      12 mutation/hand/scaffolding tools
    _tools_comments.py   5 comment CRUD tools
    _tools_local.py      11 local tools (PM session, feedback, planning, registry)
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
- 16 test files mirror source: `test_config.py`, `test_api.py`, `test_cards.py`, `test_commands.py`, `test_formatters.py`, `test_gdd.py`, `test_cli.py`, `test_models.py`, `test_setup_wizard.py`, `test_client.py`, `test_scaffolding.py`, `test_exceptions.py`, `test_mcp_server.py`, `test_planning.py`, `test_lanes.py`, `test_tags.py`
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

## MCP Server
- Install: `py -m pip install .[mcp]`
- Run: `py -m codecks_cli.mcp_server` (stdio transport)
- 38 tools exposed (27 CodecksClient wrappers + 3 PM session tools + 4 planning tools + 2 feedback tools + 2 registry tools)
- Response mode: `CODECKS_MCP_RESPONSE_MODE=legacy|envelope` (default `legacy`)
  - `legacy`: preserve top-level success shapes, normalize dicts with `ok`/`schema_version`
  - `envelope`: success always returned as `{"ok": true, "schema_version": "1.0", "data": ...}`

## CLI Feedback (from the PM Agent)

The PM agent ("Decks") at `C:\Users\USER\GitHubDirectory\AIAgentCodecks` uses this CLI daily and saves feedback about missing features, bugs, errors, and improvement ideas to **`.cli_feedback.json`** in this project root.

**At the start of every dev session, read this file** to see what the PM agent has reported:
```python
import json
with open(".cli_feedback.json") as f:
    feedback = json.load(f)
for item in feedback["items"]:
    print(f"[{item['category']}] {item['message']}")
```

Or via MCP: `get_cli_feedback()` / `get_cli_feedback(category="bug")`

Feedback categories: `missing_feature`, `bug`, `error`, `improvement`, `usability`.
Each item has: `timestamp`, `category`, `message`, optional `tool_name` and `context`.

When you fix an issue reported in feedback, consider clearing those items or noting the fix. The file caps at 200 items (oldest removed automatically).

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
