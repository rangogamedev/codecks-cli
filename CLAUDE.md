# CLAUDE.md — codecks-cli

Python CLI + library for managing Codecks project cards. Zero runtime dependencies (stdlib only).
Public repo (MIT): https://github.com/rangogamedev/codecks-cli

## Environment
- **Python**: `py` (never `python`/`python3`). Requires 3.10+.
- **Run**: `py codecks_api.py` (no args = help). `--version` for version.
- **Test**: `pwsh -File scripts/run-tests.ps1` (433 tests, no API calls)
- **Lint**: `py -m ruff check .` | **Format**: `py -m ruff format --check .`
- **Type check**: `py -m mypy codecks_cli/api.py codecks_cli/cards.py codecks_cli/client.py codecks_cli/commands.py codecks_cli/formatters.py codecks_cli/models.py`
- **CI**: `.github/workflows/test.yml` — ruff, mypy, pytest (matrix: 3.10, 3.12, 3.14)
- **Dev deps**: `py -m pip install .[dev]` (ruff, mypy, pytest-cov in `pyproject.toml`)
- **Version**: `VERSION` in `codecks_cli/config.py` (currently 0.4.0)

## Modules (`codecks_cli/`)
| Module | Purpose |
|--------|---------|
| `codecks_api.py` | Backward-compat wrapper → `cli:main()` (project root) |
| `__init__.py` | Exports `CodecksClient`, `CliError`, `SetupError`, `VERSION` |
| `config.py` | Env, tokens, constants, `CliError`/`SetupError` exceptions |
| `api.py` | HTTP layer: `query()`, `dispatch()`, token validation |
| `cards.py` | Card CRUD, hand, conversations, enrichment, `_get_field()` |
| `client.py` | **`CodecksClient` class** — public API (27 keyword-only methods returning flat dicts) |
| `commands.py` | Thin CLI `cmd_*()` wrappers: argparse → `CodecksClient` → formatters |
| `formatters.py` | JSON/table/CSV output dispatch |
| `mcp_server.py` | MCP server: wraps `CodecksClient` as 25 MCP tools (stdio) |
| `models.py` | `ObjectPayload`, `FeatureSpec` dataclasses |
| `gdd.py` | Google OAuth2, GDD fetch/parse/sync |
| `setup_wizard.py` | Interactive `.env` bootstrap |
| `cli.py` | Entry point: argparse, `build_parser()`, `main()` dispatch |

All imports are absolute (`from codecks_cli.config import ...`). No circular deps.

## Programmatic API
```python
from codecks_cli import CodecksClient
client = CodecksClient()  # validates token
cards = client.list_cards(status="started", sort="priority")
```
Methods use keyword-only args, return flat dicts (AI-agent-friendly). Map 1:1 to future MCP tools.

## Tokens (`.env`, never committed)
- `CODECKS_TOKEN` — session cookie (`at`), **expires**. Empty 200 response = expired (not 401).
- `CODECKS_REPORT_TOKEN` — card creation, never expires. URL param `?token=`.
- `CODECKS_ACCESS_KEY` — generates report tokens, never expires.
- `CODECKS_USER_ID` — hand operations. Auto-discovered if unset.
- No-token commands: `setup`, `gdd-auth`, `gdd-revoke`, `generate-token`, `--version`

## API Pitfalls (will cause bugs if ignored)
- Response: snake_case. Query: camelCase. Use `_get_field(d, snake, camel)` for safe lookups.
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
- Test files mirror source: `test_config.py`, `test_api.py`, `test_cards.py`, `test_commands.py`, `test_formatters.py`, `test_gdd.py`, `test_cli.py`, `test_models.py`, `test_setup_wizard.py`, `test_client.py`
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
`/pm` (PM session), `/test-all` (regression), `/release` (version bump), `/api-ref` (command ref), `/security-audit` (secrets scan), `/codecks-docs <topic>` (Codecks manual), `/quality` (lint+format+mypy+pytest)

## Git
- Commit style: short present tense ("Add X", "Fix Y")
- Never commit `.env`, `.gdd_tokens.json`, `.gdd_cache.md`
- `.claude/` is gitignored
- Run `/security-audit` before pushing (public repo)
