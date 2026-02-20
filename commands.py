"""
Command implementations for codecks-cli.
Each cmd_*() function receives an argparse.Namespace and handles one CLI command.
"""

import json
import sys

import config
from config import CliError
from api import (_safe_json_parse, _mask_token,
                 query, dispatch, generate_report_token)
from cards import (get_account, list_decks, list_cards, get_card,
                   list_milestones, list_activity, list_projects,
                   enrich_cards, compute_card_stats,
                   create_card, update_card, archive_card, unarchive_card,
                   delete_card, bulk_status,
                   list_hand, add_to_hand, remove_from_hand,
                   extract_hand_card_ids,
                   create_comment, reply_comment, close_comment,
                   reopen_comment, get_conversations,
                   resolve_deck_id, resolve_milestone_id,
                   get_project_deck_ids, load_users, load_project_names)
from formatters import (output, mutation_response,
                        format_account_table, format_cards_table,
                        format_card_detail, format_conversations_table,
                        format_decks_table, format_projects_table,
                        format_milestones_table, format_stats_table,
                        format_activity_table, format_cards_csv,
                        format_gdd_table, format_sync_report)
from gdd import (_run_google_auth_flow, _revoke_google_auth,
                 fetch_gdd, parse_gdd, sync_gdd)
from models import (ObjectPayload, FeatureSpec,
                    FeatureSubcard, FeatureScaffoldReport)
from setup_wizard import cmd_setup


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SORT_KEY_MAP = {
    "status": "status",
    "priority": "priority",
    "effort": "effort",
    "deck": "deck_name",
    "title": "title",
    "owner": "owner_name",
    "updated": "lastUpdatedAt",
    "created": "createdAt",
}


def _sort_cards(cards_dict, sort_field):
    """Sort a {card_id: card_data} dict by *sort_field*; return a new dict."""
    field = _SORT_KEY_MAP[sort_field]
    reverse = sort_field in ("updated", "created")

    def _key(item):
        v = item[1].get(field)
        if v is None or v == "":
            return (1, "") if not reverse else (-1, "")
        if isinstance(v, (int, float)):
            return (0, v)
        return (0, str(v).lower())

    return dict(sorted(cards_dict.items(), key=_key, reverse=reverse))


def _normalize_dispatch_path(path):
    """Normalize and validate a dispatch path segment."""
    normalized = (path or "").strip()
    if not normalized:
        raise CliError("[ERROR] Dispatch path cannot be empty.")
    normalized = normalized.lstrip("/")
    if normalized.startswith("dispatch/"):
        normalized = normalized[len("dispatch/"):]
    if not normalized or normalized.startswith("/") or " " in normalized:
        raise CliError("[ERROR] Invalid dispatch path. Use e.g. cards/update")
    return normalized


def _resolve_owner_id(owner_name):
    """Resolve owner display name to user ID."""
    user_map = load_users()
    for uid, name in user_map.items():
        if name.lower() == owner_name.lower():
            return uid
    available = list(user_map.values())
    hint = f" Available: {', '.join(available)}" if available else ""
    raise CliError(f"[ERROR] Owner '{owner_name}' not found.{hint}")


# ---------------------------------------------------------------------------
# Read commands
# ---------------------------------------------------------------------------

def cmd_query(ns):
    q = ObjectPayload.from_value(
        _safe_json_parse(ns.json_query, "query"), "query").data
    if config.RUNTIME_STRICT:
        root = q.get("_root")
        if not isinstance(root, list) or not root:
            raise CliError(
                "[ERROR] Strict mode: query payload must include non-empty "
                "'_root' array."
            )
    output(query(q), fmt=ns.format)


def cmd_account(ns):
    output(get_account(), format_account_table, ns.format)


def cmd_decks(ns):
    output(list_decks(), format_decks_table, ns.format)


def cmd_projects(ns):
    output(list_projects(), format_projects_table, ns.format)


