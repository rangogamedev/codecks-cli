# HANDOFF.md — codecks-cli

Last updated: 2026-02-20 | Version: 0.4.0 | Tests: 389

## Recent Changes

### API-First Library Refactoring
- **New `CodecksClient`** (`client.py`, ~1300 lines) — 27 public methods, keyword-only args, flat dict returns
- **Removed GUI** (~2000 lines) — `gui/` directory, 4 test files, `docs/` folder
- **Updated**: `__init__.py` exports, `models.py` added `FeatureSpec.from_kwargs()`, `commands.py` imports helpers from `client.py`
- **New tests**: `test_client.py` (60 tests). Suite: 329 existing + 60 new = 389 passing

### Earlier (summarized)
- Package restructuring into `codecks_cli/`
- Duplicate title guardrails (`--allow-duplicate`)
- Code quality hardening (safe .env parsing, atomic writes, exception chaining, response caps)
- PM features (standup, pm-focus, multi-value filters, stale detection)
- Strict mode, typed models, feature scaffolding with transaction-safe rollback

## Next Work
1. **MCP server** — wrap `CodecksClient` as MCP tools (~100 lines)
2. **Thin commands.py** — migrate `cmd_*` to delegate to `CodecksClient` (update test mocks)
3. **Type annotations** — return type hints on `CodecksClient` using `TypedDict`

## Notes
- `commands.py` keeps original implementations (not delegating to `CodecksClient`) to preserve test mock compat
- `_guard_duplicate_title`, `_sort_cards`, `_resolve_owner_id` etc. live in `client.py`, imported by `commands.py`
