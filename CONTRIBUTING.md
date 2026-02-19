# Contributing to codecks-cli

Thanks for your interest in contributing! This is a small, focused project and contributions of all kinds are welcome.

## Development setup

1. Clone the repo and create a `.env` file (see [README.md](README.md#setup))
2. You need a [Codecks](https://codecks.io) account to test against (free tier works)
3. Run `py codecks_api.py` with no arguments to see all available commands

## Project principles

- **Single file, zero dependencies.** The entire tool is `codecks_api.py` using only Python's standard library. Please don't add external packages.
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
2. Make your changes in `codecks_api.py`
3. Test your changes with real Codecks API calls
4. Update the docstring at the top of `codecks_api.py` if you add/change commands
5. Update `README.md` if you add new features
6. Open a pull request with a clear description

### Commit messages

- Use present tense: "Add feature" not "Added feature"
- Be concise but descriptive
- Reference issue numbers if applicable: "Fix #42"

## Code style

- Standard Python conventions (PEP 8 mostly)
- Functions are grouped: HTTP layer > query helpers > mutation helpers > formatters > CLI dispatch
- Error messages use `[ERROR]` prefix, token issues use `[TOKEN_EXPIRED]`
- All HTTP calls go through `session_request()`, `report_request()`, or `generate_report_token()`

## AI-assisted development

This project was developed with AI assistance (Claude Code). If you use AI tools in your contributions, that's fine — just make sure the code works and you understand what it does.

## Questions?

Open an issue or start a discussion. Happy to help you navigate the Codecks API quirks!