def cmd_milestones(ns):
    output(list_milestones(), format_milestones_table, ns.format)


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
        hand_card_ids = extract_hand_card_ids(hand_result)
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
    result["card"] = enrich_cards(result.get("card", {}),
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
    if ns.sort and result.get("card"):
        result["card"] = _sort_cards(result["card"], ns.sort)

    if ns.stats:
        stats = compute_card_stats(result.get("card", {}))
        output(stats, format_stats_table, fmt)
    else:
        output(result, format_cards_table, fmt,
               csv_formatter=format_cards_csv)


def cmd_card(ns):
    result = get_card(ns.card_id)
    result["card"] = enrich_cards(result.get("card", {}),
                                   result.get("user"))
    # Check if this card is in hand
    hand_result = list_hand()
    hand_card_ids = extract_hand_card_ids(hand_result)
    for card_key, card in result.get("card", {}).items():
        card["in_hand"] = card_key in hand_card_ids
    output(result, format_card_detail, ns.format)


# ---------------------------------------------------------------------------
# Mutation commands
# ---------------------------------------------------------------------------

def cmd_create(ns):
    fmt = ns.format
    result = create_card(ns.title, ns.content, ns.severity)
    card_id = result.get("cardId", "")
    if not card_id:
        raise CliError("[ERROR] Card creation failed: API response missing "
                       f"'cardId'. Response: {str(result)[:200]}")
    placed_in = None
    post_update = {}
    if ns.deck:
        post_update["deckId"] = resolve_deck_id(ns.deck)
        placed_in = ns.deck
    elif ns.project:
        decks_result = list_decks()
        project_deck_ids = get_project_deck_ids(decks_result, ns.project)
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
    mutation_response("Created", card_id, detail, result, fmt)


def cmd_feature(ns):
    """Scaffold one Hero feature plus Code/Design/(optional Art) sub-cards."""
    spec = FeatureSpec.from_namespace(ns)
    fmt = spec.format

    hero_deck_id = resolve_deck_id(spec.hero_deck)
    code_deck_id = resolve_deck_id(spec.code_deck)
    design_deck_id = resolve_deck_id(spec.design_deck)
    art_deck_id = resolve_deck_id(spec.art_deck) if spec.art_deck else None

    owner_id = _resolve_owner_id(spec.owner) if spec.owner else None
    priority = None if spec.priority == "null" else spec.priority
    common_update = {}
    if owner_id:
        common_update["assigneeId"] = owner_id
    if priority is not None:
        common_update["priority"] = priority
    if spec.effort is not None:
        common_update["effort"] = spec.effort

    hero_title = f"Feature: {spec.title}"
    hero_body = (
        (spec.description.strip() + "\n\n" if spec.description else "")
        + "Success criteria:\n"
          "- [] Lane coverage agreed (Code/Design/Art)\n"
          "- [] Acceptance criteria validated\n"
          "- [] Integration verified\n\n"
          "Tags: #hero #feature"
    )
    created = []
    created_ids = []

    try:
        hero_result = create_card(hero_title, hero_body)
        hero_id = hero_result.get("cardId")
        if not hero_id:
            raise CliError("[ERROR] Hero creation failed: missing cardId.")
        created_ids.append(hero_id)
        update_card(hero_id, deckId=hero_deck_id,
                    masterTags=["hero", "feature"], **common_update)

        def _make_sub(lane, deck_id, tags, checklist_lines):
            sub_title = f"[{lane}] {spec.title}"
            sub_body = (
                "Scope:\n"
                f"- {lane} lane execution for feature goal\n\n"
                "Checklist:\n"
                + "\n".join(f"- [] {line}" for line in checklist_lines)
                + "\n\nTags: " + " ".join(f"#{t}" for t in tags)
            )
            res = create_card(sub_title, sub_body)
            sub_id = res.get("cardId")
            if not sub_id:
                raise CliError(
                    f"[ERROR] {lane} sub-card creation failed: missing cardId.")
            created_ids.append(sub_id)
            update_card(
                sub_id,
                parentCardId=hero_id,
                deckId=deck_id,
                masterTags=tags,
                **common_update,
            )
            created.append(FeatureSubcard(lane=lane.lower(), id=sub_id))

        _make_sub("Code", code_deck_id, ["code", "feature"], [
            "Implement core logic",
            "Handle edge cases",
            "Add tests/verification",
        ])
        _make_sub("Design", design_deck_id, ["design", "feel", "economy", "feature"], [
            "Define target player feel",
            "Tune balance/economy parameters",
            "Run playtest and iterate",
        ])
        if not spec.skip_art and art_deck_id:
            _make_sub("Art", art_deck_id, ["art", "feature"], [
                "Create required assets/content",
                "Integrate assets in game flow",
                "Visual quality pass",
            ])
    except Exception as err:
        # Transaction safety: best-effort compensating rollback.
        rolled_back = []
        rollback_failed = []
        for cid in reversed(created_ids):
            try:
                archive_card(cid)
                rolled_back.append(cid)
            except Exception:
                rollback_failed.append(cid)
        detail = (
            f"[ERROR] Feature scaffold failed: {err}\n"
            f"[ERROR] Rollback archived {len(rolled_back)}/{len(created_ids)} "
            "created cards."
        )
        if rollback_failed:
            detail += f"\n[ERROR] Rollback failed for: {', '.join(rollback_failed)}"
        raise CliError(detail) from err

    report = FeatureScaffoldReport(
        hero_id=hero_id,
        hero_title=hero_title,
        subcards=created,
        hero_deck=spec.hero_deck,
        code_deck=spec.code_deck,
        design_deck=spec.design_deck,
        art_deck=None if spec.skip_art else spec.art_deck,
    )
    if fmt == "table":
        lines = [
            f"Hero created: {hero_id} ({hero_title})",
            f"Sub-cards created: {len(created)}",
        ]
        for item in created:
            lines.append(f"  - [{item.lane}] {item.id}")
        print("\n".join(lines))
    else:
        output(report.to_dict(), fmt=fmt)


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
                raise CliError(f"[ERROR] Invalid effort value '{ns.effort}': "
                               "must be a number or 'null'")

    if ns.deck is not None:
        update_kwargs["deckId"] = resolve_deck_id(ns.deck)

    if ns.title is not None:
        if len(card_ids) > 1:
            raise CliError("[ERROR] --title can only be used with a single card.")
        card_data = get_card(card_ids[0])
        cards = card_data.get("card", {})
        if not cards:
            raise CliError(f"[ERROR] Card '{card_ids[0]}' not found.")
        for k, c in cards.items():
            old_content = c.get("content", "")
            parts = old_content.split("\n", 1)
            new_content = ns.title + ("\n" + parts[1] if len(parts) > 1 else "")
            update_kwargs["content"] = new_content
            break

    if ns.content is not None:
        if len(card_ids) > 1:
            raise CliError("[ERROR] --content can only be used with a single card.")
        update_kwargs["content"] = ns.content

    if ns.milestone is not None:
        if ns.milestone.lower() == "none":
            update_kwargs["milestoneId"] = None
        else:
            update_kwargs["milestoneId"] = resolve_milestone_id(ns.milestone)

    if ns.hero is not None:
        if ns.hero.lower() == "none":
            update_kwargs["parentCardId"] = None
        else:
            update_kwargs["parentCardId"] = ns.hero

    if ns.owner is not None:
        if ns.owner.lower() == "none":
            update_kwargs["assigneeId"] = None
        else:
            user_map = load_users()
            owner_id = None
            for uid, name in user_map.items():
                if name.lower() == ns.owner.lower():
                    owner_id = uid
                    break
            if owner_id is None:
                available = list(user_map.values())
                hint = f" Available: {', '.join(available)}" if available else ""
                raise CliError(f"[ERROR] Owner '{ns.owner}' not found.{hint}")
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
            raise CliError(f"[ERROR] Invalid --doc value '{ns.doc}'. "
                           "Use true or false.")

    if not update_kwargs:
        raise CliError("[ERROR] No update flags provided. Use --status, "
                       "--priority, --effort, --owner, --tag, --doc, etc.")

    last_result = None
    for cid in card_ids:
        last_result = update_card(cid, **update_kwargs)
    detail_parts = [f"{k}={v}" for k, v in update_kwargs.items()]
    if len(card_ids) > 1:
        mutation_response("Updated", details=f"{len(card_ids)} card(s), "
                           + ", ".join(detail_parts), data=last_result, fmt=fmt)
    else:
        mutation_response("Updated", card_ids[0], ", ".join(detail_parts),
                           last_result, fmt)


def cmd_archive(ns):
    result = archive_card(ns.card_id)
    mutation_response("Archived", ns.card_id, data=result, fmt=ns.format)


def cmd_unarchive(ns):
    result = unarchive_card(ns.card_id)
    mutation_response("Unarchived", ns.card_id, data=result, fmt=ns.format)


def cmd_delete(ns):
    result = delete_card(ns.card_id)
    mutation_response("Deleted", ns.card_id, data=result, fmt=ns.format)


def cmd_done(ns):
    result = bulk_status(ns.card_ids, "done")
    mutation_response("Marked done", details=f"{len(ns.card_ids)} card(s)",
                       data=result, fmt=ns.format)


def cmd_start(ns):
    result = bulk_status(ns.card_ids, "started")
    mutation_response("Marked started", details=f"{len(ns.card_ids)} card(s)",
                       data=result, fmt=ns.format)


# ---------------------------------------------------------------------------
# Hand commands
# ---------------------------------------------------------------------------

def cmd_hand(ns):
    fmt = ns.format
    if not ns.card_ids:
        # No args = list hand cards
        hand_result = list_hand()
        hand_card_ids = extract_hand_card_ids(hand_result)
        if not hand_card_ids:
            print("Your hand is empty.", file=sys.stderr)
            sys.exit(0)
        result = list_cards()
        filtered = {k: v for k, v in result.get("card", {}).items()
                    if k in hand_card_ids}
        result["card"] = enrich_cards(filtered, result.get("user"))
        output(result, format_cards_table, fmt,
               csv_formatter=format_cards_csv)
    else:
        result = add_to_hand(ns.card_ids)
        mutation_response("Added to hand", details=f"{len(ns.card_ids)} card(s)",
                           data=result, fmt=fmt)


def cmd_unhand(ns):
    result = remove_from_hand(ns.card_ids)
    mutation_response("Removed from hand", details=f"{len(ns.card_ids)} card(s)",
                       data=result, fmt=ns.format)


# ---------------------------------------------------------------------------
# Activity command
# ---------------------------------------------------------------------------

def cmd_activity(ns):
    limit = ns.limit
    if limit <= 0:
        raise CliError("[ERROR] --limit must be a positive integer.")
    result = list_activity(limit)
    activities = result.get("activity", {})
    if len(activities) > limit:
        trimmed = dict(list(activities.items())[:limit])
        result["activity"] = trimmed
    output(result, format_activity_table, ns.format)


# ---------------------------------------------------------------------------
# Comment commands
# ---------------------------------------------------------------------------

def cmd_comment(ns):
    fmt = ns.format
    card_id = ns.card_id
    selected = [bool(ns.thread), bool(ns.close), bool(ns.reopen)]
    if sum(selected) > 1:
        raise CliError("[ERROR] Use only one of --thread, --close, or --reopen.")
    if ns.close:
        if ns.message:
            raise CliError("[ERROR] Do not provide a message with --close.")
        result = close_comment(ns.close, card_id)
        mutation_response("Closed thread", ns.close, "", result, fmt)
    elif ns.reopen:
        if ns.message:
            raise CliError("[ERROR] Do not provide a message with --reopen.")
        result = reopen_comment(ns.reopen, card_id)
        mutation_response("Reopened thread", ns.reopen, "", result, fmt)
    elif ns.thread:
        if not ns.message:
            raise CliError("[ERROR] Reply message is required.")
        result = reply_comment(ns.thread, ns.message)
        mutation_response("Replied to thread", ns.thread, "", result, fmt)
    else:
        if not ns.message:
            raise CliError("[ERROR] Comment message is required.")
        result = create_comment(card_id, ns.message)
        mutation_response("Created thread on", card_id, "", result, fmt)


def cmd_conversations(ns):
    result = get_conversations(ns.card_id)
    output(result, format_conversations_table, ns.format)


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
    output(sections, format_gdd_table, ns.format)


def cmd_gdd_sync(ns):
    fmt = ns.format
    if not ns.project:
        available = [n for n in load_project_names().values()]
        hint = f" Available: {', '.join(available)}" if available else ""
        raise CliError(f"[ERROR] --project is required for gdd-sync.{hint}")
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
    output(report, format_sync_report, fmt)


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
    path = _normalize_dispatch_path(ns.path)
    payload = ObjectPayload.from_value(
        _safe_json_parse(ns.json_data, "dispatch data"),
        "dispatch data").data
    if config.RUNTIME_STRICT:
        if "/" not in path:
            raise CliError(
                "[ERROR] Strict mode: dispatch path should include action "
                "segment, e.g. cards/update."
            )
        if not payload:
            raise CliError(
                "[ERROR] Strict mode: dispatch payload cannot be empty."
            )
    result = dispatch(path, payload)
    output(result, fmt=ns.format)
