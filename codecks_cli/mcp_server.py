"""MCP server exposing CodecksClient methods as tools.

Run: python -m codecks_cli.mcp_server
Requires: pip install codecks-cli[mcp]
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from codecks_cli import CliError, CodecksClient, SetupError

mcp = FastMCP("codecks", instructions="Codecks project management tools")


def _call(method_name: str, **kwargs):
    """Call a CodecksClient method, converting exceptions to error dicts."""
    try:
        client = CodecksClient()
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

    Returns dict with keys: name, id, email, organizationId, role.
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
    sort: str | None = None,
    card_type: str | None = None,
    hero: str | None = None,
    hand_only: bool = False,
    stale_days: int | None = None,
    updated_after: str | None = None,
    updated_before: str | None = None,
    archived: bool = False,
    include_stats: bool = False,
) -> dict:
    """List project cards with optional filters.

    Args:
        deck: Filter by deck name.
        status: Filter by status (comma-separated for multiple).
        project: Filter by project name.
        search: Search cards by title/content.
        milestone: Filter by milestone name.
        tag: Filter by tag name.
        owner: Filter by owner name ('none' for unassigned).
        priority: Filter by priority (comma-separated for multiple).
        sort: Sort field (status, priority, effort, deck, title, owner, updated, created).
        card_type: Filter by card type ('hero' or 'doc').
        hero: Show only sub-cards of this hero card ID.
        hand_only: If True, show only cards in the user's hand.
        stale_days: Find cards not updated in N days.
        updated_after: Cards updated after this date (YYYY-MM-DD).
        updated_before: Cards updated before this date (YYYY-MM-DD).
        archived: If True, show archived cards instead of active ones.
        include_stats: If True, also compute aggregate stats.

    Returns:
        dict with 'cards' list and 'stats' (null unless include_stats=True).
    """
    return _call(
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


@mcp.tool()
def get_card(card_id: str) -> dict:
    """Get full details for a single card.

    Args:
        card_id: The card's UUID or short ID prefix.

    Returns:
        dict with card details including checklist, sub_cards, conversations,
        and hand status.
    """
    return _call("get_card", card_id=card_id)


@mcp.tool()
def list_decks() -> dict:
    """List all decks with card counts.

    Returns:
        list of deck dicts with id, title, project_name, card_count.
    """
    return _call("list_decks")


@mcp.tool()
def list_projects() -> dict:
    """List all projects.

    Returns:
        list of project dicts with id, name, deck_count, decks.
    """
    return _call("list_projects")


@mcp.tool()
def list_milestones() -> dict:
    """List all milestones.

    Returns:
        list of milestone dicts with id, name, card_count.
    """
    return _call("list_milestones")


@mcp.tool()
def list_activity(limit: int = 20) -> dict:
    """Show recent activity feed for the account.

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
    """Generate PM focus dashboard data.

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

    Args:
        days: Lookback for recent completions (default 2).
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

    Returns:
        list of card dicts sorted by hand order.
    """
    return _call("list_hand")


@mcp.tool()
def add_to_hand(card_ids: list[str]) -> dict:
    """Add cards to the user's hand (personal work queue).

    Args:
        card_ids: List of full card UUIDs (36-char format) to add.

    Returns:
        dict with ok=True and count of added cards.
    """
    return _call("add_to_hand", card_ids=card_ids)


@mcp.tool()
def remove_from_hand(card_ids: list[str]) -> dict:
    """Remove cards from the user's hand (personal work queue).

    Args:
        card_ids: List of full card UUIDs (36-char format) to remove.

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
    severity: str | None = None,
    doc: bool = False,
    allow_duplicate: bool = False,
) -> dict:
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
    status: str | None = None,
    priority: str | None = None,
    effort: str | None = None,
    deck: str | None = None,
    title: str | None = None,
    content: str | None = None,
    milestone: str | None = None,
    hero: str | None = None,
    owner: str | None = None,
    tags: str | None = None,
    doc: str | None = None,
) -> dict:
    """Update one or more cards.

    Args:
        card_ids: List of card UUIDs.
        status: New status (not_started, started, done, blocked, in_review).
        priority: New priority (a, b, c, or 'null' to clear).
        effort: New effort (integer as string, or 'null' to clear).
        deck: Move to this deck (by name).
        title: New title (single card only).
        content: New content (single card only).
        milestone: Milestone name (or 'none' to clear).
        hero: Parent card ID (or 'none' to detach).
        owner: Owner name (or 'none' to unassign).
        tags: Comma-separated tags (or 'none' to clear all).
        doc: 'true'/'false' to toggle doc card mode.

    Returns:
        dict with ok=True, updated count, and fields changed.
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

    Args:
        card_ids: List of card UUIDs.

    Returns:
        dict with ok=True and count.
    """
    return _call("mark_done", card_ids=card_ids)


@mcp.tool()
def mark_started(card_ids: list[str]) -> dict:
    """Mark one or more cards as started.

    Args:
        card_ids: List of card UUIDs.

    Returns:
        dict with ok=True and count.
    """
    return _call("mark_started", card_ids=card_ids)


@mcp.tool()
def archive_card(card_id: str) -> dict:
    """Archive a card (reversible).

    Args:
        card_id: Card UUID.

    Returns:
        dict with ok=True and card_id.
    """
    return _call("archive_card", card_id=card_id)


@mcp.tool()
def unarchive_card(card_id: str) -> dict:
    """Restore an archived card.

    Args:
        card_id: Card UUID.

    Returns:
        dict with ok=True and card_id.
    """
    return _call("unarchive_card", card_id=card_id)


@mcp.tool()
def delete_card(card_id: str) -> dict:
    """Permanently delete a card. This cannot be undone.

    Args:
        card_id: Card UUID.

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
    priority: str | None = None,
    effort: int | None = None,
    allow_duplicate: bool = False,
) -> dict:
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
        effort: Effort estimation (integer).
        allow_duplicate: Bypass duplicate title protection.

    Returns:
        FeatureScaffoldReport as dict.
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

    Args:
        card_id: Card UUID.
        message: Comment text.

    Returns:
        dict with ok=True.
    """
    return _call("create_comment", card_id=card_id, message=message)


@mcp.tool()
def list_conversations(card_id: str) -> dict:
    """List all comment threads on a card.

    Args:
        card_id: Card UUID.

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
