# Changelog

All notable changes to codecks-cli will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.2.0] - 2026-02-19

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

## [0.1.0] - 2026-02-19

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
