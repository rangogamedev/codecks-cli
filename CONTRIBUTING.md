# Contributing to codecks-cli

Thanks for your interest in contributing! This is a small, focused project and contributions of all kinds are welcome.

For architecture details, see `AGENTS.md` (agent-agnostic) or `CLAUDE.md` (Claude Code). For development setup, see `DEVELOPMENT.md`.

## Quick start

```bash
git clone https://github.com/rangogamedev/codecks-cli.git
cd codecks-cli
uv sync --extra dev          # or: py -m pip install -e .[dev]
pwsh -File scripts/run-tests.ps1   # 1000+ tests, no API calls
```

## Project principles

- **Zero runtime dependencies.** The CLI uses only Python's standard library.
- **Dev tooling is allowed.** Lint/type/test tools may be added as `dev` extras in `pyproject.toml`, but must not become runtime dependencies.
- **AI-agent first, human-friendly second.** JSON output is the default for agent consumption. Table output (`--format table`) is for humans.
- **Token efficiency.** Minimize output noise — AI agents pay per token.
- **Semantic versioning.** Follow [semver](https://semver.org/) — see the release process in `DEVELOPMENT.md`.

## How to contribute

### Reporting bugs

[Open an issue](../../issues/new) with:
- The command you ran
- What happened vs. what you expected
- Whether you see `[ERROR]` or `[TOKEN_EXPIRED]` in the output
- Your Python version and OS

### Suggesting features

Open an issue describing:
- What command or feature you'd like
- Your use case (human usage? AI agent?)
- If you've explored the Codecks API, share what you found

### Submitting code

1. Fork the repo and create a branch
2. Make your changes in the relevant module (see `DEVELOPMENT.md` for module layout)
3. Install dev tools: `uv sync --extra dev` (or `py -m pip install -e .[dev]`)
4. Run quality checks:
   ```bash
   py -m ruff check .                    # lint
   py -m ruff format --check .           # format
   py scripts/quality_gate.py --mypy-only  # type check
   pwsh -File scripts/run-tests.ps1      # tests
   ```
5. Test your changes with real Codecks API calls if they touch the API layer
6. Update `CHANGELOG.md` under `[Unreleased]` with user-visible changes
7. Open a pull request with a clear description

### Commit messages

- Use present tense: "Add feature" not "Added feature"
- Be concise but descriptive
- Reference issue numbers if applicable: "Fix #42"

### Changelog entries

When your change is user-visible (new feature, bug fix, breaking change), add an entry to `CHANGELOG.md` under the `[Unreleased]` heading. We follow [Keep a Changelog](https://keepachangelog.com/) format:

- **Added** for new features
- **Changed** for changes in existing functionality
- **Fixed** for bug fixes
- **Removed** for removed features

## Code style

- Standard Python conventions (PEP 8)
- Enforced by [ruff](https://docs.astral.sh/ruff/) (lint + format)
- Type annotations checked by [mypy](https://mypy.readthedocs.io/) (strict on source, not tests)
- Error messages use `[ERROR]` prefix, token issues use `[TOKEN_EXPIRED]`
- All HTTP calls go through `api.py` (`session_request`, `report_request`, `generate_report_token`)
- Always use `raise X from e` in except blocks (ruff B904)

## Testing

The test suite has **1000+ tests** across 20 test files. All must pass before submitting:

```bash
pwsh -File scripts/run-tests.ps1
```

Tests mock at module boundaries — no live API calls are made.

## Important constraints

- **Zero runtime dependencies.** Do not add non-stdlib runtime requirements.
- **Dev-only packages must stay optional.** Tooling belongs in `[project.optional-dependencies].dev`.
- **Paid-only features (do NOT use):** Due dates (`dueAt`), Dependencies, Time tracking, Runs/Capacity, Guardians, Beast Cards, Vision Board Smart Nodes.
- **Doc cards** cannot have `--status`, `--priority`, or `--effort` set (API returns 400).
- **Python command:** Always use `py` (never `python` or `python3`). Requires 3.10+.

See `DEVELOPMENT.md` for full architecture details, module layout, and release process.

## AI-assisted development

This project was developed with AI assistance (Claude Code). If you use AI tools in your contributions, that's fine — just make sure the code works and you understand what it does.

## Questions?

Open an issue or start a discussion. Happy to help you navigate the Codecks API quirks!
