"""Read tools: queries and dashboards (10 tools). Cache-aware."""

from datetime import UTC
from typing import Literal

from codecks_cli import CliError
from codecks_cli.mcp_server import _core
from codecks_cli.mcp_server._core import (
    _call,
    _card_summary,
    _contract_error,
    _finalize_tool_result,
    _slim_card,
    _slim_deck,
    _validate_uuid,
)
from codecks_cli.mcp_server._security import _sanitize_activity, _sanitize_card


def _try_cache(key: str) -> dict | list | None:  # type: ignore[type-arg]
    """Return cached data for *key* if cache is valid, else None."""
    _core._load_cache_from_disk()
    if not _core._is_cache_valid():
        return None
    snapshot = _core._get_snapshot()
    if snapshot is None or key not in snapshot:
        return None
    value = snapshot[key]
    if isinstance(value, (dict, list)):
        return value
    return None


def get_account() -> dict:
    """Get current account info (name, id, email, role).

    Returns:
        Dict with name, id, email, organizationId, role.
    """
    cached = _try_cache("account")
    if cached is not None and isinstance(cached, dict):
        result = dict(cached)
        result.update(_core._get_cache_metadata())
        return _finalize_tool_result(result)
    return _finalize_tool_result(_call("get_account"))


def list_cards(
    deck: str | None = None,
    status: str | None = None,
    project: str | None = None,
    search: str | None = None,
    milestone: str | None = None,
    tag: str | None = None,
    owner: str | None = None,
    priority: str | None = None,
    sort: Literal["status", "priority", "effort", "deck", "title", "owner", "updated", "created"]
    | None = None,
    card_type: Literal["hero", "doc"] | None = None,
    hero: str | None = None,
    hand_only: bool = False,
    stale_days: int | None = None,
    updated_after: str | None = None,
    updated_before: str | None = None,
    archived: bool = False,
    include_stats: bool = False,
    limit: int = 50,
    offset: int = 0,
    effort_min: int | None = None,
    effort_max: int | None = None,
    has_effort: bool | None = None,
) -> dict:
    """List cards. Filters combine with AND.

    Args:
        status: Comma-separated. Values: not_started, started, done, blocked, in_review.
        priority: Comma-separated. Values: a, b, c, null.
        owner: Owner name, or 'none' for unassigned.
        stale_days: Cards not updated in N days.
        updated_after/updated_before: YYYY-MM-DD date strings.
        effort_min/effort_max: Filter by effort range (inclusive).
        has_effort: True for estimated cards only, False for unestimated only.
        limit/offset: Pagination (default 50/0).

    Returns:
        Dict with cards (list), stats, total_count, has_more, limit, offset.
    """
    # Try serving from cache for non-archived, unfiltered queries
    if not archived:
        cached = _try_cache("cards_result")
        if cached is not None and isinstance(cached, dict) and "cards" in cached:
            all_cards = cached["cards"]
            # Apply client-side filtering to cached cards
            filtered = _filter_cached_cards(
                all_cards,
                deck=deck,
                status=status,
                project=project,
                search=search,
                milestone=milestone,
                tag=tag,
                owner=owner,
                priority=priority,
                card_type=card_type,
                hero=hero,
                hand_only=hand_only,
                stale_days=stale_days,
                updated_after=updated_after,
                updated_before=updated_before,
                effort_min=effort_min,
                effort_max=effort_max,
                has_effort=has_effort,
            )
            if sort:
                filtered = _sort_cards(filtered, sort)
            total = len(filtered)
            page = filtered[offset : offset + limit]
            payload: dict = {
                "cards": [_sanitize_card(_core._slim_card_list(c)) for c in page],
                "total_count": total,
                "has_more": offset + limit < total,
                "limit": limit,
                "offset": offset,
            }
            if include_stats:
                payload["stats"] = cached.get("stats")
            payload.update(_core._get_cache_metadata())
            return _finalize_tool_result(payload)

    # Cache miss — original API path
    # Only fetch content when searching (needed for text match); otherwise skip
    # to save ~40-60% of payload size.
    result = _call(
        "list_cards",
        deck=deck,
        status=status,
        project=project,
        search=search,
        milestone=milestone,
        tag=tag,
        owner=owner,
        priority=priority,
        sort=sort,
        card_type=card_type,
        hero=hero,
        hand_only=hand_only,
        stale_days=stale_days,
        updated_after=updated_after,
        updated_before=updated_before,
        archived=archived,
        include_stats=include_stats,
        include_content=bool(search),
    )
    if isinstance(result, dict) and result.get("ok") is False:
        return _finalize_tool_result(result)
    # Apply client-side pagination.
    if isinstance(result, dict) and "cards" in result:
        all_cards = result["cards"]
        total = len(all_cards)
        page = all_cards[offset : offset + limit]
        payload = {
            "cards": [_sanitize_card(_core._slim_card_list(c)) for c in page],
            "total_count": total,
            "has_more": offset + limit < total,
            "limit": limit,
            "offset": offset,
        }
        if include_stats:
            payload["stats"] = result.get("stats")
        return _finalize_tool_result(payload)
    return _finalize_tool_result(result)


