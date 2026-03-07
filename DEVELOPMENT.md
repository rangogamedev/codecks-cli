# Development Guide

Everything you need to set up, build, test, and release codecks-cli.

## Prerequisites

- **Python 3.10+** — use `py` command (never `python` or `python3`)
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

## Quality checks

```bash
# Individual checks
py -m ruff check .                       # lint
py -m ruff format --check .              # format
py scripts/quality_gate.py --mypy-only   # type check
pwsh -File scripts/run-tests.ps1         # 900 tests

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
  client.py             <- CodecksClient: 25 core methods
  scaffolding.py        <- scaffold_feature(), split_features()
  cards.py              <- Card CRUD, hand, conversations
  api.py                <- HTTP layer (retries, timeouts, tokens)
  config.py             <- .env loading, constants, VERSION
  exceptions.py         <- CliError, SetupError, HTTPError
  _content.py           <- Title/body parsing and serialization
  _utils.py             <- Field helpers, parsers
  types.py              <- TypedDict response shapes
  models.py             <- FeatureSpec, SplitFeaturesSpec dataclasses
  tags.py               <- Tag registry (TagDefinition, TAGS)
  lanes.py              <- Lane registry (LaneDefinition, LANES)
  formatters/           <- JSON/table/CSV output (7 sub-modules)
  planning.py           <- File-based planning tools
  gdd.py                <- Google OAuth2, GDD sync
  setup_wizard.py       <- Interactive .env bootstrap
  mcp_server/           <- 55 MCP tools (package)
    __init__.py          <- FastMCP init, registration, re-exports
    __main__.py          <- py -m codecks_cli.mcp_server entry
    _core.py             <- Client cache, dispatcher, snapshot cache
    _security.py         <- Injection detection, sanitization
    _tools_read.py       <- 10 query/dashboard tools
    _tools_write.py      <- 13 mutation/hand/scaffolding tools
    _tools_comments.py   <- 5 comment CRUD tools
    _tools_local.py      <- 15 local tools (PM, feedback, cache)
    _tools_team.py       <- 8 team coordination tools
```

### Request flow

```
CLI:  cli.py -> commands.py -> CodecksClient (client.py) -> cards.py/api.py
MCP:  mcp_server/ -> _core._call() -> CodecksClient -> _core._finalize_tool_result()
```

### Key design decisions

- **Zero runtime dependencies** — stdlib only, dev tools are optional extras
- **AI-agent first** — JSON default output, token-efficient responses
- **Content format** — card title is always first line of `content` field (`"Title\nBody"`)
- **Error prefixes** — `[ERROR]` and `[TOKEN_EXPIRED]` for pattern matching
- **Flat dict returns** — CodecksClient methods return plain dicts, not custom objects
- **Snake/camel compat** — `_get_field()` helper handles both naming conventions

## Testing

### Running tests

```bash
pwsh -File scripts/run-tests.ps1      # full suite (900 tests)
py -m pytest tests/test_client.py -x   # single file, stop on first failure
py -m pytest -k "test_update" -x       # run tests matching pattern
py -m pytest --tb=short                # shorter tracebacks
```

### Test organization

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

### Writing tests

- Mock at module boundaries — no live API calls
- Test patches target sub-modules: `_core.CodecksClient`, `_core.MCP_RESPONSE_MODE`
- Use `conftest.py` fixtures for common setup (cache reset, path patches)
- Follow existing patterns — look at neighboring tests in the same file

## MCP Server

```bash
# Install MCP dependency
uv sync --extra mcp     # or: py -m pip install .[mcp]

# Run (stdio transport)
py -m codecks_cli.mcp_server

# Or via entry point
codecks-mcp
```

55 tools across 5 modules. Call `session_start()` at session start for fast reads and full context.

## Docker (optional)

```bash
./docker/build.sh        # build image
./docker/test.sh         # run tests in container
./docker/quality.sh      # quality checks in container
./docker/cli.sh cards    # run CLI commands
./docker/mcp.sh          # MCP server (stdio)
./docker/shell.sh        # interactive shell
```

Security: non-root user, no-new-privileges, cap_drop ALL, pids_limit 256, tmpfs /tmp:64M.

## Versioning

This project follows [Semantic Versioning](https://semver.org/):

- **MAJOR** (1.0.0) — breaking changes to CLI commands or programmatic API
- **MINOR** (0.x.0) — new features, new commands, new MCP tools
- **PATCH** (0.0.x) — bug fixes, documentation updates, internal refactors

### Version locations

Version is maintained in **two files** (must stay in sync):
- `codecks_cli/config.py` — `VERSION = "x.y.z"` (runtime)
- `pyproject.toml` — `version = "x.y.z"` (packaging)

### Git tags

Every release gets an annotated git tag: `v0.1.0`, `v0.2.0`, etc.

```bash
git tag -a v0.5.0 -m "v0.5.0 - Description of release"
git push origin v0.5.0
```

### Release process

1. **Review changes** — read `[Unreleased]` section in `CHANGELOG.md`
2. **Determine version** — patch, minor, or major based on changes
3. **Update version** in both `config.py` and `pyproject.toml`
4. **Update CHANGELOG** — move `[Unreleased]` entries under new version heading with date
5. **Run quality gate** — `py scripts/quality_gate.py` (must pass clean)
6. **Commit** — `git commit -m "Release v0.5.0"`
7. **Tag** — `git tag -a v0.5.0 -m "v0.5.0 - Summary"`
8. **Push** — `git push && git push --tags`
9. **GitHub Release** (optional) — create release from tag on GitHub

The `/release` and `/changelog` Claude Code skills automate steps 1-8.

## Adding features

### New CLI command

1. `codecks_cli/cli.py` — add argparse subparser
2. `codecks_cli/commands.py` — add `cmd_*()` handler
3. `codecks_cli/client.py` — add business logic method
4. `tests/test_cli.py`, `tests/test_commands.py`, `tests/test_client.py` — add tests
5. `CHANGELOG.md` — add entry under `[Unreleased]`

### New MCP tool

1. `codecks_cli/mcp_server/_tools_*.py` — add function + register in `register()`
2. `codecks_cli/mcp_server/__init__.py` — add to re-exports
3. `tests/test_mcp_server.py` — add tests
4. `CHANGELOG.md` — add entry under `[Unreleased]`

### New formatter

1. `codecks_cli/formatters/_*.py` — add formatter module
2. `codecks_cli/formatters/__init__.py` — add to export list
3. `tests/test_formatters.py` — add tests

## CI/CD

GitHub Actions (`.github/workflows/test.yml`):
- **Quality checks** — ruff lint, ruff format, mypy, pytest
- **Matrix** — Python 3.10, 3.12, 3.14
- **Coverage** — uploaded to Codecov
- **Docker smoke test** — builds and runs tests in container

Automated docs backup (`.github/workflows/backup-docs.yml`):
- Syncs `*.md` files to private backup repo on push to main

## Useful commands

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
