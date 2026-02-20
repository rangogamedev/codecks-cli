# CLAUDE.md — codecks-cli

Multi-module Python CLI for managing Codecks project cards. Zero external dependencies (stdlib only). Public repo, MIT license.

## Environment
- **Python**: `py` — never `python` or `python3`. Requires 3.10+.
- **Run**: `py codecks_api.py` (no args = full help). `--version` prints version.
- **Version**: `VERSION` constant in `config.py` (currently 0.4.0)

## Architecture

**Module layout** (~3000 lines across 7 files):
| Module | Lines | Purpose |
|--------|-------|---------|
| `codecks_api.py` | ~700 | Entry point: `__doc__`, `parse_flags()`, `main()` dispatch |
| `config.py` | ~95 | Shared state: env, tokens, constants, `load_env()`, `save_env_value()` |
| `api.py` | ~225 | HTTP layer: `session_request`, `query`, `dispatch`, token validation |
| `cards.py` | ~570 | Card CRUD, hand, conversations, name resolution, enrichment |
| `formatters.py` | ~470 | All `_format_*` functions, `output()`, `_mutation_response()` |
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
codecks_api.py     ← all modules
```

**Key patterns:**
- Module-level state lives in `config.py` — setup wizard updates via `config.SESSION_TOKEN = ...`
- `_try_call(fn)` in `api.py` wraps functions that may `sys.exit()` — returns `None` on failure
- `output(data, formatter, fmt, csv_formatter)` in `formatters.py` dispatches JSON/table/CSV
- `config._cache` dict caches deck lookups per-invocation
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
- Card title = first line of `content` field
- Project/milestone names not queryable — stored as `.env` mappings (`CODECKS_PROJECTS=uuid=Name,...`)
- Rate limit: 40 req / 5 sec. `sync_gdd` sleeps 1s every 10 cards created.
- Hand uses `queueEntries` (not `handCards`) for the card list. Add via `handQueue/setCardOrders`, remove via `handQueue/removeCards`.
- Tags: use `masterTags` field (string array). Setting `masterTags` syncs `tags` automatically. Setting `tags` alone does NOT sync `masterTags`.
- Owner: use `assigneeId` in `cards/update`. Set to `null` to unassign. Query via `assignee` relation (returns user model).
- Activity: `activities` on account with `type`, `createdAt`, `card`, `data.diff`, `changer`/`deck` relations.
- `isDoc` field toggles doc card mode. `childCardInfo` returns sub-card count for hero cards.
- **Doc cards** are for documentation, not tasks. They cannot have priority, effort, or status changed (API returns 400). Only owner, tags, milestone, deck, title, content, and hero can be set on doc cards.

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

Invalid → `[ERROR]` with valid options listed.

## Commands Quick Reference
**Read:** `account`, `cards` (filters: `--deck --status --project --milestone --search --tag --owner --sort --stats --hand --hero <id> --type hero|doc --archived`), `card <id>` (shows checklist, conversations, sub-cards), `decks`, `projects`, `milestones`, `activity` (`--limit`)
**Hand:** `hand` (list hand cards), `hand <id...>` (add to hand), `unhand <id...>` (remove from hand)
**Comments:** `comment <card_id> "msg"` (new thread), `comment <card_id> --thread <id> "reply"`, `comment <card_id> --close <id>`, `comment <card_id> --reopen <id>`, `conversations <card_id>` (list all)
**Mutate:** `create <title>` (`--deck --project --content --severity --doc`), `update <id> [id...]` (`--status --priority --effort --deck --title --content --milestone --hero --owner --tag --doc`), `done/start <id...>`, `archive/unarchive <id>`, `delete <id> --confirm`
**GDD:** `gdd` (`--refresh --file --save-cache`), `gdd-sync` (`--project --section --apply --quiet --refresh --file`), `gdd-auth`, `gdd-revoke`
**Other:** `setup`, `generate-token --label`, `query <json>`, `dispatch <path> <json>`
**Global flags:** `--format table|csv|json` (default json), `--version`

## Known Bugs Fixed (do not reintroduce)
1. **False TOKEN_EXPIRED on filtered empty results** — `warn_if_empty` only called when no server-side filters applied
2. **account table showed raw JSON** — added `_format_account_table()`
3. **Sort by effort crashed with None** — tuple sort key `(0, val)` / `(1, "")` for blanks-last

## Skills (`.claude/commands/`)
- `/test-all` — full regression test against live API (8 groups)
- `/release` — version bump, changelog, test, commit, push, optional GitHub release
- `/api-ref` — complete command/flag reference (loads into context)
- `/security-audit` — scan for leaked secrets before pushing
- `/codecks-docs <topic>` — fetch and summarize Codecks manual pages (e.g. `/codecks-docs hand`)

## Git & Releases
- Commit style: short present tense (e.g. "Add --sort flag to cards command")
- Never commit `.env`, `.gdd_tokens.json`, `.gdd_cache.md` — all gitignored
- `.claude/` is gitignored (local settings/commands only)
- Run `/security-audit` before pushing (repo is public)
- Run `/test-all` for full regression (8 groups, live API)
- Run `/release` for version bump + changelog + test + commit + push
