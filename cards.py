"""
Card CRUD operations, hand management, conversations, and helper functions
for codecks-cli.
"""

import json
import sys
import uuid

import config
from api import (query, warn_if_empty, session_request, report_request,
                 _try_call)


# ---------------------------------------------------------------------------
# Config helpers (.env name mappings)
# ---------------------------------------------------------------------------

def _load_env_mapping(env_key):
    """Load an id=Name mapping from a comma-separated .env value.
    Format: id1=Name1,id2=Name2"""
    mapping = {}
    raw = config.env.get(env_key, "")
    for pair in raw.split(","):
        pair = pair.strip()
        if "=" in pair:
            k, name = pair.split("=", 1)
            mapping[k.strip()] = name.strip()
    return mapping


def _load_project_names():
    return _load_env_mapping("CODECKS_PROJECTS")


def _load_milestone_names():
    return _load_env_mapping("CODECKS_MILESTONES")


def _load_users():
    """Load user ID->name mapping from account roles. Cached per invocation."""
    if "users" in config._cache:
        return config._cache["users"]
    result = _try_call(query, {"_root": [{"account": [
        {"roles": ["userId", "role", {"user": ["id", "name"]}]}
    ]}]})
    user_map = {}
    if result:
        for uid, udata in result.get("user", {}).items():
            user_map[uid] = udata.get("name", "")
    config._cache["users"] = user_map
    return user_map


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def _filter_cards(result, predicate):
    """Filter result['card'] dict by predicate(key, card). Returns result."""
    result["card"] = {k: v for k, v in result.get("card", {}).items()
                      if predicate(k, v)}
    return result


def get_account():
    q = {"_root": [{"account": ["name", "id"]}]}
    return query(q)


def list_decks():
    if "decks" in config._cache:
        return config._cache["decks"]
    q = {"_root": [{"account": [{"decks": ["title", "id", "projectId"]}]}]}
    result = query(q)
    warn_if_empty(result, "deck")
    config._cache["decks"] = result
    return result


def list_cards(deck_filter=None, status_filter=None, project_filter=None,
               search_filter=None, milestone_filter=None, tag_filter=None,
               owner_filter=None, archived=False):
    card_fields = ["title", "status", "priority", "deckId", "effort",
                   "createdAt", "milestoneId", "masterTags", "lastUpdatedAt",
                   "isDoc", "childCardInfo", {"assignee": ["name", "id"]}]
    if search_filter:
        card_fields.append("content")
    card_query = {"visibility": "archived" if archived else "default"}
    if status_filter:
        card_query["status"] = status_filter

    # Resolve deck filter
    if deck_filter:
        decks_result = list_decks()
        deck_id = None
        for key, deck in decks_result.get("deck", {}).items():
            if deck.get("title", "").lower() == deck_filter.lower():
                deck_id = deck.get("id")
                break
        if deck_id:
            card_query["deckId"] = deck_id
        else:
            print(f"[ERROR] Deck '{deck_filter}' not found.", file=sys.stderr)
            sys.exit(1)

    q = {"_root": [{"account": [{f"cards({json.dumps(card_query)})": card_fields}]}]}
    result = query(q)
    # Only warn about token expiry when no server-side filters are applied —
    # a filtered query returning 0 results is normal (e.g. no "started" cards).
    if not status_filter and not deck_filter and not archived:
        warn_if_empty(result, "card")

    # Client-side project filter (cards don't have projectId directly)
    if project_filter:
        decks_result = list_decks()
        project_deck_ids = _get_project_deck_ids(decks_result, project_filter)
        if project_deck_ids is None:
            available = [n for n in _load_project_names().values()]
            hint = f" Available: {', '.join(available)}" if available else ""
            print(f"[ERROR] Project '{project_filter}' not found.{hint}",
                  file=sys.stderr)
            sys.exit(1)
        _filter_cards(result, lambda k, c:
                      (c.get("deck_id") or c.get("deckId")) in project_deck_ids)

    # Client-side text search
    if search_filter:
        search_lower = search_filter.lower()
        _filter_cards(result, lambda k, c:
                      search_lower in (c.get("title", "") or "").lower() or
                      search_lower in (c.get("content", "") or "").lower())

    # Client-side milestone filter
    if milestone_filter:
        milestone_id = _resolve_milestone_id(milestone_filter)
        _filter_cards(result, lambda k, c:
                      (c.get("milestone_id") or c.get("milestoneId")) == milestone_id)

    # Client-side tag filter
    if tag_filter:
        tag_lower = tag_filter.lower()
        _filter_cards(result, lambda k, c:
                      any(t.lower() == tag_lower
                          for t in (c.get("master_tags") or c.get("masterTags") or [])))

    # Client-side owner filter
    if owner_filter:
        owner_lower = owner_filter.lower()
        # Resolve owner name to user ID
        users = result.get("user", {})
        owner_id = None
        for uid, udata in users.items():
            if (udata.get("name") or "").lower() == owner_lower:
                owner_id = uid
                break
        if owner_id is None:
            user_map = _load_users()
            for uid, name in user_map.items():
                if name.lower() == owner_lower:
                    owner_id = uid
                    break
        if owner_id is None:
            available = [u.get("name", "") for u in result.get("user", {}).values()]
            if not available:
                available = list(_load_users().values())
            hint = f" Available: {', '.join(available)}" if available else ""
            print(f"[ERROR] Owner '{owner_filter}' not found.{hint}",
                  file=sys.stderr)
            sys.exit(1)
        _filter_cards(result, lambda k, c: c.get("assignee") == owner_id)

    return result


