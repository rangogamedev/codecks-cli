"""
Command implementations for codecks-cli.
Each cmd_*() function receives an argparse.Namespace and handles one CLI command.
"""

import json
import sys

import config
from api import (_safe_json_parse, _mask_token,
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
# Read commands
# ---------------------------------------------------------------------------

def cmd_query(ns):
    q = _safe_json_parse(ns.json_query, "query")
    output(query(q), fmt=ns.format)


def cmd_account(ns):
    output(get_account(), _format_account_table, ns.format)


def cmd_decks(ns):
    output(list_decks(), _format_decks_table, ns.format)


def cmd_projects(ns):
    output(list_projects(), _format_projects_table, ns.format)


def cmd_milestones(ns):
    output(list_milestones(), _format_milestones_table, ns.format)


def cmd_cards(ns):
    fmt = ns.format
    result = list_cards(
        deck_filter=ns.deck,
        status_filter=ns.status,
        project_filter=ns.project,
        search_filter=ns.search,
        milestone_filter=ns.milestone,
        tag_filter=ns.tag,
        owner_filter=ns.owner,
        archived=ns.archived,
    )
    # Filter to hand cards if requested
    if ns.hand:
        hand_result = list_hand()
        hand_card_ids = set()
        for entry in (hand_result.get("queueEntry") or {}).values():
            cid = entry.get("card") or entry.get("cardId")
            if cid:
                hand_card_ids.add(cid)
        result["card"] = {k: v for k, v in result.get("card", {}).items()
                          if k in hand_card_ids}
    # Filter to sub-cards of a hero card
    if ns.hero:
        hero_result = get_card(ns.hero)
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
    card_type = ns.type
    if card_type:
        if card_type == "doc":
            result["card"] = {k: v for k, v in result.get("card", {}).items()
                              if v.get("is_doc") or v.get("isDoc")}
        elif card_type == "hero":
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
    sort_field = ns.sort
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

    if ns.stats:
        stats = _compute_card_stats(result.get("card", {}))
        output(stats, _format_stats_table, fmt)
    else:
        output(result, _format_cards_table, fmt,
               csv_formatter=_format_cards_csv)


def cmd_card(ns):
    result = get_card(ns.card_id)
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
    output(result, _format_card_detail, ns.format)


# ---------------------------------------------------------------------------
# Mutation commands
# ---------------------------------------------------------------------------

def cmd_create(ns):
    fmt = ns.format
    result = create_card(ns.title, ns.content, ns.severity)
    card_id = result.get("cardId", "")
    placed_in = None
    post_update = {}
    if ns.deck:
        post_update["deckId"] = _resolve_deck_id(ns.deck)
        placed_in = ns.deck
    elif ns.project:
        decks_result = list_decks()
        project_deck_ids = _get_project_deck_ids(decks_result, ns.project)
        if project_deck_ids:
            post_update["deckId"] = next(iter(project_deck_ids))
            placed_in = ns.project
        else:
            print(f"[ERROR] Project '{ns.project}' not found.",
                  file=sys.stderr)
    if ns.doc:
        post_update["isDoc"] = True
    if post_update:
        update_card(card_id, **post_update)
    detail = f"title='{ns.title}'"
    if placed_in:
        detail += f", deck='{placed_in}'"
    if ns.doc:
        detail += ", type=doc"
    _mutation_response("Created", card_id, detail, result, fmt)


def cmd_update(ns):
    fmt = ns.format
    card_ids = ns.card_ids
    update_kwargs = {}

    if ns.status is not None:
        update_kwargs["status"] = ns.status

    if ns.priority is not None:
        update_kwargs["priority"] = None if ns.priority == "null" else ns.priority

    if ns.effort is not None:
        if ns.effort == "null":
            update_kwargs["effort"] = None
        else:
            try:
                update_kwargs["effort"] = int(ns.effort)
            except ValueError:
                print(f"[ERROR] Invalid effort value '{ns.effort}': "
                      "must be a number or 'null'", file=sys.stderr)
                sys.exit(1)

    if ns.deck is not None:
        update_kwargs["deckId"] = _resolve_deck_id(ns.deck)

    if ns.title is not None:
        if len(card_ids) > 1:
            print("[ERROR] --title can only be used with a single card.",
                  file=sys.stderr)
            sys.exit(1)
        card_data = get_card(card_ids[0])
        cards = card_data.get("card", {})
        if not cards:
            print(f"[ERROR] Card '{card_ids[0]}' not found.", file=sys.stderr)
            sys.exit(1)
        for k, c in cards.items():
            old_content = c.get("content", "")
            parts = old_content.split("\n", 1)
            new_content = ns.title + ("\n" + parts[1] if len(parts) > 1 else "")
            update_kwargs["content"] = new_content
            break

    if ns.content is not None:
        if len(card_ids) > 1:
            print("[ERROR] --content can only be used with a single card.",
                  file=sys.stderr)
            sys.exit(1)
        update_kwargs["content"] = ns.content

    if ns.milestone is not None:
        if ns.milestone.lower() == "none":
            update_kwargs["milestoneId"] = None
        else:
            update_kwargs["milestoneId"] = _resolve_milestone_id(ns.milestone)

    if ns.hero is not None:
        if ns.hero.lower() == "none":
            update_kwargs["parentCardId"] = None
        else:
            update_kwargs["parentCardId"] = ns.hero

    if ns.owner is not None:
        if ns.owner.lower() == "none":
            update_kwargs["assigneeId"] = None
        else:
            user_map = _load_users()
            owner_id = None
            for uid, name in user_map.items():
                if name.lower() == ns.owner.lower():
                    owner_id = uid
                    break
            if owner_id is None:
                available = list(user_map.values())
                hint = f" Available: {', '.join(available)}" if available else ""
                print(f"[ERROR] Owner '{ns.owner}' not found.{hint}",
                      file=sys.stderr)
                sys.exit(1)
            update_kwargs["assigneeId"] = owner_id

    if ns.tag is not None:
        if ns.tag.lower() == "none":
            update_kwargs["masterTags"] = []
        else:
            new_tags = [t.strip() for t in ns.tag.split(",") if t.strip()]
            update_kwargs["masterTags"] = new_tags

    if ns.doc is not None:
        val = ns.doc.lower()
        if val in ("true", "yes", "1"):
            update_kwargs["isDoc"] = True
        elif val in ("false", "no", "0"):
            update_kwargs["isDoc"] = False
        else:
            print(f"[ERROR] Invalid --doc value '{ns.doc}'. Use true or false.",
                  file=sys.stderr)
            sys.exit(1)

    if not update_kwargs:
        print("[ERROR] No update flags provided. Use --status, --priority, "
              "--effort, --owner, --tag, --doc, etc.",
              file=sys.stderr)
        sys.exit(1)

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


def cmd_archive(ns):
    result = archive_card(ns.card_id)
    _mutation_response("Archived", ns.card_id, data=result, fmt=ns.format)


def cmd_unarchive(ns):
    result = unarchive_card(ns.card_id)
    _mutation_response("Unarchived", ns.card_id, data=result, fmt=ns.format)


def cmd_delete(ns):
    result = delete_card(ns.card_id)
    _mutation_response("Deleted", ns.card_id, data=result, fmt=ns.format)


def cmd_done(ns):
    result = bulk_status(ns.card_ids, "done")
    _mutation_response("Marked done", details=f"{len(ns.card_ids)} card(s)",
                       data=result, fmt=ns.format)


def cmd_start(ns):
    result = bulk_status(ns.card_ids, "started")
    _mutation_response("Marked started", details=f"{len(ns.card_ids)} card(s)",
                       data=result, fmt=ns.format)


# ---------------------------------------------------------------------------
# Hand commands
# ---------------------------------------------------------------------------

def cmd_hand(ns):
    fmt = ns.format
    if not ns.card_ids:
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
        result = list_cards()
        filtered = {k: v for k, v in result.get("card", {}).items()
                    if k in hand_card_ids}
        result["card"] = _enrich_cards(filtered, result.get("user"))
        output(result, _format_cards_table, fmt,
               csv_formatter=_format_cards_csv)
    else:
        result = add_to_hand(ns.card_ids)
        _mutation_response("Added to hand", details=f"{len(ns.card_ids)} card(s)",
                           data=result, fmt=fmt)


def cmd_unhand(ns):
    result = remove_from_hand(ns.card_ids)
    _mutation_response("Removed from hand", details=f"{len(ns.card_ids)} card(s)",
                       data=result, fmt=ns.format)


# ---------------------------------------------------------------------------
# Activity command
# ---------------------------------------------------------------------------

def cmd_activity(ns):
    limit = ns.limit
    result = list_activity(limit)
    activities = result.get("activity", {})
    if len(activities) > limit:
        trimmed = dict(list(activities.items())[:limit])
        result["activity"] = trimmed
    output(result, _format_activity_table, ns.format)


# ---------------------------------------------------------------------------
# Comment commands
# ---------------------------------------------------------------------------

def cmd_comment(ns):
    fmt = ns.format
    card_id = ns.card_id
    if ns.close:
        result = close_comment(ns.close, card_id)
        _mutation_response("Closed thread", ns.close, "", result, fmt)
    elif ns.reopen:
        result = reopen_comment(ns.reopen, card_id)
        _mutation_response("Reopened thread", ns.reopen, "", result, fmt)
    elif ns.thread:
        if not ns.message:
            print("[ERROR] Reply message is required.", file=sys.stderr)
            sys.exit(1)
        result = reply_comment(ns.thread, ns.message)
        _mutation_response("Replied to thread", ns.thread, "", result, fmt)
    else:
        if not ns.message:
            print("[ERROR] Comment message is required.", file=sys.stderr)
            sys.exit(1)
        result = create_comment(card_id, ns.message)
        _mutation_response("Created thread on", card_id, "", result, fmt)


def cmd_conversations(ns):
    result = get_conversations(ns.card_id)
    output(result, _format_conversations_table, ns.format)


# ---------------------------------------------------------------------------
# GDD commands
# ---------------------------------------------------------------------------

def cmd_gdd(ns):
    content = fetch_gdd(
        force_refresh=ns.refresh,
        local_file=ns.file,
        save_cache=ns.save_cache,
    )
    sections = parse_gdd(content)
    output(sections, _format_gdd_table, ns.format)


def cmd_gdd_sync(ns):
    fmt = ns.format
    if not ns.project:
        available = [n for n in _load_project_names().values()]
        hint = f" Available: {', '.join(available)}" if available else ""
        print(f"[ERROR] --project is required for gdd-sync.{hint}",
              file=sys.stderr)
        sys.exit(1)
    content = fetch_gdd(
        force_refresh=ns.refresh,
        local_file=ns.file,
        save_cache=ns.save_cache,
    )
    sections = parse_gdd(content)
    report = sync_gdd(
        sections, ns.project,
        target_section=ns.section,
        apply=ns.apply,
        quiet=ns.quiet,
    )
    output(report, _format_sync_report, fmt)


def cmd_gdd_auth(ns):
    _run_google_auth_flow()


def cmd_gdd_revoke(ns):
    _revoke_google_auth()


# ---------------------------------------------------------------------------
# Token & raw API commands
# ---------------------------------------------------------------------------

def cmd_generate_token(ns):
    result = generate_report_token(ns.label)
    print(f"Report Token created: {_mask_token(result['token'])}")
    print("Full token saved to .env as CODECKS_REPORT_TOKEN")


def cmd_dispatch(ns):
    result = dispatch(ns.path, _safe_json_parse(ns.json_data, "dispatch data"))
    output(result, fmt=ns.format)
