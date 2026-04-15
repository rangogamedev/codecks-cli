# codecks-cli

![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue)
![License: MIT](https://img.shields.io/badge/License-MIT-green)
![Tests: 1000+](https://img.shields.io/badge/Tests-1000%2B-brightgreen)
![CI](https://github.com/rangogamedev/codecks-cli/actions/workflows/test.yml/badge.svg)
[![codecov](https://codecov.io/gh/rangogamedev/codecks-cli/branch/main/graph/badge.svg)](https://codecov.io/gh/rangogamedev/codecks-cli)

Game developers should be making games, not managing task boards.

codecks-cli gives your AI agent project management tools for [Codecks.io](https://codecks.io) — standups, feature scaffolding, sprint health, batch operations, and multi-agent coordination. Your agent handles the admin. You focus on the game.

Also works as a standalone CLI and Python API. Zero runtime dependencies.

## Agent Quick Start

```bash
pip install codecks-cli
codecks-cli setup                # interactive token wizard (runs in your terminal)
codecks-cli agent-init --agent   # verify: returns account + project context
```

Your agent can now use `codecks-cli <command> --agent` via Bash. No special prompt needed — the CLI outputs stable JSON.

Want a plug-and-play PM skill? Copy `examples/skills/pm/SKILL.md` to `.claude/commands/pm.md` and use `/pm`.

Want MCP tools too? `pip install codecks-cli[mcp]` — see [docs/ai-agent-guide.md](docs/ai-agent-guide.md).

## What Your Agent Can Do

- Run standups and sprint triage
- Create, update, archive, and batch-close cards
- Scaffold Hero cards with Code/Design/Art/Audio sub-cards
- Batch operations via `--ids-only | --stdin` pipes (~40 bytes/card)
- Sync tasks from a Game Design Document
- Coordinate multiple agents via MCP (claim/release/delegate)

## Why CLI-First

The CLI is the recommended default for AI agents:

- **25x leaner context** than loading 52 MCP tool schemas
- JSON output with `--agent` flag
- Pipe-friendly batch workflows (`--ids-only`, `--stdin`, `@last`)
- No MCP dependency needed for routine PM work

MCP adds caching, team coordination, and richer editor integrations when you need them.

## Human Quick Start

```bash
codecks-cli cards --format table
codecks-cli standup --format table
codecks-cli create "Fix login bug" --deck Backlog
```

See [docs/cli-reference.md](docs/cli-reference.md) for the full command reference.

## How It Works

```
CLI (codecks-cli)  ─┐
Python API         ─┤── CodecksClient ── Codecks HTTP API
MCP Server         ─┘   (33 methods)
```

All three interfaces wrap the same `CodecksClient` library. The CLI formats output for terminals, the API returns dicts, and the MCP server adds caching, guardrails, and team coordination.

## Features

- **Card management** — create, update, archive, delete with filtering by status, priority, deck, owner, milestone, tags, and text search
- **Feature scaffolding** — Hero cards with linked Code/Design/Art/Audio sub-cards
- **Daily standups** — done, in-progress, blocked, and in-hand snapshot
- **Sprint health** — blocked, stale, unassigned, and suggested next cards
- **Batch operations** — pipe workflows and MCP batch tools (up to 20 cards/call)
- **Team coordination** — claim/release/delegate across multiple agents (MCP)
- **GDD sync** — parse a Game Design Document and sync tasks to Codecks
- **Snapshot caching** — MCP reads in <50ms with selective invalidation
- **1000+ tests** — full offline test suite, no live API calls

## Token Architecture

| Token | Used for | How to get it |
|-------|----------|---------------|
| `CODECKS_TOKEN` | Read + write | Browser cookies (`at` value) |
| `CODECKS_REPORT_TOKEN` | Creating cards | `codecks-cli generate-token` |
| `CODECKS_ACCESS_KEY` | Generating report tokens | Codecks Settings > Integrations |

Run `codecks-cli setup` for guided configuration, or see `.env.example` for manual setup.

## Documentation

| Document | Contents |
|----------|----------|
| [docs/ai-agent-guide.md](docs/ai-agent-guide.md) | Full AI agent setup, CLI reference, MCP setup, customization |
| [docs/cli-reference.md](docs/cli-reference.md) | CLI command reference and Python API |
| [docs/mcp-reference.md](docs/mcp-reference.md) | MCP tool inventory, caching, error contract, team coordination |
| [examples/](examples/) | Setup wizard, PM skill, game-dev agent example |
| [AGENTS.md](AGENTS.md) | AI agent instructions (tokens, API pitfalls, known bugs) |
| [DEVELOPMENT.md](DEVELOPMENT.md) | Architecture, dev setup, testing, release process |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute |
| [CHANGELOG.md](CHANGELOG.md) | Version history |
| [SECURITY.md](SECURITY.md) | Vulnerability reporting |

## Community

Questions? Ideas? Share your agent setup? Visit [Discussions](https://github.com/rangogamedev/codecks-cli/discussions).

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).