def _get_project_deck_ids(decks_result, project_name):
    """Return set of deck IDs belonging to a project, matched by name."""
    projects = _build_project_map(decks_result)
    for pid, info in projects.items():
        if info["name"].lower() == project_name.lower():
            return info["deck_ids"]
    return None


def _build_project_map(decks_result):
    """Build a map of projectId -> {name, deck_ids} from deck data.
    Project names come from CODECKS_PROJECTS in .env (API can't query them)."""
    project_names = _load_project_names()
    project_decks = {}
    for key, deck in decks_result.get("deck", {}).items():
        pid = deck.get("project_id") or deck.get("projectId")
        if pid:
            if pid not in project_decks:
                project_decks[pid] = {"deck_ids": set(), "deck_titles": []}
            project_decks[pid]["deck_ids"].add(deck.get("id"))
            project_decks[pid]["deck_titles"].append(deck.get("title", ""))

    # Apply names from .env mapping, fallback to projectId
    for pid, info in project_decks.items():
        info["name"] = project_names.get(pid, pid)

    return project_decks


def get_card(card_id):
    card_filter = json.dumps({"cardId": card_id, "visibility": "default"})
    q = {"_root": [{"account": [{f"cards({card_filter})": [
        "title", "status", "priority", "content", "deckId",
        "effort", "createdAt", "milestoneId", "masterTags",
        "lastUpdatedAt", "isDoc", "checkboxStats",
        {"assignee": ["name", "id"]},
        {"childCards": ["title", "status"]},
        {"resolvables": [
            "context", "isClosed", "createdAt",
            {"creator": ["name"]},
            {"entries": ["content", "createdAt", {"author": ["name"]}]},
        ]},
    ]}]}]}
    return query(q)


def list_milestones():
    """List milestones. Scans cards for milestone IDs and uses .env names."""
    milestone_names = _load_milestone_names()
    result = list_cards()
    used_ids = {}
    for key, card in result.get("card", {}).items():
        mid = card.get("milestone_id") or card.get("milestoneId")
        if mid:
            if mid not in used_ids:
                used_ids[mid] = []
            used_ids[mid].append(card.get("title", ""))
    output = {}
    for mid, name in milestone_names.items():
        output[mid] = {"name": name, "cards": used_ids.get(mid, [])}
    for mid, cards in used_ids.items():
        if mid not in output:
            output[mid] = {"name": mid, "cards": cards}
    return output


def list_activity(limit=20):
    """Query recent account activity."""
    q = {"_root": [{"account": [{"activities": [
        "type", "createdAt", "card", "data",
        {"changer": ["name"]},
        {"deck": ["title"]},
    ]}]}]}
    result = query(q)
    return result


def list_projects():
    """List projects by querying decks and grouping by projectId."""
    decks_result = list_decks()
    projects = _build_project_map(decks_result)
    output = {}
    for pid, info in projects.items():
        output[pid] = {
            "name": info.get("name", pid),
            "deck_count": len(info["deck_ids"]),
            "decks": info["deck_titles"],
        }
    return output


# ---------------------------------------------------------------------------
# Enrichment (resolve IDs to human-readable names)
# ---------------------------------------------------------------------------

