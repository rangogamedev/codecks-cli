# CLAUDE.md — codecks-cli

Agent-first CLI + MCP for AI-powered Codecks project management.
Public repo (MIT): https://github.com/rangogamedev/codecks-cli

## Environment
- **Python**: `py` (never `python`/`python3`). Requires 3.12+.
- **Run**: `py codecks_api.py` (no args = help). `--version` for version.
- **Test**: `pwsh -File scripts/run-tests.ps1` (1013+ tests, no API calls)
- **Lint**: `py -m ruff check .` | **Format**: `py -m ruff format --check .`
- **Type check**: `py scripts/quality_gate.py --mypy-only` (targets in `scripts/quality_gate.py:MYPY_TARGETS`)
- **CI**: `.github/workflows/test.yml` — ruff, mypy, pytest (matrix: 3.12, 3.14) + Codecov + Docker smoke. All Actions pinned to commit hashes (Node.js 24).
- **Deps**: `uv sync --extra dev --extra mcp` (uv manages lock file; mcp extra required for test collection). Fallback: `py -m pip install .[dev,mcp]`
- **Lock file**: `uv.lock` — pinned dependency versions, committed to git
- **Dependabot**: `.github/dependabot.yml` — weekly PRs for pip deps, GitHub Actions, and Docker
- **Version**: `VERSION` in `codecks_cli/config.py` + `pyproject.toml` (keep in sync). See `DEVELOPMENT.md` for release process.
- **Tags**: annotated git tags (`v0.1.0`..`v0.5.0`). Create with `git tag -a vX.Y.Z -m "..."`

## Architecture

