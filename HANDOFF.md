# HANDOFF.md — codecks-cli

Quick context for any AI agent or contributor picking up this project.

**Reading order:** `HANDOFF.md` (you are here) -> `CLAUDE.md` -> `PROJECT_INDEX.md` -> `PM_AGENT_WORKFLOW.md`

Last updated: 2026-02-20 | Version: 0.4.0 | Tests: 328 | HEAD: `0b17ad0`

## Project Summary

Python CLI (stdlib only, zero dependencies) for managing [Codecks](https://codecks.io) project cards. Designed for AI agent consumption (JSON default) with human-readable table output. MIT licensed.

- **Run:** `py codecks_api.py` (help) | `py codecks_api.py --version`
- **Test:** `pwsh -File scripts/run-tests.ps1` (328 unit tests, no API calls)
- **Python:** `py` command (never `python` or `python3`), requires 3.10+

## Safety: Paid-Only Constraints

These constraints must be respected by all agents and contributors:

- **Never set `dueAt` or any date/deadline field on cards.** Due dates are a paid-only feature. Do not include deadlines in card creation or update workflows.
- The `--stale`, `--updated-after`, and `--updated-before` flags only **read** existing `lastUpdatedAt` timestamps for filtering. They never write any date field.
- **Doc cards** cannot have `--status`, `--priority`, or `--effort` set (API returns 400). Only owner, tags, milestone, deck, title, content, and hero can be set.
- Other paid-only features (do NOT use): Dependencies, Time tracking, Runs/Capacity, Guardians, Beast Cards, Vision Board Smart Nodes.

## What Was Completed

### Latest Update — Duplicate Title Guardrails

- Added lightweight duplicate preflight checks to `create` and `feature`:
  exact title collisions now fail by default to prevent accidental duplicate cards.
- Added `--allow-duplicate` to both commands to keep intentional duplicate workflows possible.
- Added similar-title warnings (non-blocking) for better operator awareness.
- Added parser/model/command coverage for duplicate detection paths.
- Test suite now: **328 passing** (`C:\Users\USER\AppData\Local\Python\bin\python.exe -m pytest tests/ -q`).

### Latest Update — Post-223b1d2 Reliability Fixes

Committed and pushed in `b4ea42c`:

- Preserved `SetupError` semantics in `feature` rollback flow (`commands.py`):
  rollback still runs, but token/setup failures keep exit-code-2 behavior.
- Fixed `_get_field()` falsy-value handling (`cards.py`):
  snake_case value now wins by key presence (not truthiness), preventing `False`/`0` bugs.
- Consolidated activity limit behavior:
  `list_activity(limit)` now owns trimming; duplicate trimming removed from `cmd_activity`.
- Added regression tests:
  - `tests/test_commands.py`: rollback `SetupError` preservation + activity limit forwarding
  - `tests/test_cards.py`: `_get_field` key precedence and falsy behavior

Validation status for this update:

- Targeted suites pass (`101 passed` for `tests/test_commands.py` + `tests/test_cards.py`).
- Full suite should be executed via `pwsh -File scripts/run-tests.ps1`, which pins temp paths to `.tmp/` and uses per-run pytest temp dirs to reduce lock/permission failures.

### Phase 3 — Code Quality Hardening

6 critical + 9 medium fixes across all modules.

| Type | Fix | Commit |
|------|-----|--------|
| Critical | Safe `.env` parsing (malformed lines, whitespace, edge cases) | `c3816e1` |
| Critical | Response size cap (5 MB default, `CODECKS_HTTP_MAX_RESPONSE_BYTES`) | `c3816e1` |
| Critical | Exception chaining (`raise ... from e`) in date parsing | `2168cd5` |
| Critical | Atomic `.env` writes via `tempfile.mkstemp()` + `os.replace()` | `2168cd5` |
| Critical | HTTP Content-Type check on parse failure (proxy/HTML detection) | `c3816e1` |
| Critical | Strict JSON response shape enforcement in query/dispatch | `c3816e1` |
| Medium | `_get_field(d, snake, camel)` helper — DRY snake/camelCase lookups | `2168cd5` |
| Medium | `get_card_tags(card)` — normalized tag access | `2168cd5` |
| Medium | `_card_section()` — shared section renderer for pm-focus/standup | `2168cd5` |
| Medium | `_RETRYABLE_HTTP_CODES` — centralized frozenset | `2168cd5` |
| Medium | OAuth HTTP server try/finally cleanup | `2168cd5` |
| Medium | Module-level imports (removed redundant function-scope imports) | `2168cd5` |
| Medium | Owner resolution dedup (single lookup path) | `2168cd5` |
| Medium | `_sanitize_str()` for ANSI escape removal in table output | `d50ef1a` |

### Phase 2 — PM Features

Standup, multi-value filters, date filtering, stale detection, pm-focus.

| Feature | Detail | Commit |
|---------|--------|--------|
| `standup` command | Done/In-Progress/Blocked/Hand sections, `--days`, `--project`, `--owner` | `855543c` |
| `pm-focus` command | Sprint health: blocked, unassigned, started, in-review, stale | `d86c091` |
| Multi-value `--status` | Comma-separated values: `--status started,blocked` | `855543c` |
| Multi-value `--priority` | Comma-separated values: `--priority a,b` | `855543c` |
| `--stale <days>` filter | Cards not updated in N days | `855543c` |
| `--updated-after/before` | Date range filters (read-only) | `855543c` |
| ANSI sanitization | Strip escape sequences from table output | `d50ef1a` |
| PM workflow doc rewrite | Self-evolving agent playbook format | `8ffa681` |

### Phase 1 — Agent Reliability

Strict mode, typed models, feature scaffolding, transaction safety.

| Feature | Detail | Commit |
|---------|--------|--------|
| `--strict` global flag | Fail-fast on ambiguous query/dispatch responses | `18cc18d` |
| Raw query/dispatch validation | Reject empty payloads, enforce JSON objects | `8cfec86` |
| `feature` scaffolding command | Hero + Code + Design + optional Art sub-cards | `d467b93` |
| Transaction-safe rollback | Archive created cards on partial failure | `9d8c7a0` |
| Typed models (`models.py`) | `ObjectPayload`, `FeatureSpec`, `FeatureSubcard`, `FeatureScaffoldReport` | `b1222ca` |
| JSON error envelopes | Structured errors on stderr in JSON mode | `d86c091` |
| Art lane auto-skip | Skip Art when `--art-deck` not provided (no hard fail) | `2613545` |

### Phase 0 — Foundation

Full CLI surface, GDD pipeline, setup wizard, exception hierarchy, test suite.

| Feature | Detail | Commit |
|---------|--------|--------|
| CLI surface | All read/mutate/hand/comment/GDD commands | `02679a4`..`eaf1993` |
| Exception hierarchy | `CliError`/`SetupError` instead of `sys.exit()` | `eaf1993` |
| Input validation | Status/priority/sort/effort validation with helpful errors | `ee89739` |
| Test suite | 170 initial tests across 7 modules (now 328 across 8) | `02679a4` |
| GDD pipeline | Google OAuth2, fetch/parse/sync with Codecks | `02679a4` |
| Setup wizard | Interactive `.env` bootstrap with auto-discovery | `02679a4` |

## Module Inventory

| Module | Lines | Purpose | Key exports |
|--------|-------|---------|-------------|
| `codecks_api.py` | ~380 | Entry point, argparse, dispatch | `main()`, `build_parser()` |
| `config.py` | ~95 | Env, tokens, constants, error classes | `load_env()`, `save_env_value()`, `CliError`, `SetupError` |
| `api.py` | ~220 | HTTP transport, query/dispatch | `session_request()`, `query()`, `dispatch()`, `_RETRYABLE_HTTP_CODES` |
| `cards.py` | ~550 | Card CRUD, hand, conversations, enrichment | `list_cards()`, `enrich_cards()`, `_get_field()`, `get_card_tags()` |
| `commands.py` | ~475 | Command handlers | `cmd_cards()`, `cmd_standup()`, `cmd_pm_focus()`, etc. |
| `formatters.py` | ~500 | JSON/table/CSV output | `output()`, `_mutation_response()`, `_card_section()` |
| `models.py` | ~100 | Typed dataclass contracts | `ObjectPayload`, `FeatureSpec` |
| `gdd.py` | ~540 | Google OAuth2, GDD sync | `fetch_gdd()`, `sync_gdd()` |
| `setup_wizard.py` | ~400 | Interactive setup | `run_setup()` |

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

## Important Behavior Decisions

- Keep the PM agent flexible; avoid over-restrictive validation that blocks productive iteration.
- No Journeys dependency by default. Reassess only if automation value outweighs authoring overhead.
- Preserve `unhand` functionality. It remains supported and documented.
- Card lists omit `content` for token efficiency; `--search` adds it back.
- Default output is JSON (agent-optimized); `--format table` for human consumption.

## Recommended Next Work

1. **Expand test coverage** — Strict mode edge-cases, retry exhaustion, rollback partial-failure paths.
2. **Push typed models deeper** — Validate API payloads via dataclasses to reduce dynamic dict drift.
3. **Improve pm-focus/standup heuristics** — Smarter section grouping, owner-based summaries.
4. **Structured rollback reporting** — Report which cards were archived vs failed in `feature` scaffolding.

## Agent-Specific Tooling

- **Claude Code**: Has skill files in `.claude/commands/` (`/pm`, `/test-all`, `/api-ref`, `/release`, `/security-audit`). These are Claude-specific and gitignored.
- **Other agents**: Use `CLAUDE.md` for architecture, this file for project state, `PM_AGENT_WORKFLOW.md` for PM workflows. The CLI's `--help` flags are the authoritative command reference.
