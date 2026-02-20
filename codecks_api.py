"""
codecks-cli — CLI tool for managing Codecks.io cards, decks, and projects
"""

import argparse
import sys

import config
from api import _check_token
from commands import (
    cmd_setup, cmd_query, cmd_account, cmd_decks, cmd_projects,
    cmd_milestones, cmd_cards, cmd_card, cmd_create, cmd_update,
    cmd_archive, cmd_unarchive, cmd_delete, cmd_done, cmd_start,
    cmd_hand, cmd_unhand, cmd_activity, cmd_comment, cmd_conversations,
    cmd_gdd, cmd_gdd_sync, cmd_gdd_auth, cmd_gdd_revoke,
    cmd_generate_token, cmd_dispatch,
)

HELP_TEXT = """\
Usage: py codecks_api.py <command> [args...]

Global flags:
  --format table          Output as readable text instead of JSON (default: json)
  --format csv            Output cards as CSV (cards command only)
  --version               Show version number

Commands:
  setup                   - Interactive setup wizard (run this first!)
  query <json>            - Run a raw query against the API (uses session token)
  account                 - Show account info
  cards                   - List all cards
    --deck <name>           Filter by deck name (e.g. --deck Features)
    --status <s>            Filter: not_started, started, done, blocked
    --project <name>        Filter by project (e.g. --project "Tea Shop")
    --milestone <name>      Filter by milestone (e.g. --milestone MVP)
    --search <text>         Search cards by title/content
    --tag <name>            Filter by tag (e.g. --tag bug)
    --owner <name>          Filter by owner (e.g. --owner Thomas)
    --sort <field>          Sort by: status, priority, effort, deck, title,
                            owner, updated, created
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
  create <title>          - Create a card via Report Token (stable, no expiry)
    --deck <name>           Place card in a specific deck
    --project <name>        Place card in first deck of a project
    --content <text>        Card description/content
    --severity <level>      critical, high, low, or null
    --doc                   Create as a doc card (no workflow states)
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
    """Extract --format and --version from argv regardless of position.
    Returns (format_str, remaining_argv). Handles --version directly."""
    fmt = "json"
    remaining = []
    i = 0
    while i < len(argv):
        if argv[i] == "--version":
            print(f"codecks-cli {config.VERSION}")
            sys.exit(0)
        elif argv[i] == "--format" and i + 1 < len(argv):
            fmt = argv[i + 1]
            if fmt not in ("json", "table", "csv"):
                print(f"[ERROR] Invalid format '{fmt}'. Use: json, table, csv",
                      file=sys.stderr)
                sys.exit(1)
            i += 2
            continue
        else:
            remaining.append(argv[i])
        i += 1
    return fmt, remaining


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

class _SubcommandParser(argparse.ArgumentParser):
    """Subparser that prints concise errors instead of full help text."""
    def error(self, message):
        print(f"[ERROR] {message}", file=sys.stderr)
        sys.exit(1)


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
    p.add_argument("--status", choices=sorted(config.VALID_STATUSES))
    p.add_argument("--project")
    p.add_argument("--search")
    p.add_argument("--milestone")
    p.add_argument("--tag")
    p.add_argument("--owner")
    p.add_argument("--sort", choices=sorted(config.VALID_SORT_FIELDS))
    p.add_argument("--type", choices=sorted(config.VALID_CARD_TYPES))
    p.add_argument("--hero")
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
    p.add_argument("--severity")
    p.add_argument("--doc", action="store_true")

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
    p.add_argument("--limit", type=int, default=20)

    # --- comment ---
    p = sub.add_parser("comment")
    p.add_argument("card_id")
    p.add_argument("message", nargs="?")
    p.add_argument("--thread")
    p.add_argument("--close")
    p.add_argument("--reopen")

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
    "archive": cmd_archive,
    "remove": cmd_archive,
    "unarchive": cmd_unarchive,
    "delete": cmd_delete,
    "done": cmd_done,
    "start": cmd_start,
    "hand": cmd_hand,
    "unhand": cmd_unhand,
    "activity": cmd_activity,
    "comment": cmd_comment,
    "conversations": cmd_conversations,
    "gdd": cmd_gdd,
    "gdd-sync": cmd_gdd_sync,
    "gdd-auth": cmd_gdd_auth,
    "gdd-revoke": cmd_gdd_revoke,
    "generate-token": cmd_generate_token,
    "dispatch": cmd_dispatch,
}


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    if len(sys.argv) < 2:
        print(HELP_TEXT)
        sys.exit(0)

    # Extract --format and --version from anywhere in argv
    fmt, remaining_argv = _extract_global_flags(sys.argv[1:])

    if not remaining_argv:
        print(HELP_TEXT)
        sys.exit(0)

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
        print("[ERROR] Permanent deletion requires --confirm flag.",
              file=sys.stderr)
        print(f"Did you mean: py codecks_api.py archive {ns.card_id}",
              file=sys.stderr)
        sys.exit(1)

    # Validate token before any API command
    if cmd not in NO_TOKEN_COMMANDS:
        _check_token()

    handler = DISPATCH.get(cmd)
    if handler:
        handler(ns)
    else:
        print(f"[ERROR] Unknown command: {cmd}", file=sys.stderr)
        print(HELP_TEXT)
        sys.exit(1)


if __name__ == "__main__":
    main()