def _enrich_cards(cards_dict, user_data=None):
    """Add deck_name, milestone_name, owner_name to card dicts."""
    decks_result = list_decks()
    deck_names = {}
    for key, deck in decks_result.get("deck", {}).items():
        deck_names[deck.get("id")] = deck.get("title", "")

    milestone_names = _load_milestone_names()

    # Build user name map from user_data (query result) or _load_users()
    user_names = {}
    if user_data:
        for uid, udata in user_data.items():
            user_names[uid] = udata.get("name", "")
    if not user_names:
        user_names = _load_users()

    for key, card in cards_dict.items():
        did = card.get("deck_id") or card.get("deckId")
        if did:
            card["deck_name"] = deck_names.get(did, did)
        mid = card.get("milestone_id") or card.get("milestoneId")
        if mid:
            card["milestone_name"] = milestone_names.get(mid, mid)
        # Resolve owner name
        assignee = card.get("assignee")
        if assignee:
            card["owner_name"] = user_names.get(assignee, assignee)
        # Normalize tags field
        tags = card.get("master_tags") or card.get("masterTags") or []
        card["tags"] = tags
        # Sub-card info
        child_info = card.get("child_card_info") or card.get("childCardInfo")
        if child_info:
            if isinstance(child_info, str):
                try:
                    child_info = json.loads(child_info)
                except (json.JSONDecodeError, TypeError):
                    child_info = {}
            if isinstance(child_info, dict):
                card["sub_card_count"] = child_info.get("count", 0)

    return cards_dict


def _compute_card_stats(cards_dict):
    """Compute summary statistics from card data."""
    stats = {
        "total": len(cards_dict),
        "by_status": {},
        "by_priority": {},
        "by_deck": {},
    }
    total_effort = 0
    effort_count = 0
    for key, card in cards_dict.items():
        status = card.get("status", "unknown")
        stats["by_status"][status] = stats["by_status"].get(status, 0) + 1

        priority = card.get("priority") or "none"
        stats["by_priority"][priority] = stats["by_priority"].get(priority, 0) + 1

        deck = card.get("deck_name", card.get("deck_id", "unknown"))
        stats["by_deck"][deck] = stats["by_deck"].get(deck, 0) + 1

        effort = card.get("effort")
        if effort is not None:
            total_effort += effort
            effort_count += 1

    stats["total_effort"] = total_effort
    stats["avg_effort"] = round(total_effort / effort_count, 1) if effort_count else 0
    return stats


# ---------------------------------------------------------------------------
# Mutation helpers
# ---------------------------------------------------------------------------

def create_card(title, content=None, severity=None):
    """Create a card using the Report Token (stable, no expiry).
    First line of content becomes the card title."""
    if content:
        full_content = title + "\n\n" + content
    else:
        full_content = title
    return report_request(full_content, severity=severity)


def update_card(card_id, **kwargs):
    """Update card properties via dispatch (uses session token).
    Supported fields: status, priority, effort, deckId, title, content,
    milestoneId, parentCardId, assigneeId, masterTags, isDoc.
    None values are sent as JSON null to clear fields."""
    payload = {"id": card_id}
    payload.update(kwargs)
    return session_request("/dispatch/cards/update", payload)


def archive_card(card_id):
    """Archive a card (uses session token)."""
    return session_request("/dispatch/cards/update", {
        "id": card_id,
        "isArchived": True,
    })


def unarchive_card(card_id):
    """Unarchive a card (uses session token)."""
    return session_request("/dispatch/cards/update", {
        "id": card_id,
        "isArchived": False,
    })


def delete_card(card_id):
    """Delete a card — archives first, then deletes (uses session token)."""
    archive_card(card_id)
    try:
        return session_request("/dispatch/cards/bulkUpdate", {
            "ids": [card_id],
            "visibility": "deleted",
            "deleteFiles": False,
        })
    except SystemExit:
        print(f"Warning: Card {card_id} was archived but delete failed. "
              f"Use 'unarchive' to recover.", file=sys.stderr)
        raise


def bulk_status(card_ids, status):
    """Update status for multiple cards at once."""
    return session_request("/dispatch/cards/bulkUpdate", {
        "ids": card_ids,
        "status": status,
    })


# ---------------------------------------------------------------------------
# Hand helpers (personal card queue)
# ---------------------------------------------------------------------------

