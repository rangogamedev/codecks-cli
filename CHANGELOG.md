# Changelog

All notable changes to codecks-cli will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security
- MCP HTTP runner (`scripts/run_mcp_http.py`) binds `127.0.0.1` by default instead of `0.0.0.0`, and the `mcp-http` Compose service publishes its port on loopback only (`127.0.0.1:${MCP_HTTP_PORT:-8808}:8808`) while setting `MCP_HTTP_HOST=0.0.0.0` inside the container. The MCP SDK only auto-enables DNS-rebinding (Host/Origin) protection for loopback binds, so a non-loopback `MCP_HTTP_HOST` now gets explicit `TransportSecuritySettings` built from `MCP_HTTP_ALLOWED_HOSTS` / `MCP_HTTP_ALLOWED_ORIGINS` (defaults `localhost:*,127.0.0.1:*,[::1]:*` and `http://localhost:*,http://127.0.0.1:*,http://[::1]:*`, mirroring the SDK's own loopback allowlists — IPv6 loopback included).
- `.gitignore` covers the atomic-write temp files (`.gdd_tmp_*`, `.env_tmp_*`, `tmp*.tmp`) that a crash can leave behind holding `.env` contents or a Google refresh token.
- Multipart upload fields from the `/s3/sign` response are validated before use: CR/LF in a field name or value is refused, and field names get the same backslash/quote escaping as the file name. `build_multipart_body` re-checks the file name for CR/LF defensively.
- `CODECKS_ATTACH_ALLOW_DIRS` entries that are not absolute paths, are not existing directories, or name a whole filesystem root are skipped with a warning instead of silently widening the attachment allowlist to everything.

### Added
- AI-agent guide, reusable example skills, and MCP prompts for PM sessions and setup.
- Attachment support: `create --file`, new `attach` command, `CodecksClient.attach_files()`, and MCP `attach_files` tool using stdlib multipart uploads.
- `attach_files` `dry_run` flag (MCP tool, `CodecksClient.attach_files()`, and the CLI's global `--dry-run` on `attach`) — validates every path and reports resolved path, size, and SHA-256 without uploading.
- `CODECKS_ATTACH_ALLOW_DIRS` environment variable — `os.pathsep`-separated extra roots that attachments may be read from, on top of the project root.
- `failed` list (`{card_id, error}` per card) in `batch_delete_cards`, `batch_archive_cards`, and `batch_unarchive_cards` results.

### Changed
- Dependency audit + full lock refresh to latest (`mcp` 1.27→1.28→2.1, `pytest` 9.0.3→9.1→9.1.1, `ruff` 0.15.13→0.15.17→0.16.5, `mypy` 1.20→2.1→2.3.1, `coverage` 7.14→7.16, Docker `uv` 0.11.6→0.12.9, GitHub Action `setup-uv` v9→v10.0.1, `python:3.14-slim` digest refresh, plus transitives — `httpx` replaced by `httpx2`, `pydantic-settings` dropped, `mcp-types` and `opentelemetry-api` added).
- MCP SDK v2 migration: `FastMCP` → `MCPServer`; `scripts/run_mcp_http.py` now passes host/port to `run()`.
- `create_tag` MCP tool drops the unsupported `color` parameter — the `projects/addTag` dispatch endpoint has no color field, so it was validated and documented but never sent.
- Attachments: the current working directory is an allowed root alongside the project root — a pip-installed package's project root is `site-packages`, which holds nothing shareable. `SECURITY.md` now also states the limit of the policy: it constrains an agent restricted to the CLI/MCP tools, not one that can also write files into an allowed root.
- Version bumped to 0.5.1.
- MCP SDK dev console (`mcp[cli]`) moved from the shipped `mcp` extra to the `dev` extra — end-user `pip install codecks-cli[mcp]` is now slim (drops `typer`, `rich`, `shellingham`, `pygments`, `markdown-it-py`, `mdurl`); developers keep `mcp dev` via the `dev` extra.
- Dockerfile installs dev+mcp dependencies from the committed `uv.lock` via `uv export` instead of a hardcoded version list — `pyproject.toml`/`uv.lock` are now the single source of truth (no version drift).

### Fixed
- Thread safety under MCP SDK v2: the SDK runs synchronous tool functions on a worker-thread pool (v1 ran them inline on the event loop), so the unguarded module globals in `mcp_server/_core.py` (client/store singletons, snapshot cache, batch flag, rate-limit timestamps, agent claims) and the `CardRepository` indexes could interleave. `_core` now has a module-level `RLock` around every state mutation — never held across a Codecks API request — `CardRepository` has its own `RLock` and returns snapshot copies from its read accessors, and the `.pm_undo.json` read-modify-write is serialized.
- MCP `attach_files(dry_run=True)` built a `CodecksClient` (and therefore validated the session token over the network) just to preview paths — it now runs the path policy locally via `preview_attachment_files()`, so a preview needs neither a token nor a network call.
- `gdd._write_private_file` leaked the `mkstemp` descriptor if `os.fdopen` raised, and the Google OAuth callback `HTTPServer` was constructed outside the `try:` whose `finally` closes it — both now close on every path.
- `batch_delete_cards` / `batch_archive_cards` / `batch_unarchive_cards` hardcoded `ok: true` even when every card failed — `ok` now reflects whether all cards succeeded, and a `failed` list names each failure.
- `undo` used truthiness when restoring a snapshot, so a card whose `status`/`priority`/`effort` had been empty was reported as reverted while keeping the new value — empty fields are now restored with the `"null"` clear sentinel (`CodecksClient.update_cards` learned `status="null"` to match `priority`/`effort`).
- `archive_deck` (MCP tool) and `CodecksClient.archive_deck_admin` documented themselves as "reversible" while dispatching `decks/delete` — docstrings and docs now say the deck is deleted and cannot be restored (cards are preserved). Tool name unchanged.
- `session_start().removed_tools` pointed at CLI commands that do not exist — no `plan` subcommand (planning is the `codecks_cli.planning` Python API), `feedback save` filed the literal word "save" (`feedback` takes a positional message), and `cache status` is `cache --show`.
- `.gdd_tokens.json` and `.gdd_cache.md` were created with the default umask and only chmod'ed afterwards, leaving a window in which the refresh token was world-readable — both now use the `mkstemp` + `os.replace` pattern already used for `.env`.
- SQLite WAL sidecars (`.pm_store.db-wal` / `-shm`) are now explicitly chmod'ed to 0600 after the `journal_mode=WAL` pragma instead of relying on SQLite copying the DB file's mode.
- Google OAuth callback bound port 0 on a throwaway socket and only created the `HTTPServer` later, leaving a window for another process to take the port — the server is now bound first and the redirect URI reads its actual port.
- `sync_gdd --apply` built its seen-titles map once, so a title repeated inside one GDD created duplicate cards — newly created titles are registered as they are created.
- `attach_files` hardening: paths are resolved (symlinks followed) and must land inside an allowed root; dot-prefixed components, credential-looking basenames (`*.pem`, `*.key`, `id_rsa*`, `id_ed25519*`, `*token*`, `*secret*`) and `/etc`, `/proc`, `/sys` are always refused; file names containing `"`, CR, or LF are rejected and backslashes/quotes are escaped in the multipart `Content-Disposition` header.
- `scripts/project_meta.py` read the removed `codecks_cli/mcp_server.py` module and always reported 0 MCP tools, and its source-module count omitted `mcp_server/` — both now walk the package (53 tools).
- `scripts/validate_docs.py --fix` stored issue locations as bare basenames, so every file under `docs/` (and `.claude/`, `.github/`) was silently skipped while still being counted as "fixed" — locations are now repo-relative.
- `docker/build.sh` passed `--build-arg PYTHON_VERSION` to a Dockerfile with no such `ARG` (the base image is digest-pinned) — the dead argument and its `DEVELOPMENT.md` line are gone.
- Cached-card filters in `list_cards` (MCP) now match the flattened keys that `CodecksClient.list_cards()` actually emits (`deck_name`, `owner_name`, `milestone_name`, `lastUpdatedAt`), so `deck`, `owner`, `owner=none`, `milestone`, `stale_days`, `updated_after` and `updated_before` no longer return empty or wrong results when served from cache.
- Cards with no timestamp are no longer counted as infinitely stale by `stale_days`, and no longer silently dropped from `updated_after` matches.
- `sort` by `deck`, `owner` or `updated` no longer degrades to insertion order on cached cards.
- `project` filters resolve a card's deck to its project instead of reading a `project` key that flattened cards never carry — affects `list_cards`, `quick_overview`, `partition_cards`, `partition_by_lane`, `partition_by_owner` and `team_dashboard`.
- `quick_overview` reports a real `stale_count` and a real `deck_summary` instead of `0` and `unassigned`.
- `isDoc` is now part of the list field set, so the MCP doc-card guardrail fires `DOC_CARD_VIOLATION` from a warmed cache instead of letting status/priority/effort updates through to doc cards.
- `CodecksClient.pm_focus()` echoes the requested `owner` in `filters.owner` instead of the last processed card's owner.
- `admin.create_deck()` actually seeds the new deck into the deck cache, so an immediately following `resolve_deck_id()` finds it; the duplicate check also reads `project_id`/`projectId` in either spelling.
- `tags.sync_from_api()` queries `masterTags` under `account` and reads the `title` field, so live tag sync no longer returns zero tags.
- Concurrency hardening after the SDK v2 thread-pool review: the MCP rate limiter now prunes, checks the window and reserves its slot in a single critical section (splitting them let N threads each see room and over-admit); the batch flag that suppresses per-mutation disk writes is a depth counter, so two overlapping batches no longer clear each other's flag; `undo` reads *and* removes `.pm_undo.json` under one lock, so a snapshot written by a concurrent mutation is never the one deleted; and the undo snapshot writer closes its `mkstemp` descriptor when `os.fdopen` raises.
- Attachment roots: the default roots (project root and working directory) now go through the same validation as `CODECKS_ATTACH_ALLOW_DIRS` entries, so a client that launches the MCP server with `/` as its working directory no longer makes the whole disk attachable.

### Removed
- Unused `admin` extra (Playwright) and the orphaned Playwright-era dead code: `playwright_admin.py`, `playwright_selectors.json`, and `endpoint_cache.py` (admin operations use the dispatch API; these were imported nowhere). Removes `playwright`, `pyee`, `greenlet` from the lock.

### Security
- Refreshed security-relevant transitive dependencies: `cryptography` 46.0.7 → 49.0.0 → 50.0.1, `starlette` 1.0.0 → 1.3.1 → 1.6.0, `python-multipart` 0.0.29 → 0.0.32, `pyjwt` 2.12.1 → 2.13.0, `certifi` 2026.2.25 → 2026.5.20 → 2026.7.22, `pip` 26.1.2 → 26.2.1 (PYSEC-2026-3721). `urllib3` and `requests` unchanged.
- Attachment path allowlist (project root + `CODECKS_ATTACH_ALLOW_DIRS`) plus a credential denylist, closing an exfiltration path for a prompt-injected agent; multipart header-injection fix for crafted file names.
- Token, cache, and SQLite WAL sidecar files are created owner-only (0600) with no world-readable window.

## [0.5.1] - 2026-04-12

### Added
- `partition_cards` `max_cards_per_group` parameter (default 10, 0=unlimited) — caps cards per partition group, priority-sorted, with `total_in_group` and `truncated` metadata
- `team_dashboard` `summary_only` parameter — returns counts only (~2KB vs ~45KB)
- 25 new tests: batch operations, `tick_checkboxes` both checkbox formats, `find_and_update` dry_run, partition fields, team_dashboard summary_only, list_activity entity trimming
- `validate_docs.py --fix` flag auto-repairs stale counts in doc files
- `validate_docs.py` scans ALL `.md` files for count mismatches — 8 checks total (up from 6)
- `docs/cli-reference.md` — full CLI command reference (extracted from README)
- `docs/mcp-reference.md` — full MCP tool inventory and agent patterns

### Changed
- `tick_checkboxes` MCP tool delegates to `_operations.py` (removed 180 lines of duplicated regex logic)
- `batch_delete_cards`, `batch_archive_cards`, `batch_unarchive_cards` use shared `_batch_single_card_op` helper
- `list_activity` strips orphaned entity references and account key after limit trim (224KB → 2.8KB for limit=5)
- `create_card` resolves deck/project BEFORE creating card (prevents orphaned cards on resolution failure)
- MCP server instructions expanded with token efficiency defaults for `partition_cards`, `team_dashboard`, `get_card`
- Documentation restructured: each fact in one canonical location (README condensed to ~140 lines, references split to docs/)
- Minimum Python version raised from 3.10 to 3.12; CI matrix reduced to 2 versions (3.12, 3.14)
- `from __future__ import annotations` removed from all files (no longer needed with 3.12+ floor)
- Dependency versions bumped: pytest >=9.0.3, pytest-cov >=7.1.0, ruff >=0.15.10, mcp >=1.27.0, setuptools >=82.0.1
- mypy expanded to all 41 source modules (up from 15)
- Return type annotations added to core MCP dispatcher; parameter types to config helpers

### Fixed
- `resolve_deck_id` project filter: used `deck.get("projectId")` but API returns `project_id` (snake_case) — deck resolution with `project=` always failed
- `find_and_update` Phase 2 passed `dry_run` to `CodecksClient.update_cards()` which doesn't accept it — now handles dry_run locally
- Checkbox regex in 5 locations: `\[\]` only matched `- []`, not `- [ ]` (standard Markdown) — changed to `\[ ?\]`
- `tick_checkboxes` shadowing builtin `all()` with parameter name (latent bug)
- `CardRepository.update_card` null status handling in status index
- `rich` transitive dependency updated 14.3.4 → 15.0.0

### Removed
- `HANDOFF.md` — stale session handoff doc, redundant with DEVELOPMENT.md + CHANGELOG
- `PROJECT_INDEX.md` — navigation map, redundant with CLAUDE.md architecture section

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
