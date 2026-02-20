"""
codecks-cli — CLI tool for managing Codecks.io cards, decks, and projects
"""

import argparse
import json
import sys

import config
from config import CliError
from api import _check_token
from commands import (
    cmd_setup, cmd_query, cmd_account, cmd_decks, cmd_projects,
    cmd_milestones, cmd_cards, cmd_card, cmd_create, cmd_update,
    cmd_feature,
    cmd_archive, cmd_unarchive, cmd_delete, cmd_done, cmd_start,
    cmd_hand, cmd_unhand, cmd_activity, cmd_pm_focus, cmd_standup,
    cmd_comment, cmd_conversations,
    cmd_gdd, cmd_gdd_sync, cmd_gdd_auth, cmd_gdd_revoke,
    cmd_generate_token, cmd_dispatch,
)

HELP_TEXT = """\
Usage: py codecks_api.py <command> [args...]

Global flags:
  --format table          Output as readable text instead of JSON (default: json)
  --format csv            Output cards as CSV (cards command only)
  --strict                Enable strict agent mode (fail fast on ambiguous raw API responses)
  --version               Show version number

Commands:
  setup                   - Interactive setup wizard (run this first!)
  query <json>            - Run a raw query against the API (uses session token)
  account                 - Show account info
  cards                   - List all cards
    --deck <name>           Filter by deck name (e.g. --deck Features)
    --status <s>            Filter: not_started, started, done, blocked, in_review
                            (comma-separated: --status started,blocked)
    --priority <p>          Filter: a, b, c, null
                            (comma-separated: --priority a,b)
    --project <name>        Filter by project (e.g. --project "Tea Shop")
    --milestone <name>      Filter by milestone (e.g. --milestone MVP)
    --search <text>         Search cards by title/content
    --tag <name>            Filter by tag (e.g. --tag bug)
    --owner <name>          Filter by owner (e.g. --owner Thomas, --owner none)
    --sort <field>          Sort by: status, priority, effort, deck, title,
                            owner, updated, created
    --stale <days>          Find cards not updated in N days
    --updated-after <date>  Cards updated after date (YYYY-MM-DD)
    --updated-before <date> Cards updated before date (YYYY-MM-DD)
    --stats                 Show card count summary instead of card list
    --hand                  Show only cards in your hand
    --hero <id>             Show only sub-cards of a hero card
    --type <type>           Filter by card type: hero, doc
    --archived              Show archived cards instead of active ones
  card <id>               - Get details for a specific card
  decks                   - List all decks
  projects                - List all projects (derived from decks)
  milestones              - List all milestones
  activity                - Show recent activity feed
    --limit <n>             Number of events to show (default: 20)
  pm-focus                - Focus dashboard for PM triage
    --project <name>        Filter by project
    --owner <name>          Filter by owner
    --limit <n>             Suggested next-card count (default: 5)
    --stale-days <n>        Days threshold for stale detection (default: 14)
  standup                 - Daily standup summary
    --days <n>              Lookback for recent completions (default: 2)
    --project <name>        Filter by project
    --owner <name>          Filter by owner
  create <title>          - Create a card via Report Token (stable, no expiry)
    --deck <name>           Place card in a specific deck
    --project <name>        Place card in first deck of a project
    --content <text>        Card description/content
    --severity <level>      critical, high, low, or null
    --doc                   Create as a doc card (no workflow states)
    --allow-duplicate       Bypass exact duplicate-title protection
  feature <title>         - Scaffold Hero + lane sub-cards (no Journey mode)
    --hero-deck <name>      Hero destination deck (required)
    --code-deck <name>      Code sub-card deck (required)
    --design-deck <name>    Design sub-card deck (required)
    --art-deck <name>       Art sub-card deck (required unless --skip-art)
    --skip-art              Skip art lane for non-visual features
    --description <text>    Feature context/goal
    --owner <name>          Assign owner to hero and sub-cards
    --priority <level>      a, b, c, or null
    --effort <n>            Apply effort to sub-cards
    --allow-duplicate       Bypass exact duplicate Hero-title protection
  update <id> [id...]     - Update card properties (supports multiple IDs)
    --status <state>        not_started, started, done, blocked, in_review
    --priority <level>      a (high), b (medium), c (low), or null
    --effort <n>            Effort estimation (number)
    --deck <name>           Move card to a different deck
    --title <text>          Rename the card (single card only)
    --content <text>        Update card description (single card only)
    --milestone <name>      Assign to milestone (use "none" to clear)
    --hero <parent_id>      Make this a sub-card of a hero card (use "none" to detach)
    --owner <name>          Assign owner (use "none" to unassign)
    --tag <tags>            Set tags (comma-separated, use "none" to clear all)
    --doc <true|false>      Convert to/from doc card
  archive|remove <id>     - Remove a card (reversible, this is the standard way)
  unarchive <id>          - Restore an archived card
  delete <id> --confirm   - PERMANENTLY delete (requires --confirm, prefer archive)
  done <id> [id...]       - Mark one or more cards as done
  start <id> [id...]      - Mark one or more cards as started
  hand                    - List cards in your hand
  hand <id> [id...]       - Add cards to your hand
  unhand <id> [id...]     - Remove cards from your hand
  comment <card_id> "msg" - Start a new comment thread on a card
    --thread <id> "msg"     Reply to an existing thread
    --close <id>            Close a thread
    --reopen <id>           Reopen a closed thread
  conversations <card_id> - List all conversations on a card
  gdd                     - Show parsed GDD task tree from Google Doc
    --refresh               Force re-fetch from Google (ignore cache)
    --file <path>           Use a local markdown file (use "-" for stdin)
    --save-cache            Save fetched content to .gdd_cache.md for offline use
  gdd-sync                - Sync GDD tasks to Codecks cards
    --project <name>        (required) Target project for card placement
    --section <name>        Sync only one GDD section
    --apply                 Actually create cards (dry-run without this)
    --quiet                 Show summary only (suppress per-card listing)
    --refresh               Force re-fetch GDD before syncing
    --file <path>           Use a local markdown file (use "-" for stdin)
    --save-cache            Save fetched content to .gdd_cache.md for offline use
  gdd-auth                - Authorize Google Drive access (opens browser, one-time)
  gdd-revoke              - Revoke Google Drive authorization and delete tokens
  generate-token          - Generate a new Report Token using the Access Key
    --label <text>          Label for the token (default: claude-code)
  dispatch <path> <json>  - Raw dispatch call (uses session token)
"""