def _get_user_id():
    """Return the current user's ID. Reads from .env, falls back to API."""
    if config.USER_ID:
        return config.USER_ID
    # Auto-discover: query account roles, pick the first owner
    result = query({"_root": [{"account": [
        {"roles": ["userId", "role"]}
    ]}]})
    for entry in (result.get("accountRole") or {}).values():
        if entry.get("role") == "owner":
            return entry.get("userId") or entry.get("user_id")
    # Fallback: first role found
    for entry in (result.get("accountRole") or {}).values():
        uid = entry.get("userId") or entry.get("user_id")
        if uid:
            return uid
    print("[ERROR] Could not determine your user ID. "
          "Run: py codecks_api.py setup", file=sys.stderr)
    sys.exit(1)


def list_hand():
    """Query the current user's hand (queueEntries)."""
    q = {"_root": [{"account": [{"queueEntries": [
        "card", "sortIndex", "user"
    ]}]}]}
    return query(q)


def _extract_hand_card_ids(hand_result):
    """Extract card IDs from a list_hand() result as a set."""
    hand_card_ids = set()
    for entry in (hand_result.get("queueEntry") or {}).values():
        cid = entry.get("card") or entry.get("cardId")
        if cid:
            hand_card_ids.add(cid)
    return hand_card_ids


def add_to_hand(card_ids):
    """Add cards to the current user's hand."""
    user_id = _get_user_id()
    return session_request("/dispatch/handQueue/setCardOrders", {
        "sessionId": str(uuid.uuid4()),
        "userId": user_id,
        "cardIds": card_ids,
        "draggedCardIds": card_ids,
    })


def remove_from_hand(card_ids):
    """Remove cards from the current user's hand."""
    return session_request("/dispatch/handQueue/removeCards", {
        "sessionId": str(uuid.uuid4()),
        "cardIds": card_ids,
    })


# ---------------------------------------------------------------------------
# Conversation helpers (threaded comments on cards)
# ---------------------------------------------------------------------------

def create_comment(card_id, content):
    """Create a new comment thread on a card."""
    user_id = _get_user_id()
    return session_request("/dispatch/resolvables/create", {
        "cardId": card_id,
        "userId": user_id,
        "content": content,
        "context": "comment",
    })


def reply_comment(resolvable_id, content):
    """Reply to an existing comment thread."""
    user_id = _get_user_id()
    return session_request("/dispatch/resolvables/comment", {
        "resolvableId": resolvable_id,
        "content": content,
        "authorId": user_id,
    })


def close_comment(resolvable_id, card_id):
    """Close a comment thread."""
    user_id = _get_user_id()
    return session_request("/dispatch/resolvables/close", {
        "id": resolvable_id,
        "isClosed": True,
        "cardId": card_id,
        "closedBy": user_id,
    })


def reopen_comment(resolvable_id, card_id):
    """Reopen a closed comment thread."""
    return session_request("/dispatch/resolvables/reopen", {
        "id": resolvable_id,
        "isClosed": False,
        "cardId": card_id,
    })


def get_conversations(card_id):
    """Fetch all conversations (resolvables) on a card."""
    card_filter = json.dumps({"cardId": card_id, "visibility": "default"})
    q = {"_root": [{"account": [{f"cards({card_filter})": [
        "title",
        {"resolvables": [
            "context", "isClosed", "createdAt",
            {"creator": ["name"]},
            {"entries": ["content", "createdAt", {"author": ["name"]}]},
        ]},
    ]}]}]}
    return query(q)


# ---------------------------------------------------------------------------
# Name -> ID resolution helpers
# ---------------------------------------------------------------------------

def _resolve_deck_id(deck_name):
    """Resolve deck name to ID."""
    decks_result = list_decks()
    available = []
    for key, deck in decks_result.get("deck", {}).items():
        title = deck.get("title", "")
        if title.lower() == deck_name.lower():
            return deck.get("id")
        available.append(title)
    hint = f" Available: {', '.join(available)}" if available else ""
    print(f"[ERROR] Deck '{deck_name}' not found.{hint}", file=sys.stderr)
    sys.exit(1)


def _resolve_milestone_id(milestone_name):
    """Resolve milestone name to ID using .env mapping."""
    milestone_names = _load_milestone_names()
    for mid, name in milestone_names.items():
        if name.lower() == milestone_name.lower():
            return mid
    available = list(milestone_names.values())
    hint = f" Available: {', '.join(available)}" if available else ""
    print(f"[ERROR] Milestone '{milestone_name}' not found.{hint} "
          "Add milestones to .env: CODECKS_MILESTONES=<id>=<name>", file=sys.stderr)
    sys.exit(1)
