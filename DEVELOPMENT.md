# Development Guide

Everything you need to set up, build, test, and release codecks-cli.

## Prerequisites

- **Python 3.12+** — use `py` command (never `python` or `python3`)
- **uv** (recommended) — fast Python package manager ([install](https://docs.astral.sh/uv/getting-started/installation/))
- **PowerShell** — for the test runner script (Windows: built-in, Linux/Mac: `pwsh`)
- **A Codecks account** — free tier works for testing ([codecks.io](https://codecks.io))

## Setup

```bash
# Clone
git clone https://github.com/rangogamedev/codecks-cli.git
cd codecks-cli

# Install with dev dependencies
uv sync --extra dev          # preferred
# or: py -m pip install -e .[dev]

# Create .env with your Codecks credentials
cp .env.example .env         # then fill in your tokens
```

### Required tokens (`.env`)

| Variable | Purpose | Expiry |
|----------|---------|--------|
| `CODECKS_TOKEN` | Session cookie for read/write | Expires periodically |
| `CODECKS_ACCOUNT` | Your Codecks org slug | Never |

### Optional tokens

| Variable | Purpose |
|----------|---------|
| `CODECKS_REPORT_TOKEN` | Card creation (never expires) |
| `CODECKS_ACCESS_KEY` | Generates report tokens (never expires) |
| `CODECKS_USER_ID` | Hand operations (auto-discovered if unset) |

Run `py codecks_api.py setup` for an interactive setup wizard that handles all of this.

## Running

```bash
py codecks_api.py                  # show help
py codecks_api.py cards            # list cards (JSON)
py codecks_api.py cards -f table   # list cards (human-readable)
py codecks_api.py --version        # show version
```

## Quality Checks

```bash
# Individual checks
py -m ruff check .                       # lint
py -m ruff format --check .              # format
py scripts/quality_gate.py --mypy-only   # type check
pwsh -File scripts/run-tests.ps1         # 1000+ tests

# All at once
py scripts/quality_gate.py               # lint + types + tests

# Auto-fix lint issues
py -m ruff check . --fix
py -m ruff format .
```

## Architecture

```
codecks_api.py          <- entry point (thin wrapper)
codecks_cli/
  cli.py                <- argparse parser, dispatch
  commands.py           <- cmd_*() CLI handlers
  client.py             <- CodecksClient: 33 public methods
  scaffolding.py        <- scaffold_feature(), split_features()
  cards.py              <- Card CRUD, hand, conversations
  api.py                <- HTTP layer (retries, timeouts, tokens)
  config.py             <- .env loading, constants, VERSION
  exceptions.py         <- CliError, SetupError, HTTPError
  _content.py           <- Title/body parsing and serialization
  _operations.py        <- Shared operations (CLI + MCP business logic)
  _utils.py             <- Field helpers, parsers
  _last_result.py       <- Last result caching
  types.py              <- TypedDict response shapes
  models.py             <- FeatureSpec, SplitFeaturesSpec dataclasses
  tags.py               <- Tag registry (TagDefinition, TAGS)
  lanes.py              <- Lane registry (LaneDefinition, LANES)
  store.py              <- SQLite storage layer (.pm_store.db)
  admin.py              <- Admin commands (project/deck/milestone/tag CRUD)
  endpoint_cache.py     <- API endpoint discovery cache
  planning.py           <- File-based planning tools
  gdd.py                <- Google OAuth2, GDD sync
  setup_wizard.py       <- Interactive .env bootstrap
  formatters/           <- JSON/table/CSV output (7 sub-modules)
    __init__.py          re-exports all 24 names
    _table.py            _table(), _trunc(), _sanitize_str()
    _core.py             output(), mutation_response(), pretty_print()
    _cards.py            format_cards_table, format_card_detail, format_cards_csv
    _entities.py         format_decks_table, format_projects_table, format_milestones_table
    _activity.py         format_activity_table, format_activity_diff
    _dashboards.py       format_pm_focus_table, format_standup_table
    _gdd.py              format_gdd_table, format_sync_report
  mcp_server/           <- 52 MCP tools (package, 6 tool modules)
    __init__.py          FastMCP init, registration, re-exports
    __main__.py          py -m codecks_cli.mcp_server entry
    _core.py             Client cache, dispatcher, snapshot cache
    _security.py         Injection detection, sanitization
    _repository.py       CardRepository (O(1) indexed lookups)
    _tools_read.py       11 query/dashboard tools
    _tools_write.py      21 mutation/hand/scaffolding/batch tools
    _tools_comments.py   5 comment CRUD tools
    _tools_local.py      4 session/preference tools
    _tools_team.py       6 team coordination tools
    _tools_admin.py      5 admin tools (Playwright-backed)
  pm_playbook.md        <- Agent-agnostic PM methodology
  py.typed              <- PEP 561 type marker
tests/                  <- 1000+ pytest tests across 20 files (no live API calls)
docker/                 <- Wrapper scripts (build, test, quality, cli, mcp, shell, dev, logs)
```

### Request Flow

```
CLI:  cli.py -> commands.py -> CodecksClient (client.py) -> cards.py/api.py
MCP:  mcp_server/ -> _core._call() -> CodecksClient -> _core._finalize_tool_result()
```

### Import Graph (no circular deps)

```
exceptions.py  <-  config.py  <-  _utils.py  <-  api.py  <-  cards.py  <-  scaffolding.py  <-  client.py
                                                                                                    |
types.py (standalone)    formatters/ <- commands.py <- cli.py                                  models.py
tags.py (standalone) <- lanes.py
```

### Key Design Decisions

- **Zero runtime dependencies** — stdlib only, dev tools are optional extras
- **AI-agent first** — JSON default output, token-efficient responses
- **Content format** — card title is always first line of `content` field (`"Title\nBody"`)
- **Error prefixes** — `[ERROR]` and `[TOKEN_EXPIRED]` for pattern matching
- **Flat dict returns** — CodecksClient methods return plain dicts, not custom objects
- **Snake/camel compat** — `_get_field()` helper handles both naming conventions
- **Contracts** — `CONTRACT_SCHEMA_VERSION` (`1.0`) emitted in CLI JSON errors and MCP responses
- **Pagination** — `cards --limit/--offset` applies client-side paging, JSON adds `total_count`, `has_more`
- **Mutation contract** — mutation methods return stable `ok` + `per_card` shapes; `continue_on_error=True` reports partial failures

## Testing

### Running Tests

```bash
pwsh -File scripts/run-tests.ps1      # full suite (1000+ tests)
py -m pytest tests/test_client.py -x   # single file, stop on first failure
py -m pytest -k "test_update" -x       # run tests matching pattern
py -m pytest --tb=short                # shorter tracebacks
```

### Test Organization

| File | Coverage |
|------|----------|
| `test_cli.py` | CLI argument parsing and dispatch |
| `test_commands.py` | Command handlers (cmd_*) |
| `test_client.py` | CodecksClient methods |
| `test_cards.py` | Card CRUD operations |
| `test_api.py` | HTTP layer, retries, tokens |
| `test_config.py` | Configuration loading |
| `test_content.py` | Content parsing helpers |
| `test_formatters.py` | Output formatting |
| `test_scaffolding.py` | Feature scaffolding |
| `test_mcp_server.py` | MCP tool functions |
| `test_mcp_cache.py` | Snapshot cache |
| `test_gdd.py` | Google Docs sync |
| `test_setup_wizard.py` | Setup wizard |
| `test_planning.py` | Planning tools |
| `test_models.py` | Dataclass models |
| `test_tags.py` | Tag registry |
| `test_lanes.py` | Lane registry |
| `test_repository.py` | CardRepository (indexed card access) |
| `test_store.py` | CardStore (SQLite storage layer) |
| `test_exceptions.py` | Exception hierarchy |

### Writing Tests

- Mock at module boundaries — no live API calls
- Test patches target sub-modules: `_core.CodecksClient`, `_core.MCP_RESPONSE_MODE`
- Use `conftest.py` fixtures for common setup (cache reset, path patches)
- Follow existing patterns — look at neighboring tests in the same file

## Docker

Run everything in a sandboxed Linux container — no Python install needed on the host.

```bash
./docker/build.sh                        # build image (once, or after dep changes)
./docker/test.sh                         # run pytest (1000+ tests)
./docker/quality.sh                      # ruff + mypy + pytest
./docker/cli.sh cards --format table     # any CLI command
./docker/mcp.sh                          # MCP server (stdio)
./docker/mcp-http.sh                     # MCP server (HTTP :8808)
./docker/shell.sh                        # interactive bash shell
./docker/dev.sh                          # one-command dev setup (build + shell)
./docker/logs.sh -f                      # tail MCP HTTP server logs
./docker/claude.sh                       # run Claude Code in container
```

- Source is volume-mounted — edits reflect instantly, no rebuild needed
- `.env` is mounted at runtime via `env_file:`, never baked into the image
- `PYTHON_VERSION=3.14 ./docker/build.sh` to build with a different Python version
- `MCP_HTTP_PORT=9000 ./docker/mcp-http.sh` to override the HTTP port

### Security Hardening

All Docker services inherit these settings:

- **no-new-privileges** — prevents privilege escalation via setuid/setgid
- **cap_drop ALL** — drops all Linux capabilities
- **pids_limit 256** — prevents fork bombs
- **tmpfs /tmp:64M** — writable temp capped at 64MB, cleaned on stop
- Container runs as non-root user (`codecks`)

## Versioning

This project follows [Semantic Versioning](https://semver.org/):

- **MAJOR** (1.0.0) — breaking changes to CLI commands or programmatic API
- **MINOR** (0.x.0) — new features, new commands, new MCP tools
- **PATCH** (0.0.x) — bug fixes, documentation updates, internal refactors

### Version Locations

Version is maintained in **two files** (must stay in sync):
- `codecks_cli/config.py` — `VERSION = "x.y.z"` (runtime)
- `pyproject.toml` — `version = "x.y.z"` (packaging)

### Release Process

1. Review `[Unreleased]` in `CHANGELOG.md`
2. Determine version (patch/minor/major)
3. Update version in `config.py` and `pyproject.toml`
4. Move CHANGELOG entries under new version heading with date
5. Run `py scripts/quality_gate.py` (must pass clean)
6. Commit: `git commit -m "Release v0.5.0"`
7. Tag: `git tag -a v0.5.0 -m "v0.5.0 - Summary"`
8. Push: `git push && git push --tags`

## Adding Features

### New CLI Command

1. `codecks_cli/cli.py` — add argparse subparser
2. `codecks_cli/commands.py` — add `cmd_*()` handler
3. `codecks_cli/client.py` — add business logic method
4. Tests: `test_cli.py`, `test_commands.py`, `test_client.py`
5. `CHANGELOG.md` — add entry under `[Unreleased]`

### New MCP Tool

1. `codecks_cli/mcp_server/_tools_*.py` — add function + register in `register()`
2. `codecks_cli/mcp_server/__init__.py` — add to re-exports
3. Tests: `test_mcp_server.py`
4. `CHANGELOG.md` — add entry under `[Unreleased]`

### New Formatter

1. `codecks_cli/formatters/_*.py` — add formatter module
2. `codecks_cli/formatters/__init__.py` — add to export list
3. Tests: `test_formatters.py`

## CI/CD

GitHub Actions (`.github/workflows/test.yml`):
- **Quality checks** — ruff lint, ruff format, mypy, pytest
- **Matrix** — Python 3.12, 3.14
- **Coverage** — uploaded to Codecov
- **Docker smoke test** — builds and runs tests in container
- **Docs validation** — `validate_docs.py` checks for stale counts

Automated docs backup (`.github/workflows/backup-docs.yml`):
- Syncs `*.md` files to private backup repo on push to main

## Useful Commands

```bash
# Project info
py scripts/project_meta.py          # metadata JSON
py scripts/validate_docs.py         # check for stale doc counts

# Quick iteration
py -m ruff check . --fix && py -m ruff format .   # auto-fix + format
py -m pytest tests/test_client.py -x --tb=short    # fast test cycle

# Git
git log --oneline -20               # recent commits
git tag --list -n1                  # version tags
git diff v0.4.0..HEAD --stat       # changes since last release
```
