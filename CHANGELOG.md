# Changelog

All notable changes to codecks-cli will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Bump minimum dependency versions: pytest >=9.0.3, pytest-cov >=7.1.0, ruff >=0.15.10, mcp >=1.27.0, setuptools >=82.0.1
- Expand mypy type checking to all source modules (41 files, up from 15) — covers MCP server, config, CLI, store, GDD, admin, operations
- Add return type annotations to core MCP dispatcher (`_call`, `_contract_error`, `_ensure_contract_dict`, `_finalize_tool_result`)
- Add parameter type annotations to config helpers (`_env_int`, `_env_float`, `_env_bool`)
- Fix `tick_checkboxes` shadowing builtin `all()` with parameter name (latent bug)
- Fix `CardRepository.update_card` null status handling in status index

### Fixed
- Updated `rich` transitive dependency 14.3.4 → 15.0.0

## [0.5.0] - 2026-04-12

### Added
- `session_start` MCP tool — one-call session initialization (replaces 5 startup calls: warm_cache + standup + get_account + get_workflow_preferences + project context)
- `find_and_update` MCP tool — two-phase search+update (search cards, confirm matches, apply updates in 2 calls instead of 5+)
- `quick_overview` MCP tool — aggregate project dashboard (counts by status/priority, effort stats, deck summary, no card details = minimal tokens)
- Effort filters on `list_cards` MCP tool — `effort_min`, `effort_max`, `has_effort` params
- Doc-card guardrail — `update_cards` rejects status/priority/effort on doc cards with clear error (DOC_CARD_VIOLATION)
- UUID short-ID hints — validation error suggests full UUID from cache when agent sends 8-char short ID
- Deck fuzzy matching — `resolve_deck_id` suggests closest match with "Did you mean 'X'?" on failure
- `--parent <id>` flag on `create` command — nest new cards as sub-cards under a parent card
  - Also exposed via MCP `create_card` tool (`parent` parameter)
- `split-features` command — batch-split feature cards into Code/Design/Art/Audio sub-cards
  - `--dry-run` to preview without creating cards
  - Audio lane opt-in via `--audio-deck`
- `tags` command — list project-level tags (masterTags)
- `pm-focus` command — PM-optimized dashboard with actionable insights
- `standup` command — daily standup summary
- CLI short flags: `-d` (deck), `-s` (status), `-p` (priority), `-S` (search), `-e` (effort), `-c` (content)
- `--continue-on-error` on `update` — partial batch updates
- `--no-content` / `--no-conversations` on `card` — metadata-only lookups
- `--limit` / `--offset` on `cards` — client-side pagination
- Content parsing helper module (`_content.py`) — single source of truth for title/body parsing
- `update_card_body` MCP tool — update card body without touching title
- Docker development environment with security hardening
- Automated docs backup workflow (GitHub Actions)
- Response contracts — `schema_version`, `ok`, `error_detail` on all MCP/CLI responses
- In-memory snapshot cache for MCP server — `warm_cache()` for instant reads (<50ms)
  - Selective cache invalidation (only affected keys cleared on mutations)
  - Cache stale warnings when age exceeds 80% of TTL
- Error classification in MCP responses — `retryable` and `error_code` fields
- Agent team coordination — 8 MCP tools for multi-agent work
  - `claim_card` / `release_card` / `delegate_card` — card ownership
  - `team_status` / `team_dashboard` — health and workload views
  - `partition_by_lane` / `partition_by_owner` — work division
  - `get_team_playbook` — agent team methodology
- MCP prompt injection detection and input sanitization
- PM planning tools (4 tools: init, update, measure, status)
- Tag and lane registry tools — introspect project taxonomy via MCP
- CLI feedback system — `save_cli_feedback` / `get_cli_feedback` / `clear_cli_feedback`
- uv for dependency management (`uv.lock` committed)
- SQLite persistent store (`store.py`) — `CardStore` with FTS5 full-text search, indexed queries, thread-safe operations
- `CardRepository` (`_repository.py`) — O(1) card lookups by ID, status, deck, owner
- Token diet optimization — `_card_summary()` (7-field slim format), `_slim_card_list()`, `summary_only` on `pm_focus`/`standup`
- Rate limiting — 40 req/5s Codecks API limit enforcement with headroom tracking
- `batch_create_cards` MCP tool (max 20 per call, idempotent)
- `batch_archive_cards`, `batch_delete_cards`, `batch_unarchive_cards` MCP tools
- `batch_update_bodies` MCP tool
- `include_content` parameter on `list_cards` (default False, True when searching)
- Cross-process cache coherence via mtime checking
- `.github/CODEOWNERS` for required maintainer review
- GitHub Actions pinned to commit hashes (supply chain hardening)

