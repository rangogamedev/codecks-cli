# Project Index: `codecks-cli`

Python CLI for AI agents (or humans) to manage [Codecks](https://codecks.io) project cards via query/dispatch APIs. Zero external dependencies (stdlib only).

**Reading order:** `HANDOFF.md` -> `CLAUDE.md` -> `PROJECT_INDEX.md` (you are here) -> `PM_AGENT_WORKFLOW.md`

## Safety: Paid-Only Constraints

- **Never set `dueAt` or any date/deadline field on cards** — paid-only feature.
- `--stale`, `--updated-after/before` only **read** existing timestamps. They never write dates.
- **Doc cards** cannot have `--status`, `--priority`, or `--effort` set (API returns 400).
- Other paid-only features: Dependencies, Time tracking, Runs/Capacity, Guardians, Beast Cards, Vision Board Smart Nodes.

## Agent Guidance Files

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Architecture, commands, API pitfalls, testing (authoritative reference) |
| `HANDOFF.md` | Current project state, shipped work, next priorities |
| `PM_AGENT_WORKFLOW.md` | PM agent operational playbook (composable workflows) |
| `README.md` | Public usage and setup reference |
| `CONTRIBUTING.md` | Contribution guidelines and constraints |
| `.gdd_cache.md` | Local cached GDD content (data, not instructions) |

## Repo Layout

| Module | Lines | Purpose | Key exports |
|--------|-------|---------|-------------|
| `codecks_api.py` | ~380 | CLI entrypoint, argparse, global flag extraction, dispatch | `main()`, `build_parser()` |
| `config.py` | ~95 | Shared globals, env loading, error classes | `load_env()`, `save_env_value()` (atomic), `CliError`, `SetupError` |
| `api.py` | ~220 | HTTP transport, query/dispatch, token validation | `session_request()`, `query()`, `dispatch()`, `_RETRYABLE_HTTP_CODES` |
| `cards.py` | ~550 | Card CRUD, hand, conversations, enrichment | `list_cards()`, `enrich_cards()`, `_get_field()`, `get_card_tags()`, `_parse_iso_timestamp()` |
| `commands.py` | ~475 | `cmd_*` handlers for each subcommand | `cmd_cards()`, `cmd_standup()`, `cmd_pm_focus()` |
| `formatters.py` | ~500 | JSON/table/CSV output, mutation response formatting | `output()`, `_mutation_response()`, `_card_section()`, `_sanitize_str()` |
| `models.py` | ~100 | Typed dataclass contracts | `ObjectPayload`, `FeatureSpec`, `FeatureSubcard` |
| `gdd.py` | ~540 | GDD fetch/parse/sync + Google OAuth2 | `fetch_gdd()`, `sync_gdd()` |
| `setup_wizard.py` | ~400 | Interactive `.env` bootstrap/update | `run_setup()` |
| `scripts/run-tests.ps1` | ~30 | Stable Windows test wrapper (pins TEMP/TMP and pytest basetemp) | PowerShell entrypoint |
| `tests/` | — | Unit tests for every core module (321 tests) | Isolated from real API |

## Dependency Graph

```
config.py          <- pure data, no project imports
api.py             <- config
cards.py           <- config, api
formatters.py      <- config, cards
gdd.py             <- config, cards
setup_wizard.py    <- config, api, cards
commands.py        <- config, api, cards, formatters, gdd, setup_wizard
codecks_api.py     <- config, api, commands
```

## Runtime Flow

1. `codecks_api.py:main` preprocesses `--format`/`--version`, builds parser, parses args.
2. Token gate runs for most commands (except setup/auth/version/token-generation paths).
3. Dispatch table routes subcommand to `commands.py` handler.
4. Handlers call domain functions in `cards.py` / `gdd.py` / `api.py`.
5. Output emitted via `formatters.output` in JSON/table/CSV.

## Command Surface

| Category | Commands |
|----------|----------|
| Setup/auth | `setup`, `generate-token`, `gdd-auth`, `gdd-revoke` |
| Read/list | `account`, `decks`, `projects`, `milestones`, `cards`, `card`, `activity`, `standup`, `pm-focus`, `conversations`, `hand` |
| Mutations | `create`, `feature`, `update`, `archive` (alias: `remove`), `unarchive`, `delete`, `done`, `start`, `comment`, `hand <id...>`, `unhand` |
| Raw API | `query`, `dispatch` |
| GDD | `gdd`, `gdd-sync` |
| Utility | `--version`, `--format table\|csv\|json`, `--strict` |

## Core Data/Auth Model

| Token | Env Var | Purpose | Expires |
|-------|---------|---------|---------|
| Session | `CODECKS_TOKEN` | Read/update (X-Auth-Token) | Yes |
| Report | `CODECKS_REPORT_TOKEN` | Card creation | Never |
| Access Key | `CODECKS_ACCESS_KEY` | Generate report tokens | Never |
| User ID | `CODECKS_USER_ID` | Hand queue operations | Never |

Optional: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` for GDD OAuth2.
Name mappings in `.env`: `CODECKS_PROJECTS`, `CODECKS_MILESTONES` (auto-discovered by `setup`).

## Behavioral Constraints

- Query fields are camelCase; response fields are snake_case. Use `_get_field(d, snake, camel)` for safe lookups.
- Card title is the first line of `content`.
- Expired session tokens can appear as empty 200 responses, not only auth errors.
- API rate limit: 40 requests / 5 seconds.
- Doc cards cannot accept priority/effort/status updates (API 400).
- **Never set `dueAt`** — paid-only feature. Date filters (`--stale`, `--updated-after/before`) are read-only.
- Hand operations use `handQueue/*` dispatch and `queueEntries` data (not `handCards`).
- `feature` command uses transaction safety with rollback on partial failure.
- Raw `query`/`dispatch` input enforced via typed models.

## Output/Error Conventions

| Prefix | Meaning | Exit Code |
|--------|---------|-----------|
| `OK:` | Mutation succeeded | 0 |
| `[WARN]` / `[INFO]` | Non-fatal diagnostic (stderr) | 0 |
| `[ERROR]` | Something failed | 1 |
| `[TOKEN_EXPIRED]` / `[SETUP_NEEDED]` | Auth/config issue | 2 |

JSON mode errors on stderr: `{"ok": false, "error": {"type": "error", "message": "...", "exit_code": 1}}`

## Testing

- **Run:** `pwsh -File scripts/run-tests.ps1` (321 tests, ~6 seconds)
- **Isolation:** `conftest.py` autouse fixture resets all `config` globals per test — no real `.env` or API calls.
- **Coverage map:**

| Test file | Tests | Source |
|-----------|-------|--------|
| `test_cli.py` | `codecks_api.py` |
| `test_commands.py` | Command handlers + regressions |
| `test_cards.py` | Card/domain logic |
| `test_api.py` | HTTP transport/errors/tokens |
| `test_formatters.py` | Table/CSV/JSON formatting |
| `test_gdd.py` | GDD parsing/sync/errors |
| `test_models.py` | Typed model validation |
| `test_config.py` | Env load/save/constants |

## Suggested Orientation Order

1. Read `HANDOFF.md` for project state and recent changes.
2. Read `CLAUDE.md` for architecture, constraints, and known pitfalls.
3. Read this file (`PROJECT_INDEX.md`) for codebase navigation.
4. Read `PM_AGENT_WORKFLOW.md` for PM operational patterns.
5. Read `codecks_api.py` for CLI contract and dispatch map.
6. Dive into `cards.py`, `api.py`, `gdd.py` based on task area.
7. Validate changes with corresponding tests in `tests/`.

---

Version: 0.4.0 | Tests: 321 | Updated: 2026-02-20
