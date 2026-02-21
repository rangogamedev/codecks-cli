"""MCP server exposing CodecksClient methods as tools.

Run: python -m codecks_cli.mcp_server
Requires: pip install codecks-cli[mcp]
"""

from __future__ import annotations

from typing import Literal

from mcp.server.fastmcp import FastMCP

from codecks_cli import CliError, CodecksClient, SetupError

mcp = FastMCP(
    "codecks",
    instructions=(
        "Codecks project management tools. "
        "Use list_cards with filters to find cards, get_card for full details. "
        "All card IDs must be full 36-character UUIDs. "
        "Doc cards cannot have status, priority, or effort. "
        "Rate limit: 40 requests per 5 seconds."
    ),
)

_client: CodecksClient | None = None


def _get_client() -> CodecksClient:
    """Return a cached CodecksClient, creating one on first use."""
    global _client
    if _client is None:
        _client = CodecksClient()
    return _client


def _call(method_name: str, **kwargs):
    """Call a CodecksClient method, converting exceptions to error dicts."""
    try:
        client = _get_client()
        return getattr(client, method_name)(**kwargs)
    except SetupError as e:
        return {"ok": False, "error": str(e), "type": "setup"}
    except CliError as e:
        return {"ok": False, "error": str(e), "type": "error"}


# -------------------------------------------------------------------
# Read tools
# -------------------------------------------------------------------


@mcp.tool()
def get_account() -> dict:
    """Get current account info for the authenticated user.

    Use this to verify authentication or look up the current user's ID.

    Returns:
        dict with keys: name, id, email, organizationId, role.
    """
    return _call("get_account")


