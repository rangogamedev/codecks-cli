# CLAUDE.md — codecks-cli

Python CLI + library for managing Codecks project cards. Zero runtime dependencies (stdlib only).
Public repo (MIT): https://github.com/rangogamedev/codecks-cli
Fast navigation map: `PROJECT_INDEX.md`.

## Environment
- **Python**: `py` (never `python`/`python3`). Requires 3.10+.
- **Run**: `py codecks_api.py` (no args = help). `--version` for version.
- **Test**: `pwsh -File scripts/run-tests.ps1` (711 tests, no API calls)
- **Lint**: `py -m ruff check .` | **Format**: `py -m ruff format --check .`
- **Type check**: `py scripts/quality_gate.py --mypy-only` (targets in `scripts/quality_gate.py:MYPY_TARGETS`)
- **CI**: `.github/workflows/test.yml` — ruff, mypy, pytest (matrix: 3.10, 3.12, 3.14)
- **Dev deps**: `py -m pip install .[dev]` (ruff, mypy, pytest-cov in `pyproject.toml`)
- **Version**: `VERSION` in `codecks_cli/config.py` (currently 0.4.0)

## Architecture

```
codecks_api.py          <- entry point
codecks_cli/
  cli.py                <- argparse, dispatch
  commands.py           <- cmd_*() wrappers
  client.py             <- CodecksClient: 25 core methods
  scaffolding.py        <- scaffold_feature(), split_features() + helpers
  cards.py              <- Card CRUD, hand, conversations
  api.py                <- HTTP layer
  config.py             <- Env, tokens, constants
  exceptions.py         <- CliError, SetupError, HTTPError
  _utils.py             <- _get_field(), parsers
  types.py              <- TypedDict response shapes
  models.py             <- FeatureSpec, SplitFeaturesSpec dataclasses
  tags.py               <- Tag registry (standalone)
  lanes.py              <- Lane registry (imports tags.py)
  formatters/           <- JSON/table/CSV output (7 sub-modules)
  planning.py           <- File-based planning tools
  gdd.py                <- Google OAuth2, GDD sync
  setup_wizard.py       <- Interactive .env bootstrap
  mcp_server/            <- 38 MCP tools (package: _core, _security, _tools_*)
```

Use `/architecture` for full details, import graph, and design patterns.

## Programmatic API
```python
from codecks_cli import CodecksClient
client = CodecksClient()
cards = client.list_cards(status="started", sort="priority")
```

## Tokens (`.env`, never committed)
- `CODECKS_TOKEN` — session cookie, **expires**. Empty 200 = expired.
- `CODECKS_REPORT_TOKEN` — card creation, never expires.
- `CODECKS_ACCESS_KEY` — generates report tokens, never expires.
- `CODECKS_USER_ID` — hand operations. Auto-discovered if unset.

## Commands
Use `py codecks_api.py <cmd> --help` for flags. Full reference: `/api-ref` skill.
- Common flags have short aliases: `-d` (deck), `-s` (status), `-p` (priority), `-S` (search), `-e` (effort), `-c` (content).
- `cards` supports `--limit <n>` and `--offset <n>` (client-side pagination).
- `card` supports `--no-content` and `--no-conversations` for metadata-only lookups.
- `update` supports `--continue-on-error` for partial batch updates. Effort accepts positive int or `"null"`.
- `create` supports `--parent <id>` for sub-cards.
- `tags` lists project-level tags (masterTags).
- `split-features` batch-splits feature cards (use `--dry-run` first).

Use `/api-pitfalls` for API gotchas, known bugs, and paid-only restrictions.

## Docker (optional)
Use `/docker` skill for commands, architecture, and troubleshooting.
Quick: `./docker/build.sh` then `./docker/test.sh`, `./docker/quality.sh`, `./docker/cli.sh <cmd>`.

## MCP Server
- Run: `py -m codecks_cli.mcp_server` (stdio). Install: `py -m pip install .[mcp]`
- 38 tools. Response mode: `CODECKS_MCP_RESPONSE_MODE=legacy|envelope`
- Standalone wrapper repos archived (unnecessary — use `py -m codecks_cli.mcp_server` directly)

## CLI Feedback
Read `.cli_feedback.json` at session start — PM agent reports bugs/improvements there.
Via MCP: `get_cli_feedback()` / `get_cli_feedback(category="bug")`

## Skills (`.claude/commands/`)
`/pm`, `/release`, `/api-ref`, `/codecks-docs <topic>`, `/quality`, `/mcp-validate`, `/troubleshoot`, `/split-features`, `/doc-update`, `/changelog`, `/docker`, `/registry`, `/architecture`, `/api-pitfalls`, `/maintenance`

## Subagents (`.claude/agents/`)
- `security-reviewer` — credential exposure, injection vulns, unsafe patterns
- `test-runner` — full test suite

## Context7 Library IDs (pre-resolved)
Always use Context7 MCP for library/API docs. These IDs are pre-resolved — skip the resolve step.

| Library | Context7 ID |
|---------|-------------|
| MCP SDK (Python) | `/modelcontextprotocol/python-sdk` |
| pytest | `/pytest-dev/pytest` |
| ruff | `/websites/astral_sh_ruff` |
| mypy | `/websites/mypy_readthedocs_io_en` |

## MCP Servers (`.claude/settings.json`)
- `codecks` — this project's own MCP server (38 tools, Codecks API access)
- `context7` — live documentation lookup
- `github` — GitHub issues/PRs integration

## Hooks (`.claude/settings.json`)
- **PreToolUse** `Edit|Write`: blocks edits to `.env` and `.gdd_tokens.json`
- **PostToolUse** `Edit|Write`: auto-formats `.py` with ruff, auto-runs matching tests

## Scripts (`scripts/`)
- `py scripts/quality_gate.py` — all checks (ruff, mypy, pytest). `--skip-tests`, `--fix`, `--mypy-only`.
- `py scripts/project_meta.py` — project metadata JSON.
- `py scripts/validate_docs.py` — checks docs for stale counts.

## Git
- Commit style: short present tense ("Add X", "Fix Y")
- Never commit `.env`, `.gdd_tokens.json`, `.gdd_cache.md`
- `.claude/` is gitignored
- Run security-reviewer agent before pushing (public repo)

## Maintenance
Use `/maintenance` skill for the full checklist. Key points:
- mypy targets: single source of truth in `scripts/quality_gate.py:MYPY_TARGETS`
- Keep `AGENTS.md` in sync when architecture changes
- Add bug patterns to `/api-pitfalls` "Known Bugs Fixed"
- Update project memory at `C:\Users\USER\.claude\projects\C--Users-USER-GitHubDirectory-codecks-cli\memory\MEMORY.md`
