# codecks-cli

![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue)
![License: MIT](https://img.shields.io/badge/License-MIT-green)
![Tests: 1000+](https://img.shields.io/badge/Tests-1000%2B-brightgreen)
![CI](https://github.com/rangogamedev/codecks-cli/actions/workflows/test.yml/badge.svg)
[![codecov](https://codecov.io/gh/rangogamedev/codecks-cli/branch/main/graph/badge.svg)](https://codecov.io/gh/rangogamedev/codecks-cli)

A command-line tool, Python library, and MCP server for managing [Codecks.io](https://codecks.io) cards, decks, and projects. Zero runtime dependencies.

## Why codecks-cli?

[Codecks](https://codecks.io) is a project management tool popular with game developers, but it has no official CLI or public API client. codecks-cli fills that gap:

- **For humans** — manage cards, run standups, and track sprints from your terminal
- **For scripts** — typed Python API with 33 methods, JSON output by default
- **For AI agents** — 52 MCP tools with snapshot caching, batch operations, and multi-agent coordination
- **Zero dependencies** — stdlib only, installs anywhere Python 3.12+ runs

## Installation

```bash
git clone https://github.com/rangogamedev/codecks-cli.git
cd codecks-cli
py -m pip install .
```

This installs two commands: `codecks-cli` (CLI) and `codecks-mcp` (MCP server).

You can also run without installing: `py codecks_api.py <command>`

Docker is also supported — see [DEVELOPMENT.md](DEVELOPMENT.md#docker).

## Quick Start

```bash
# Interactive setup wizard — walks you through tokens, projects, milestones
codecks-cli setup

# List your cards
codecks-cli cards --format table

# Create a card
codecks-cli create "Fix login bug" --deck "Backlog"

# Daily standup snapshot
codecks-cli standup --format table
```

Manual setup alternative: `cp .env.example .env` and fill in your tokens.

## Quick Start for AI Agents (MCP)

```bash
# Install MCP dependency
py -m pip install .[mcp]
```

Add to your MCP configuration (Claude Code, Cursor, etc.):

```json
{
  "mcpServers": {
    "codecks": {
      "command": "codecks-mcp",
      "args": []
    }
  }
}
```

**Important:** Call `session_start()` as your first MCP tool call in every session. It returns account info, project context, and warms the cache for instant reads.

See [docs/mcp-reference.md](docs/mcp-reference.md) for the full tool inventory and agent patterns.

## Features

- **Card management** — create, update, archive, delete with filtering by status, priority, deck, owner, milestone, tags, and text search
- **Feature scaffolding** — create Hero cards with linked Code/Design/Art/Audio sub-cards in one command
- **Daily standups** — snapshot of done, in-progress, blocked, and in-hand cards
- **Sprint health** — PM focus dashboard with blocked, stale, unassigned, and in-review cards
- **GDD sync** — parse a Game Design Document (Google Docs or local file) and sync tasks to Codecks
- **Batch operations** — create, archive, delete, or update up to 20 cards per call
- **Team coordination** — claim/release/delegate cards across multiple AI agents
- **Shell completions** — bash, zsh, and fish
- **Snapshot caching** — MCP reads in <50ms with selective invalidation
- **1000+ tests** — full offline test suite, no live API calls

## CLI Overview

```bash
codecks-cli cards --status started --format table   # filter and display cards
codecks-cli card <id>                                # single card details
codecks-cli create "New task" --deck "Backlog"       # create a card
codecks-cli update <id> --status done --effort 3     # update card properties
codecks-cli standup --days 3 --format table          # standup report
codecks-cli pm-focus --format table                  # sprint health dashboard
```

See [docs/cli-reference.md](docs/cli-reference.md) for the full command reference with all flags and examples.

## Python API

```python
from codecks_cli import CodecksClient

client = CodecksClient()
cards = client.list_cards(status="started", sort="priority")
result = client.create_card(title="Fix bug", deck="Backlog")
```

33 methods with keyword-only args and flat dict returns. See [docs/cli-reference.md](docs/cli-reference.md#python-api) for the full method table.

## MCP Server

52 tools for AI agents — read, write, batch, comments, team coordination, and admin operations. Key features:

- **One-call startup** — `session_start()` returns everything an agent needs
- **Token diet** — `summary_only` modes on dashboards, content omitted by default
- **Snapshot cache** — in-memory + disk with selective invalidation
- **Team coordination** — claim/release/delegate for multi-agent workflows
- **Guardrails** — doc-card protection, UUID hints, deck fuzzy matching

See [docs/mcp-reference.md](docs/mcp-reference.md) for setup, tool inventory, and usage patterns.

## Token Architecture

The tool uses three tokens, each for a different purpose:

| Token | Used for | Expiry |
|-------|----------|--------|
| `CODECKS_TOKEN` | Reading data, updating cards | Session (browser cookie) |
| `CODECKS_REPORT_TOKEN` | Creating cards | Never (until disabled) |
| `CODECKS_ACCESS_KEY` | Generating report tokens | Never |

Run `codecks-cli setup` for guided configuration, or see `.env.example` for manual setup.

## Documentation

| Document | Contents |
|----------|----------|
| [docs/cli-reference.md](docs/cli-reference.md) | Full CLI command reference and Python API |
| [docs/mcp-reference.md](docs/mcp-reference.md) | MCP tool inventory, caching, error contract, team coordination |
| [DEVELOPMENT.md](DEVELOPMENT.md) | Architecture, dev setup, testing, release process |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute |
| [AGENTS.md](AGENTS.md) | AI agent instructions (tokens, API pitfalls, known bugs) |
| [CHANGELOG.md](CHANGELOG.md) | Version history |
| [SECURITY.md](SECURITY.md) | Vulnerability reporting |

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Security

Found a vulnerability? See [SECURITY.md](SECURITY.md) for responsible disclosure.

## License

MIT License — see [LICENSE](LICENSE) for details.
