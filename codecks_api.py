"""
codecks-cli — CLI tool for managing Codecks.io cards, decks, and projects
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

import json
import sys

import config
from api import (_check_token, _safe_json_parse, _mask_token,
                 query, dispatch, generate_report_token)
from cards import (get_account, list_decks, list_cards, get_card,
                   list_milestones, list_activity, list_projects,
                   _enrich_cards, _compute_card_stats,
                   create_card, update_card, archive_card, unarchive_card,
                   delete_card, bulk_status,
                   list_hand, add_to_hand, remove_from_hand,
                   create_comment, reply_comment, close_comment,
                   reopen_comment, get_conversations,
                   _resolve_deck_id, _resolve_milestone_id,
                   _get_project_deck_ids, _load_users, _load_project_names)
from formatters import (output, _mutation_response,
                        _format_account_table, _format_cards_table,
                        _format_card_detail, _format_conversations_table,
                        _format_decks_table, _format_projects_table,
                        _format_milestones_table, _format_stats_table,
                        _format_activity_table, _format_cards_csv,
                        _format_gdd_table, _format_sync_report)
from gdd import (_run_google_auth_flow, _revoke_google_auth,
                 fetch_gdd, parse_gdd, sync_gdd)
from setup_wizard import cmd_setup


# ---------------------------------------------------------------------------
# CLI flag parsing
# ---------------------------------------------------------------------------

def parse_flags(args, flag_names, bool_flag_names=None):
    """Parse --flag value pairs and --boolean flags from args.
    Returns (dict_of_flags, remaining_args)."""
    bool_flag_names = bool_flag_names or []
    flags = {}
    remaining = []
    i = 0
    while i < len(args):
        if args[i].startswith("--"):
            name = args[i][2:]
            if name in bool_flag_names:
                flags[name] = True
                i += 1
            elif name in flag_names and i + 1 < len(args):
                flags[name] = args[i + 1]
                i += 2
            else:
                remaining.append(args[i])
                i += 1
        else:
            remaining.append(args[i])
            i += 1
    return flags, remaining


# ---------------------------------------------------------------------------
# Main CLI
# ---------------------------------------------------------------------------

def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    # Extract global --format flag before command dispatch
    all_args = sys.argv[1:]
    global_flags, all_args = parse_flags(all_args, ["format"],
                                         bool_flag_names=["version"])
    fmt = global_flags.get("format", "json")

    if global_flags.get("version"):
        print(f"codecks-cli {config.VERSION}")
        sys.exit(0)

    if not all_args:
        print(__doc__)
        sys.exit(0)

    cmd = all_args[0].lower()

    if cmd == "version":
        print(f"codecks-cli {config.VERSION}")
        sys.exit(0)

    if cmd == "setup":
        cmd_setup()
        sys.exit(0)

    args = all_args[1:]

    # Validate token before any API command
    NO_TOKEN_COMMANDS = {"gdd-auth", "gdd-revoke", "generate-token"}
    if cmd not in NO_TOKEN_COMMANDS:
        _check_token()

    if cmd == "query":
        if not args:
            print("Usage: py codecks_api.py query '<json>'", file=sys.stderr)
            sys.exit(1)
        q = _safe_json_parse(args[0], "query")
        output(query(q), fmt=fmt)

    elif cmd == "account":
        output(get_account(), _format_account_table, fmt)

    elif cmd == "decks":
        output(list_decks(), _format_decks_table, fmt)

    elif cmd == "projects":
        output(list_projects(), _format_projects_table, fmt)

    elif cmd == "milestones":
        output(list_milestones(), _format_milestones_table, fmt)

    elif cmd == "cards":
        flags, _ = parse_flags(args,
                               ["deck", "status", "project", "search",
                                "milestone", "sort", "tag", "owner",
                                "hero", "type"],
                               bool_flag_names=["stats", "hand", "archived"])
        if flags.get("status") and flags["status"] not in config.VALID_STATUSES:
            print(f"[ERROR] Invalid status '{flags['status']}'. "
                  f"Use: {', '.join(sorted(config.VALID_STATUSES))}",
                  file=sys.stderr)
            sys.exit(1)
        sort_field = flags.get("sort")
        if sort_field and sort_field not in config.VALID_SORT_FIELDS:
            print(f"[ERROR] Invalid sort field '{sort_field}'. "
                  f"Use: {', '.join(sorted(config.VALID_SORT_FIELDS))}",
                  file=sys.stderr)
            sys.exit(1)
        card_type = flags.get("type")
        if card_type and card_type not in config.VALID_CARD_TYPES:
            print(f"[ERROR] Invalid type '{card_type}'. "
                  f"Use: {', '.join(sorted(config.VALID_CARD_TYPES))}",
                  file=sys.stderr)
            sys.exit(1)
        result = list_cards(
            deck_filter=flags.get("deck"),
            status_filter=flags.get("status"),
            project_filter=flags.get("project"),
            search_filter=flags.get("search"),
            milestone_filter=flags.get("milestone"),
            tag_filter=flags.get("tag"),
            owner_filter=flags.get("owner"),
            archived=flags.get("archived", False),
        )
        # Filter to hand cards if requested
        if flags.get("hand"):
            hand_result = list_hand()
            hand_card_ids = set()
            for entry in (hand_result.get("queueEntry") or {}).values():
                cid = entry.get("card") or entry.get("cardId")
                if cid:
                    hand_card_ids.add(cid)
            result["card"] = {k: v for k, v in result.get("card", {}).items()
                              if k in hand_card_ids}
        # Filter to sub-cards of a hero card
        if flags.get("hero"):
            hero_result = get_card(flags["hero"])
            child_ids = set()
            for cdata in hero_result.get("card", {}).values():
                for cid in (cdata.get("childCards") or []):
                    child_ids.add(cid)
            result["card"] = {k: v for k, v in result.get("card", {}).items()
                              if k in child_ids}
        # Enrich cards with deck/milestone/owner names
        result["card"] = _enrich_cards(result.get("card", {}),
                                       result.get("user"))
        # Filter by card type
        if card_type:
            if card_type == "doc":
                result["card"] = {k: v for k, v in result.get("card", {}).items()
                                  if v.get("is_doc") or v.get("isDoc")}
            elif card_type == "hero":
                # Query childCards to find cards with children
                card_filter = json.dumps({"visibility": "default"})
                hero_q = {"_root": [{"account": [{
                    f"cards({card_filter})": [{"childCards": ["title"]}]
                }]}]}
                hero_result = query(hero_q)
                hero_ids = {k for k, v in hero_result.get("card", {}).items()
                            if v.get("childCards")}
                result["card"] = {k: v for k, v in result.get("card", {}).items()
                                  if k in hero_ids}

        # Sort cards if requested
        if sort_field and result.get("card"):
            sort_key_map = {
                "status": "status",
                "priority": "priority",
                "effort": "effort",
                "deck": "deck_name",
                "title": "title",
                "owner": "owner_name",
                "updated": "lastUpdatedAt",
                "created": "createdAt",
            }
            field = sort_key_map[sort_field]
            # Date fields sort newest-first; others sort ascending
            reverse = sort_field in ("updated", "created")
            def _sort_val(item):
                v = item[1].get(field)
                if v is None or v == "":
                    return (1, "") if not reverse else (-1, "")
                if isinstance(v, (int, float)):
                    return (0, v)
                return (0, str(v).lower())
            sorted_items = sorted(result["card"].items(), key=_sort_val,
                                  reverse=reverse)
            result["card"] = dict(sorted_items)

        if flags.get("stats"):
            stats = _compute_card_stats(result.get("card", {}))
            output(stats, _format_stats_table, fmt)
        else:
            output(result, _format_cards_table, fmt,
                   csv_formatter=_format_cards_csv)

    elif cmd == "card":
        if not args:
            print("Usage: py codecks_api.py card <card_id>", file=sys.stderr)
            sys.exit(1)
        result = get_card(args[0])
        result["card"] = _enrich_cards(result.get("card", {}),
                                       result.get("user"))
        # Check if this card is in hand
        hand_result = list_hand()
        hand_card_ids = set()
        for entry in (hand_result.get("queueEntry") or {}).values():
            cid = entry.get("card") or entry.get("cardId")
            if cid:
                hand_card_ids.add(cid)
        for card_key, card in result.get("card", {}).items():
            card["in_hand"] = card_key in hand_card_ids
        output(result, _format_card_detail, fmt)

    elif cmd == "create":
        if not args:
            print("Usage: py codecks_api.py create <title> [--deck <name>] "
                  "[--project <name>] [--content <text>] [--severity ...] "
                  "[--doc]", file=sys.stderr)
            sys.exit(1)
        title = args[0]
        flags, _ = parse_flags(args[1:], ["content", "severity", "deck", "project"],
                               bool_flag_names=["doc"])
        result = create_card(title, flags.get("content"), flags.get("severity"))
        card_id = result.get("cardId", "")
        # Optionally move to a specific deck or project's first deck
        placed_in = None
        post_update = {}
        if flags.get("deck"):
            post_update["deckId"] = _resolve_deck_id(flags["deck"])
            placed_in = flags["deck"]
        elif flags.get("project"):
            decks_result = list_decks()
            project_deck_ids = _get_project_deck_ids(decks_result, flags["project"])
            if project_deck_ids:
                post_update["deckId"] = next(iter(project_deck_ids))
                placed_in = flags["project"]
            else:
                print(f"[ERROR] Project '{flags['project']}' not found.",
                      file=sys.stderr)
        if flags.get("doc"):
            post_update["isDoc"] = True
        if post_update:
            update_card(card_id, **post_update)
        detail = f"title='{title}'"
        if placed_in:
            detail += f", deck='{placed_in}'"
        if flags.get("doc"):
            detail += ", type=doc"
        _mutation_response("Created", card_id, detail, result, fmt)

    elif cmd == "update":
        if not args:
            print("Usage: py codecks_api.py update <id> [id...] [--status ...] "
                  "[--priority ...] [--effort ...] [--deck ...] [--title ...] "
                  "[--content ...] [--milestone ...] [--hero ...] [--owner ...] "
                  "[--tag ...] [--doc true|false]", file=sys.stderr)
            sys.exit(1)
        flags, remaining = parse_flags(args, [
            "status", "priority", "effort", "deck", "title", "content",
            "milestone", "hero", "owner", "tag", "doc",
        ])
        card_ids = remaining if remaining else [args[0]]

        update_kwargs = {}

        if "status" in flags:
            val = flags["status"]
            if val not in config.VALID_STATUSES:
                print(f"[ERROR] Invalid status '{val}'. "
                      f"Use: {', '.join(sorted(config.VALID_STATUSES))}",
                      file=sys.stderr)
                sys.exit(1)
            update_kwargs["status"] = val

        if "priority" in flags:
            val = flags["priority"]
            if val not in config.VALID_PRIORITIES:
                print(f"[ERROR] Invalid priority '{val}'. "
                      "Use: a (high), b (medium), c (low), or null",
                      file=sys.stderr)
                sys.exit(1)
            update_kwargs["priority"] = None if val == "null" else val

        if "effort" in flags:
            val = flags["effort"]
            if val == "null":
                update_kwargs["effort"] = None
            else:
                try:
                    update_kwargs["effort"] = int(val)
                except ValueError:
                    print(f"[ERROR] Invalid effort value '{val}': must be a number or 'null'",
                          file=sys.stderr)
                    sys.exit(1)

        if "deck" in flags:
            update_kwargs["deckId"] = _resolve_deck_id(flags["deck"])

        if "title" in flags:
            if len(card_ids) > 1:
                print("[ERROR] --title can only be used with a single card.",
                      file=sys.stderr)
                sys.exit(1)
            # Title = first line of content. Fetch current content, replace first line.
            card_data = get_card(card_ids[0])
            for k, c in card_data.get("card", {}).items():
                old_content = c.get("content", "")
                parts = old_content.split("\n", 1)
                new_content = flags["title"] + ("\n" + parts[1] if len(parts) > 1 else "")
                update_kwargs["content"] = new_content
                break

        if "content" in flags:
            if len(card_ids) > 1:
                print("[ERROR] --content can only be used with a single card.",
                      file=sys.stderr)
                sys.exit(1)
            update_kwargs["content"] = flags["content"]

        if "milestone" in flags:
            val = flags["milestone"]
            if val.lower() == "none":
                update_kwargs["milestoneId"] = None
            else:
                update_kwargs["milestoneId"] = _resolve_milestone_id(val)

        if "hero" in flags:
            val = flags["hero"]
            if val.lower() == "none":
                update_kwargs["parentCardId"] = None
            else:
                update_kwargs["parentCardId"] = val

        if "owner" in flags:
            val = flags["owner"]
            if val.lower() == "none":
                update_kwargs["assigneeId"] = None
            else:
                user_map = _load_users()
                owner_id = None
                for uid, name in user_map.items():
                    if name.lower() == val.lower():
                        owner_id = uid
                        break
                if owner_id is None:
                    available = list(user_map.values())
                    hint = f" Available: {', '.join(available)}" if available else ""
                    print(f"[ERROR] Owner '{val}' not found.{hint}",
                          file=sys.stderr)
                    sys.exit(1)
                update_kwargs["assigneeId"] = owner_id

        if "tag" in flags:
            val = flags["tag"]
            if val.lower() == "none":
                update_kwargs["masterTags"] = []
            else:
                # Comma-separated tags: "bug,ui,feature"
                new_tags = [t.strip() for t in val.split(",") if t.strip()]
                update_kwargs["masterTags"] = new_tags

        if "doc" in flags:
            val = flags["doc"].lower()
            if val in ("true", "yes", "1"):
                update_kwargs["isDoc"] = True
            elif val in ("false", "no", "0"):
                update_kwargs["isDoc"] = False
            else:
                print(f"[ERROR] Invalid --doc value '{flags['doc']}'. Use true or false.",
                      file=sys.stderr)
                sys.exit(1)

        if not update_kwargs:
            print("[ERROR] No update flags provided. Use --status, --priority, "
                  "--effort, --owner, --tag, --doc, etc.",
                  file=sys.stderr)
            sys.exit(1)

        # Bulk update: apply to each card
        last_result = None
        for cid in card_ids:
            last_result = update_card(cid, **update_kwargs)
        detail_parts = [f"{k}={v}" for k, v in update_kwargs.items()]
        if len(card_ids) > 1:
            _mutation_response("Updated", details=f"{len(card_ids)} card(s), "
                               + ", ".join(detail_parts), data=last_result, fmt=fmt)
        else:
            _mutation_response("Updated", card_ids[0], ", ".join(detail_parts),
                               last_result, fmt)

    elif cmd in ("archive", "remove"):
        if not args:
            print("Usage: py codecks_api.py archive <card_id>", file=sys.stderr)
            sys.exit(1)
        result = archive_card(args[0])
        _mutation_response("Archived", args[0], data=result, fmt=fmt)

    elif cmd == "unarchive":
        if not args:
            print("Usage: py codecks_api.py unarchive <card_id>", file=sys.stderr)
            sys.exit(1)
        result = unarchive_card(args[0])
        _mutation_response("Unarchived", args[0], data=result, fmt=fmt)

    elif cmd == "delete":
        if not args:
            print("Usage: py codecks_api.py delete <card_id> --confirm", file=sys.stderr)
            sys.exit(1)
        flags, remaining = parse_flags(args, [], bool_flag_names=["confirm"])
        card_id = remaining[0] if remaining else args[0]
        if not flags.get("confirm"):
            print("[ERROR] Permanent deletion requires --confirm flag.", file=sys.stderr)
            print(f"Did you mean: py codecks_api.py archive {card_id}",
                  file=sys.stderr)
            sys.exit(1)
        result = delete_card(card_id)
        _mutation_response("Deleted", card_id, data=result, fmt=fmt)

    elif cmd == "done":
        if not args:
            print("Usage: py codecks_api.py done <card_id> [card_id...]", file=sys.stderr)
            sys.exit(1)
        result = bulk_status(args, "done")
        _mutation_response("Marked done", details=f"{len(args)} card(s)", data=result, fmt=fmt)

    elif cmd == "start":
        if not args:
            print("Usage: py codecks_api.py start <card_id> [card_id...]", file=sys.stderr)
            sys.exit(1)
        result = bulk_status(args, "started")
        _mutation_response("Marked started", details=f"{len(args)} card(s)",
                           data=result, fmt=fmt)

    elif cmd == "hand":
        if not args:
            # No args = list hand cards
            hand_result = list_hand()
            hand_card_ids = set()
            for entry in (hand_result.get("queueEntry") or {}).values():
                cid = entry.get("card") or entry.get("cardId")
                if cid:
                    hand_card_ids.add(cid)
            if not hand_card_ids:
                print("Your hand is empty.", file=sys.stderr)
                sys.exit(0)
            # Fetch card details for the hand cards
            result = list_cards()
            filtered = {k: v for k, v in result.get("card", {}).items()
                        if k in hand_card_ids}
            result["card"] = _enrich_cards(filtered, result.get("user"))
            output(result, _format_cards_table, fmt,
                   csv_formatter=_format_cards_csv)
        else:
            result = add_to_hand(args)
            _mutation_response("Added to hand", details=f"{len(args)} card(s)",
                               data=result, fmt=fmt)

    elif cmd == "unhand":
        if not args:
            print("Usage: py codecks_api.py unhand <card_id> [card_id...]",
                  file=sys.stderr)
            sys.exit(1)
        result = remove_from_hand(args)
        _mutation_response("Removed from hand", details=f"{len(args)} card(s)",
                           data=result, fmt=fmt)

    elif cmd == "activity":
        flags, _ = parse_flags(args, ["limit"])
        limit = 20
        if "limit" in flags:
            try:
                limit = int(flags["limit"])
            except ValueError:
                print("[ERROR] --limit must be a number.", file=sys.stderr)
                sys.exit(1)
        result = list_activity(limit)
        # Trim to limit
        activities = result.get("activity", {})
        if len(activities) > limit:
            trimmed = dict(list(activities.items())[:limit])
            result["activity"] = trimmed
        output(result, _format_activity_table, fmt)

    elif cmd == "generate-token":
        flags, _ = parse_flags(args, ["label"])
        label = flags.get("label", "claude-code")
        result = generate_report_token(label)
        print(f"Report Token created: {_mask_token(result['token'])}")
        print("Full token saved to .env as CODECKS_REPORT_TOKEN")

    elif cmd == "gdd":
        flags, _ = parse_flags(args, ["file"],
                               bool_flag_names=["refresh", "save-cache"])
        content = fetch_gdd(
            force_refresh=flags.get("refresh", False),
            local_file=flags.get("file"),
            save_cache=flags.get("save-cache", False),
        )
        sections = parse_gdd(content)
        output(sections, _format_gdd_table, fmt)

    elif cmd == "gdd-sync":
        flags, _ = parse_flags(args, ["project", "section", "file"],
                               bool_flag_names=["apply", "refresh", "save-cache",
                                                "quiet"])
        if not flags.get("project"):
            available = [n for n in _load_project_names().values()]
            hint = f" Available: {', '.join(available)}" if available else ""
            print(f"[ERROR] --project is required for gdd-sync.{hint}",
                  file=sys.stderr)
            sys.exit(1)
        content = fetch_gdd(
            force_refresh=flags.get("refresh", False),
            local_file=flags.get("file"),
            save_cache=flags.get("save-cache", False),
        )
        sections = parse_gdd(content)
        report = sync_gdd(
            sections, flags["project"],
            target_section=flags.get("section"),
            apply=flags.get("apply", False),
            quiet=flags.get("quiet", False),
        )
        output(report, _format_sync_report, fmt)

    elif cmd == "gdd-auth":
        _run_google_auth_flow()

    elif cmd == "gdd-revoke":
        _revoke_google_auth()

    elif cmd == "comment":
        if not args:
            print("Usage: py codecks_api.py comment <card_id> \"message\"\n"
                  "       comment <card_id> --thread <id> \"reply\"\n"
                  "       comment <card_id> --close <thread_id>\n"
                  "       comment <card_id> --reopen <thread_id>",
                  file=sys.stderr)
            sys.exit(1)
        card_id = args[0]
        flags, remaining = parse_flags(args[1:], ["thread", "close", "reopen"])
        if flags.get("close"):
            result = close_comment(flags["close"], card_id)
            _mutation_response("Closed thread", flags["close"], "", result, fmt)
        elif flags.get("reopen"):
            result = reopen_comment(flags["reopen"], card_id)
            _mutation_response("Reopened thread", flags["reopen"], "", result, fmt)
        elif flags.get("thread"):
            if not remaining:
                print("[ERROR] Reply message is required.", file=sys.stderr)
                sys.exit(1)
            result = reply_comment(flags["thread"], remaining[0])
            _mutation_response("Replied to thread", flags["thread"], "", result, fmt)
        else:
            if not remaining:
                print("[ERROR] Comment message is required.", file=sys.stderr)
                sys.exit(1)
            result = create_comment(card_id, remaining[0])
            _mutation_response("Created thread on", card_id, "", result, fmt)

    elif cmd == "conversations":
        if not args:
            print("Usage: py codecks_api.py conversations <card_id>",
                  file=sys.stderr)
            sys.exit(1)
        result = get_conversations(args[0])
        output(result, _format_conversations_table, fmt)

    elif cmd == "dispatch":
        if len(args) < 2:
            print("Usage: py codecks_api.py dispatch <path> '<json>'", file=sys.stderr)
            sys.exit(1)
        result = dispatch(args[0], _safe_json_parse(args[1], "dispatch data"))
        output(result, fmt=fmt)

    else:
        print(f"[ERROR] Unknown command: {cmd}", file=sys.stderr)
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
