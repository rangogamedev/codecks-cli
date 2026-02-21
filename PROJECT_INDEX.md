# PROJECT_INDEX.md — codecks-cli

Fast index for agents and maintainers.

## Quick Commands
- Run CLI help: `py codecks_api.py`
- Version: `py codecks_api.py --version`
- Tests: `pwsh -File scripts/run-tests.ps1`
- Lint: `py -m ruff check .`
- Format check: `py -m ruff format --check .`
- Types: `py -m mypy codecks_cli/api.py codecks_cli/cards.py codecks_cli/client.py codecks_cli/commands.py codecks_cli/formatters/ codecks_cli/models.py codecks_cli/exceptions.py codecks_cli/_utils.py codecks_cli/types.py`

## Entry Points
- CLI wrapper: `codecks_api.py`
- CLI parser + dispatch: `codecks_cli/cli.py`
- Command handlers: `codecks_cli/commands.py`
- Programmatic API: `codecks_cli/client.py`
- MCP server: `codecks_cli/mcp_server.py`

## Core Modules
- HTTP + retries + token checks: `codecks_cli/api.py`
- Card CRUD + filters + hand + conversations: `codecks_cli/cards.py`
- Runtime config + .env loading + response contract settings: `codecks_cli/config.py`
- Shared exceptions: `codecks_cli/exceptions.py`
- Field/parsing helpers: `codecks_cli/_utils.py`
- Typed API shapes: `codecks_cli/types.py`
- Dataclasses for payload contracts: `codecks_cli/models.py`
- Output formatters: `codecks_cli/formatters/`
- Google Docs sync/auth: `codecks_cli/gdd.py`
- Setup wizard: `codecks_cli/setup_wizard.py`

## Flow By Concern
- CLI request flow: `cli.py` -> `commands.py` -> `CodecksClient` (`client.py`) -> `cards.py`/`api.py`
- Output flow: `commands.py` -> `formatters/*` -> JSON/table/CSV
- MCP flow: `mcp_server.py` -> `_call()` -> `CodecksClient` methods -> `_finalize_tool_result()` contract shape

## Change Hotspots
- Add/modify command:
  - `codecks_cli/cli.py` (parser args)
  - `codecks_cli/commands.py` (`cmd_*`)
  - `codecks_cli/client.py` (business method)
  - `tests/test_cli.py`, `tests/test_commands.py`, `tests/test_client.py`
- Add formatter:
  - `codecks_cli/formatters/_*.py`
  - `codecks_cli/formatters/__init__.py` export list
  - `tests/test_formatters.py`
- Add MCP tool:
  - `codecks_cli/mcp_server.py` (`@mcp.tool()`)
  - `tests/test_mcp_server.py`
  - Update AI docs: `AGENTS.md`, `CLAUDE.md`, `.claude/commands/api-ref.md`, `.claude/commands/mcp-validate.md`
- Update response contracts/pagination:
  - `codecks_cli/config.py` (`CONTRACT_SCHEMA_VERSION`, `CODECKS_MCP_RESPONSE_MODE`)
  - `codecks_cli/cli.py` (`_emit_cli_error` JSON envelope)
  - `codecks_cli/commands.py` (`cmd_cards` `limit`/`offset` + pagination metadata)
  - `codecks_cli/client.py` (mutation `per_card`/`failed`, `continue_on_error`)
  - `codecks_cli/mcp_server.py` (`legacy` vs `envelope` success output)

## Non-Negotiables
- Do not set `dueAt` (paid-only).
- For doc cards, do not set `status`, `priority`, or `effort`.
- Keep title as first line of card `content`.
- Use `_get_field()` for snake/camel compatibility.