@mcp.tool()
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
    """List project cards with optional filters and pagination.

    Use this to search, filter, or browse cards. Combine multiple filters
    to narrow results. Returns paginated results (default 50 cards).

    Args:
        deck: Filter by deck name (exact match).
        status: Filter by status. Comma-separated for multiple values
            (e.g. "started,blocked"). Values: not_started, started, done,
            blocked, in_review.
        project: Filter by project name.
        search: Search cards by title/content.
        milestone: Filter by milestone name.
        tag: Filter by tag name (case-insensitive).
        owner: Filter by owner name, or 'none' for unassigned.
        priority: Filter by priority. Comma-separated for multiple values
            (e.g. "a,b"). Values: a, b, c, null.
        sort: Sort field.
        card_type: Filter by card type.
        hero: Show only sub-cards of this hero card UUID.
        hand_only: If True, show only cards in the user's hand.
        stale_days: Find cards not updated in N days.
        updated_after: Cards updated after this date (YYYY-MM-DD).
        updated_before: Cards updated before this date (YYYY-MM-DD).
        archived: If True, show archived cards instead of active ones.
        include_stats: If True, include aggregate stats by status/priority/deck/owner.
        limit: Max cards to return per page (default 50). Use with offset to paginate.
        offset: Number of cards to skip (default 0).

    Returns:
        dict with 'cards' (list), 'stats' (null unless include_stats),
        'total_count', 'has_more', 'limit', 'offset'.
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
    # Apply client-side pagination (error dicts pass through unchanged)
    if isinstance(result, dict) and "cards" in result:
        all_cards = result["cards"]
        total = len(all_cards)
        page = all_cards[offset : offset + limit]
        return {
            "cards": page,
            "stats": result.get("stats"),
            "total_count": total,
            "has_more": offset + limit < total,
            "limit": limit,
            "offset": offset,
        }
    return result


@mcp.tool()
def get_card(card_id: str) -> dict:
    """Get full details for a single card.

    Use this when you need a card's content, checklist, sub-cards,
    conversations, or hand status. Accepts full UUIDs or short ID prefixes.

    Args:
        card_id: The card's 36-character UUID or unique short ID prefix.

    Returns:
        dict with card details including title, content, status, priority,
        effort, owner, tags, milestone, deck, checklist, sub_cards,
        conversations, and in_hand.
    """
    return _call("get_card", card_id=card_id)


@mcp.tool()
def list_decks() -> dict:
    """List all decks with card counts.

    Use this to discover available decks before filtering cards or
    moving cards to a deck.

    Returns:
        list of dicts with id, title, project_name, card_count.
    """
    return _call("list_decks")


@mcp.tool()
def list_projects() -> dict:
    """List all projects.

    Use this to discover project names for filtering cards.

    Returns:
        list of dicts with id, name, deck_count, decks.
    """
    return _call("list_projects")


@mcp.tool()
def list_milestones() -> dict:
    """List all milestones.

    Use this to discover milestone names for filtering or assigning cards.

    Returns:
        list of dicts with id, name, card_count.
    """
    return _call("list_milestones")


@mcp.tool()
def list_activity(limit: int = 20) -> dict:
    """Show recent activity feed for the account.

    Use this to see what changed recently across all cards and users.

    Args:
        limit: Maximum number of activity events to return (default 20).

    Returns:
        dict with activity events, referenced cards, and users.
    """
    return _call("list_activity", limit=limit)


@mcp.tool()
def pm_focus(
    project: str | None = None,
    owner: str | None = None,
    limit: int = 5,
    stale_days: int = 14,
) -> dict:
    """Generate PM focus dashboard showing sprint health.

    Use this for a high-level overview: blocked cards, unassigned work,
    stale items, and suggested next actions.

    Args:
        project: Filter by project name.
        owner: Filter by owner name.
        limit: Number of suggested next cards (default 5).
        stale_days: Days threshold for stale detection (default 14).

    Returns:
        dict with counts, blocked, in_review, hand, stale, suggested.
    """
    return _call("pm_focus", project=project, owner=owner, limit=limit, stale_days=stale_days)


@mcp.tool()
def standup(days: int = 2, project: str | None = None, owner: str | None = None) -> dict:
    """Generate daily standup summary.

    Use this to prepare for standups: see recently completed work,
    in-progress cards, blockers, and hand queue.

    Args:
        days: Lookback period for recent completions (default 2).
        project: Filter by project name.
        owner: Filter by owner name.

    Returns:
        dict with recently_done, in_progress, blocked, hand.
    """
    return _call("standup", days=days, project=project, owner=owner)


# -------------------------------------------------------------------
# Hand tools
# -------------------------------------------------------------------


@mcp.tool()
def list_hand() -> dict:
    """List cards in the user's hand (personal work queue).

    Use this to see the user's prioritized to-do list.

    Returns:
        list of card dicts sorted by hand order.
    """
    return _call("list_hand")


@mcp.tool()
def add_to_hand(card_ids: list[str]) -> dict:
    """Add cards to the user's hand (personal work queue).

    Use this to queue cards for the user to work on next.

    Args:
        card_ids: List of full 36-character card UUIDs to add.

    Returns:
        dict with ok=True and count of added cards.
    """
    return _call("add_to_hand", card_ids=card_ids)


@mcp.tool()
def remove_from_hand(card_ids: list[str]) -> dict:
    """Remove cards from the user's hand (personal work queue).

    Use this when work on a card is done or deprioritized.

    Args:
        card_ids: List of full 36-character card UUIDs to remove.

    Returns:
        dict with ok=True and count of removed cards.
    """
    return _call("remove_from_hand", card_ids=card_ids)


# -------------------------------------------------------------------
# Mutation tools
# -------------------------------------------------------------------


@mcp.tool()
def create_card(
    title: str,
    content: str | None = None,
    deck: str | None = None,
    project: str | None = None,
    severity: Literal["critical", "high", "low", "null"] | None = None,
    doc: bool = False,
    allow_duplicate: bool = False,
) -> dict:
    """Create a new card.

    Use this to add a bug report, task, or doc card. Specify a deck or
    project to place the card; otherwise it goes to the default inbox.

    Args:
        title: Card title (required).
        content: Card body/description (markdown supported).
        deck: Place card in this deck (by name).
        project: Place card in the first deck of this project.
        severity: Bug severity level. Use 'null' to clear.
        doc: If True, create as a doc card (no status/priority/effort).
        allow_duplicate: Bypass duplicate title protection.

    Returns:
        dict with ok=True, card_id, and title.
    """
    return _call(
        "create_card",
        title=title,
        content=content,
        deck=deck,
        project=project,
        severity=severity,
        doc=doc,
        allow_duplicate=allow_duplicate,
    )


@mcp.tool()
def update_cards(
    card_ids: list[str],
    status: Literal["not_started", "started", "done", "blocked", "in_review"] | None = None,
    priority: Literal["a", "b", "c", "null"] | None = None,
    effort: str | None = None,
    deck: str | None = None,
    title: str | None = None,
    content: str | None = None,
    milestone: str | None = None,
    hero: str | None = None,
    owner: str | None = None,
    tags: str | None = None,
    doc: Literal["true", "false"] | None = None,
) -> dict:
    """Update one or more cards' properties.

    Use this to change status, priority, owner, tags, deck, or content.
    Doc cards cannot have status, priority, or effort — only
    owner/tags/milestone/deck/title/content/hero can be set.

    Args:
        card_ids: List of full 36-character UUIDs (short IDs will 400).
        status: New status. Not valid for doc cards.
        priority: New priority. Use 'null' to clear. Not valid for doc cards.
        effort: New effort (integer as string, or 'null' to clear). Not valid for doc cards.
        deck: Move to this deck (by name).
        title: New title (single card only).
        content: New content/body (single card only).
        milestone: Milestone name, or 'none' to clear.
        hero: Parent hero card UUID, or 'none' to detach.
        owner: Owner name, or 'none' to unassign.
        tags: Comma-separated tags, or 'none' to clear all.
        doc: Toggle doc card mode.

    Returns:
        dict with ok=True, updated (count), and fields (list of changed field names).
    """
    return _call(
        "update_cards",
        card_ids=card_ids,
        status=status,
        priority=priority,
        effort=effort,
        deck=deck,
        title=title,
        content=content,
        milestone=milestone,
        hero=hero,
        owner=owner,
        tags=tags,
        doc=doc,
    )


@mcp.tool()
def mark_done(card_ids: list[str]) -> dict:
    """Mark one or more cards as done.

    Use this as a shortcut instead of update_cards with status='done'.

    Args:
        card_ids: List of full 36-character card UUIDs.

    Returns:
        dict with ok=True and count.
    """
    return _call("mark_done", card_ids=card_ids)


@mcp.tool()
def mark_started(card_ids: list[str]) -> dict:
    """Mark one or more cards as started.

    Use this as a shortcut instead of update_cards with status='started'.

    Args:
        card_ids: List of full 36-character card UUIDs.

    Returns:
        dict with ok=True and count.
    """
    return _call("mark_started", card_ids=card_ids)


@mcp.tool()
def archive_card(card_id: str) -> dict:
    """Archive a card (reversible with unarchive_card).

    Use this to hide a card without permanently deleting it.

    Args:
        card_id: Full 36-character card UUID.

    Returns:
        dict with ok=True and card_id.
    """
    return _call("archive_card", card_id=card_id)


@mcp.tool()
def unarchive_card(card_id: str) -> dict:
    """Restore an archived card.

    Use this to bring back a previously archived card.

    Args:
        card_id: Full 36-character card UUID.

    Returns:
        dict with ok=True and card_id.
    """
    return _call("unarchive_card", card_id=card_id)


@mcp.tool()
def delete_card(card_id: str) -> dict:
    """Permanently delete a card. This cannot be undone.

    Use archive_card instead if the deletion should be reversible.

    Args:
        card_id: Full 36-character card UUID.

    Returns:
        dict with ok=True and card_id.
    """
    return _call("delete_card", card_id=card_id)


@mcp.tool()
def scaffold_feature(
    title: str,
    hero_deck: str,
    code_deck: str,
    design_deck: str,
    art_deck: str | None = None,
    skip_art: bool = False,
    description: str | None = None,
    owner: str | None = None,
    priority: Literal["a", "b", "c", "null"] | None = None,
    effort: int | None = None,
    allow_duplicate: bool = False,
) -> dict:
    """Scaffold a Hero feature with lane sub-cards.

    Use this to create a Hero card plus Code, Design, and optionally Art
    sub-cards in one operation. Transaction-safe: archives created cards
    on partial failure.

    Args:
        title: Feature title (required).
        hero_deck: Hero card destination deck name (required).
        code_deck: Code sub-card deck name (required).
        design_deck: Design sub-card deck name (required).
        art_deck: Art sub-card deck name (required unless skip_art=True).
        skip_art: Skip creating the art lane sub-card.
        description: Feature context/goal for the hero card body.
        owner: Owner name for hero and all sub-cards.
        priority: Priority for hero and sub-cards. Use 'null' to clear.
        effort: Effort estimation (integer) for sub-cards.
        allow_duplicate: Bypass duplicate title protection.

    Returns:
        dict with ok=True, hero (card dict), subcards (list), and summary.
    """
    return _call(
        "scaffold_feature",
        title=title,
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


# -------------------------------------------------------------------
# Comment tools
# -------------------------------------------------------------------


@mcp.tool()
def create_comment(card_id: str, message: str) -> dict:
    """Start a new comment thread on a card.

    Use this to leave feedback, ask questions, or document decisions.

    Args:
        card_id: Full 36-character card UUID.
        message: Comment text.

    Returns:
        dict with ok=True.
    """
    return _call("create_comment", card_id=card_id, message=message)


@mcp.tool()
def reply_comment(thread_id: str, message: str) -> dict:
    """Reply to an existing comment thread.

    Use this to continue a conversation in an existing thread.
    Use list_conversations to find thread IDs.

    Args:
        thread_id: Thread/resolvable UUID from list_conversations.
        message: Reply text.

    Returns:
        dict with ok=True and thread_id.
    """
    return _call("reply_comment", thread_id=thread_id, message=message)


@mcp.tool()
def close_comment(thread_id: str, card_id: str) -> dict:
    """Close (resolve) a comment thread.

    Use this to mark a discussion as resolved.

    Args:
        thread_id: Thread/resolvable UUID from list_conversations.
        card_id: Full 36-character card UUID the thread belongs to.

    Returns:
        dict with ok=True and thread_id.
    """
    return _call("close_comment", thread_id=thread_id, card_id=card_id)


@mcp.tool()
def reopen_comment(thread_id: str, card_id: str) -> dict:
    """Reopen a closed comment thread.

    Use this to re-open a previously resolved discussion.

    Args:
        thread_id: Thread/resolvable UUID from list_conversations.
        card_id: Full 36-character card UUID the thread belongs to.

    Returns:
        dict with ok=True and thread_id.
    """
    return _call("reopen_comment", thread_id=thread_id, card_id=card_id)


@mcp.tool()
def list_conversations(card_id: str) -> dict:
    """List all comment threads on a card.

    Use this to read existing discussions and find thread IDs for
    reply_comment, close_comment, or reopen_comment.

    Args:
        card_id: Full 36-character card UUID.

    Returns:
        dict with resolvable threads, messages, and referenced users.
    """
    return _call("list_conversations", card_id=card_id)


# -------------------------------------------------------------------
# Entry point
# -------------------------------------------------------------------


def main():
    """Run the MCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
