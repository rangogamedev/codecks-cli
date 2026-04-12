# Contributing to codecks-cli

Thanks for your interest in contributing! This is a small, focused project and contributions of all kinds are welcome.

For architecture details, see [DEVELOPMENT.md](DEVELOPMENT.md). For agent instructions, see [AGENTS.md](AGENTS.md).

## Quick Start

```bash
git clone https://github.com/rangogamedev/codecks-cli.git
cd codecks-cli
uv sync --extra dev          # or: py -m pip install -e .[dev]
py scripts/quality_gate.py   # lint + type check + 1000+ tests
```

## Project Principles

- **Zero runtime dependencies.** The CLI uses only Python's standard library.
- **Dev tooling is allowed.** Lint/type/test tools may be added as `dev` extras in `pyproject.toml`, but must not become runtime dependencies.
- **AI-agent first, human-friendly second.** JSON output is the default for agent consumption. Table output (`--format table`) is for humans.
- **Token efficiency.** Minimize output noise — AI agents pay per token.
- **Semantic versioning.** Follow [semver](https://semver.org/) — see [DEVELOPMENT.md](DEVELOPMENT.md#release-process).

## How to Contribute

### Reporting Bugs

[Open an issue](../../issues/new) with:
- The command you ran
- What happened vs. what you expected
- Whether you see `[ERROR]` or `[TOKEN_EXPIRED]` in the output
- Your Python version and OS

### Suggesting Features

Open an issue describing:
- What command or feature you'd like
- Your use case (human usage? AI agent?)
- If you've explored the Codecks API, share what you found

### Submitting Code

1. Fork the repo and create a branch
2. Make your changes (see [DEVELOPMENT.md](DEVELOPMENT.md) for module layout)
3. Run quality checks: `py scripts/quality_gate.py`
4. Test with real Codecks API calls if touching the API layer
5. Update `CHANGELOG.md` under `[Unreleased]` for user-visible changes
6. Update docs if adding features:
   - [docs/cli-reference.md](docs/cli-reference.md) for new CLI commands
   - [docs/mcp-reference.md](docs/mcp-reference.md) for new MCP tools
   - [DEVELOPMENT.md](DEVELOPMENT.md) for architecture changes
7. Open a pull request with a clear description

### Commit Messages

- Use present tense: "Add feature" not "Added feature"
- Be concise but descriptive
- Reference issue numbers if applicable: "Fix #42"

### Changelog Entries

For user-visible changes, add an entry to `CHANGELOG.md` under `[Unreleased]`. We follow [Keep a Changelog](https://keepachangelog.com/) format:

- **Added** for new features
- **Changed** for changes in existing functionality
- **Fixed** for bug fixes
- **Removed** for removed features

## Code Style

- Standard Python conventions (PEP 8)
- Enforced by [ruff](https://docs.astral.sh/ruff/) (lint + format)
- Type annotations checked by [mypy](https://mypy.readthedocs.io/) (strict on source, not tests)
- Error messages use `[ERROR]` prefix, token issues use `[TOKEN_EXPIRED]`
- All HTTP calls go through `api.py`
- Always use `raise X from e` in except blocks (ruff B904)

## Important Constraints

- **Zero runtime dependencies.** Do not add non-stdlib runtime requirements.
- **Dev-only packages must stay optional.** Tooling belongs in `[project.optional-dependencies].dev`.
- **Paid-only features (do NOT use):** Due dates, Dependencies, Time tracking, Runs/Capacity, Guardians, Beast Cards.
- **Doc cards** cannot have `--status`, `--priority`, or `--effort` set (API returns 400).
- **Python command:** Always use `py` (never `python` or `python3`).

## AI-Assisted Development

This project was developed with AI assistance (Claude Code). If you use AI tools in your contributions, that's fine — just make sure the code works and you understand what it does.

## Questions?

Open an issue or start a discussion. Happy to help you navigate the Codecks API quirks!
