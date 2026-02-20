# Contributing to codecks-cli

Thanks for your interest in contributing! This is a small, focused project and contributions of all kinds are welcome.

For architecture details, see `CLAUDE.md`. For current project state, see `HANDOFF.md`.

## Development setup

1. Clone the repo and create a `.env` file (see [README.md](README.md#setup))
2. You need a [Codecks](https://codecks.io) account to test against (free tier works)
3. Run `py codecks_api.py` with no arguments to see all available commands

## Project principles

- **Zero runtime dependencies.** The CLI runtime uses only Python's standard library.
- **Dev tooling is allowed.** Lint/type/test tools may be added as `dev` extras in `pyproject.toml`, but must not become runtime dependencies.
- **AI-agent first, human-friendly second.** JSON output is the default for agent consumption. Table output (`--format table`) is for humans.
- **Token efficiency.** Minimize output noise — AI agents pay per token. Avoid verbose responses.

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
2. Make your changes in the relevant module (see `PROJECT_INDEX.md` or `CLAUDE.md` for module layout)
3. Install dev tools: `py -m pip install .[dev]`
4. Run quality checks:
   - `py -m ruff check .`
   - `py -m ruff format --check .`
   - `py -m mypy api.py cards.py commands.py formatters.py models.py`
   - `py -m pytest tests/ -v --basetemp .tmp/pytest`
5. Test your changes with real Codecks API calls if they touch the API layer
6. Update `README.md` if you add new commands or flags
7. Open a pull request with a clear description

### Commit messages

- Use present tense: "Add feature" not "Added feature"
- Be concise but descriptive
- Reference issue numbers if applicable: "Fix #42"

## Code style

- Standard Python conventions (PEP 8 mostly)
- Code is split across 9 modules: `codecks_api.py` (entry point), `config.py` (env/constants), `api.py` (HTTP), `cards.py` (business logic), `commands.py` (CLI handlers), `formatters.py` (output), `models.py` (typed contracts), `gdd.py` (Google Docs), `setup_wizard.py` (setup)
- Error messages use `[ERROR]` prefix, token issues use `[TOKEN_EXPIRED]`
- All HTTP calls go through `session_request()`, `report_request()`, or `generate_report_token()` in `api.py`

## Important constraints

- **Zero runtime dependencies.** Do not add non-stdlib runtime requirements.
- **Dev-only packages must stay optional.** Tooling belongs in `[project.optional-dependencies].dev`.
- **Paid-only features (do NOT use):** Due dates (`dueAt`), Dependencies, Time tracking, Runs/Capacity, Guardians, Beast Cards, Vision Board Smart Nodes. Never set `dueAt` or any deadline field when creating or updating cards.
- **Doc cards** cannot have `--status`, `--priority`, or `--effort` set (API returns 400).
- **Python command:** Always use `py` (never `python` or `python3`). Requires 3.10+.
- **Tests:** `py -m pytest tests/ -v` — currently 293 tests. All must pass before submitting.

See `CLAUDE.md` for full architecture details, API pitfalls, and known bug regressions.

## AI-assisted development

This project was developed with AI assistance (Claude Code). If you use AI tools in your contributions, that's fine — just make sure the code works and you understand what it does.

## Questions?

Open an issue or start a discussion. Happy to help you navigate the Codecks API quirks!
