# AGENTS.md — codecks-cli

Agent-agnostic instructions for AI coding agents. For Claude Code specifics, see [CLAUDE.md](CLAUDE.md). For architecture and dev setup, see [DEVELOPMENT.md](DEVELOPMENT.md).

Python CLI + library + MCP server for managing Codecks project cards. Zero runtime dependencies (stdlib only). Public repo (MIT): https://github.com/rangogamedev/codecks-cli

## Environment

- **Python**: `py` (never `python`/`python3`). Requires 3.12+.
- **Run**: `py codecks_api.py` (no args = help). `--version` for version.
- **Test**: `pwsh -File scripts/run-tests.ps1` (1000+ tests, no API calls)
- **Lint**: `py -m ruff check .` | **Format**: `py -m ruff format --check .`
- **Type check**: `py scripts/quality_gate.py --mypy-only`
- **All checks**: `py scripts/quality_gate.py`
- **CI**: `.github/workflows/test.yml` — ruff, mypy, pytest (matrix: 3.12, 3.14)
- **Version**: `VERSION` in `codecks_cli/config.py` (keep in sync with `pyproject.toml`)

## Architecture

See [DEVELOPMENT.md](DEVELOPMENT.md#architecture) for the full file tree, import graph, and design patterns.

## Tokens (`.env`, never committed)

| Token | Used for | Auth method | Expiry |
|-------|----------|-------------|--------|
| `CODECKS_TOKEN` | Reading data, mutations | `X-Auth-Token` header | Session (browser cookie) |
| `CODECKS_REPORT_TOKEN` | Creating cards | URL query parameter | Never (until disabled) |
| `CODECKS_ACCESS_KEY` | Generating report tokens | URL query parameter | Never |
| `CODECKS_USER_ID` | Hand operations | Auto-discovered if unset | N/A |

- Session token validated on every command. Expired tokens return empty data (not 401).
- No-token commands: `setup`, `gdd-auth`, `gdd-revoke`, `generate-token`, `--version`

## Error Patterns

| Pattern | Meaning | Agent action |
|---------|---------|-------------|
| `[TOKEN_EXPIRED]` | Session token expired | Re-run `setup` or refresh browser cookie |
| `[SETUP_NEEDED]` | No `.env` configuration | Run `py codecks_api.py setup` |
| `[ERROR] ...` | General error | Check message for details |
| JSON on stderr: `{"ok": false, ...}` | Structured error (with `--format json`) | Parse `error_code` and `retryable` fields |

MCP error responses include `error_code` (e.g., `NOT_FOUND`, `DOC_CARD_VIOLATION`, `RATE_LIMITED`) and `retryable` (bool) for automated decision-making.

## API Pitfalls (will cause bugs if ignored)

### Naming Conventions

- Response fields: `snake_case`. Query fields: `camelCase`.
- Use `_get_field(d, snake, camel)` from `_utils.py` for safe lookups.

### Query Patterns

- Query cards: `cards({"cardId":"...", "visibility":"default"})` — never `card({"id":...})` (returns 500).
- Card title = first line of `content` field.
- Hand: `queueEntries` (not `handCards`). Add via `handQueue/setCardOrders`, remove via `handQueue/removeCards`.

### Dangerous Fields (cause HTTP 500)

`id`, `updatedAt`, `assigneeId`, `parentCardId`, `dueAt`, `creatorId`, `severity`, `isArchived` — do not include in queries. Use `assignee` relation instead of `assigneeId` field.

### Mutation Gotchas

- Archive/unarchive: use `visibility` field (`"archived"`/`"default"`), NOT `isArchived` (silently ignored).
- Tags: set `masterTags` (syncs `tags`). Setting `tags` alone does NOT sync.
- Owner: `assigneeId` in `cards/update`. Set `null` to unassign.
- **Doc cards**: no priority/effort/status (API 400). Only owner/tags/milestone/deck/title/content/hero.
- Content title/body: use `_content.py` helpers — single source of truth for parsing.

### Rate Limit

40 requests per 5 seconds per IP. HTTP 429 = specific error message. Transient errors (429/502/503/504) are retried with backoff.

## Paid-Only (do NOT use)

Due dates (`dueAt`), Dependencies, Time tracking, Runs/Capacity, Guardians, Beast Cards, Vision Board Smart Nodes. **Never set `dueAt`** on cards.

## Programmatic API

```python
from codecks_cli import CodecksClient
client = CodecksClient()  # validates token
cards = client.list_cards(status="started", sort="priority")
```

33 methods, keyword-only args, flat dict returns. See [docs/cli-reference.md](docs/cli-reference.md#python-api) for the full method table.

## MCP Server

- **Install**: `py -m pip install .[mcp]`
- **Run**: `py -m codecks_cli.mcp_server` (stdio transport)
- **Startup**: Call `session_start()` first in every session.
- 52 tools across 6 modules. See [docs/mcp-reference.md](docs/mcp-reference.md) for the full tool inventory, cache behavior, error contract, and team coordination patterns.

## Testing

- `conftest.py` autouse fixture isolates all `config.*` globals — no real API calls
- 20 test files mirror source modules (see [DEVELOPMENT.md](DEVELOPMENT.md#test-organization))
- Mocks at module boundary (e.g., `codecks_cli.commands.list_cards`, `codecks_cli.client.list_cards`)

## Known Bugs Fixed (do not reintroduce)

| # | Bug | Fix | Guard |
|---|-----|-----|-------|
| 1 | `warn_if_empty` fires false TOKEN_EXPIRED | Only warn when no server-side filters | Check filter args |
| 2 | Sort by effort puts blanks first | Tuple key `(0,val)`/`(1,"")` for blanks-last | Test with blank efforts |
| 3 | `update_card()` drops None values | Pass None through (clear ops: `--priority null`) | Test null clears |
| 4 | `_get_field()` loses `False`/`0` | Key-presence check, not truthiness | Test falsy values |
| 5 | `get_card()` returns wrong card | Find by ID match, not first dict result | Test multi-card response |
| 6 | `severity` field causes API 500 | Removed from card queries | Never add back |
| 7 | Archive uses wrong field | Use `visibility: "archived"` not `isArchived` | Covered in API pitfalls |
| 8 | `parentCardId` in query causes 500 | Use `{"parentCard": ["title"]}` relation | Never query `parentCardId` |
| 9 | Tags in body create wrong tag type | Use `masterTags` dispatch, not `#tag` in body | Covered in API pitfalls |
| 10 | Content update duplicates title | Auto-detect and skip via `_content.py` | Test title-in-content edge case |
| 11 | Error responses lack structure | Added `retryable`, `error_code`, cache `stale_warning` | Test error shapes |

## Docker

Sandboxed Linux container, non-root user, security hardened. See [DEVELOPMENT.md](DEVELOPMENT.md#docker) for commands and security details.

## Commands

Use `py codecks_api.py <cmd> --help` for flags. Full reference: [docs/cli-reference.md](docs/cli-reference.md).

- Common flags: `-d` (deck), `-s` (status), `-p` (priority), `-S` (search), `-e` (effort), `-c` (content)
- `cards`: `--limit`, `--offset` (client-side pagination)
- `card`: `--no-content`, `--no-conversations` (metadata-only)
- `update`: `--continue-on-error` (partial batch). Effort: positive int or `"null"`
- `create`: `--parent <id>` (sub-cards)
- `split-features`: batch-split into Code/Design/Art/Audio (use `--dry-run` first)

### Agent Mode

- `--json` forces JSON output for all commands
- `--agent` enables JSON + suppress warnings + strict envelope
- `CODECKS_AGENT=1` env var auto-enables agent mode
- `--stdin` on `done`/`start`/`hand`/`unhand`/`update`: read card IDs from stdin
- Pipe workflow: `cards -s started --json | jq '.cards[].id' | done --stdin`

## Git

- Commit style: short present tense ("Add X", "Fix Y")
- Never commit `.env`, `.gdd_tokens.json`, `.gdd_cache.md`, `.pm_store.db*`, `.pm_claims.json`

## Maintenance

When adding new modules, commands, tests, or fixing bugs:

- Update `DEVELOPMENT.md` architecture section and test count
- Update `MYPY_TARGETS` in `scripts/quality_gate.py` if new modules need type checking
- Add new bug patterns to "Known Bugs Fixed" above
- Run `py scripts/validate_docs.py` to catch stale counts
