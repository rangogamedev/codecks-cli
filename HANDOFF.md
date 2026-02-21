# HANDOFF.md — codecks-cli

Last updated: 2026-02-21 | Version: 0.4.0

## Recent Changes

### Documentation Polish
- README rewritten: added TOC, Installation, Python API, MCP Server sections; removed stale file structure
- CHANGELOG v0.4.0 backfilled with full architecture refactoring, MCP, CodecksClient, new flags
- pyproject.toml metadata: authors, keywords, classifiers, package-data, URLs
- CONTRIBUTING.md, PR template modernized

### Architecture Refactoring (v0.4.0)
- `exceptions.py` — all exception classes (`CliError`, `SetupError`, `HTTPError`)
- `_utils.py` — pure utility helpers extracted from `cards.py`
- `formatters/` — package with 7 sub-modules, `__init__.py` re-exports all 24 names
- `types.py` — TypedDict response shapes for documentation
- `commands.py` thinned to delegate all business logic to `CodecksClient`
- CLI dispatch uses `set_defaults(func=cmd_xxx)` per subparser

### MCP Server (28 tools)
- 25 tools mapping 1:1 to CodecksClient methods
- 3 PM session tools: `get_pm_playbook`, `get_workflow_preferences`, `save_workflow_preferences`
- PM playbook (`pm_playbook.md`) — agent-agnostic PM methodology readable via MCP
- Literal types, pagination, cached client, agent-friendly docstrings

### CodecksClient (27 methods)
- Full programmatic API: read, create, update, archive, hand, comments, raw queries
- `py.typed` marker for PEP 561 editor support
- Keyword-only args, flat `dict[str, Any]` returns

### CLI Enhancements
- `--dry-run`, `--quiet`, `--verbose` flags
- `--version` flag, `completion` command (bash/zsh/fish)
- `--format csv`, `--milestone` filter, input validation, priority labels

## Next Work
1. **Open-LLM-VTuber fork** — register codecks MCP server in `mcp_servers.json`
2. **PyPI publish** — `python -m build && twine upload dist/*`
3. **GitHub Actions release** — auto-publish on tag push

## Stats
- 491 tests, 12 test files, 22 source modules
- 28 MCP tools, 27 CodecksClient methods
- Zero runtime dependencies
