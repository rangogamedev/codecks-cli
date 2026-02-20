# CLAUDE.md — codecks-cli

Multi-module Python CLI for managing Codecks project cards. Zero external dependencies (stdlib only).
Public repo (MIT): https://github.com/rangogamedev/codecks-cli

## Environment
- **Python**: `py` — never `python` or `python3`. Requires 3.10+.
- **Run**: `py codecks_api.py` (no args = full help). `--version` prints version.
- **Test**: `py -m pytest tests/ -v` (178 unit tests, no API calls)
- **Version**: `VERSION` constant in `config.py` (currently 0.4.0)

## Architecture

**Module layout** (~3150 lines across 8 files):
| Module | Lines | Purpose |
|--------|-------|---------|
| `codecks_api.py` | ~380 | Entry point: help text, `_extract_global_flags()`, `build_parser()`, `main()` dispatch |
| `config.py` | ~95 | Shared state: env, tokens, constants, `load_env()`, `save_env_value()` |
| `api.py` | ~220 | HTTP layer: `session_request`, `query`, `dispatch`, token validation |
| `cards.py` | ~550 | Card CRUD, hand, conversations, name resolution, enrichment |
| `commands.py` | ~475 | Command handlers: `cmd_*()` functions receiving `argparse.Namespace` |
| `formatters.py` | ~500 | All `_format_*` functions, `output()`, `_mutation_response()` |
| `gdd.py` | ~540 | Google OAuth2, GDD fetch/parse/sync |
| `setup_wizard.py` | ~400 | Interactive setup wizard |

**Dependency graph** (no circular imports):
```
config.py          ← pure data, no project imports
api.py             ← config
cards.py           ← config, api
formatters.py      ← config, cards
gdd.py             ← config, cards
setup_wizard.py    ← config, api, cards
commands.py        ← config, api, cards, formatters, gdd, setup_wizard
codecks_api.py     ← config, api, commands
```

**Key patterns:**
- Module-level state lives in `config.py` — setup wizard updates via `config.SESSION_TOKEN = ...`
- `_extract_global_flags()` pre-processes argv for `--format`/`--version` before argparse
- `build_parser()` returns argparse parser with subparsers for each command
- `DISPATCH` dict in `main()` maps command names → `cmd_*` handlers
- `NO_TOKEN_COMMANDS` set for commands that skip `_check_token()`
- `CliError(msg)` / `SetupError(msg)` exceptions in `config.py` — raised instead of `sys.exit(1)`/`sys.exit(2)`. Caught once in `main()`. Messages include `[ERROR]`/`[TOKEN_EXPIRED]`/`[SETUP_NEEDED]` prefixes.
- `_try_call(fn)` in `api.py` wraps functions that may raise `CliError` — returns `None` on failure
- `_http_request()` checks Content-Type on parse failure — proxy/HTML responses get a specific error message
- `sync_gdd` uses structured exceptions: `SetupError` aborts batch, `CliError` logged per-card, unexpected errors labeled
- `output(data, formatter, fmt, csv_formatter)` in `formatters.py` dispatches JSON/table/CSV
- `config._cache` dict caches deck/user lookups per-invocation
- Card lists omit `content` for token efficiency; `--search` adds it back
- Errors/warnings → `sys.stderr`. Data → `sys.stdout`
- `sys.stdout.reconfigure(encoding='utf-8')` for Windows Unicode support

**Output prefixes:** `OK:` (mutation success), `[ERROR]` (exit 1), `[TOKEN_EXPIRED]` / `[SETUP_NEEDED]` (exit 2), `[WARN]` / `[INFO]` (non-fatal, stderr)

## Tokens (in `.env`, never committed)
- `CODECKS_TOKEN` — session cookie (`at`), expires. Validated by `_check_token()` before every API command. Expired token returns HTTP 200 with empty data (not 401).
- `CODECKS_REPORT_TOKEN` — card creation, never expires. Uses URL param `?token=`.
- `CODECKS_ACCESS_KEY` — generates report tokens, never expires. Uses URL param `?accessKey=`.
- `CODECKS_USER_ID` — current user's UUID, used for hand operations. Auto-discovered from account roles if not set.
- Skip token check: `setup`, `gdd-auth`, `gdd-revoke`, `generate-token`, `--version`

## API Pitfalls
- Response: snake_case (`deck_id`). Query: camelCase (`deckId`)
- Use `cards({"cardId":"...", "visibility":"default"})` — never `card({"id":...})` (500 error)
- 500 error fields: `id`/`updatedAt`/`assigneeId`/`parentCardId`/`dueAt`/`creatorId`; relations: `users`/`projects`/`milestones`/`tags`/`userTags`/`projectTags`
- `lastUpdatedAt` works on card query. `assigneeId` as a field gives 500 (use `assignee` relation instead).
- Card title = first line of `content` field
- Rate limit: 40 req / 5 sec. `sync_gdd` sleeps 1s every 10 cards created. HTTP 429 returns a specific guidance message.
- Hand uses `queueEntries` (not `handCards`) for the card list. Add via `handQueue/setCardOrders` (`sessionId`, `userId`, `cardIds`, `draggedCardIds`), remove via `handQueue/removeCards` (`sessionId`, `cardIds`). `handCards` is a different model (top-7 bookmarked cards).
- Tags: use `masterTags` field (string array). Setting `masterTags` syncs `tags` automatically. Setting `tags` alone does NOT sync `masterTags`.
- Owner: use `assigneeId` in `cards/update`. Set to `null` to unassign. Query via `assignee` relation (returns user model).
- Activity: `activities` on account with `type`, `createdAt`, `card`, `data.diff`, `changer`/`deck` relations.
- `isDoc` field toggles doc card mode. `childCardInfo` returns sub-card count for hero cards.
- **Doc cards** cannot have priority, effort, or status changed (API returns 400). Only owner, tags, milestone, deck, title, content, and hero can be set.
- `.env name mappings`: `CODECKS_PROJECTS=uuid=Name,uuid=Name`, `CODECKS_MILESTONES=uuid=Name,uuid=Name` — auto-discovered by `setup`