# ---------------------------------------------------------------------------
# Global flag extraction (before argparse, so --format works after subcommand)
# ---------------------------------------------------------------------------

def _extract_global_flags(argv):
    """Extract global flags from argv regardless of position.
    Returns (format_str, strict_bool, remaining_argv). Handles --version directly."""
    fmt = "json"
    strict = False
    remaining = []
    i = 0
    while i < len(argv):
        if argv[i] == "--version":
            print(f"codecks-cli {config.VERSION}")
            sys.exit(0)
        elif argv[i] == "--strict":
            strict = True
            i += 1
            continue
        elif argv[i] == "--format" and i + 1 < len(argv):
            fmt = argv[i + 1]
            if fmt not in ("json", "table", "csv"):
                raise CliError(f"[ERROR] Invalid format '{fmt}'. "
                               "Use: json, table, csv")
            i += 2
            continue
        else:
            remaining.append(argv[i])
        i += 1
    return fmt, strict, remaining


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

class _SubcommandParser(argparse.ArgumentParser):
    """Subparser that raises CliError instead of printing full help text."""
    def error(self, message):
        raise CliError(f"[ERROR] {message}")


def _positive_int(value):
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def build_parser():
    parser = _SubcommandParser(
        prog="codecks-cli",
        description="CLI tool for managing Codecks.io cards, decks, and projects",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    parser.add_argument("--help", "-h", action="store_true", dest="show_help")
    sub = parser.add_subparsers(dest="command",
                                parser_class=_SubcommandParser)

    # --- setup ---
    sub.add_parser("setup")

    # --- query ---
    p = sub.add_parser("query")
    p.add_argument("json_query")

    # --- account / decks / projects / milestones ---
    sub.add_parser("account")
    sub.add_parser("decks")
    sub.add_parser("projects")
    sub.add_parser("milestones")

    # --- cards ---
    p = sub.add_parser("cards")
    p.add_argument("--deck")
    p.add_argument("--status")  # comma-separated: started,blocked
    p.add_argument("--priority")  # comma-separated: a,b
    p.add_argument("--project")
    p.add_argument("--search")
    p.add_argument("--milestone")
    p.add_argument("--tag")
    p.add_argument("--owner")
    p.add_argument("--sort", choices=sorted(config.VALID_SORT_FIELDS))
    p.add_argument("--type", choices=sorted(config.VALID_CARD_TYPES))
    p.add_argument("--hero")
    p.add_argument("--stale", type=_positive_int, metavar="DAYS")
    p.add_argument("--updated-after", dest="updated_after")
    p.add_argument("--updated-before", dest="updated_before")
    p.add_argument("--stats", action="store_true")
    p.add_argument("--hand", action="store_true")
    p.add_argument("--archived", action="store_true")

    # --- card ---
    p = sub.add_parser("card")
    p.add_argument("card_id")

    # --- create ---
    p = sub.add_parser("create")
    p.add_argument("title")
    p.add_argument("--deck")
    p.add_argument("--project")
    p.add_argument("--content")
    p.add_argument("--severity", choices=sorted(config.VALID_SEVERITIES))
    p.add_argument("--doc", action="store_true")
    p.add_argument("--allow-duplicate", action="store_true",
                   dest="allow_duplicate")

    # --- update ---
    p = sub.add_parser("update")
    p.add_argument("card_ids", nargs="+")
    p.add_argument("--status", choices=sorted(config.VALID_STATUSES))
    p.add_argument("--priority", choices=sorted(config.VALID_PRIORITIES))
    p.add_argument("--effort")
    p.add_argument("--deck")
    p.add_argument("--title")
    p.add_argument("--content")
    p.add_argument("--milestone")
    p.add_argument("--hero")
    p.add_argument("--owner")
    p.add_argument("--tag")
    p.add_argument("--doc")

    # --- feature ---
    p = sub.add_parser("feature")
    p.add_argument("title")
    p.add_argument("--hero-deck", required=True, dest="hero_deck")
    p.add_argument("--code-deck", required=True, dest="code_deck")
    p.add_argument("--design-deck", required=True, dest="design_deck")
    p.add_argument("--art-deck", dest="art_deck")
    p.add_argument("--skip-art", action="store_true", dest="skip_art")
    p.add_argument("--description")
    p.add_argument("--owner")
    p.add_argument("--priority", choices=sorted(config.VALID_PRIORITIES))
    p.add_argument("--effort", type=_positive_int)
    p.add_argument("--allow-duplicate", action="store_true",
                   dest="allow_duplicate")

    # --- archive / remove ---
    for name in ("archive", "remove"):
        p = sub.add_parser(name)
        p.add_argument("card_id")

    # --- unarchive ---
    p = sub.add_parser("unarchive")
    p.add_argument("card_id")

    # --- delete ---
    p = sub.add_parser("delete")
    p.add_argument("card_id")
    p.add_argument("--confirm", action="store_true")

    # --- done / start ---
    p = sub.add_parser("done")
    p.add_argument("card_ids", nargs="+")
    p = sub.add_parser("start")
    p.add_argument("card_ids", nargs="+")

    # --- hand ---
    p = sub.add_parser("hand")
    p.add_argument("card_ids", nargs="*")

    # --- unhand ---
    p = sub.add_parser("unhand")
    p.add_argument("card_ids", nargs="+")

    # --- activity ---
    p = sub.add_parser("activity")
    p.add_argument("--limit", type=_positive_int, default=20)

    # --- pm-focus ---
    p = sub.add_parser("pm-focus")
    p.add_argument("--project")
    p.add_argument("--owner")
    p.add_argument("--limit", type=_positive_int, default=5)
    p.add_argument("--stale-days", type=_positive_int, default=14, dest="stale_days")

    # --- standup ---
    p = sub.add_parser("standup")
    p.add_argument("--days", type=_positive_int, default=2)
    p.add_argument("--project")
    p.add_argument("--owner")

    # --- comment ---
    p = sub.add_parser("comment")
    p.add_argument("card_id")
    p.add_argument("message", nargs="?")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--thread")
    mode.add_argument("--close")
    mode.add_argument("--reopen")

    # --- conversations ---
    p = sub.add_parser("conversations")
    p.add_argument("card_id")

    # --- gdd ---
    p = sub.add_parser("gdd")
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--file")
    p.add_argument("--save-cache", action="store_true", dest="save_cache")

    # --- gdd-sync ---
    p = sub.add_parser("gdd-sync")
    p.add_argument("--project")
    p.add_argument("--section")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--file")
    p.add_argument("--save-cache", action="store_true", dest="save_cache")

    # --- gdd-auth / gdd-revoke ---
    sub.add_parser("gdd-auth")
    sub.add_parser("gdd-revoke")

    # --- generate-token ---
    p = sub.add_parser("generate-token")
    p.add_argument("--label", default="claude-code")

    # --- dispatch ---
    p = sub.add_parser("dispatch")
    p.add_argument("path")
    p.add_argument("json_data")

    # --- version (bare word) ---
    sub.add_parser("version")

    return parser


# ---------------------------------------------------------------------------
# Command dispatch
# ---------------------------------------------------------------------------

NO_TOKEN_COMMANDS = {"setup", "gdd-auth", "gdd-revoke", "generate-token",
                     "version"}

DISPATCH = {
    "query": cmd_query,
    "account": cmd_account,
    "decks": cmd_decks,
    "projects": cmd_projects,
    "milestones": cmd_milestones,
    "cards": cmd_cards,
    "card": cmd_card,
    "create": cmd_create,
    "update": cmd_update,
    "feature": cmd_feature,
    "archive": cmd_archive,
    "remove": cmd_archive,
    "unarchive": cmd_unarchive,
    "delete": cmd_delete,
    "done": cmd_done,
    "start": cmd_start,
    "hand": cmd_hand,
    "unhand": cmd_unhand,
    "activity": cmd_activity,
    "pm-focus": cmd_pm_focus,
    "standup": cmd_standup,
    "comment": cmd_comment,
    "conversations": cmd_conversations,
    "gdd": cmd_gdd,
    "gdd-sync": cmd_gdd_sync,
    "gdd-auth": cmd_gdd_auth,
    "gdd-revoke": cmd_gdd_revoke,
    "generate-token": cmd_generate_token,
    "dispatch": cmd_dispatch,
}


def _error_type_from_message(message):
    if message.startswith("[TOKEN_EXPIRED]"):
        return "token_expired"
    if message.startswith("[SETUP_NEEDED]"):
        return "setup_needed"
    if message.startswith("[ERROR]"):
        return "error"
    return "cli_error"


def _emit_cli_error(err, fmt):
    msg = str(err)
    if fmt == "json":
        payload = {
            "ok": False,
            "error": {
                "type": _error_type_from_message(msg),
                "message": msg,
                "exit_code": getattr(err, "exit_code", 1),
            },
        }
        print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
        return
    print(msg, file=sys.stderr)


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    if len(sys.argv) < 2:
        print(HELP_TEXT)
        sys.exit(0)

    # Extract --format and --version from anywhere in argv
    fmt, strict, remaining_argv = _extract_global_flags(sys.argv[1:])
    config.RUNTIME_STRICT = strict

    if not remaining_argv:
        print(HELP_TEXT)
        sys.exit(0)

    try:
        parser = build_parser()
        ns = parser.parse_args(remaining_argv)
        ns.format = fmt  # inject global format flag

        if ns.show_help or not ns.command:
            print(HELP_TEXT)
            sys.exit(0)

        cmd = ns.command

        if cmd == "version":
            print(f"codecks-cli {config.VERSION}")
            sys.exit(0)

        if cmd == "setup":
            cmd_setup()
            sys.exit(0)

        if cmd == "delete" and not ns.confirm:
            raise CliError(
                "[ERROR] Permanent deletion requires --confirm flag.\n"
                f"Did you mean: py codecks_api.py archive {ns.card_id}")

        # Validate token before any API command
        if cmd not in NO_TOKEN_COMMANDS:
            _check_token()

        handler = DISPATCH.get(cmd)
        if handler:
            handler(ns)
        else:
            raise CliError(f"[ERROR] Unknown command: {cmd}")

    except CliError as e:
        _emit_cli_error(e, fmt)
        sys.exit(e.exit_code)


if __name__ == "__main__":
    main()
