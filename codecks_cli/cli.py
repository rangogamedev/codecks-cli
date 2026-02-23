"""
codecks-cli — CLI tool for managing Codecks.io cards, decks, and projects
"""

import argparse
import json
import sys

from codecks_cli import config
from codecks_cli.api import _check_token
from codecks_cli.commands import (
    cmd_account,
    cmd_activity,
    cmd_archive,
    cmd_card,
    cmd_cards,
    cmd_comment,
    cmd_completion,
    cmd_conversations,
    cmd_create,
    cmd_decks,
    cmd_delete,
    cmd_dispatch,
    cmd_done,
    cmd_feature,
    cmd_gdd,
    cmd_gdd_auth,
    cmd_gdd_revoke,
    cmd_gdd_sync,
    cmd_generate_token,
    cmd_hand,
    cmd_milestones,
    cmd_pm_focus,
    cmd_projects,
    cmd_query,
    cmd_split_features,
    cmd_standup,
    cmd_start,
    cmd_tags,
    cmd_unarchive,
    cmd_unhand,
    cmd_update,
)
from codecks_cli.exceptions import CliError
from codecks_cli.setup_wizard import cmd_setup

HELP_TEXT = """\
Usage: py codecks_api.py <command> [args...]

Global flags:
  --format table          Output as readable text instead of JSON (default: json)
  --format csv            Output cards as CSV (cards command only)
  --strict                Enable strict agent mode (fail fast on ambiguous raw API responses)
  --dry-run               Preview mutations without executing them
  --quiet, -q             Suppress confirmations and warnings
  --verbose, -v           Enable HTTP request logging
  --version               Show version number

Commands:
  setup                   - Interactive setup wizard (run this first!)
  query <json>            - Run a raw query against the API (uses session token)
  account                 - Show account info
  cards                   - List all cards
    -d, --deck <name>       Filter by deck name (e.g. -d Features)
    -s, --status <s>        Filter: not_started, started, done, blocked, in_review
                            (comma-separated: -s started,blocked)
    -p, --priority <p>      Filter: a, b, c, null
                            (comma-separated: -p a,b)
    --project <name>        Filter by project (e.g. --project "Tea Shop")
    --milestone <name>      Filter by milestone (e.g. --milestone MVP)
    -S, --search <text>     Search cards by title/content
    --tag <name>            Filter by tag (e.g. --tag bug)
    --owner <name>          Filter by owner (e.g. --owner Thomas, --owner none)
    --sort <field>          Sort by: status, priority, effort, deck, title,
                            owner, updated, created
    --stale <days>          Find cards not updated in N days
    --updated-after <date>  Cards updated after date (YYYY-MM-DD)
    --updated-before <date> Cards updated before date (YYYY-MM-DD)
    --limit <n>             Limit output count (client-side pagination)
    --offset <n>            Skip first N results (pagination)
    --stats                 Show card count summary instead of card list
    --hand                  Show only cards in your hand
    --hero <id>             Show only sub-cards of a hero card
    --type <type>           Filter by card type: hero, doc
    --archived              Show archived cards instead of active ones
  card <id>               - Get details for a specific card
    --no-content            Strip card body (keep title only)
    --no-conversations      Skip comment thread resolution
  decks                   - List all decks
  projects                - List all projects (derived from decks)
  milestones              - List all milestones
  tags                    - List project-level tags (sanctioned taxonomy)
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
    -d, --deck <name>       Place card in a specific deck
    --project <name>        Place card in first deck of a project
    -c, --content <text>    Card description/content
    --severity <level>      critical, high, low, or null
    --doc                   Create as a doc card (no workflow states)
    --allow-duplicate       Bypass exact duplicate-title protection
    --parent <id>           Nest as sub-card under parent card ID
  feature <title>         - Scaffold Hero + lane sub-cards (no Journey mode)
    --hero-deck <name>      Hero destination deck (required)
    --code-deck <name>      Code sub-card deck (required)
    --design-deck <name>    Design sub-card deck (required)
    --art-deck <name>       Art sub-card deck (required unless --skip-art)
    --skip-art              Skip art lane for non-visual features
    --audio-deck <name>     Audio sub-card deck (optional)
    --skip-audio            Skip audio lane
    --description <text>    Feature context/goal
    --owner <name>          Assign owner to hero and sub-cards
    --priority <level>      a, b, c, or null
    --effort <n>            Apply effort to sub-cards
    --allow-duplicate       Bypass exact duplicate Hero-title protection
  split-features          - Batch-split feature cards into discipline sub-cards
    --deck <name>           Source deck containing features (required)
    --code-deck <name>      Code sub-card deck (required)
    --design-deck <name>    Design sub-card deck (required)
    --art-deck <name>       Art sub-card deck (optional)
    --skip-art              Skip art lane
    --audio-deck <name>     Audio sub-card deck (optional)
    --skip-audio            Skip audio lane
    --priority <level>      Override priority for sub-cards (a, b, c, null)
    --dry-run               Preview analysis without creating cards
  update <id> [id...]     - Update card properties (supports multiple IDs)
    -s, --status <state>    not_started, started, done, blocked, in_review
    -p, --priority <level>  a (high), b (medium), c (low), or null
    -e, --effort <n>        Effort estimation (positive integer or "null")
    -d, --deck <name>       Move card to a different deck
    --title <text>          Rename the card (single card only)
    --content <text>        Update card description (single card only)
    --milestone <name>      Assign to milestone (use "none" to clear)
    --hero <parent_id>      Make this a sub-card of a hero card (use "none" to detach)
    --owner <name>          Assign owner (use "none" to unassign)
    --tag <tags>            Set tags (comma-separated, use "none" to clear all)
    --doc <true|false>      Convert to/from doc card
    --continue-on-error     Continue updating remaining cards after failure
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

    Returns (format_str, strict, dry_run, quiet, verbose, remaining_argv).
    Handles --version directly.
    """
    fmt = "json"
    strict = False
    dry_run = False
    quiet = False
    verbose = False
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
        elif argv[i] == "--dry-run":
            dry_run = True
            i += 1
            continue
        elif argv[i] in ("--quiet", "-q"):
            quiet = True
            i += 1
            continue
        elif argv[i] in ("--verbose", "-v"):
            verbose = True
            i += 1
            continue
        elif argv[i] == "--format" and i + 1 < len(argv):
            fmt = argv[i + 1]
            if fmt not in ("json", "table", "csv"):
                raise CliError(f"[ERROR] Invalid format '{fmt}'. Use: json, table, csv")
            i += 2
            continue
        else:
            remaining.append(argv[i])
        i += 1
    if quiet and verbose:
        raise CliError("[ERROR] --quiet and --verbose are mutually exclusive.")
    return fmt, strict, dry_run, quiet, verbose, remaining


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


