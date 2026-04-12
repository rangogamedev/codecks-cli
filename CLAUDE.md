# CLAUDE.md — codecks-cli

Claude Code-specific configuration. For shared agent instructions, see [AGENTS.md](AGENTS.md). For architecture and dev setup, see [DEVELOPMENT.md](DEVELOPMENT.md). For MCP tool reference, see [docs/mcp-reference.md](docs/mcp-reference.md).

## Environment

- **Python**: `py` (never `python`/`python3`). Requires 3.12+.
- **Test**: `pwsh -File scripts/run-tests.ps1` (1000+ tests, no API calls)
- **Deps**: `uv sync --extra dev --extra mcp` (uv manages lock file; mcp extra required for test collection). Fallback: `py -m pip install .[dev,mcp]`
- **Lock file**: `uv.lock` — pinned dependency versions, committed to git
- **CI**: `.github/workflows/test.yml` — ruff, mypy, pytest (matrix: 3.12, 3.14) + Codecov + Docker smoke. All Actions pinned to commit hashes.
- **Dependabot**: `.github/dependabot.yml` — weekly PRs for pip deps, GitHub Actions, and Docker
- **Version**: `VERSION` in `codecks_cli/config.py` + `pyproject.toml` (keep in sync). Tags: `v0.1.0`..`v0.5.0`.

## Skills (`.claude/commands/`)

`/pm`, `/release`, `/api-ref`, `/codecks-docs <topic>`, `/quality`, `/mcp-validate`, `/troubleshoot`, `/split-features`, `/doc-update`, `/changelog`, `/docker`, `/registry`, `/architecture`, `/api-pitfalls`, `/maintenance`

## Subagents (`.claude/agents/`)

- `security-reviewer` — credential exposure, injection vulns, unsafe patterns
- `test-runner` — full test suite

## Context7 Library IDs (pre-resolved)

Always use Context7 MCP for library/API docs. Skip the resolve step with these IDs:

| Library | Context7 ID |
|---------|-------------|
| MCP SDK (Python) | `/modelcontextprotocol/python-sdk` |
| pytest | `/pytest-dev/pytest` |
| ruff | `/websites/astral_sh_ruff` |
| mypy | `/websites/mypy_readthedocs_io_en` |

## MCP Servers (`.claude/settings.json`)

- `codecks` — this project's own MCP server (52 tools, Codecks API access)
- `context7` — live documentation lookup
- `github` — GitHub issues/PRs integration

## Hooks (`.claude/settings.json`)

- **PreToolUse** `Edit|Write`: blocks edits to `.env` and `.gdd_tokens.json`
- **PostToolUse** `Edit|Write`: auto-formats `.py` with ruff, auto-runs matching tests

## Scripts (`scripts/`)

- `py scripts/quality_gate.py` — all checks (ruff, mypy, pytest). `--skip-tests`, `--fix`, `--mypy-only`.
- `py scripts/project_meta.py` — project metadata JSON.
- `py scripts/validate_docs.py` — checks docs for stale counts. `--fix` auto-repairs.

## Git & Versioning

- Commit style: short present tense ("Add X", "Fix Y")
- Never commit `.env`, `.gdd_tokens.json`, `.gdd_cache.md`, `.pm_store.db*`, `.pm_claims.json`, `.pm_last_result.json`, `.pm_undo.json`
- `.claude/` is gitignored
- Run security-reviewer agent before pushing (public repo)
- **Semver**: see [DEVELOPMENT.md](DEVELOPMENT.md#versioning) for release process
- **Branch protection**: PRs required for main, status checks must pass

## Security

- Secret scanning + push protection enabled on GitHub
- All GitHub Actions pinned to commit hashes (supply chain hardening)
- Docker: non-root user, capabilities dropped. See [DEVELOPMENT.md](DEVELOPMENT.md#security-hardening)
- See [SECURITY.md](SECURITY.md) for vulnerability disclosure policy
