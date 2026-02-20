# HANDOFF.md — codecks-cli

Last updated: 2026-02-21 | Version: 0.4.0

## Recent Changes

### MCP Server Improvements
- **25 tools** (was 22) — added `reply_comment`, `close_comment`, `reopen_comment`
- **Literal types** for enum params (status, priority, sort, card_type, severity, doc)
- **Pagination** on `list_cards` (limit/offset, default 50 cards per page)
- **Cached client** — single `CodecksClient` instance reused across tool calls
- **Agent-friendly docstrings** — "when to use" hints, return shapes, gotchas
- **Enhanced server instructions** — UUID requirement, doc card constraints, rate limit

### MCP Server
- **New `mcp_server.py`** — 25 MCP tools wrapping `CodecksClient` via FastMCP (stdio transport)
- **Install**: `pip install .[mcp]` (optional dep `mcp[cli]>=1.6.0`)
- **Run**: `python -m codecks_cli.mcp_server` or `codecks-mcp` entry point
- **Client fixes**: `_guard_duplicate_title()` returns warnings in dict (no stderr), `list_cards()` always returns `{cards, stats}` shape, improved docstrings for tool descriptions
- **New tests**: `test_mcp_server.py` (skipped if mcp not installed)

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
1. **Thin commands.py** — migrate `cmd_*` to delegate to `CodecksClient` (update test mocks)
2. **Type annotations** — return type hints on `CodecksClient` using `TypedDict`
3. **Open-LLM-VTuber fork** — register codecks MCP server in `mcp_servers.json`

## Notes
- `commands.py` keeps original implementations (not delegating to `CodecksClient`) to preserve test mock compat
- `_guard_duplicate_title`, `_sort_cards`, `_resolve_owner_id` etc. live in `client.py`, imported by `commands.py`
