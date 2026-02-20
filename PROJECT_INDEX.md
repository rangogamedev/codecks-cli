# Project Index: `codecks-cli`

Purpose: Python CLI for an AI agent (or human) to control Codecks (web-based project management) via query/dispatch APIs.

## AI/Agent Guidance Files Read
- `CLAUDE.md`: Primary agent-facing operational guidance (architecture, pitfalls, commands, testing).
- `README.md`: Public usage and setup reference.
- `AGENTS.md` instructions from session context: skill and workflow constraints.
- `.gdd_cache.md`: Local cached GDD content used by GDD features (not code instructions, but relevant to behavior).

## Skills Used This Turn
- `skill-creator`: Used to structure reusable, low-noise project knowledge capture.
- `skill-installer`: Applied as requested; workflow conventions followed (no install action required for indexing task).

## Repo Layout
- `codecks_api.py`: CLI entrypoint, argparse parser, global flag extraction, command dispatch.
- `commands.py`: `cmd_*` handlers for each subcommand.
- `cards.py`: Domain operations for cards, decks, projects, milestones, hand, conversations.
- `api.py`: HTTP transport, query/dispatch wrappers, token checks, error shaping.
- `formatters.py`: JSON/table/CSV output and mutation response formatting.
- `gdd.py`: GDD fetch/parse/sync pipeline + Google OAuth support.
- `setup_wizard.py`: Interactive bootstrap/update flow for `.env`.
- `config.py`: Shared globals/constants, env loading/persistence, error classes.
- `tests/`: Unit tests for every core module, isolated from real API.

## Runtime Flow
1. `codecks_api.py:main` preprocesses `--format`/`--version`, builds parser, parses args.
2. Token gate runs for most commands (except setup/auth/version/token-generation paths).
3. Dispatch table routes subcommand to `commands.py` handler.
4. Handlers call domain functions in `cards.py` / `gdd.py` / `api.py`.
5. Output emitted via `formatters.output` in JSON/table/CSV.

## Command Surface (Subcommands)
- Setup/auth/config: `setup`, `generate-token`, `gdd-auth`, `gdd-revoke`
- Read/list: `account`, `decks`, `projects`, `milestones`, `cards`, `card`, `activity`, `conversations`, `hand`
- Mutations: `create`, `feature`, `update`, `archive`, `remove`, `unarchive`, `delete`, `done`, `start`, `comment`, `unhand`
- Raw API: `query`, `dispatch`
- GDD: `gdd`, `gdd-sync`
- Utility: `version`, global `--format table|csv|json`, `--version`

## Core Data/Auth Model
- `CODECKS_TOKEN`: Session token (`X-Auth-Token`) for read/update paths.
- `CODECKS_REPORT_TOKEN`: Stable report token for card creation.
- `CODECKS_ACCESS_KEY`: Generates report tokens.
- `CODECKS_USER_ID`: Needed for hand queue ops.
- Optional Google OAuth fields: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`.
- Name mapping in `.env`: `CODECKS_PROJECTS`, `CODECKS_MILESTONES`.

## Important Behavioral Constraints
- Query fields are camelCase; response fields are snake_case.
- Card title is the first line of `content`.
- Expired session tokens can appear as empty 200 responses, not only auth errors.
- API rate limit: 40 requests / 5 seconds.
- Doc cards cannot accept priority/effort/status updates.
- Hand operations use `handQueue/*` dispatch and `queueEntries` data.

## Output/Error Conventions
- Success mutation prefix: `OK:`
- Non-fatal stderr prefixes: `[WARN]`, `[INFO]`
- Fatal prefixes: `[ERROR]` (exit 1), `[TOKEN_EXPIRED]` / `[SETUP_NEEDED]` (exit 2)
- Data should go to stdout; diagnostics to stderr.

## Testing Index
- Test entrypoint: `py -m pytest tests/ -v`
- Isolation fixture: `tests/conftest.py` resets `config` globals each test.
- Coverage map:
  - `tests/test_cli.py` -> `codecks_api.py`
  - `tests/test_commands.py` -> command handlers and regression edge cases
  - `tests/test_cards.py` -> card/domain logic
  - `tests/test_api.py` -> transport/error handling/token behavior
  - `tests/test_formatters.py` -> table/csv/json formatting
  - `tests/test_gdd.py` -> GDD parsing/sync/error handling
  - `tests/test_config.py` -> env load/save/constants

## Suggested Orientation Order For New Agents
1. Read `CLAUDE.md` for constraints and known pitfalls.
2. Read `codecks_api.py` for CLI contract and dispatch map.
3. Read `commands.py` for command-level behavior.
4. Dive into `cards.py`, `api.py`, `gdd.py` based on task area.
5. Validate changes with corresponding tests in `tests/`.