```
codecks_api.py          <- entry point
codecks_cli/
  cli.py                <- argparse, dispatch, --json/--agent flags
  commands.py           <- cmd_*() wrappers, --stdin batch support
  client.py             <- CodecksClient: 33 public methods
  scaffolding.py        <- scaffold_feature(), split_features() + helpers
  cards.py              <- Card CRUD, hand, conversations, field selection
  api.py                <- HTTP layer
  config.py             <- Env, tokens, constants
  exceptions.py         <- CliError, SetupError, HTTPError
  _utils.py             <- _get_field(), parsers
  types.py              <- TypedDict response shapes
  models.py             <- FeatureSpec, SplitFeaturesSpec dataclasses
  tags.py               <- Tag registry (standalone)
  lanes.py              <- Lane registry (imports tags.py)
  _content.py           <- Content title/body parse, serialize, replace
  _operations.py        <- Shared operations (CLI + MCP business logic)
  _last_result.py       <- Last result caching
  admin.py              <- Admin commands (project/deck/milestone/tag CRUD)
  endpoint_cache.py     <- API endpoint discovery cache
  store.py              <- SQLite storage layer (.pm_store.db)
  formatters/           <- JSON/table/CSV output (7 sub-modules)
  planning.py           <- File-based planning tools
  gdd.py                <- Google OAuth2, GDD sync
  setup_wizard.py       <- Interactive .env bootstrap
  mcp_server/           <- 52 MCP tools (package: _core, _security, _repository, _tools_*)
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

### Agent Mode (v0.5.0)
- `--json` flag forces JSON output for all commands
- `--agent` flag: JSON output + suppress warnings + strict envelope
- `CODECKS_AGENT=1` env var auto-enables agent mode
- `--stdin` on `done`/`start`/`hand`/`unhand`/`update`: read card IDs from stdin pipe
- Pipe workflow: `cards -s started --json | jq '.cards[].id' | done --stdin`

Use `/api-pitfalls` for API gotchas, known bugs, and paid-only restrictions.

## Docker (optional)
Use `/docker` skill for commands, architecture, and troubleshooting.
Quick: `./docker/build.sh` then `./docker/test.sh`, `./docker/quality.sh`, `./docker/cli.sh <cmd>`.
Dockerfile pins Node.js 22 LTS via NodeSource. Non-root user with dropped capabilities.

## MCP Server
- Run: `py -m codecks_cli.mcp_server` (stdio). Install: `py -m pip install .[mcp]`
- 52 tools (down from 55 in v0.4.0, consolidated in v0.5.0). Response mode: `CODECKS_MCP_RESPONSE_MODE=legacy|envelope`
- **Startup**: Call `session_start()` first — returns account, standup, preferences, project context (deck names, tag/lane registries), playbook rules, and `removed_tools` migration guide in one call.
- **Token efficiency** (v0.5.0):
  - `list_cards` omits content by default (only fetched when `search` is set)
  - `pm_focus(summary_only=True)` — counts + deck_health only (~2KB vs ~65KB)
  - `standup(summary_only=True)` — counts only
  - `quick_overview()` — aggregate counts (no card details)
  - `_card_summary()` — 7-field compact card representation for dashboards
- **Composite tools**: `find_and_update()` — search cards then update in 2 calls instead of 5+.
- **Guardrails**: Doc-card guardrail blocks status/priority/effort on doc cards. UUID validation suggests full IDs from cache. Deck name resolution does fuzzy matching.
- **Snapshot cache**: TTL: `CODECKS_CACHE_TTL_SECONDS` (default 60). Cache warming uses `include_content=False` for smaller payloads. Mutations use selective invalidation. Cross-process coherence via mtime checking.
- **Error contract**: Errors include `retryable` (bool) and `error_code` (str) for agent decision-making.
- **Agent teams**: 6 tools — claim/release/delegate cards, team status/dashboard, `partition_cards(by='lane'|'owner')`.
- **Checkboxes**: `tick_checkboxes(all=True)` ticks all checkboxes at once.

### Removed Tools (v0.5.0)
13 tools removed from MCP, data now in `session_start()` or CLI:
`get_pm_playbook`, `get_team_playbook`, `get_tag_registry`, `get_lane_registry`, `planning_*` (4), `*_cli_feedback` (3), `warm_cache`, `cache_status`.
Merged: `partition_by_lane`/`partition_by_owner` → `partition_cards(by=...)`. `tick_all_checkboxes` → `tick_checkboxes(all=True)`.

## SQLite Store (v0.5.0)
- File: `.pm_store.db` (gitignored). Config: `STORE_DB_PATH` in config.py.
- Provides indexed persistence for cards, decks, claims, and metadata.
- FTS5 full-text search on card title/content.
- Additive layer — JSON cache still primary, SQLite is secondary persistence.

## CLI Feedback
Read `.cli_feedback.json` at session start — PM agent reports bugs/improvements there.
Via CLI: `py codecks_api.py feedback list` / `py codecks_api.py feedback save`

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
- `codecks` — this project's own MCP server (52 tools, Codecks API access)
- `context7` — live documentation lookup
- `github` — GitHub issues/PRs integration

## Hooks (`.claude/settings.json`)
- **PreToolUse** `Edit|Write`: blocks edits to `.env` and `.gdd_tokens.json`
- **PostToolUse** `Edit|Write`: auto-formats `.py` with ruff, auto-runs matching tests

## Scripts (`scripts/`)
- `py scripts/quality_gate.py` — all checks (ruff, mypy, pytest). `--skip-tests`, `--fix`, `--mypy-only`.
- `py scripts/project_meta.py` — project metadata JSON.
- `py scripts/validate_docs.py` — checks docs for stale counts.

## Git & Versioning
- Commit style: short present tense ("Add X", "Fix Y")
- Never commit `.env`, `.gdd_tokens.json`, `.gdd_cache.md`, `.pm_store.db*`, `.pm_claims.json`, `.pm_last_result.json`, `.pm_undo.json`
- `.claude/` is gitignored
- Run security-reviewer agent before pushing (public repo)
- **Semver**: version in `config.py` + `pyproject.toml`. Tags: `v0.1.0`..`v0.5.0`
- **Release**: update version in both files, move CHANGELOG unreleased to versioned section, tag, push. Use `/release` skill.
- **Dev docs**: `DEVELOPMENT.md` (setup, architecture, release process), `CONTRIBUTING.md` (contributor guide)
- **Branch protection**: PRs required for main, 1 reviewer, status checks must pass, stale reviews dismissed
- **CODEOWNERS**: `@rangogamedev` required for all file changes
- **Open source**: `CODE_OF_CONDUCT.md`, `.editorconfig`, CI/coverage badges in README

## Security
- **GitHub**: Secret scanning + push protection enabled. Dependabot security updates enabled.
- **Supply chain**: All GitHub Actions pinned to commit hashes with version comments. CODEOWNERS requires maintainer review.
- **Secrets**: `.env`, `.gdd_tokens.json`, `.pm_store.db*`, state files all in `.gitignore`. PR template includes "no secrets" checklist item.
- **Docker**: Non-root user, `no-new-privileges`, all capabilities dropped, PID limit, tmpfs.
- **Tokens**: Session tokens expire. Report tokens rotatable. See `SECURITY.md` for disclosure policy.

## Maintenance
Use `/maintenance` skill for the full checklist. Key points:
- mypy targets: single source of truth in `scripts/quality_gate.py:MYPY_TARGETS`
- Keep `AGENTS.md` in sync when architecture changes
- Add bug patterns to `/api-pitfalls` "Known Bugs Fixed"
- Update project memory at `C:\Users\USER\.claude\projects\C--Users-USER-GitHubDirectory-codecks-cli\memory\MEMORY.md`
- Keep GitHub Actions pinned hashes current — Dependabot auto-PRs when new versions are available
- Keep Node.js version in Dockerfile current (22 LTS via NodeSource, review annually)
- Keep `VERSION` in `config.py` and `pyproject.toml` in sync on every release
- Run `uv lock --upgrade` periodically to refresh transitive dependency versions