### Changed
- MCP server refactored from single file to package (7 sub-modules, 55 tools)
  - `_core.py` — client caching, dispatcher, response contract, snapshot cache, UUID hints
  - `_security.py` — injection detection, sanitization, validation
  - `_tools_read.py` (11), `_tools_write.py` (15), `_tools_comments.py` (5)
  - `_tools_local.py` (16), `_tools_team.py` (8)
- `scaffolding.py` extracted from `client.py` — scaffold/split logic isolated
- `tags.py` — standalone tag registry (TagDefinition, TAGS, helpers)
- `lanes.py` — standalone lane registry (LaneDefinition, LANES, helpers)
- `models.py` — dataclasses for payload contracts (FeatureSpec, SplitFeaturesSpec)
- `client.py` content handling refactored to use `_content.py` helpers
- CI matrix expanded to Python 3.10, 3.12, 3.14
- mypy targets centralized in `scripts/quality_gate.py`
- Test suite grown from 588 to 1013 tests across 20 files
- MCP tools: 52 registered (13 removed, new batch/overview/team/admin tools added)
- Cache TTL reduced from 300s to 60s
- `session_start()` returns removed-tools migration guide + project context
- Batch operations suppress disk writes until completion

### Removed
- 13 MCP tools (registry, playbook, planning, feedback, cache tools) — data now in `session_start()` or CLI