def _filter_cached_cards(
    cards: list[dict],
    *,
    deck: str | None = None,
    status: str | None = None,
    project: str | None = None,
    search: str | None = None,
    milestone: str | None = None,
    tag: str | None = None,
    owner: str | None = None,
    priority: str | None = None,
    card_type: str | None = None,
    hero: str | None = None,
    hand_only: bool = False,
    stale_days: int | None = None,
    updated_after: str | None = None,
    updated_before: str | None = None,
    effort_min: int | None = None,
    effort_max: int | None = None,
    has_effort: bool | None = None,
) -> list[dict]:
    """Apply filters to cached card list. Mirrors CodecksClient.list_cards() filtering."""
    result = list(cards)

    if deck:
        deck_lower = deck.lower()
        result = [c for c in result if str(c.get("deck", "")).lower() == deck_lower]

    if status:
        statuses = {s.strip() for s in status.split(",")}
        result = [c for c in result if c.get("status") in statuses]

    if project:
        project_lower = project.lower()
        result = [c for c in result if str(c.get("project", "")).lower() == project_lower]

    if search:
        search_lower = search.lower()
        result = [
            c
            for c in result
            if search_lower in str(c.get("title", "")).lower()
            or search_lower in str(c.get("content", "")).lower()
        ]

    if milestone:
        milestone_lower = milestone.lower()
        result = [c for c in result if str(c.get("milestone", "")).lower() == milestone_lower]

    if tag:
        tag_lower = tag.lower()
        result = [
            c
            for c in result
            if tag_lower in [str(t).lower() for t in (c.get("tags") or c.get("tag_list") or [])]
        ]

    if owner:
        if owner.lower() == "none":
            result = [c for c in result if not c.get("owner")]
        else:
            owner_lower = owner.lower()
            result = [c for c in result if str(c.get("owner", "")).lower() == owner_lower]

    if priority:
        priorities = {p.strip() for p in priority.split(",")}
        result = [c for c in result if c.get("priority") in priorities]

    if card_type == "hero":
        result = [c for c in result if c.get("child_cards") or c.get("childCards")]
    elif card_type == "doc":
        result = [c for c in result if c.get("is_doc") or c.get("cardType") == "doc"]

    if hand_only:
        snapshot = _core._get_snapshot()
        if snapshot and "hand" in snapshot:
            hand_ids = {c.get("id") for c in snapshot["hand"] if isinstance(c, dict)}
            result = [c for c in result if c.get("id") in hand_ids]

    if stale_days is not None:
        from datetime import datetime, timedelta

        cutoff = datetime.now(UTC) - timedelta(days=stale_days)
        cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%S")
        result = [
            c for c in result if (c.get("updated_at") or c.get("updatedAt") or "") < cutoff_str
        ]

    if updated_after:
        result = [
            c for c in result if (c.get("updated_at") or c.get("updatedAt") or "") >= updated_after
        ]

    if updated_before:
        result = [
            c for c in result if (c.get("updated_at") or c.get("updatedAt") or "") <= updated_before
        ]

    # hero filter: not easily applicable in cache without additional data
    # Fall through to API for hero filter — but we still apply other filters above

    if effort_min is not None:
        result = [c for c in result if (c.get("effort") or 0) >= effort_min]

    if effort_max is not None:
        result = [c for c in result if (c.get("effort") or 0) <= effort_max]

    if has_effort is True:
        result = [c for c in result if c.get("effort") is not None]
    elif has_effort is False:
        result = [c for c in result if c.get("effort") is None]

    return result


def _sort_cards(cards: list[dict], sort: str) -> list[dict]:
    """Sort cards by field name. Mirrors CodecksClient sorting."""
    key_map = {
        "title": lambda c: str(c.get("title", "")).lower(),
        "status": lambda c: str(c.get("status", "")),
        "priority": lambda c: str(c.get("priority", "z")),
        "effort": lambda c: c.get("effort") or 999,
        "deck": lambda c: str(c.get("deck", "")).lower(),
        "owner": lambda c: str(c.get("owner", "")).lower(),
        "updated": lambda c: str(c.get("updated_at") or c.get("updatedAt") or ""),
        "created": lambda c: str(c.get("created_at") or c.get("createdAt") or ""),
    }
    key_fn = key_map.get(sort)
    if key_fn:
        return sorted(cards, key=key_fn)
    return cards


