"""Read tools: queries and dashboards (10 tools)."""

from __future__ import annotations

from typing import Literal

from codecks_cli import CliError
from codecks_cli.mcp_server._core import (
    _call,
    _contract_error,
    _finalize_tool_result,
    _slim_card,
    _validate_uuid,
)
from codecks_cli.mcp_server._security import _sanitize_activity, _sanitize_card


def get_account() -> dict:
    """Get current account info (name, id, email, role).

    Returns:
        Dict with name, id, email, organizationId, role.
    """
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
) -> dict:
    """List cards. Filters combine with AND.

    Args:
        status: Comma-separated. Values: not_started, started, done, blocked, in_review.
        priority: Comma-separated. Values: a, b, c, null.
        owner: Owner name, or 'none' for unassigned.
        stale_days: Cards not updated in N days.
        updated_after/updated_before: YYYY-MM-DD date strings.
        limit/offset: Pagination (default 50/0).

    Returns:
        Dict with cards (list), stats, total_count, has_more, limit, offset.
    """
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
    )
    if isinstance(result, dict) and result.get("ok") is False:
        return _finalize_tool_result(result)
    # Apply client-side pagination.
    if isinstance(result, dict) and "cards" in result:
        all_cards = result["cards"]
        total = len(all_cards)
        page = all_cards[offset : offset + limit]
        payload = {
            "cards": [_sanitize_card(_slim_card(c)) for c in page],
            "stats": result.get("stats"),
            "total_count": total,
            "has_more": offset + limit < total,
            "limit": limit,
            "offset": offset,
        }
        return _finalize_tool_result(payload)
    return _finalize_tool_result(result)


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
) -> dict:
    """PM focus dashboard: blocked, stale, unassigned, and suggested next cards.

    Args:
        project: Filter to a specific project name.
        owner: Filter to a specific owner name.
        limit: Max cards per category (default 5).
        stale_days: Days since last update to consider stale (default 14).

    Returns:
        Dict with counts, blocked, stale, in_review, hand, and suggested lists.
    """
    result = _call("pm_focus", project=project, owner=owner, limit=limit, stale_days=stale_days)
    if isinstance(result, dict) and "counts" in result:
        result = dict(result)
        for key in ("blocked", "in_review", "hand", "stale", "suggested"):
            if key in result and isinstance(result[key], list):
                result[key] = [
                    _sanitize_card(_slim_card(r)) if isinstance(r, dict) else r for r in result[key]
                ]
    return _finalize_tool_result(result)


def standup(days: int = 2, project: str | None = None, owner: str | None = None) -> dict:
    """Daily standup summary: recently done, in-progress, blocked, and hand.

    Args:
        days: Lookback window for recently done cards (default 2).
        project: Filter to a specific project name.
        owner: Filter to a specific owner name.

    Returns:
        Dict with recently_done, in_progress, blocked, and hand lists.
    """
    result = _call("standup", days=days, project=project, owner=owner)
    if isinstance(result, dict) and result.get("ok") is not False:
        result = dict(result)
        for key in ("recently_done", "in_progress", "blocked", "hand"):
            if key in result and isinstance(result[key], list):
                result[key] = [
                    _sanitize_card(_slim_card(r)) if isinstance(r, dict) else r for r in result[key]
                ]
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
