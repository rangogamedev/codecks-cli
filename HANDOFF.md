# HANDOFF.md

Purpose: quick context handoff for Claude Code and other coding agents working on `codecks-cli`.

Last updated: 2026-02-20

## Project Goal
- Build a robust CLI that lets an AI `/PM` agent manage Codecks workflows directly.
- Prioritize Codecks-native PM behavior (hero cards + sub-cards by discipline) over generic PM frameworks.
- Start without Journeys automation unless a clear ROI appears.

## What Was Completed
1. Agent strictness and reliability
- Added global `--strict` mode in `codecks_api.py`.
- Hardened raw `query` and `dispatch` validation/contracts.
- Added JSON error envelopes on stderr in JSON mode.
- Added strict JSON mutation output support.

2. REST/API transport hardening
- Added idempotent retries for safe read/query operations.
- Added `Retry-After` handling.
- Added response-size cap protections.
- Added per-request `X-Request-Id`.
- Added optional structured HTTP logging with sampling and redaction.

3. Codecks PM workflow commands
- Added `feature` scaffolding command to create:
  - Hero card
  - Code sub-card
  - Design sub-card
  - Optional Art sub-card
- Implemented transaction safety with compensating rollback (best-effort archive of created cards on partial failure).
- Relaxed Art lane behavior for AI flexibility:
  - If `--art-deck` is missing and `--skip-art` is not set, auto-skip art lane rather than hard-fail.
- Added `pm-focus` command for PM triage view (`blocked`, `hand`, suggested next work).

4. Typed models introduction
- Added `models.py` dataclass contracts:
  - `ObjectPayload`
  - `FeatureSpec`
  - `FeatureSubcard`
  - `FeatureScaffoldReport`
- Updated `commands.py` to consume typed models for safer payload/report handling.

5. Docs and guidance updates
- Updated `README.md`, `CLAUDE.md`, `PROJECT_INDEX.md`, `PM_AGENT_WORKFLOW.md` for new command surface and behavior.
- Updated local Claude command docs under `.claude/commands/` (local-only, may be gitignored).

6. Test coverage updates
- Expanded tests across:
  - `tests/test_api.py`
  - `tests/test_cli.py`
  - `tests/test_commands.py`
  - `tests/test_formatters.py`
  - `tests/test_models.py` (new)
- Latest reported targeted run in prior session: 151 tests passed.

## Important Behavior Decisions
- Keep the PM agent flexible; avoid over-restrictive validation that blocks productive iteration.
- No Journeys dependency by default. Reassess later only if automation value outweighs authoring overhead.
- Preserve `unhand` functionality. It remains supported and documented in command references.

## Recent Commits Already Pushed
- `18cc18d` Harden agent workflows and strict API behavior
- `8cfec86` Harden raw query/dispatch validation for strict mode
- `d467b93` Add no-journey feature scaffolding command for PM agents
- `9d8c7a0` Add transaction-safe rollback for feature scaffolding
- `b1222ca` Introduce typed models for payload and feature contracts
- `d86c091` Add pm-focus command and strict JSON mutation output
- `2613545` Relax feature art lane with typed auto-skip behavior

## Current Baseline
- Branch: `main`
- Core docs: `CLAUDE.md`, `PROJECT_INDEX.md`, `PM_AGENT_WORKFLOW.md`
- Architecture remains modular (`codecks_api.py`, `commands.py`, `cards.py`, `api.py`, `formatters.py`, `models.py`, `config.py`, `gdd.py`).

## High-Value Next Improvements
1. Strengthen idempotency semantics
- Ensure retries are strictly limited to non-mutating operations unless explicit idempotency keys exist.

2. Tighten transaction observability
- Add structured rollback result reporting for `feature` scaffolding (which cards were archived successfully vs failed).

3. Expand PM-agent flow quality
- Improve `/pm` heuristics for category routing (Code vs Art vs Design) with clearer confidence markers.
- Add lightweight safeguards to prevent card spam/duplicates while keeping flexibility.

4. Extend typed model usage
- Push dataclass validation boundaries deeper into API payload construction to reduce dynamic dict drift.

5. Add regression tests
- Add targeted tests for strict mode edge-cases, retry exhaustion behavior, and rollback partial-failure paths.

## Notes for Claude Code
- Read `CLAUDE.md` first for architecture, command surface, and constraints.
- Then read this file for latest delivery state and recommended next work.
- Keep changes aligned with Codecks-native PM patterns rather than generic agile templates.