def _append_hand_suggestions(result: dict) -> dict:
    """Add hand_suggestions to pm_focus result based on workflow preferences."""
    import json
    import os

    from codecks_cli.config import _PROJECT_ROOT

    prefs_path = os.path.join(_PROJECT_ROOT, ".pm_preferences.json")
    prefs: dict = {}
    try:
        with open(prefs_path, encoding="utf-8") as f:
            prefs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass

    lane_pref = prefs.get("hand_lane_preference", "code")
    exclude_heroes = prefs.get("hand_exclude_heroes", True)
    max_size = prefs.get("hand_max_size", 10)

    # Get all cards from cache
    cached_cards = _try_cache("cards_result")
    if not isinstance(cached_cards, dict) or "cards" not in cached_cards:
        return result

    all_cards = cached_cards["cards"]

    # Get current hand IDs
    hand_cached = _try_cache("hand")
    hand_ids = set()
    if isinstance(hand_cached, list):
        hand_ids = {c.get("id") for c in hand_cached if isinstance(c, dict)}

    # Find cards matching lane preference not in hand
    lane_tag = f"[{lane_pref.title()}]"
    candidates = [
        c
        for c in all_cards
        if isinstance(c, dict)
        and c.get("status") not in ("done",)
        and not c.get("archived")
        and lane_tag in str(c.get("title", ""))
        and c.get("id") not in hand_ids
    ]

    if exclude_heroes:
        candidates = [c for c in candidates if not c.get("child_cards") and not c.get("childCards")]

    # Sort by priority (a > b > c > null)
    priority_order = {"a": 0, "b": 1, "c": 2}
    candidates.sort(key=lambda c: priority_order.get(c.get("priority", ""), 3))

    suggestions = candidates[:5]

    result["hand_suggestions"] = {
        "lane_preference": lane_pref,
        "exclude_heroes": exclude_heroes,
        "max_hand_size": max_size,
        "current_hand_size": len(hand_ids),
        "cards": [
            {
                "id": c.get("id"),
                "title": c.get("title"),
                "priority": c.get("priority"),
                "status": c.get("status"),
            }
            for c in suggestions
        ],
    }
    return result


def get_card(
    card_id: str,
    include_content: bool = True,
    include_conversations: bool = True,
    archived: bool = False,
) -> dict:
    """Get full card details (content, checklist, sub-cards, conversations, hand status).

    Args:
        include_content: False to strip body (keeps title) for metadata-only checks.
        include_conversations: False to skip comment thread resolution.
        archived: True to look up archived cards.

    Returns:
        Card dict with id, title, status, content, sub_cards, conversations, etc.
    """
    try:
        _validate_uuid(card_id)
    except CliError as e:
        return _finalize_tool_result(_contract_error(str(e), "error"))

    # Try cache when conversations not needed and not archived (O(1) indexed lookup)
    if not archived and not include_conversations:
        repo = _core.get_repository()
        card = repo.get(card_id)
        if card is not None:
            if include_content:
                # Return full card from cache (no slimming — preserve body text)
                detail = dict(card)
            else:
                # Slim the card for metadata-only checks
                detail = _slim_card(dict(card))
                detail.pop("content", None)
            detail.update(_core._get_cache_metadata())
            return _finalize_tool_result(_sanitize_card(detail))

    result = _call(
        "get_card",
        card_id=card_id,
        include_content=include_content,
        include_conversations=include_conversations,
        archived=archived,
    )
    if isinstance(result, dict) and result.get("ok") is not False:
        return _finalize_tool_result(_sanitize_card(result))
    return _finalize_tool_result(result)


def list_decks(include_card_counts: bool = False) -> dict:
    """List all decks. Set include_card_counts=True for per-deck counts (extra API call)."""
    cached = _try_cache("decks")
    if cached is not None and isinstance(cached, list):
        result = {"decks": [_slim_deck(d) for d in cached]}
        result.update(_core._get_cache_metadata())
        return _finalize_tool_result(result)
    return _finalize_tool_result(_call("list_decks", include_card_counts=include_card_counts))


def list_projects() -> dict:
    """List all projects with deck info."""
    return _finalize_tool_result(_call("list_projects"))


