# CLAUDE.md — codecks-cli

Python CLI + library for managing Codecks project cards. Zero runtime dependencies (stdlib only).
Public repo (MIT): https://github.com/rangogamedev/codecks-cli
Fast navigation map: `PROJECT_INDEX.md`.

## Environment
- **Python**: `py` (never `python`/`python3`). Requires 3.10+.
- **Run**: `py codecks_api.py` (no args = help). `--version` for version.
- **Test**: `pwsh -File scripts/run-tests.ps1` (627 tests, no API calls)
- **Lint**: `py -m ruff check .` | **Format**: `py -m ruff format --check .`
- **Type check**: `py -m mypy codecks_cli/api.py codecks_cli/cards.py codecks_cli/client.py codecks_cli/commands.py codecks_cli/formatters/ codecks_cli/models.py codecks_cli/exceptions.py codecks_cli/_utils.py codecks_cli/types.py codecks_cli/planning.py codecks_cli/setup_wizard.py`
- **CI**: `.github/workflows/test.yml` — ruff, mypy, pytest (matrix: 3.10, 3.12, 3.14)
- **Docs backup**: `.github/workflows/backup-docs.yml` — auto-syncs all `*.md` files to private `codecks-cli-docs-backup` repo on push to main. Manual trigger via `workflow_dispatch`. Requires `BACKUP_TOKEN` secret (fine-grained PAT with Contents R/W on the backup repo).
- **Dev deps**: `py -m pip install .[dev]` (ruff, mypy, pytest-cov in `pyproject.toml`)
- **Version**: `VERSION` in `codecks_cli/config.py` (currently 0.4.0)

