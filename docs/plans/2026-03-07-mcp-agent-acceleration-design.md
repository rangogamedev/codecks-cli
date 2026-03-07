# MCP Agent Acceleration — Design Document

**Date:** 2026-03-07
**Status:** Approved
**Pain points:** Slow startup (5 calls), too many tool calls, agent confusion, missing features

## Problem

The PM agent "Decks" needs 5+ tool calls before useful work, requires multiple round-trips for simple updates, gets confused by short IDs and doc-card constraints, and lacks effort filtering and quick overviews.

## Solution

3 new composite tools + 4 guardrail enhancements. Total tools: 51 → 54.

### New Tools

**`session_start(agent_name?)`** — One call replaces warm_cache + standup + get_workflow_preferences + get_account. Returns account, standup, preferences, and project_context (deck names, tag names, lane names, card/hand counts). Playbook excluded (9.4KB — belongs in system prompt).

**`find_and_update(search, updates...)`** — Two-phase search-then-update. Phase 1 returns matches (read-only). Phase 2 applies updates to confirmed IDs. Reduces "update 3 cards" from 5+ calls to 2.

**`quick_overview(project?)`** — Aggregate-only dashboard: counts by status/priority, effort stats (total/avg/unestimated), deck summary, stale count, hand size. No card details = minimal tokens.

### Guardrail Enhancements

**Effort filters** — `effort_min`, `effort_max`, `has_effort` on `list_cards()`.

**Doc-card guardrail** — `update_cards()` checks cache for doc cards and rejects status/priority/effort with clear error listing allowed fields.

**UUID short-ID hints** — `_validate_uuid()` searches cache when given 8-char ID and suggests full UUID in error: "Did you mean 'abc12345-...' (My Card Title)?".

**Deck fuzzy matching** — `resolve_deck_id()` tries prefix then substring match and suggests closest: "Did you mean 'Code'?".

## Deliberately Excluded

- **Tool consolidation** (merging hand/comment tools) — harder for agents to discover
- **Bulk tag tool** — project uses inline body tags convention, `update_card_body` already handles this
- **Auto-resolving short IDs** — silent resolution could match wrong card; hint-based approach is safer
- **Playbook in session_start** — 9.4KB wastes tokens; should be in agent system prompt

## Files Changed

| File | Change |
|------|--------|
| `_tools_local.py` | `session_start()` |
| `_tools_write.py` | `find_and_update()`, doc-card guardrail |
| `_tools_read.py` | `quick_overview()`, effort filters |
| `_core.py` | UUID hints, warm_cache deck names |
| `__init__.py` | Re-exports, instructions update |
| `cards.py` | Fuzzy deck matching |
| `tests/test_mcp_server.py` | ~45 new tests |