def list_milestones() -> dict:
    """List all milestones with card counts."""
    return _finalize_tool_result(_call("list_milestones"))


def list_tags() -> dict:
    """List project-level tags (sanctioned taxonomy).

    Falls back to the local tag registry if the API is unavailable.
    Note: tag *creation* is not supported via the API — use the Codecks web UI
    to add new project-level tags, then they will appear here.
    """
    result = _call("list_tags")
    if isinstance(result, dict) and result.get("ok") is False:
        # API failed — fall back to local tag registry
        from codecks_cli.tags import TAGS

        tag_dicts = [
            {
                "name": t.name,
                "display_name": t.display_name,
                "category": t.category,
                "description": t.description,
            }
            for t in TAGS
        ]
        return _finalize_tool_result(
            {
                "tags": tag_dicts,
                "count": len(tag_dicts),
                "source": "local_registry",
                "warning": "API unavailable — showing local tag definitions (may not include recently added tags)",
            }
        )
    return _finalize_tool_result(result)


def list_activity(limit: int = 20) -> dict:
    """Show recent activity feed."""
    result = _call("list_activity", limit=limit)
    if isinstance(result, dict) and result.get("ok") is not False:
        return _finalize_tool_result(_sanitize_activity(result))
    return _finalize_tool_result(result)


def pm_focus(
    project: str | None = None,
    owner: str | None = None,
    limit: int = 5,
    stale_days: int = 14,
    summary_only: bool = False,
) -> dict:
    """PM focus dashboard: blocked, stale, unassigned, and suggested next cards.

    Args:
        project: Filter to a specific project name.
        owner: Filter to a specific owner name.
        limit: Max cards per category (default 5).
        stale_days: Days since last update to consider stale (default 14).
        summary_only: If True, return only counts + deck_health (no card arrays).
            Reduces response from ~65KB to ~2KB. Use for "how's the project?" checks.

    Returns:
        Dict with counts, blocked, stale, in_review, hand, and suggested lists.
        With summary_only=True: counts + deck_health only.
    """
    # Serve from cache when no project/owner filter
    if project is None and owner is None:
        cached = _try_cache("pm_focus")
        if cached is not None and isinstance(cached, dict) and "counts" in cached:
            result = dict(cached)
            if summary_only:
                result = {
                    "counts": result.get("counts", {}),
                    "deck_health": result.get("deck_health", {}),
                    "filters": result.get("filters", {}),
                    "summary_only": True,
                }
                result.update(_core._get_cache_metadata())
                return _finalize_tool_result(result)
            # Re-slice to requested limit, use _card_summary for compact output
            for key in ("blocked", "in_review", "hand", "stale", "suggested"):
                if key in result and isinstance(result[key], list):
                    result[key] = [
                        _sanitize_card(_card_summary(r)) if isinstance(r, dict) else r
                        for r in result[key][:limit]
                    ]
            result.update(_core._get_cache_metadata())
            result = _append_hand_suggestions(result)
            return _finalize_tool_result(result)

    result = _call("pm_focus", project=project, owner=owner, limit=limit, stale_days=stale_days)
    if isinstance(result, dict) and "counts" in result:
        result = dict(result)
        if summary_only:
            result = {
                "counts": result.get("counts", {}),
                "deck_health": result.get("deck_health", {}),
                "filters": result.get("filters", {}),
                "summary_only": True,
            }
            return _finalize_tool_result(result)
        for key in ("blocked", "in_review", "hand", "stale", "suggested"):
            if key in result and isinstance(result[key], list):
                result[key] = [
                    _sanitize_card(_card_summary(r)) if isinstance(r, dict) else r
                    for r in result[key]
                ]

    # Append hand suggestions based on workflow preferences
    if isinstance(result, dict):
        result = _append_hand_suggestions(result)

    return _finalize_tool_result(result)


