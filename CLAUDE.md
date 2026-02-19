# CLAUDE.md — codecks-cli

Single-file Python CLI (`codecks_api.py`, ~2500 lines) for managing Codecks project cards. Zero external dependencies (stdlib only). Public repo, MIT license.

## Environment
- **Python**: `py` — never `python` or `python3`. Requires 3.10+.
- **Run**: `py codecks_api.py` (no args = full help). `--version` prints version.
- **Version**: `VERSION` constant in `codecks_api.py` (currently 0.4.0)

## Architecture

**File layout** (single file, top-to-bottom):
1. Module docstring (doubles as CLI help) → imports → `load_env`/`save_env_value`
2. `VERSION` + module globals (tokens, constants, `_cache`)
3. Security helpers (`_mask_token`, `_safe_json_parse`, `_sanitize_error`, `_try_call`, `_check_token`)
4. Google OAuth2 helpers
5. HTTP layer (`session_request`, `report_request`, `generate_report_token`)
6. Config helpers (`_load_project_names`, `_load_milestone_names`, `_load_users`)
7. Query helpers (`query`, `get_account`, `list_decks`, `list_cards`, `get_card`, `list_activity`, etc.)
8. Enrichment (`_enrich_cards` — resolves deck/milestone/owner names, normalizes tags)
9. Mutations (`create_card`, `update_card`, `archive_card`, `delete_card`, `bulk_status`, `dispatch`)
9b. Hand helpers (`_get_user_id`, `list_hand`, `add_to_hand`, `remove_from_hand`)
10. Resolution (`_resolve_deck_id`, `_resolve_milestone_id` — case-insensitive, exit on not-found)
10. Setup wizard (`_setup_discover_projects/milestones`, `cmd_setup`)
11. GDD helpers (`fetch_gdd`, `parse_gdd`, `sync_gdd`)
12. Output formatters (`output`, `_format_*_table`, `_format_cards_csv`, `_mutation_response`)
13. `parse_flags` → `main()` if/elif dispatch

**Key patterns:**
- Module-level globals for tokens — `cmd_setup()` uses `global` declarations to update them
- `_try_call(fn)` wraps functions that may `sys.exit()` — returns `None` on failure
- `output(data, formatter, fmt, csv_formatter)` dispatches JSON (default) / table / CSV
- `_cache` dict caches deck lookups per-invocation
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
**Read:** `account`, `cards` (filters: `--deck --status --project --milestone --search --tag --owner --sort --stats --hand --archived`), `card <id>`, `decks`, `projects`, `milestones`, `activity` (`--limit`)
**Hand:** `hand` (list hand cards), `hand <id...>` (add to hand), `unhand <id...>` (remove from hand)
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
