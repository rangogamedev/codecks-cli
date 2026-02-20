# Changelog

All notable changes to codecks-cli will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.4.0] - 2026-02-19

### Added
- `setup` command — interactive setup wizard for new and returning users
  - Auto-discovers projects from deck data and prompts for names
  - Auto-discovers milestones from card data with sample titles to help identify
  - Validates session token with retry (up to 3 attempts)
  - Auto-generates report token if access key is provided
  - Optional GDD URL configuration
  - Returning users get a menu: refresh mappings, update token, or full setup
- Automatic token validation on every API command
  - Catches expired tokens immediately with clear instructions
  - `[SETUP_NEEDED]` prefix when no configuration found
  - Skips check for commands that don't need the session token
- `--version` flag to show current version
- `--format csv` output format on card listings
- `--milestone` filter on `cards` command
- `--quiet` flag on `gdd-sync` to suppress per-item listings
- Input validation for `--status` and `--priority` values with helpful error messages
- Priority labels in table output (high/med/low instead of a/b/c)
- Helpful error messages that list available options (decks, projects, milestones, statuses)
- Unmatched GDD section warning in sync reports

### Fixed
- `account --format table` now shows formatted output instead of raw JSON
- `cards --status started` no longer shows false TOKEN_EXPIRED warning when 0 cards match

### Changed
- Version bumped to 0.4.0

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