def standup(
    days: int = 2,
    project: str | None = None,
    owner: str | None = None,
    summary_only: bool = False,
) -> dict:
    """Daily standup summary: recently done, in-progress, blocked, and hand.

    Args:
        days: Lookback window for recently done cards (default 2).
        project: Filter to a specific project name.
        owner: Filter to a specific owner name.
        summary_only: If True, return only counts (no card arrays).
            Reduces response size significantly.

    Returns:
        Dict with recently_done, in_progress, blocked, and hand lists.
        With summary_only=True: counts only.
    """
    # Serve from cache when no project/owner filter
    if project is None and owner is None:
        cached = _try_cache("standup")
        if cached is not None and isinstance(cached, dict):
            result = dict(cached)
            if summary_only:
                result = {
                    "counts": {
                        key: len(result.get(key, []))
                        for key in ("recently_done", "in_progress", "blocked", "hand")
                    },
                    "filters": result.get("filters", {}),
                    "summary_only": True,
                }
                result.update(_core._get_cache_metadata())
                return _finalize_tool_result(result)
            for key in ("recently_done", "in_progress", "blocked", "hand"):
                if key in result and isinstance(result[key], list):
                    result[key] = [
                        _sanitize_card(_card_summary(r)) if isinstance(r, dict) else r
                        for r in result[key]
                    ]
            result.update(_core._get_cache_metadata())
            return _finalize_tool_result(result)

    result = _call("standup", days=days, project=project, owner=owner)
    if isinstance(result, dict) and result.get("ok") is not False:
        result = dict(result)
        if summary_only:
            result = {
                "counts": {
                    key: len(result.get(key, []))
                    for key in ("recently_done", "in_progress", "blocked", "hand")
                },
                "filters": result.get("filters", {}),
                "summary_only": True,
            }
            return _finalize_tool_result(result)
        for key in ("recently_done", "in_progress", "blocked", "hand"):
            if key in result and isinstance(result[key], list):
                result[key] = [
                    _sanitize_card(_card_summary(r)) if isinstance(r, dict) else r
                    for r in result[key]
                ]
    return _finalize_tool_result(result)


def quick_overview(project: str | None = None) -> dict:
    """Compact project overview with aggregate counts only. No card details — minimal tokens.

    Use for "how's the project?" checks. For card-level dashboards, use pm_focus() or standup().

    Args:
        project: Optional project name filter.

    Returns:
        Dict with total_cards, by_status, by_priority, effort_stats,
        hand_size, stale_count, deck_summary.
    """
    cached = _try_cache("cards_result")
    if cached is not None and isinstance(cached, dict) and "cards" in cached:
        cards = cached["cards"]
    else:
        api_result = _call("list_cards")
        if isinstance(api_result, dict) and api_result.get("ok") is False:
            return _finalize_tool_result(api_result)
        cards = api_result.get("cards", []) if isinstance(api_result, dict) else []

    if project:
        project_lower = project.lower()
        cards = [c for c in cards if str(c.get("project", "")).lower() == project_lower]

    # Aggregate counts
    by_status: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    deck_counts: dict[str, int] = {}
    total_effort = 0
    estimated_count = 0
    stale_count = 0

    from datetime import datetime, timedelta

    cutoff = datetime.now(UTC) - timedelta(days=14)
    cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%S")

    for card in cards:
        if not isinstance(card, dict):
            continue
        s = card.get("status", "unknown")
        by_status[s] = by_status.get(s, 0) + 1

        p = card.get("priority") or "null"
        by_priority[p] = by_priority.get(p, 0) + 1

        d = card.get("deck", "") or card.get("deck_name", "") or "unassigned"
        deck_counts[d] = deck_counts.get(d, 0) + 1

        effort = card.get("effort")
        if effort is not None:
            total_effort += effort
            estimated_count += 1

        updated = card.get("updated_at") or card.get("updatedAt") or ""
        if updated and updated < cutoff_str and s in ("started", "not_started", "blocked"):
            stale_count += 1

    avg_effort = round(total_effort / estimated_count, 1) if estimated_count else 0.0

    hand_cached = _try_cache("hand")
    hand_size = len(hand_cached) if isinstance(hand_cached, list) else 0

    result = {
        "ok": True,
        "total_cards": len(cards),
        "by_status": by_status,
        "by_priority": by_priority,
        "effort_stats": {
            "total": total_effort,
            "avg": avg_effort,
            "estimated": estimated_count,
            "unestimated": len(cards) - estimated_count,
        },
        "hand_size": hand_size,
        "stale_count": stale_count,
        "deck_summary": [{"name": k, "count": v} for k, v in sorted(deck_counts.items())],
    }
    result.update(_core._get_cache_metadata())
    return _finalize_tool_result(result)


def register(mcp):
    """Register all read tools with the FastMCP instance."""
    mcp.tool()(get_account)
    mcp.tool()(list_cards)
    mcp.tool()(get_card)
    mcp.tool()(list_decks)
    mcp.tool()(list_projects)
    mcp.tool()(list_milestones)
    mcp.tool()(list_tags)
    mcp.tool()(list_activity)
    mcp.tool()(pm_focus)
    mcp.tool()(standup)
    mcp.tool()(quick_overview)