def _non_negative_int(value):
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a non-negative integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be a non-negative integer")
    return parsed


def _effort_value(value):
    """Parse effort: positive integer or 'null' to clear."""
    if value == "null":
        return "null"
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer or 'null'") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer or 'null'")
    return str(parsed)


def build_parser():
    parser = _SubcommandParser(
        prog="codecks-cli",
        description="CLI tool for managing Codecks.io cards, decks, and projects",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    parser.add_argument("--help", "-h", action="store_true", dest="show_help")
    sub = parser.add_subparsers(dest="command", parser_class=_SubcommandParser)

    # --- setup ---
    sub.add_parser("setup").set_defaults(func=None)

    # --- query ---
    p = sub.add_parser("query")
    p.add_argument("json_query")
    p.set_defaults(func=cmd_query)

    # --- account / decks / projects / milestones / tags ---
    sub.add_parser("account").set_defaults(func=cmd_account)
    sub.add_parser("decks").set_defaults(func=cmd_decks)
    sub.add_parser("projects").set_defaults(func=cmd_projects)
    sub.add_parser("milestones").set_defaults(func=cmd_milestones)
    sub.add_parser("tags").set_defaults(func=cmd_tags)

    # --- cards ---
    p = sub.add_parser("cards")
    p.add_argument("--deck", "-d")
    p.add_argument("--status", "-s")  # comma-separated: started,blocked
    p.add_argument("--priority", "-p")  # comma-separated: a,b
    p.add_argument("--project")
    p.add_argument("--search", "-S")
    p.add_argument("--milestone")
    p.add_argument("--tag")
    p.add_argument("--owner")
    p.add_argument("--sort", choices=sorted(config.VALID_SORT_FIELDS))
    p.add_argument("--type", choices=sorted(config.VALID_CARD_TYPES))
    p.add_argument("--hero")
    p.add_argument("--stale", type=_positive_int, metavar="DAYS")
    p.add_argument("--updated-after", dest="updated_after")
    p.add_argument("--updated-before", dest="updated_before")
    p.add_argument("--limit", type=_positive_int)
    p.add_argument("--offset", type=_non_negative_int, default=0)
    p.add_argument("--stats", action="store_true")
    p.add_argument("--hand", action="store_true")
    p.add_argument("--archived", action="store_true")
    p.set_defaults(func=cmd_cards)

    # --- card ---
    p = sub.add_parser("card")
    p.add_argument("card_id")
    p.add_argument("--no-content", action="store_true", dest="no_content")
    p.add_argument("--no-conversations", action="store_true", dest="no_conversations")
    p.set_defaults(func=cmd_card)

    # --- create ---
    p = sub.add_parser("create")
    p.add_argument("title")
    p.add_argument("--deck", "-d")
    p.add_argument("--project")
    p.add_argument("--content", "-c")
    p.add_argument("--severity", choices=sorted(config.VALID_SEVERITIES))
    p.add_argument("--doc", action="store_true")
    p.add_argument("--allow-duplicate", action="store_true", dest="allow_duplicate")
    p.add_argument("--parent")
    p.set_defaults(func=cmd_create)

    # --- update ---
    p = sub.add_parser("update")
    p.add_argument("card_ids", nargs="+")
    p.add_argument("--status", "-s", choices=sorted(config.VALID_STATUSES))
    p.add_argument("--priority", "-p", choices=sorted(config.VALID_PRIORITIES))
    p.add_argument("--effort", "-e", type=_effort_value)
    p.add_argument("--deck", "-d")
    p.add_argument("--title")
    p.add_argument("--content")
    p.add_argument("--milestone")
    p.add_argument("--hero")
    p.add_argument("--owner")
    p.add_argument("--tag")
    p.add_argument("--doc")
    p.add_argument("--continue-on-error", action="store_true", dest="continue_on_error")
    p.set_defaults(func=cmd_update)

    # --- feature ---
    from codecks_cli.lanes import LANES

    p = sub.add_parser("feature")
    p.add_argument("title")
    p.add_argument("--hero-deck", required=True, dest="hero_deck")
    for lane_def in LANES:
        if lane_def.required:
            p.add_argument(
                f"--{lane_def.name}-deck",
                required=True,
                dest=f"{lane_def.name}_deck",
                help=lane_def.cli_help,
            )
        else:
            p.add_argument(
                f"--{lane_def.name}-deck",
                dest=f"{lane_def.name}_deck",
                help=lane_def.cli_help,
            )
            p.add_argument(
                f"--skip-{lane_def.name}",
                action="store_true",
                dest=f"skip_{lane_def.name}",
            )
    p.add_argument("--description")
    p.add_argument("--owner")
    p.add_argument("--priority", choices=sorted(config.VALID_PRIORITIES))
    p.add_argument("--effort", type=_positive_int)
    p.add_argument("--allow-duplicate", action="store_true", dest="allow_duplicate")
    p.set_defaults(func=cmd_feature)

    # --- split-features ---
    p = sub.add_parser("split-features")
    p.add_argument("--deck", required=True)
    for lane_def in LANES:
        if lane_def.required:
            p.add_argument(
                f"--{lane_def.name}-deck",
                required=True,
                dest=f"{lane_def.name}_deck",
                help=lane_def.cli_help,
            )
        else:
            p.add_argument(
                f"--{lane_def.name}-deck",
                dest=f"{lane_def.name}_deck",
                help=lane_def.cli_help,
            )
            p.add_argument(
                f"--skip-{lane_def.name}",
                action="store_true",
                dest=f"skip_{lane_def.name}",
            )
    p.add_argument("--priority", choices=sorted(config.VALID_PRIORITIES))
    p.add_argument("--dry-run", action="store_true", dest="dry_run")
    p.set_defaults(func=cmd_split_features)

    # --- archive / remove ---
    for name in ("archive", "remove"):
        p = sub.add_parser(name)
        p.add_argument("card_id")
        p.set_defaults(func=cmd_archive)

    # --- unarchive ---
    p = sub.add_parser("unarchive")
    p.add_argument("card_id")
    p.set_defaults(func=cmd_unarchive)

    # --- delete ---
    p = sub.add_parser("delete")
    p.add_argument("card_id")
    p.add_argument("--confirm", action="store_true")
    p.set_defaults(func=cmd_delete)

    # --- done / start ---
    p = sub.add_parser("done")
    p.add_argument("card_ids", nargs="+")
    p.set_defaults(func=cmd_done)
    p = sub.add_parser("start")
    p.add_argument("card_ids", nargs="+")
    p.set_defaults(func=cmd_start)

    # --- hand ---
    p = sub.add_parser("hand")
    p.add_argument("card_ids", nargs="*")
    p.set_defaults(func=cmd_hand)

    # --- unhand ---
    p = sub.add_parser("unhand")
    p.add_argument("card_ids", nargs="+")
    p.set_defaults(func=cmd_unhand)

    # --- activity ---
    p = sub.add_parser("activity")
    p.add_argument("--limit", type=_positive_int, default=20)
    p.set_defaults(func=cmd_activity)

    # --- pm-focus ---
    p = sub.add_parser("pm-focus")
    p.add_argument("--project")
    p.add_argument("--owner")
    p.add_argument("--limit", type=_positive_int, default=5)
    p.add_argument("--stale-days", type=_positive_int, default=14, dest="stale_days")
    p.set_defaults(func=cmd_pm_focus)

    # --- standup ---
    p = sub.add_parser("standup")
    p.add_argument("--days", type=_positive_int, default=2)
    p.add_argument("--project")
    p.add_argument("--owner")
    p.set_defaults(func=cmd_standup)

    # --- comment ---
    p = sub.add_parser("comment")
    p.add_argument("card_id")
    p.add_argument("message", nargs="?")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--thread")
    mode.add_argument("--close")
    mode.add_argument("--reopen")
    p.set_defaults(func=cmd_comment)

    # --- conversations ---
    p = sub.add_parser("conversations")
    p.add_argument("card_id")
    p.set_defaults(func=cmd_conversations)

    # --- gdd ---
    p = sub.add_parser("gdd")
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--file")
    p.add_argument("--save-cache", action="store_true", dest="save_cache")
    p.set_defaults(func=cmd_gdd)

    # --- gdd-sync ---
    p = sub.add_parser("gdd-sync")
    p.add_argument("--project")
    p.add_argument("--section")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--file")
    p.add_argument("--save-cache", action="store_true", dest="save_cache")
    p.set_defaults(func=cmd_gdd_sync)

    # --- gdd-auth / gdd-revoke ---
    sub.add_parser("gdd-auth").set_defaults(func=cmd_gdd_auth)
    sub.add_parser("gdd-revoke").set_defaults(func=cmd_gdd_revoke)

    # --- generate-token ---
    p = sub.add_parser("generate-token")
    p.add_argument("--label", default="claude-code")
    p.set_defaults(func=cmd_generate_token)

    # --- dispatch ---
    p = sub.add_parser("dispatch")
    p.add_argument("path")
    p.add_argument("json_data")
    p.set_defaults(func=cmd_dispatch)

    # --- completion ---
    p = sub.add_parser("completion")
    p.add_argument("--shell", choices=["bash", "zsh", "fish"], required=True)
    p.set_defaults(func=cmd_completion)

    # --- version (bare word) ---
    sub.add_parser("version").set_defaults(func=None)

    return parser


# ---------------------------------------------------------------------------
# Command dispatch
# ---------------------------------------------------------------------------

NO_TOKEN_COMMANDS = {"setup", "gdd-auth", "gdd-revoke", "generate-token", "version", "completion"}


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
            "schema_version": config.CONTRACT_SCHEMA_VERSION,
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
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if len(sys.argv) < 2:
        print(HELP_TEXT)
        sys.exit(0)

    # Extract global flags from anywhere in argv
    fmt, strict, dry_run, quiet, verbose, remaining_argv = _extract_global_flags(sys.argv[1:])
    config.RUNTIME_STRICT = strict
    config.RUNTIME_DRY_RUN = dry_run
    config.RUNTIME_QUIET = quiet
    config.RUNTIME_VERBOSE = verbose
    if verbose:
        config.HTTP_LOG_ENABLED = True

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
                f"Did you mean: py codecks_api.py archive {ns.card_id}"
            )

        # Validate token before any API command
        if cmd not in NO_TOKEN_COMMANDS:
            _check_token()

        handler = getattr(ns, "func", None)
        if handler:
            handler(ns)
        else:
            raise CliError(f"[ERROR] Unknown command: {cmd}")

    except CliError as e:
        _emit_cli_error(e, fmt)
        sys.exit(e.exit_code)


if __name__ == "__main__":
    main()
