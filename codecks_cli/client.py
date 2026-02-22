"""
CodecksClient — public Python API for managing Codecks project cards.

Single entry point for programmatic use and future MCP server integration.
All methods return flat dicts suitable for JSON serialization.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

# TypedDict return types live in codecks_cli.types for documentation.
# Method signatures use plain dict[str, Any] for mypy compatibility.
from typing import Any

from codecks_cli import config
from codecks_cli._utils import _get_field, _parse_iso_timestamp
from codecks_cli.api import (
    _check_token,
    _safe_json_parse,
    dispatch,
    query,
)
from codecks_cli.cards import (
    add_to_hand,
    archive_card,
    bulk_status,
    close_comment,
    compute_card_stats,
    create_card,
    create_comment,
    delete_card,
    enrich_cards,
    extract_hand_card_ids,
    get_account,
    get_card,
    get_conversations,
    get_project_deck_ids,
    list_activity,
    list_cards,
    list_decks,
    list_hand,
    list_milestones,
    list_projects,
    load_project_names,
    load_users,
    remove_from_hand,
    reopen_comment,
    reply_comment,
    resolve_deck_id,
    resolve_milestone_id,
    unarchive_card,
    update_card,
)
from codecks_cli.exceptions import CliError, SetupError
from codecks_cli.models import (
    FeatureScaffoldReport,
    FeatureSpec,
    FeatureSubcard,
    SplitFeatureDetail,
    SplitFeaturesReport,
    SplitFeaturesSpec,
)

# ---------------------------------------------------------------------------
# Helpers (moved from commands.py)
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


def _sort_field_value(card, sort_field):
    """Return the sortable value for a field with snake/camel compatibility."""
    if sort_field == "updated":
        return _get_field(card, "last_updated_at", "lastUpdatedAt")
    if sort_field == "created":
        return _get_field(card, "created_at", "createdAt")
    field = _SORT_KEY_MAP[sort_field]
    return card.get(field)


def _sort_cards(cards_dict, sort_field):
    """Sort a {card_id: card_data} dict by *sort_field*; return a new dict."""
    reverse = sort_field in ("updated", "created")

    def _key(item):
        v = _sort_field_value(item[1], sort_field)
        if v is None or v == "":
            return (1, "") if not reverse else (-1, "")
        if isinstance(v, (int, float)):
            return (0, v)
        return (0, str(v).lower())

    return dict(sorted(cards_dict.items(), key=_key, reverse=reverse))


def _resolve_owner_id(owner_name):
    """Resolve owner display name to user ID."""
    user_map = load_users()
    for uid, name in user_map.items():
        if name.lower() == owner_name.lower():
            return uid
    available = list(user_map.values())
    hint = f" Available: {', '.join(available)}" if available else ""
    raise CliError(f"[ERROR] Owner '{owner_name}' not found.{hint}")


def _card_row(cid, card):
    return {
        "id": cid,
        "title": card.get("title", ""),
        "status": card.get("status"),
        "priority": card.get("priority"),
        "effort": card.get("effort"),
        "deck_name": card.get("deck_name") or card.get("deck"),
        "owner_name": card.get("owner_name"),
    }


def _normalize_title(title):
    return " ".join((title or "").strip().lower().split())


def _find_duplicate_title_candidates(title, limit=5):
    """Return (exact, similar) duplicate candidates for a card title."""
    normalized_target = _normalize_title(title)
    if not normalized_target:
        return [], []

    result = list_cards(search_filter=title, archived=False)
    cards = result.get("card", {})

    exact = []
    similar = []
    for cid, card in cards.items():
        existing_title = (card.get("title") or "").strip()
        if not existing_title:
            continue
        normalized_existing = _normalize_title(existing_title)
        if not normalized_existing:
            continue

        status = card.get("status") or "unknown"
        row = {"id": cid, "title": existing_title, "status": status}
        if normalized_existing == normalized_target:
            exact.append(row)
            continue

        score = SequenceMatcher(None, normalized_target, normalized_existing).ratio()
        if (
            normalized_target in normalized_existing
            or normalized_existing in normalized_target
            or score >= 0.88
        ):
            row["score"] = score
            similar.append(row)

    similar.sort(key=lambda item: item.get("score", 0), reverse=True)
    return exact[:limit], similar[:limit]


def _guard_duplicate_title(title, allow_duplicate=False, context="card"):
    """Fail on exact duplicates and warn on near matches unless explicitly allowed.

    Returns:
        list of warning strings (empty if no near matches found).
    """
    if allow_duplicate:
        return []

    exact, similar = _find_duplicate_title_candidates(title)
    if exact:
        preview = ", ".join(
            f"{item['id']} ('{item['title']}', status={item['status']})" for item in exact
        )
        raise CliError(
            f"[ERROR] Duplicate {context} title detected: '{title}'.\n"
            f"[ERROR] Existing: {preview}\n"
            "[ERROR] Re-run with --allow-duplicate to bypass this check."
        )

    warnings = []
    if similar:
        preview = ", ".join(
            f"{item['id']} ('{item['title']}', status={item['status']})" for item in similar
        )
        warnings.append(f"Similar {context} titles found for '{title}': {preview}")
    return warnings


def _normalize_dispatch_path(path):
    """Normalize and validate a dispatch path segment."""
    normalized = (path or "").strip()
    if not normalized:
        raise CliError("[ERROR] Dispatch path cannot be empty.")
    normalized = normalized.lstrip("/")
    if normalized.startswith("dispatch/"):
        normalized = normalized[len("dispatch/") :]
    if not normalized or normalized.startswith("/") or " " in normalized:
        raise CliError("[ERROR] Invalid dispatch path. Use e.g. cards/update")
    return normalized


def _flatten_cards(cards_dict):
    """Convert {uuid: card_data} dict to flat list with 'id' injected."""
    result = []
    for cid, card in cards_dict.items():
        flat = dict(card)
        flat["id"] = cid
        result.append(flat)
    return result


def _to_legacy_format(cards_list):
    """Convert flat card list back to {uuid: card_data} dict for formatters."""
    result = {}
    for card in cards_list:
        card_copy = dict(card)
        cid = card_copy.pop("id", None)
        if cid:
            result[cid] = card_copy
    return result


# ---------------------------------------------------------------------------
# Content analysis helpers for split-features
# ---------------------------------------------------------------------------

_LANE_KEYWORDS: dict[str, list[str]] = {
    "code": [
        "implement",
        "build",
        "create bp_",
        "struct",
        "function",
        "test:",
        "logic",
        "system",
        "enum",
        "component",
        "manager",
        "tracking",
        "handle",
        "wire",
        "connect",
        "refactor",
        "fix",
        "debug",
        "integrate",
        "script",
        "blueprint",
        "variable",
        "class",
        "method",
    ],
    "art": [
        "sprite",
        "animation",
        "visual",
        "portrait",
        "ui layout",
        "effect",
        "icon",
        "color",
        "asset",
        "texture",
        "particle",
        "vfx",
    ],
    "design": [
        "balance",
        "tune",
        "playtest",
        "define",
        "pacing",
        "feel",
        "scaling",
        "progression",
        "economy",
        "curve",
        "difficulty",
        "feedback",
        "flow",
        "reward",
        "threshold",
    ],
}


def _classify_checklist_item(text: str) -> str | None:
    """Score a checklist item against lane keywords, return highest lane or None."""
    lower = text.lower()
    scores: dict[str, int] = {}
    for lane, keywords in _LANE_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in lower)
        if score > 0:
            scores[lane] = score
    if not scores:
        return None
    return max(scores, key=lambda k: scores[k])


def _analyze_feature_for_lanes(content: str, *, include_art: bool = True) -> dict[str, list[str]]:
    """Parse checklist items from card content and classify into lanes.

    Handles both ``- []`` (Codecks interactive) and ``- [ ]`` (markdown) formats.
    Unclassified items go to the smallest lane. Empty lanes get generic defaults.
    """
    import re

    lanes: dict[str, list[str]] = {"code": [], "design": []}
    if include_art:
        lanes["art"] = []

    items: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        match = re.match(r"^-\s*\[[\sx]?\]\s*(.+)", stripped)
        if match:
            items.append(match.group(1).strip())

    unclassified: list[str] = []
    for item in items:
        lane = _classify_checklist_item(item)
        if lane and lane in lanes:
            lanes[lane].append(item)
        else:
            unclassified.append(item)

    # Distribute unclassified items to the smallest lane
    for item in unclassified:
        smallest = min(lanes, key=lambda k: len(lanes[k]))
        lanes[smallest].append(item)

    # Fill empty lanes with generic defaults
    defaults = {
        "code": ["Implement core logic", "Handle edge cases", "Add tests/verification"],
        "design": [
            "Define target player feel",
            "Tune balance/economy parameters",
            "Run playtest and iterate",
        ],
        "art": [
            "Create required assets/content",
            "Integrate assets in game flow",
            "Visual quality pass",
        ],
    }
    for lane in lanes:
        if not lanes[lane]:
            lanes[lane] = list(defaults.get(lane, [f"Complete {lane} tasks"]))

    return lanes


# ---------------------------------------------------------------------------
# CodecksClient
# ---------------------------------------------------------------------------


class CodecksClient:
    """Public API surface for Codecks project management.

    All methods use keyword-only arguments and return plain dicts
    suitable for JSON serialization. Raises CliError/SetupError on failure.
    """

    def __init__(self, *, validate_token=True):
        """Initialize the client.

        Args:
            validate_token: If True, check that the session token is valid
                before any API call. Set to False for commands that don't
                need a token (setup, gdd-auth, etc.).
        """
        if validate_token:
            _check_token()

    # -------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------

    def _get_hand_card_ids(self) -> set[str]:
        """Return cached set of card IDs in hand."""
        if "hand" not in config._cache:
            hand_result = list_hand()
            config._cache["hand"] = set(extract_hand_card_ids(hand_result))
        result: set[str] = config._cache["hand"]  # type: ignore[assignment]
        return result

    # -------------------------------------------------------------------
    # Read commands
    # -------------------------------------------------------------------

    def get_account(self) -> dict[str, Any]:
        """Get current account info for the authenticated user.

        Returns:
            dict with keys: name, id, email, organizationId, role.
        """
        return get_account()  # type: ignore[no-any-return]

    def list_cards(
        self,
        *,
        deck: str | None = None,
        status: str | None = None,
        project: str | None = None,
        search: str | None = None,
        milestone: str | None = None,
        tag: str | None = None,
        owner: str | None = None,
        priority: str | None = None,
        sort: str | None = None,
        card_type: str | None = None,
        hero: str | None = None,
        hand_only: bool = False,
        stale_days: int | None = None,
        updated_after: str | None = None,
        updated_before: str | None = None,
        archived: bool = False,
        include_stats: bool = False,
    ) -> dict[str, Any]:
        """List cards with optional filters.

        Args:
            deck: Filter by deck name.
            status: Filter by status (comma-separated for multiple).
            project: Filter by project name.
            search: Search cards by title/content.
            milestone: Filter by milestone name.
            tag: Filter by tag name.
            owner: Filter by owner name ('none' for unassigned).
            priority: Filter by priority (comma-separated for multiple).
            sort: Sort field (status, priority, effort, deck, title, owner,
                  updated, created).
            card_type: Filter by card type ('hero' or 'doc').
            hero: Show only sub-cards of this hero card ID.
            hand_only: If True, show only cards in the user's hand.
            stale_days: Find cards not updated in N days.
            updated_after: Cards updated after this date (YYYY-MM-DD).
            updated_before: Cards updated before this date (YYYY-MM-DD).
            archived: If True, show archived cards instead of active ones.
            include_stats: If True, also compute aggregate stats.

        Returns:
            dict with 'cards' (list of card dicts with id, title, status,
            priority, effort, deck_name, owner_name) and 'stats' (null unless
            include_stats=True, then dict with total, by_status, by_priority,
            by_effort counts).
        """
        # Validate sort field
        if sort and sort not in config.VALID_SORT_FIELDS:
            raise CliError(
                f"[ERROR] Invalid sort field '{sort}'. "
                f"Valid: {', '.join(sorted(config.VALID_SORT_FIELDS))}"
            )
        # Validate card_type
        if card_type and card_type not in config.VALID_CARD_TYPES:
            raise CliError(
                f"[ERROR] Invalid card type '{card_type}'. "
                f"Valid: {', '.join(sorted(config.VALID_CARD_TYPES))}"
            )

        result = list_cards(
            deck_filter=deck,
            status_filter=status,
            project_filter=project,
            search_filter=search,
            milestone_filter=milestone,
            tag_filter=tag,
            owner_filter=owner,
            priority_filter=priority,
            stale_days=stale_days,
            updated_after=updated_after,
            updated_before=updated_before,
            archived=archived,
        )

        # Filter to hand cards if requested
        if hand_only:
            hand_result = list_hand()
            hand_card_ids = extract_hand_card_ids(hand_result)
            result["card"] = {k: v for k, v in result.get("card", {}).items() if k in hand_card_ids}

        # Filter to sub-cards of a hero card
        if hero:
            hero_result = get_card(hero)
            child_ids = set()
            for cdata in hero_result.get("card", {}).values():
                for cid in cdata.get("childCards") or []:
                    child_ids.add(cid)
            result["card"] = {k: v for k, v in result.get("card", {}).items() if k in child_ids}

        # Enrich cards with deck/milestone/owner names
        result["card"] = enrich_cards(result.get("card", {}), result.get("user"))

        # Filter by card type
        if card_type:
            if card_type == "doc":
                result["card"] = {
                    k: v
                    for k, v in result.get("card", {}).items()
                    if _get_field(v, "is_doc", "isDoc")
                }
            elif card_type == "hero":
                card_filter = json.dumps({"visibility": "default"})
                hero_q = {
                    "_root": [{"account": [{f"cards({card_filter})": [{"childCards": ["title"]}]}]}]
                }
                hero_result = query(hero_q)
                hero_ids = {
                    k for k, v in hero_result.get("card", {}).items() if v.get("childCards")
                }
                result["card"] = {k: v for k, v in result.get("card", {}).items() if k in hero_ids}

        # Sort cards if requested
        if sort and result.get("card"):
            result["card"] = _sort_cards(result["card"], sort)

        if include_stats:
            stats = compute_card_stats(result.get("card", {}))
            return {"cards": _flatten_cards(result.get("card", {})), "stats": stats}

        return {"cards": _flatten_cards(result.get("card", {})), "stats": None}

    def get_card(
        self,
        card_id: str,
        *,
        include_content: bool = True,
        include_conversations: bool = True,
    ) -> dict[str, Any]:
        """Get full details for a single card.

        Args:
            card_id: The card's UUID or short ID.
            include_content: If False, strip the content field (keep title).
            include_conversations: If False, skip conversation resolution.

        Returns:
            dict with card details including checklist, sub-cards,
            conversations, and hand status.
        """
        result = get_card(card_id)
        result["card"] = enrich_cards(result.get("card", {}), result.get("user"))

        # Check if this card is in hand (cached)
        hand_card_ids = self._get_hand_card_ids()
        for card_key, card in result.get("card", {}).items():
            card["in_hand"] = card_key in hand_card_ids

        # Find the requested card — API returns it plus child cards in same dict
        cards = result.get("card", {})
        if not cards:
            raise CliError(f"[ERROR] Card '{card_id}' not found.")

        # Look for exact match first, then prefix match (short IDs)
        target_key = None
        if card_id in cards:
            target_key = card_id
        else:
            for cid in cards:
                if cid.startswith(card_id):
                    target_key = cid
                    break

        if target_key is None:
            raise CliError(f"[ERROR] Card '{card_id}' not found.")

        card_data = cards[target_key]
        detail = dict(card_data)
        detail["id"] = target_key

        # Resolve sub-cards
        child_cards = card_data.get("childCards")
        if child_cards:
            sub_cards = []
            for ckey in child_cards:
                child = cards.get(ckey, {})
                sub_cards.append(
                    {
                        "id": ckey,
                        "title": child.get("title", ckey),
                        "status": child.get("status", "unknown"),
                    }
                )
            detail["sub_cards"] = sub_cards

        # Resolve conversations
        resolvables = card_data.get("resolvables") or []
        if include_conversations and resolvables:
            resolvable_data = result.get("resolvable", {})
            entry_data = result.get("resolvableEntry", {})
            user_data = result.get("user", {})
            conversations = []
            for rid in resolvables:
                r = resolvable_data.get(rid, {})
                creator_id = r.get("creator")
                creator_name = user_data.get(creator_id, {}).get("name", "?") if creator_id else "?"
                is_closed = _get_field(r, "is_closed", "isClosed")
                entries = r.get("entries") or []
                messages = []
                for eid in entries:
                    e = entry_data.get(eid, {})
                    author_id = e.get("author")
                    author_name = (
                        user_data.get(author_id, {}).get("name", "?") if author_id else "?"
                    )
                    messages.append(
                        {
                            "author": author_name,
                            "content": e.get("content", ""),
                            "created_at": _get_field(e, "created_at", "createdAt") or "",
                        }
                    )
                conversations.append(
                    {
                        "id": rid,
                        "status": "closed" if is_closed else "open",
                        "creator": creator_name,
                        "created_at": _get_field(r, "created_at", "createdAt") or "",
                        "messages": messages,
                    }
                )
            detail["conversations"] = conversations

        if not include_content:
            detail.pop("content", None)

        return detail

    def list_decks(self, *, include_card_counts: bool = True) -> list[dict[str, Any]]:
        """List all decks with optional card counts.

        Args:
            include_card_counts: If True, fetch all cards to count per deck
                (extra API call). If False, card_count is None.

        Returns:
            list of deck dicts with id, title, project_name, card_count.
        """
        decks_result = list_decks()
        deck_counts: dict[str, int] | None = None
        if include_card_counts:
            cards_result = list_cards()
            deck_counts = {}
            for card in cards_result.get("card", {}).values():
                did = _get_field(card, "deck_id", "deckId")
                if did:
                    deck_counts[did] = deck_counts.get(did, 0) + 1

        project_names = load_project_names()
        result = []
        for key, deck in decks_result.get("deck", {}).items():
            did = deck.get("id", key)
            pid = _get_field(deck, "project_id", "projectId") or ""
            result.append(
                {
                    "id": did,
                    "title": deck.get("title", ""),
                    "project_name": project_names.get(pid, pid),
                    "card_count": deck_counts.get(did, 0) if deck_counts is not None else None,
                }
            )
        return result

    def list_projects(self) -> list[dict[str, Any]]:
        """List all projects.

        Returns:
            list of project dicts with id, name, deck_count, decks.
        """
        raw = list_projects()
        result = []
        for pid, info in raw.items():
            result.append(
                {
                    "id": pid,
                    "name": info.get("name", pid),
                    "deck_count": info.get("deck_count", 0),
                    "decks": info.get("decks", []),
                }
            )
        return result

    def list_milestones(self) -> list[dict[str, Any]]:
        """List all milestones.

        Returns:
            list of milestone dicts with id, name, card_count.
        """
        raw = list_milestones()
        result = []
        for mid, info in raw.items():
            result.append(
                {
                    "id": mid,
                    "name": info.get("name", mid),
                    "card_count": len(info.get("cards", [])),
                }
            )
        return result

    def list_activity(self, *, limit: int = 20) -> dict[str, Any]:
        """Show recent activity feed for the account.

        Args:
            limit: Maximum number of activity events to return (default 20).

        Returns:
            dict with 'activity' (map of event_id to event dict with type,
            card, user, createdAt), 'card' (referenced cards), and 'user'
            (referenced users).
        """
        if limit <= 0:
            raise CliError("[ERROR] --limit must be a positive integer.")
        return list_activity(limit)  # type: ignore[no-any-return]

    def pm_focus(
        self,
        *,
        project: str | None = None,
        owner: str | None = None,
        limit: int = 5,
        stale_days: int = 14,
    ) -> dict[str, Any]:
        """Generate PM focus dashboard data.

        Args:
            project: Filter by project name.
            owner: Filter by owner name.
            limit: Number of suggested next cards (default 5).
            stale_days: Days threshold for stale detection (default 14).

        Returns:
            dict with counts, blocked, in_review, hand, stale, suggested.
        """
        result = list_cards(project_filter=project, owner_filter=owner)
        cards = enrich_cards(result.get("card", {}), result.get("user"))
        hand_ids = extract_hand_card_ids(list_hand())

        cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)

        started = []
        blocked = []
        in_review = []
        hand = []
        stale = []
        candidates = []

        for cid, card in cards.items():
            status = card.get("status")
            row = _card_row(cid, card)
            if status == "started":
                started.append(row)
            if status == "blocked":
                blocked.append(row)
            if status == "in_review":
                in_review.append(row)
            if cid in hand_ids:
                hand.append(row)
            if status == "not_started" and cid not in hand_ids:
                candidates.append(row)
            # Stale: started or in_review cards not updated in stale_days
            if status in ("started", "in_review"):
                updated = _parse_iso_timestamp(_get_field(card, "last_updated_at", "lastUpdatedAt"))
                if updated and updated < cutoff:
                    stale.append(row)

        pri_rank = {"a": 0, "b": 1, "c": 2, None: 3, "": 3}
        candidates.sort(
            key=lambda c: (
                pri_rank.get(c.get("priority"), 3),
                0 if c.get("effort") is not None else 1,
                -(c.get("effort") or 0),
                c.get("title", "").lower(),
            )
        )
        suggested = candidates[:limit]

        return {
            "counts": {
                "started": len(started),
                "blocked": len(blocked),
                "in_review": len(in_review),
                "hand": len(hand),
                "stale": len(stale),
            },
            "blocked": blocked,
            "in_review": in_review,
            "hand": hand,
            "stale": stale,
            "suggested": suggested,
            "filters": {
                "project": project,
                "owner": owner,
                "limit": limit,
                "stale_days": stale_days,
            },
        }

    def standup(
        self, *, days: int = 2, project: str | None = None, owner: str | None = None
    ) -> dict[str, Any]:
        """Generate daily standup summary.

        Args:
            days: Lookback for recent completions (default 2).
            project: Filter by project name.
            owner: Filter by owner name.

        Returns:
            dict with recently_done, in_progress, blocked, hand.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        result = list_cards(project_filter=project, owner_filter=owner)
        cards = enrich_cards(result.get("card", {}), result.get("user"))
        hand_ids = extract_hand_card_ids(list_hand())

        recently_done = []
        in_progress = []
        blocked = []
        hand = []

        for cid, card in cards.items():
            status = card.get("status")
            row = _card_row(cid, card)

            if status == "done":
                updated = _parse_iso_timestamp(_get_field(card, "last_updated_at", "lastUpdatedAt"))
                if updated and updated >= cutoff:
                    recently_done.append(row)

            elif status in ("started", "in_review"):
                in_progress.append(row)

            if status == "blocked":
                blocked.append(row)

            if cid in hand_ids and status != "done":
                hand.append(row)

        return {
            "recently_done": recently_done,
            "in_progress": in_progress,
            "blocked": blocked,
            "hand": hand,
            "filters": {"project": project, "owner": owner, "days": days},
        }

    # -------------------------------------------------------------------
    # Hand commands
    # -------------------------------------------------------------------

    def list_hand(self) -> list[dict[str, Any]]:
        """List cards in the user's hand.

        Returns:
            list of card dicts sorted by hand order.
        """
        hand_result = list_hand()
        hand_card_ids = extract_hand_card_ids(hand_result)
        if not hand_card_ids:
            return []

        result = list_cards()
        filtered = {k: v for k, v in result.get("card", {}).items() if k in hand_card_ids}
        enriched = enrich_cards(filtered, result.get("user"))

        # Sort by hand sort order (sortIndex from queueEntries)
        sort_map = {}
        for entry in (hand_result.get("queueEntry") or {}).values():
            cid = _get_field(entry, "card", "cardId")
            if cid:
                sort_map[cid] = entry.get("sortIndex", 0) or 0
        sorted_cards = dict(sorted(enriched.items(), key=lambda item: sort_map.get(item[0], 0)))
        return _flatten_cards(sorted_cards)  # type: ignore[no-any-return]

    def add_to_hand(self, card_ids: list[str]) -> dict[str, Any]:
        """Add cards to the user's hand (personal work queue).

        Args:
            card_ids: List of full card UUIDs (36-char format) to add.

        Returns:
            dict with ok=True and count of added cards.
        """
        add_to_hand(card_ids)
        config._cache.pop("hand", None)
        return {
            "ok": True,
            "added": len(card_ids),
            "failed": 0,
            "per_card": [{"card_id": cid, "ok": True} for cid in card_ids],
        }

    def remove_from_hand(self, card_ids: list[str]) -> dict[str, Any]:
        """Remove cards from the user's hand (personal work queue).

        Args:
            card_ids: List of full card UUIDs (36-char format) to remove.

        Returns:
            dict with ok=True and count of removed cards.
        """
        remove_from_hand(card_ids)
        config._cache.pop("hand", None)
        return {
            "ok": True,
            "removed": len(card_ids),
            "failed": 0,
            "per_card": [{"card_id": cid, "ok": True} for cid in card_ids],
        }

    # -------------------------------------------------------------------
    # Mutation commands
    # -------------------------------------------------------------------

    def create_card(
        self,
        title: str,
        *,
        content: str | None = None,
        deck: str | None = None,
        project: str | None = None,
        severity: str | None = None,
        doc: bool = False,
        allow_duplicate: bool = False,
    ) -> dict[str, Any]:
        """Create a new card.

        Args:
            title: Card title.
            content: Card body/description.
            deck: Place card in this deck (by name).
            project: Place card in the first deck of this project.
            severity: Card severity (critical, high, low, null).
            doc: If True, create as a doc card.
            allow_duplicate: Bypass duplicate title protection.

        Returns:
            dict with ok=True, card_id, and title.
        """
        warnings = _guard_duplicate_title(title, allow_duplicate=allow_duplicate, context="card")

        result = create_card(title, content, severity)
        card_id = result.get("cardId", "")
        if not card_id:
            raise CliError(
                "[ERROR] Card creation failed: API response missing "
                f"'cardId'. Response: {str(result)[:200]}"
            )

        placed_in = None
        post_update = {}
        if deck:
            post_update["deckId"] = resolve_deck_id(deck)
            placed_in = deck
        elif project:
            decks_result = list_decks()
            project_deck_ids = get_project_deck_ids(decks_result, project)
            if project_deck_ids:
                post_update["deckId"] = next(iter(project_deck_ids))
                placed_in = project
            else:
                available = list(load_project_names().values())
                hint = f" Available: {', '.join(available)}" if available else ""
                raise CliError(f"[ERROR] Project '{project}' not found.{hint}")
        if doc:
            post_update["isDoc"] = True
        if post_update:
            update_card(card_id, **post_update)

        result_dict = {
            "ok": True,
            "card_id": card_id,
            "title": title,
            "deck": placed_in,
            "doc": doc,
        }
        if warnings:
            result_dict["warnings"] = warnings
        return result_dict

    def update_cards(
        self,
        card_ids: list[str],
        *,
        status: str | None = None,
        priority: str | None = None,
        effort: str | int | None = None,
        deck: str | None = None,
        title: str | None = None,
        content: str | None = None,
        milestone: str | None = None,
        hero: str | None = None,
        owner: str | None = None,
        tags: str | None = None,
        doc: str | None = None,
        continue_on_error: bool = False,
    ) -> dict[str, Any]:
        """Update one or more cards.

        Args:
            card_ids: List of card UUIDs.
            status: New status (not_started, started, done, blocked, in_review).
            priority: New priority (a, b, c, or 'null' to clear).
            effort: New effort (int, or 'null' to clear).
            deck: Move to this deck (by name).
            title: New title (single card only).
            content: New content (single card only).
            milestone: Milestone name (or 'none' to clear).
            hero: Parent card ID (or 'none' to detach).
            owner: Owner name (or 'none' to unassign).
            tags: Comma-separated tags (or 'none' to clear all).
            doc: 'true'/'false' to toggle doc card mode.
            continue_on_error: If True, continue updating remaining cards
                after a per-card failure and report partial results.

        Returns:
            dict with ok=True, updated count, and fields changed.
        """
        update_kwargs: dict[str, Any] = {}

        if status is not None:
            update_kwargs["status"] = status

        if priority is not None:
            update_kwargs["priority"] = None if priority == "null" else priority

        if effort is not None:
            if effort == "null" or effort is None:
                update_kwargs["effort"] = None
            else:
                try:
                    update_kwargs["effort"] = int(effort)
                except (ValueError, TypeError) as e:
                    raise CliError(
                        f"[ERROR] Invalid effort value '{effort}': must be a number or 'null'"
                    ) from e

        if deck is not None:
            update_kwargs["deckId"] = resolve_deck_id(deck)

        if title is not None:
            if len(card_ids) > 1:
                raise CliError("[ERROR] --title can only be used with a single card.")
            card_data = get_card(card_ids[0])
            cards = card_data.get("card", {})
            if not cards:
                raise CliError(f"[ERROR] Card '{card_ids[0]}' not found.")
            for _k, c in cards.items():
                old_content = c.get("content") or ""
                parts = old_content.split("\n", 1)
                new_content = title + ("\n" + parts[1] if len(parts) > 1 else "")
                update_kwargs["content"] = new_content
                break

        if content is not None:
            if len(card_ids) > 1:
                raise CliError("[ERROR] --content can only be used with a single card.")
            update_kwargs["content"] = content

        if milestone is not None:
            if milestone.lower() == "none":
                update_kwargs["milestoneId"] = None
            else:
                update_kwargs["milestoneId"] = resolve_milestone_id(milestone)

        if hero is not None:
            if hero.lower() == "none":
                update_kwargs["parentCardId"] = None
            else:
                update_kwargs["parentCardId"] = hero

        if owner is not None:
            if owner.lower() == "none":
                update_kwargs["assigneeId"] = None
            else:
                update_kwargs["assigneeId"] = _resolve_owner_id(owner)

        if tags is not None:
            if tags.lower() == "none":
                update_kwargs["masterTags"] = []
            else:
                new_tags = [t.strip() for t in tags.split(",") if t.strip()]
                update_kwargs["masterTags"] = new_tags

        if doc is not None:
            val = str(doc).lower()
            if val in ("true", "yes", "1"):
                update_kwargs["isDoc"] = True
            elif val in ("false", "no", "0"):
                update_kwargs["isDoc"] = False
            else:
                raise CliError(f"[ERROR] Invalid --doc value '{doc}'. Use true or false.")

        if not update_kwargs:
            raise CliError(
                "[ERROR] No update flags provided. Use --status, "
                "--priority, --effort, --owner, --tag, --doc, etc."
            )

        per_card: list[dict[str, Any]] = []
        updated = 0
        failed = 0
        first_error: CliError | None = None

        for cid in card_ids:
            try:
                update_card(cid, **update_kwargs)
                updated += 1
                per_card.append({"card_id": cid, "ok": True})
            except CliError as e:
                failed += 1
                per_card.append({"card_id": cid, "ok": False, "error": str(e)})
                if first_error is None:
                    first_error = e
                if not continue_on_error:
                    break

        if first_error is not None and not continue_on_error:
            raise CliError(
                f"[ERROR] Failed to update card '{per_card[-1]['card_id']}': {first_error}"
            ) from first_error

        return {
            "ok": failed == 0,
            "updated": updated,
            "failed": failed,
            "fields": update_kwargs,
            "per_card": per_card,
        }

    def mark_done(self, card_ids: list[str]) -> dict[str, Any]:
        """Mark one or more cards as done.

        Args:
            card_ids: List of card UUIDs.

        Returns:
            dict with ok=True and count.
        """
        bulk_status(card_ids, "done")
        return {
            "ok": True,
            "count": len(card_ids),
            "failed": 0,
            "per_card": [{"card_id": cid, "ok": True} for cid in card_ids],
        }

    def mark_started(self, card_ids: list[str]) -> dict[str, Any]:
        """Mark one or more cards as started.

        Args:
            card_ids: List of card UUIDs.

        Returns:
            dict with ok=True and count.
        """
        bulk_status(card_ids, "started")
        return {
            "ok": True,
            "count": len(card_ids),
            "failed": 0,
            "per_card": [{"card_id": cid, "ok": True} for cid in card_ids],
        }

    def archive_card(self, card_id: str) -> dict[str, Any]:
        """Archive a card (reversible).

        Args:
            card_id: Card UUID.

        Returns:
            dict with ok=True and card_id.
        """
        archive_card(card_id)
        return {"ok": True, "card_id": card_id, "per_card": [{"card_id": card_id, "ok": True}]}

    def unarchive_card(self, card_id: str) -> dict[str, Any]:
        """Restore an archived card.

        Args:
            card_id: Card UUID.

        Returns:
            dict with ok=True and card_id.
        """
        unarchive_card(card_id)
        return {"ok": True, "card_id": card_id, "per_card": [{"card_id": card_id, "ok": True}]}

    def delete_card(self, card_id: str) -> dict[str, Any]:
        """Permanently delete a card.

        Args:
            card_id: Card UUID.

        Returns:
            dict with ok=True and card_id.
        """
        delete_card(card_id)
        return {"ok": True, "card_id": card_id, "per_card": [{"card_id": card_id, "ok": True}]}

    def scaffold_feature(
        self,
        title: str,
        *,
        hero_deck: str,
        code_deck: str,
        design_deck: str,
        art_deck: str | None = None,
        skip_art: bool = False,
        description: str | None = None,
        owner: str | None = None,
        priority: str | None = None,
        effort: int | None = None,
        allow_duplicate: bool = False,
    ) -> dict[str, Any]:
        """Scaffold a Hero feature with lane sub-cards.

        Creates a Hero card plus Code, Design, and optionally Art sub-cards.
        Transaction-safe: archives created cards on partial failure.

        Args:
            title: Feature title.
            hero_deck: Hero card destination deck.
            code_deck: Code sub-card deck.
            design_deck: Design sub-card deck.
            art_deck: Art sub-card deck (required unless skip_art).
            skip_art: Skip art lane.
            description: Feature context/goal.
            owner: Owner name for hero and sub-cards.
            priority: Priority level (a, b, c, or 'null').
            effort: Effort estimation (int).
            allow_duplicate: Bypass duplicate title protection.

        Returns:
            FeatureScaffoldReport as dict.
        """
        spec = FeatureSpec.from_kwargs(
            title,
            hero_deck=hero_deck,
            code_deck=code_deck,
            design_deck=design_deck,
            art_deck=art_deck,
            skip_art=skip_art,
            description=description,
            owner=owner,
            priority=priority,
            effort=effort,
            allow_duplicate=allow_duplicate,
        )

        hero_title = f"Feature: {spec.title}"
        warnings = _guard_duplicate_title(
            hero_title,
            allow_duplicate=spec.allow_duplicate,
            context="feature hero",
        )

        hero_deck_id = resolve_deck_id(spec.hero_deck)
        code_deck_id = resolve_deck_id(spec.code_deck)
        design_deck_id = resolve_deck_id(spec.design_deck)
        art_deck_id = resolve_deck_id(spec.art_deck) if spec.art_deck else None

        owner_id = _resolve_owner_id(spec.owner) if spec.owner else None
        pri = None if spec.priority == "null" else spec.priority
        common_update = {}
        if owner_id:
            common_update["assigneeId"] = owner_id
        if pri is not None:
            common_update["priority"] = pri
        if spec.effort is not None:
            common_update["effort"] = spec.effort

        hero_body = (
            (spec.description.strip() + "\n\n" if spec.description else "") + "Success criteria:\n"
            "- [] Lane coverage agreed (Code/Design/Art)\n"
            "- [] Acceptance criteria validated\n"
            "- [] Integration verified\n\n"
            "Tags: #hero #feature"
        )
        created: list[FeatureSubcard] = []
        created_ids: list[str] = []

        def _rollback_created_ids():
            rolled_back = []
            rollback_failed = []
            for cid in reversed(created_ids):
                try:
                    archive_card(cid)
                    rolled_back.append(cid)
                except Exception:
                    rollback_failed.append(cid)
            return rolled_back, rollback_failed

        try:
            hero_result = create_card(hero_title, hero_body)
            hero_id = hero_result.get("cardId")
            if not hero_id:
                raise CliError("[ERROR] Hero creation failed: missing cardId.")
            created_ids.append(hero_id)
            update_card(
                hero_id, deckId=hero_deck_id, masterTags=["hero", "feature"], **common_update
            )

            def _make_sub(lane, deck_id, lane_tags, checklist_lines):
                sub_title = f"[{lane}] {spec.title}"
                sub_body = (
                    "Scope:\n"
                    f"- {lane} lane execution for feature goal\n\n"
                    "Checklist:\n"
                    + "\n".join(f"- [] {line}" for line in checklist_lines)
                    + "\n\nTags: "
                    + " ".join(f"#{t}" for t in lane_tags)
                )
                res = create_card(sub_title, sub_body)
                sub_id = res.get("cardId")
                if not sub_id:
                    raise CliError(f"[ERROR] {lane} sub-card creation failed: missing cardId.")
                created_ids.append(sub_id)
                update_card(
                    sub_id,
                    parentCardId=hero_id,
                    deckId=deck_id,
                    masterTags=lane_tags,
                    **common_update,
                )
                created.append(FeatureSubcard(lane=lane.lower(), id=sub_id))

            _make_sub(
                "Code",
                code_deck_id,
                ["code", "feature"],
                [
                    "Implement core logic",
                    "Handle edge cases",
                    "Add tests/verification",
                ],
            )
            _make_sub(
                "Design",
                design_deck_id,
                ["design", "feel", "economy", "feature"],
                [
                    "Define target player feel",
                    "Tune balance/economy parameters",
                    "Run playtest and iterate",
                ],
            )
            if not spec.skip_art and art_deck_id:
                _make_sub(
                    "Art",
                    art_deck_id,
                    ["art", "feature"],
                    [
                        "Create required assets/content",
                        "Integrate assets in game flow",
                        "Visual quality pass",
                    ],
                )
        except SetupError as err:
            rolled_back, rollback_failed = _rollback_created_ids()
            detail = (
                f"{err}\n[ERROR] Rollback archived "
                f"{len(rolled_back)}/{len(created_ids)} created cards."
            )
            if rollback_failed:
                detail += f"\n[ERROR] Rollback failed for: {', '.join(rollback_failed)}"
            raise SetupError(detail) from err
        except Exception as err:
            rolled_back, rollback_failed = _rollback_created_ids()
            detail = (
                f"[ERROR] Feature scaffold failed: {err}\n"
                f"[ERROR] Rollback archived {len(rolled_back)}/{len(created_ids)} "
                "created cards."
            )
            if rollback_failed:
                detail += f"\n[ERROR] Rollback failed for: {', '.join(rollback_failed)}"
            raise CliError(detail) from err

        notes = []
        if spec.auto_skip_art:
            notes.append("Art lane auto-skipped (no --art-deck provided).")
        if warnings:
            notes.extend(warnings)
        report = FeatureScaffoldReport(
            hero_id=hero_id,
            hero_title=hero_title,
            subcards=created,
            hero_deck=spec.hero_deck,
            code_deck=spec.code_deck,
            design_deck=spec.design_deck,
            art_deck=None if spec.skip_art else spec.art_deck,
            notes=notes or None,
        )
        return report.to_dict()  # type: ignore[no-any-return]

    def split_features(
        self,
        *,
        deck: str,
        code_deck: str,
        design_deck: str,
        art_deck: str | None = None,
        skip_art: bool = False,
        priority: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Batch-split feature cards into discipline sub-cards.

        Finds unsplit cards in *deck*, analyzes their checklist content,
        and creates Code/Design/(optional Art) sub-cards in lane decks.
        Transaction-safe: archives created cards on partial failure.

        Args:
            deck: Source deck containing feature cards.
            code_deck: Destination deck for Code sub-cards.
            design_deck: Destination deck for Design sub-cards.
            art_deck: Destination deck for Art sub-cards (required unless skip_art).
            skip_art: Skip creating art lane sub-cards.
            priority: Override priority for sub-cards (a, b, c, or 'null').
            dry_run: Preview analysis without creating cards.

        Returns:
            SplitFeaturesReport as dict with ok=True.
        """
        spec = SplitFeaturesSpec.from_kwargs(
            deck=deck,
            code_deck=code_deck,
            design_deck=design_deck,
            art_deck=art_deck,
            skip_art=skip_art,
            priority=priority,
            dry_run=dry_run,
        )

        # Resolve deck IDs upfront (fail fast)
        source_deck_id = resolve_deck_id(spec.deck)
        code_deck_id = resolve_deck_id(spec.code_deck)
        design_deck_id = resolve_deck_id(spec.design_deck)
        art_deck_id = resolve_deck_id(spec.art_deck) if spec.art_deck else None
        # Suppress unused variable warning — art_deck_id is used in the loop below
        _ = source_deck_id

        # List cards in source deck (lightweight — no content fetched)
        result = self.list_cards(deck=spec.deck)
        all_cards = result.get("cards", [])

        details: list[SplitFeatureDetail] = []
        skipped: list[dict[str, Any]] = []
        notes: list[str] = []
        created_ids: list[str] = []

        def _rollback():
            rolled_back = []
            rollback_failed = []
            for cid in reversed(created_ids):
                try:
                    archive_card(cid)
                    rolled_back.append(cid)
                except Exception:
                    rollback_failed.append(cid)
            return rolled_back, rollback_failed

        for card in all_cards:
            cid = card.get("id", "")
            title = card.get("title", "")
            sub_count = card.get("sub_card_count") or 0

            # Skip cards that already have sub-cards
            if sub_count > 0:
                skipped.append({"id": cid, "title": title, "reason": "already has sub-cards"})
                continue

            # Fetch full content for analysis
            detail = self.get_card(cid, include_conversations=False)
            content = detail.get("content") or ""

            include_art = not spec.skip_art
            lanes = _analyze_feature_for_lanes(content, include_art=include_art)

            # Determine priority: override > parent's priority
            pri = None
            if spec.priority is not None:
                pri = None if spec.priority == "null" else spec.priority
            else:
                parent_pri = detail.get("priority")
                if parent_pri:
                    pri = parent_pri

            lane_config = [
                ("code", code_deck_id, ["code", "feature"]),
                ("design", design_deck_id, ["design", "feel", "economy", "feature"]),
            ]
            if not spec.skip_art and art_deck_id:
                lane_config.append(("art", art_deck_id, ["art", "feature"]))

            if spec.dry_run:
                subs = []
                for lane_name, _deck_id, _tags in lane_config:
                    checklist = lanes.get(lane_name, [])
                    sub_title = f"[{lane_name.capitalize()}] {title}"
                    subs.append(FeatureSubcard(lane=lane_name, id="(dry-run)", title=sub_title))
                    notes_items = [f"  {lane_name}: {len(checklist)} items"]
                    if notes_items:
                        notes.extend(notes_items)
                details.append(
                    SplitFeatureDetail(
                        feature_id=cid,
                        feature_title=title,
                        subcards=subs,
                    )
                )
                continue

            # Live mode: create sub-cards
            try:
                feature_subs: list[FeatureSubcard] = []
                for lane_name, lane_deck_id, lane_tags in lane_config:
                    checklist = lanes.get(lane_name, [])
                    sub_title = f"[{lane_name.capitalize()}] {title}"
                    sub_body = (
                        "Scope:\n"
                        f"- {lane_name.capitalize()} lane execution for feature goal\n\n"
                        "Checklist:\n"
                        + "\n".join(f"- [] {item}" for item in checklist)
                        + "\n\nTags: "
                        + " ".join(f"#{t}" for t in lane_tags)
                    )
                    res = create_card(sub_title, sub_body)
                    sub_id = res.get("cardId")
                    if not sub_id:
                        raise CliError(
                            f"[ERROR] {lane_name} sub-card creation failed: missing cardId."
                        )
                    created_ids.append(sub_id)

                    update_kwargs: dict[str, Any] = {
                        "parentCardId": cid,
                        "deckId": lane_deck_id,
                        "masterTags": lane_tags,
                    }
                    if pri is not None:
                        update_kwargs["priority"] = pri
                    update_card(sub_id, **update_kwargs)

                    feature_subs.append(FeatureSubcard(lane=lane_name, id=sub_id, title=sub_title))

                details.append(
                    SplitFeatureDetail(
                        feature_id=cid,
                        feature_title=title,
                        subcards=feature_subs,
                    )
                )
            except SetupError as err:
                rolled_back, rollback_failed = _rollback()
                detail_msg = (
                    f"{err}\n[ERROR] Rollback archived "
                    f"{len(rolled_back)}/{len(created_ids)} created cards."
                )
                if rollback_failed:
                    detail_msg += f"\n[ERROR] Rollback failed for: {', '.join(rollback_failed)}"
                raise SetupError(detail_msg) from err
            except Exception as err:
                rolled_back, rollback_failed = _rollback()
                detail_msg = (
                    f"[ERROR] Split-features failed: {err}\n"
                    f"[ERROR] Rollback archived {len(rolled_back)}/{len(created_ids)} "
                    "created cards."
                )
                if rollback_failed:
                    detail_msg += f"\n[ERROR] Rollback failed for: {', '.join(rollback_failed)}"
                raise CliError(detail_msg) from err

        total_subs = sum(len(d.subcards) for d in details)
        if spec.skip_art:
            notes.append("Art lane skipped.")

        report = SplitFeaturesReport(
            features_processed=len(details),
            features_skipped=len(skipped),
            subcards_created=total_subs if not spec.dry_run else 0,
            details=details,
            skipped=skipped,
            notes=notes or None,
        )
        return report.to_dict()  # type: ignore[no-any-return]

    # -------------------------------------------------------------------
    # Comment commands
    # -------------------------------------------------------------------

    def create_comment(self, card_id: str, message: str) -> dict[str, Any]:
        """Start a new comment thread on a card.

        Args:
            card_id: Card UUID.
            message: Comment text.

        Returns:
            dict with ok=True.
        """
        if not message:
            raise CliError("[ERROR] Comment message is required.")
        create_comment(card_id, message)
        return {"ok": True, "card_id": card_id}

    def reply_comment(self, thread_id: str, message: str) -> dict[str, Any]:
        """Reply to an existing comment thread.

        Args:
            thread_id: Thread/resolvable UUID.
            message: Reply text.

        Returns:
            dict with ok=True.
        """
        if not message:
            raise CliError("[ERROR] Reply message is required.")
        reply_comment(thread_id, message)
        return {"ok": True, "thread_id": thread_id}

    def close_comment(self, thread_id: str, card_id: str) -> dict[str, Any]:
        """Close a comment thread.

        Args:
            thread_id: Thread/resolvable UUID.
            card_id: Card UUID.

        Returns:
            dict with ok=True.
        """
        close_comment(thread_id, card_id)
        return {"ok": True, "thread_id": thread_id}

    def reopen_comment(self, thread_id: str, card_id: str) -> dict[str, Any]:
        """Reopen a closed comment thread.

        Args:
            thread_id: Thread/resolvable UUID.
            card_id: Card UUID.

        Returns:
            dict with ok=True.
        """
        reopen_comment(thread_id, card_id)
        return {"ok": True, "thread_id": thread_id}

    def list_conversations(self, card_id: str) -> dict[str, Any]:
        """List all comment threads on a card.

        Args:
            card_id: Card UUID.

        Returns:
            dict with 'resolvable' (threads with isClosed, creator,
            entries), 'resolvableEntry' (messages with author, content,
            createdAt), and 'user' (referenced users).
        """
        return get_conversations(card_id)  # type: ignore[no-any-return]

    # -------------------------------------------------------------------
    # Raw API commands
    # -------------------------------------------------------------------

    def raw_query(self, query_json: dict | str) -> dict[str, Any]:
        """Execute a raw query against the Codecks API.

        Args:
            query_json: Query as a dict or JSON string.

        Returns:
            Raw API response.
        """
        if isinstance(query_json, str):
            from codecks_cli.models import ObjectPayload

            q = ObjectPayload.from_value(_safe_json_parse(query_json, "query"), "query").data
        else:
            q = query_json
        if config.RUNTIME_STRICT:
            root = q.get("_root")
            if not isinstance(root, list) or not root:
                raise CliError(
                    "[ERROR] Strict mode: query payload must include non-empty '_root' array."
                )
        return query(q)  # type: ignore[no-any-return]

    def raw_dispatch(self, path: str, data: dict | str) -> dict[str, Any]:
        """Execute a raw dispatch call against the Codecks API.

        Args:
            path: Dispatch path (e.g. 'cards/update').
            data: Payload as a dict or JSON string.

        Returns:
            Raw API response.
        """
        normalized = _normalize_dispatch_path(path)
        if isinstance(data, str):
            from codecks_cli.models import ObjectPayload

            payload = ObjectPayload.from_value(
                _safe_json_parse(data, "dispatch data"), "dispatch data"
            ).data
        else:
            payload = data
        if config.RUNTIME_STRICT:
            if "/" not in normalized:
                raise CliError(
                    "[ERROR] Strict mode: dispatch path should include action "
                    "segment, e.g. cards/update."
                )
            if not payload:
                raise CliError("[ERROR] Strict mode: dispatch payload cannot be empty.")
        return dispatch(normalized, payload)  # type: ignore[no-any-return]
