# CLAUDE.md — codecks-cli

Python CLI + library for managing Codecks project cards. Zero runtime dependencies (stdlib only).
Public repo (MIT): https://github.com/rangogamedev/codecks-cli

## Environment
- **Python**: `py` (never `python`/`python3`). Requires 3.10+.
- **Run**: `py codecks_api.py` (no args = help). `--version` for version.
- **Test**: `pwsh -File scripts/run-tests.ps1` (464 tests, no API calls)
- **Lint**: `py -m ruff check .` | **Format**: `py -m ruff format --check .`
- **Type check**: `py -m mypy codecks_cli/api.py codecks_cli/cards.py codecks_cli/client.py codecks_cli/commands.py codecks_cli/formatters/ codecks_cli/models.py codecks_cli/exceptions.py codecks_cli/_utils.py codecks_cli/types.py`
- **CI**: `.github/workflows/test.yml` — ruff, mypy, pytest (matrix: 3.10, 3.12, 3.14)
- **Dev deps**: `py -m pip install .[dev]` (ruff, mypy, pytest-cov in `pyproject.toml`)
- **Version**: `VERSION` in `codecks_cli/config.py` (currently 0.4.0)

## Architecture

```
codecks_api.py          ← CLI entry point (backward-compat wrapper)
codecks_cli/
  cli.py                ← argparse, build_parser(), main() dispatch
  commands.py           ← cmd_*() wrappers: argparse → CodecksClient → formatters
  client.py             ← CodecksClient: 27 public methods (the API surface)
  cards.py              ← Card CRUD, hand, conversations, enrichment
  api.py                ← HTTP layer: query(), dispatch(), retries, token check
  config.py             ← Env, tokens, constants, runtime state
  exceptions.py         ← CliError, SetupError, HTTPError
  _utils.py             ← _get_field(), get_card_tags(), date/multi-value parsers
  types.py              ← TypedDict response shapes (CardRow, CardDetail, etc.)
  models.py             ← ObjectPayload, FeatureSpec dataclasses
  formatters/           ← JSON/table/CSV output (7 sub-modules)
    __init__.py          re-exports all 24 names
    _table.py            _table(), _trunc(), _sanitize_str()
    _core.py             output(), mutation_response(), pretty_print()
    _cards.py            format_cards_table, format_card_detail, format_cards_csv
    _entities.py         format_decks_table, format_projects_table, format_milestones_table
    _activity.py         format_activity_table, format_activity_diff
    _dashboards.py       format_pm_focus_table, format_standup_table
    _gdd.py              format_gdd_table, format_sync_report
  gdd.py                ← Google OAuth2, GDD fetch/parse/sync
  setup_wizard.py       ← Interactive .env bootstrap
  mcp_server.py         ← MCP server: 25 tools wrapping CodecksClient (stdio)
```

### Import graph (no circular deps)
```
exceptions.py  ←  config.py  ←  _utils.py  ←  api.py  ←  cards.py  ←  client.py
                                                                          ↑
types.py (standalone)    formatters/ ← commands.py ← cli.py          models.py
```

### Key design patterns
- **Exceptions**: All in `exceptions.py`. `config.py` and `api.py` re-export for backward compat.
- **Utilities**: Pure helpers in `_utils.py`. `cards.py` re-exports them (`# noqa: F401`).
- **Formatters**: Package with `__init__.py` re-exporting all names. Import as `from codecks_cli.formatters import format_cards_table`.
- **CLI dispatch**: `build_parser()` uses `set_defaults(func=cmd_xxx)` per subparser. `main()` calls `ns.func(ns)`.
- **Type annotations**: `client.py` uses `from __future__ import annotations` and `dict[str, Any]` returns. TypedDicts in `types.py` are documentation for consumers.

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
- 500-error fields: `id`/`updatedAt`/`assigneeId`/`parentCardId`/`dueAt`/`creatorId`. Use `assignee` relation instead of `assigneeId` field.
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
- 12 test files mirror source: `test_config.py`, `test_api.py`, `test_cards.py`, `test_commands.py`, `test_formatters.py`, `test_gdd.py`, `test_cli.py`, `test_models.py`, `test_setup_wizard.py`, `test_client.py`, `test_exceptions.py`, `test_mcp_server.py`
- Mocks at module boundary (e.g. `codecks_cli.commands.list_cards`, `codecks_cli.client.list_cards`)

## Known Bugs Fixed (do not reintroduce)
1. `warn_if_empty` only when no server-side filters (false TOKEN_EXPIRED)
2. Sort by effort: tuple key `(0,val)`/`(1,"")` for blanks-last; date sort = newest-first
3. `update_card()` must pass None values through (clear ops: `--priority null` etc.)
4. `_get_field()` uses key-presence check, not truthiness (`False`/`0` preserved)
5. `get_card()` finds requested card by ID match, not first dict iteration result

## MCP Server
- Install: `py -m pip install .[mcp]`
- Run: `py -m codecks_cli.mcp_server` (stdio transport)
- 25 tools exposed (all CodecksClient public methods except raw_query/raw_dispatch)

## Commands
Use `py codecks_api.py <cmd> --help` for flags. Full reference: `/api-ref` skill.

## Skills (`.claude/commands/`)
`/pm` (PM session), `/test-all` (regression), `/release` (version bump), `/api-ref` (command ref), `/security-audit` (secrets scan), `/codecks-docs <topic>` (Codecks manual), `/quality` (lint+format+mypy+pytest), `/mcp-validate` (MCP tool check), `/troubleshoot` (debug issues)

## Git
- Commit style: short present tense ("Add X", "Fix Y")
- Never commit `.env`, `.gdd_tokens.json`, `.gdd_cache.md`
- `.claude/` is gitignored
- Run `/security-audit` before pushing (public repo)

## Maintenance
When adding new modules, commands, tests, or fixing bugs:
- Update the Architecture section and test count in this file
- Update the mypy command if new modules need type checking
- Keep `.claude/commands/quality.md`, `release.md`, `security-audit.md` in sync
- Add new bug patterns to "Known Bugs Fixed" so they aren't reintroduced
- Update MEMORY.md with stable patterns learned across sessions