### Fixed
- Title duplication in `update_cards` when content already included the existing title
- `list_tags` API 500 — MCP tool falls back to local tag registry
- `severity` field API 500 — removed from card queries
- `isArchived` field API 500 — use `visibility` field instead
- Docker MCP HTTP binding and compose build
- Resolved 36 ruff lint errors (import sorting, missing `_core` import, E402 violations)
- Resolved 12 mypy type errors across 5 files
- Docker basetemp: use `/tmp` for non-root container user
- CI: install `--extra mcp` for test collection, `mkdir -p .tmp` for basetemp
- Filter deleted/archived projects from deck listing and setup (ported from community PR #7)
- Updated vulnerable transitive deps: cryptography 46.0.7, Pygments 2.20.0, PyJWT 2.12.1
- Upgraded GitHub Actions to Node.js 24: checkout v6.0.2, setup-uv v8.0.0, setup-python v6.2.0, codecov v6.0.0
- Added CODE_OF_CONDUCT.md, .editorconfig, CI/coverage badges, CODEOWNERS
- Dockerfile: pinned Node.js 22 LTS via NodeSource
- Dependabot: added docker ecosystem monitoring
- Secret scanning, push protection, branch protection enabled on GitHub
- Added `validate_docs.py` step to CI quality gate

## [0.4.0] - 2026-02-19

### Added
- `setup` command — interactive setup wizard for new and returning users
  - Auto-discovers projects from deck data and prompts for names
  - Auto-discovers milestones from card data with sample titles to help identify
  - Validates session token with retry (up to 3 attempts)
  - Auto-generates report token if access key is provided
  - Optional GDD URL configuration
  - Returning users get a menu: refresh mappings, update token, or full setup
- `CodecksClient` class (`client.py`) — 27 public methods, keyword-only args, flat dict returns
  - Full programmatic API: read, create, update, archive, hand, comments, raw queries
  - `py.typed` marker for PEP 561 editor support
- MCP server (`mcp_server.py`) — 28 tools wrapping CodecksClient via FastMCP (stdio transport)
  - 25 tools mapping 1:1 to CodecksClient methods
  - 3 PM session tools: `get_pm_playbook`, `get_workflow_preferences`, `save_workflow_preferences`
  - PM playbook (`pm_playbook.md`) — agent-agnostic PM methodology readable via MCP
  - Literal types for enum params (status, priority, sort, card_type, severity)
  - Pagination on `list_cards` (limit/offset, default 50)
  - Cached client instance reused across tool calls
  - Agent-friendly docstrings with "when to use" hints and return shapes
  - Install: `pip install .[mcp]`, run: `codecks-mcp` or `py -m codecks_cli.mcp_server`
- `--dry-run` flag — preview mutations without executing
- `--quiet` / `-q` flag — suppress confirmations and warnings
- `--verbose` / `-v` flag — enable HTTP request logging
- `--version` flag to show current version
- `--format csv` output format on card listings
- `--milestone` filter on `cards` command
- `completion` command — shell completions for bash, zsh, and fish
- Input validation for `--status` and `--priority` values with helpful error messages
- Priority labels in table output (high/med/low instead of a/b/c)
- Helpful error messages that list available options (decks, projects, milestones, statuses)
- Unmatched GDD section warning in sync reports

### Changed
- Architecture refactored into clean module hierarchy:
  - `exceptions.py` — all exception classes (`CliError`, `SetupError`, `HTTPError`)
  - `_utils.py` — pure utility helpers (`_get_field`, `get_card_tags`, parsers)
  - `formatters/` — package with 7 sub-modules, `__init__.py` re-exports all 24 names
  - `types.py` — TypedDict response shapes for documentation and consumers
- `commands.py` thinned to delegate all business logic to `CodecksClient`
- CLI dispatch uses `set_defaults(func=cmd_xxx)` per subparser (no DISPATCH dict)
- Client and MCP layer optimized for AI token efficiency (stripped metadata, cached lookups)

### Fixed
- `account --format table` now shows formatted output instead of raw JSON
- `cards --status started` no longer shows false TOKEN_EXPIRED warning when 0 cards match

## [0.3.0] - 2026-02-18

### Added
- Google OAuth2 for private Google Docs — no more browser extraction needed
  - `gdd-auth` command — one-time authorization flow (opens browser)
  - `gdd-revoke` command — revoke access and delete local tokens
  - Auto-refreshing access tokens (silent, no user interaction)
  - Falls back to public URL if OAuth not configured
- Zero cost: uses free Google Drive API (no billing or credit card required)

### Changed
- `fetch_gdd()` now tries OAuth Bearer token first, then public URL, then cache
- Improved error messages with setup instructions for private doc access

### Removed
- `gdd-url` command (replaced by direct OAuth access)
- Browser extraction workflow (replaced by OAuth2)

## [0.2.0] - 2026-02-17

### Added
- `gdd` command — fetch and parse a Game Design Document from Google Docs or local file
  - `--refresh` to force re-fetch from Google (ignores cache)
  - `--file <path>` to use a local markdown file instead
  - `--file -` to read from stdin (for AI agents piping via MCP)
  - `--format table` for human-readable task tree
- `gdd-sync` command — sync GDD tasks to Codecks cards
  - `--project <name>` (required) target project for card placement
  - `--section <name>` to sync only one GDD section
  - `--apply` flag required to create cards (dry-run by default)
  - Fuzzy title matching to detect already-tracked tasks
  - Auto-resolves deck names from GDD section headings
  - Sets priority and effort from `[P:a]` and `[E:5]` tags
- GDD markdown convention: `## Heading` → deck, `- bullet` → card, indented bullets → description
- Combined tag support: `[P:a E:8]` in a single bracket pair
- Local `.gdd_cache.md` cache for offline/faster access
- `gdd-url` command to print the export URL (for browser-based extraction of private docs)
- `--save-cache` flag on `gdd` and `gdd-sync` to cache stdin/file content for offline use
- Browser extraction workflow for private Google Docs (via Claude in Chrome)
- Four options for private Google Docs: browser extraction, local file, stdin piping, link-only sharing

## [0.1.0] - 2026-02-16

Initial public release.

### Added
- `cards` command with filtering by deck, status, project, and text search
- `card <id>` for detailed single-card view with sub-cards
- `create` command with `--deck`, `--project`, `--content`, `--severity` options
- `update` command for status, priority, effort, deck, title, content, milestone, and hero card
- `archive` / `remove` for reversible card removal
- `unarchive` to restore archived cards
- `delete --confirm` for permanent deletion with safety guard
- `done` and `start` for bulk status changes
- `decks`, `projects`, `milestones` listing commands
- `--format table` for human-readable output on all read commands
- `--stats` for card count summaries by status, priority, and deck
- `generate-token` for report token management
- `query` and `dispatch` for raw API access
- Token expiry detection with `[TOKEN_EXPIRED]` prefix
- Error messages with `[ERROR]` prefix for agent pattern-matching
- 30-second HTTP timeout on all requests
- Deck lookup caching to minimize API calls
- Card list output optimized for AI agent token efficiency

[Unreleased]: https://github.com/rangogamedev/codecks-cli/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/rangogamedev/codecks-cli/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/rangogamedev/codecks-cli/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/rangogamedev/codecks-cli/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/rangogamedev/codecks-cli/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/rangogamedev/codecks-cli/releases/tag/v0.1.0