## Docker (optional)
Runs the project in a sandboxed Linux container. Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
./docker/build.sh                        # Build image (once, or after dep changes)
./docker/test.sh                         # Run pytest (627 tests)
./docker/quality.sh                      # Ruff + mypy + pytest
./docker/cli.sh cards --format table     # Any CLI command
./docker/cli.sh --version                # Version check
./docker/mcp.sh                          # MCP server (stdio)
./docker/mcp-http.sh                     # MCP server (HTTP :8808)
./docker/shell.sh                        # Interactive bash shell
```

- Source is volume-mounted — edits reflect instantly, no rebuild needed.
- `.env` is mounted at runtime via `env_file:`, never baked into the image.
- Container runs as non-root user (`codecks`) for AI agent safety.
- `config.py` `load_env()` falls back to `os.environ` for known `CODECKS_*` keys (Docker passes `.env` as env vars, not as a file).
- Files: `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.gitattributes`, `docker/*.sh`, `.devcontainer/devcontainer.json`.

## Architecture

```
codecks_api.py          ← CLI entry point (backward-compat wrapper)
codecks_cli/
  cli.py                ← argparse, build_parser(), main() dispatch
  commands.py           ← cmd_*() wrappers: argparse → CodecksClient → formatters (+ cards pagination metadata)
  client.py             ← CodecksClient: 27 public methods (the API surface, stable mutation contracts)
  cards.py              ← Card CRUD, hand, conversations, enrichment
  api.py                ← HTTP layer: query(), dispatch(), retries, token check
  config.py             ← Env, tokens, constants, runtime state, contract settings
  exceptions.py         ← CliError, SetupError, HTTPError
  _utils.py             ← _get_field(), get_card_tags(), date/multi-value parsers
  types.py              ← TypedDict response shapes (CardRow, CardDetail, etc.)
  models.py             ← ObjectPayload, FeatureSpec, SplitFeaturesSpec dataclasses
  formatters/           ← JSON/table/CSV output (7 sub-modules)
    __init__.py          re-exports all 24 names
    _table.py            _table(), _trunc(), _sanitize_str()
    _core.py             output(), mutation_response(), pretty_print()
    _cards.py            format_cards_table, format_card_detail, format_cards_csv
    _entities.py         format_decks_table, format_projects_table, format_milestones_table
    _activity.py         format_activity_table, format_activity_diff
    _dashboards.py       format_pm_focus_table, format_standup_table
    _gdd.py              format_gdd_table, format_sync_report
  planning.py           ← File-based planning tools (init, status, update, measure)
  gdd.py                ← Google OAuth2, GDD fetch/parse/sync
  setup_wizard.py       ← Interactive .env bootstrap
  mcp_server.py         ← MCP server: 36 tools wrapping CodecksClient (stdio, legacy/envelope modes)
  pm_playbook.md        ← Agent-agnostic PM methodology (read by MCP tool)
docker/                 ← Wrapper scripts (build, test, quality, cli, mcp, mcp-http, shell)
Dockerfile              ← Multi-stage build (Python 3.12-slim, dev+mcp deps)
docker-compose.yml      ← Services: cli, test, quality, lint, typecheck, mcp, mcp-http, shell
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
- 12 test files mirror source: `test_config.py`, `test_api.py`, `test_cards.py`, `test_commands.py`, `test_formatters.py`, `test_gdd.py`, `test_cli.py`, `test_models.py`, `test_setup_wizard.py`, `test_client.py`, `test_exceptions.py`, `test_mcp_server.py`
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
- 36 tools exposed (27 CodecksClient wrappers + 3 PM session tools + 4 planning tools + 2 feedback tools)
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
- `cards` supports pagination flags: `--limit <n>` and `--offset <n>` (non-negative).
- `create` supports `--parent <id>` to nest as sub-card under a parent card.
- `tags` lists project-level tags (sanctioned taxonomy via masterTags).
- `split-features` batch-splits feature cards into Code/Design/Art/Audio sub-cards (use `--dry-run` first).

## Skills (`.claude/commands/`)
`/pm` (PM session), `/release` (version bump), `/api-ref` (command ref), `/codecks-docs <topic>` (Codecks manual), `/quality` (lint+format+mypy+pytest), `/mcp-validate` (MCP tool check), `/troubleshoot` (debug issues), `/split-features` (batch decomposition), `/doc-update` (audit docs for drift), `/changelog` (generate changelog from commits)

## Subagents (`.claude/agents/`)
- `security-reviewer` — scans for credential exposure, injection vulns, unsafe patterns
- `test-runner` — runs full test suite and reports failures

## MCP Servers (`.claude/settings.json`)
- `context7` — live documentation lookup for FastMCP and other libraries
- `github` — GitHub issues/PRs integration (requires `GITHUB_PERSONAL_ACCESS_TOKEN` env var)

## Hooks (`.claude/settings.json`)
- **PreToolUse** `Edit|Write`: blocks edits to `.env` and `.gdd_tokens.json` (secret protection)
- **PostToolUse** `Edit|Write`: auto-formats `.py` files with ruff after edits

## Scripts (`scripts/`)
- `py scripts/project_meta.py` — project metadata JSON (version, test count, MCP tools, modules). `--save` writes `.project-meta.json`, `--field tests.count` for single values.
- `py scripts/quality_gate.py` — all quality checks in one command (ruff lint/format, mypy, pytest). `--skip-tests` for fast, `--fix` to auto-fix.
- `py scripts/validate_docs.py` — checks doc files for stale counts/mismatches. `--fix-list` shows what needs fixing.
- `py scripts/run_mcp_http.py` — MCP server in streamable-http mode (port 8808).

## Git
- Commit style: short present tense ("Add X", "Fix Y")
- Never commit `.env`, `.gdd_tokens.json`, `.gdd_cache.md`
- `.claude/` is gitignored
- Run `/security-audit` before pushing (public repo)
- Pushing md changes to main triggers automatic backup to private `codecks-cli-docs-backup` repo

## Maintenance
When adding new modules, commands, tests, or fixing bugs:
- Update the Architecture section and test count in this file
- Keep `AGENTS.md` in sync with this file when architecture, commands, or pitfalls change
- Update the mypy command if new modules need type checking
- Keep `.claude/commands/quality.md`, `test-all.md`, `api-ref.md`, `mcp-validate.md`, `release.md`, and `security-audit.md` in sync
- Add new bug patterns to "Known Bugs Fixed" so they aren't reintroduced
- Update project memory at `C:\Users\USER\.claude\projects\C--Users-USER-GitHubDirectory-codecks-cli\memory\MEMORY.md` with stable patterns learned across sessions