## GDD Google Doc Access (OAuth2)
- Config: `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET` in `.env`
- Tokens: `.gdd_tokens.json` (gitignored), auto-refreshing
- Fetch chain: OAuth Bearer → public URL fallback → local `.gdd_cache.md`
- Manual fallback: `--file "path/to/doc.md"` or `--file -` for stdin
- Setup: `py codecks_api.py gdd-auth` (one-time, opens browser). Revoke: `gdd-revoke`

## Paid-Only Features (do NOT use)
Due dates, Dependencies, Time tracking, Runs/Capacity, Guardians, Beast Cards, Vision Board Smart Nodes

## Validation
| Flag | Valid values |
|------|-------------|
| `--status` | `not_started`, `started`, `done`, `blocked`, `in_review` |
| `--priority` | `a`, `b`, `c`, `null` |
| `--sort` | `status`, `priority`, `effort`, `deck`, `title`, `owner`, `updated`, `created` |
| `--effort` | integer or `null` |
| `--severity` | `critical`, `high`, `low`, `null` |
| `--type` | `hero`, `doc` |

Invalid → `[ERROR]` with valid options listed.

## Commands Quick Reference
**Read:** `account`, `cards` (filters: `--deck --status --project --milestone --search --tag --owner --sort --stats --hand --hero <id> --type hero|doc --archived`), `card <id>` (shows checklist, conversations, sub-cards), `decks`, `projects`, `milestones`, `activity` (`--limit`)
**Hand:** `hand` (list hand cards), `hand <id...>` (add to hand), `unhand <id...>` (remove from hand)
**Comments:** `comment <card_id> "msg"` (new thread), `comment <card_id> --thread <id> "reply"`, `comment <card_id> --close <id>`, `comment <card_id> --reopen <id>`, `conversations <card_id>` (list all)
**Mutate:** `create <title>` (`--deck --project --content --severity --doc`), `update <id> [id...]` (`--status --priority --effort --deck --title --content --milestone --hero --owner --tag --doc`), `done/start <id...>`, `archive/unarchive <id>`, `delete <id> --confirm`
**GDD:** `gdd` (`--refresh --file --save-cache`), `gdd-sync` (`--project --section --apply --quiet --refresh --file --save-cache`), `gdd-auth`, `gdd-revoke`
**Other:** `setup`, `generate-token --label`, `query <json>`, `dispatch <path> <json>`
**Global flags:** `--format table|csv|json` (default json), `--version`

## Testing
- Run: `py -m pytest tests/ -v` (170 tests, ~6 seconds)
- `conftest.py` autouse `_isolate_config` fixture monkeypatches all `config` globals (tokens, env, cache) — no real `.env` or API calls
- Test files mirror source modules: `test_config.py`, `test_api.py`, `test_cards.py`, `test_commands.py`, `test_formatters.py`, `test_gdd.py`, `test_cli.py`
- Tests mock at module boundary (e.g. `commands.list_cards`, `commands.update_card`), verify output via `capsys`
- Known bug regressions have dedicated test classes (sort crashes, title bug, clear values, false warnings)

## Known Bugs Fixed (do not reintroduce)
1. **False TOKEN_EXPIRED on filtered empty results** — `warn_if_empty` only called when no server-side filters applied
2. **account table showed raw JSON** — added `_format_account_table()`
3. **Sort by effort crashed with None** — tuple sort key `(0, val)` / `(1, "")` for blanks-last
4. **update_card() silently dropped None values** — `if val is not None` filter broke clear operations (`--priority null`, `--milestone none`, `--owner none`, `--hero none`). Fixed: `payload.update(kwargs)` to pass None as JSON null
5. **Doc cards reject priority/effort/status** — API returns 400. Platform limitation, not a bug. Code must skip these fields for doc cards.
6. **Activity table showed raw UUIDs** — milestones and user IDs displayed as UUIDs. Fixed: resolve via `_load_milestone_names()` and `_load_users()`
7. **Date sort was oldest-first** — sort by `updated`/`created` should be newest-first. Fixed: `reverse=True` for date fields, blanks-last via `(-1, "")` tuple

## Skills (`.claude/commands/`)
- `/pm` — interactive PM session: dashboard, review/update/create cards, hand management, checklist formatting
- `/test-all` — full regression test against live API (8 groups), plus unit tests
- `/release` — version bump, changelog, test, commit, push, optional GitHub release
- `/api-ref` — complete command/flag reference (loads into context)
- `/security-audit` — scan for leaked secrets before pushing
- `/codecks-docs <topic>` — fetch and summarize Codecks manual pages (e.g. `/codecks-docs hand`)

## Git & Releases
- Commit style: short present tense (e.g. "Add --sort flag to cards command")
- Never commit `.env`, `.gdd_tokens.json`, `.gdd_cache.md` — all gitignored
- `.claude/` is gitignored (local settings/commands only)
- Run `/security-audit` before pushing (repo is public)
- Run `py -m pytest tests/` for unit tests, `/test-all` for full regression (live API)
- Run `/release` for version bump + changelog + test + commit + push
