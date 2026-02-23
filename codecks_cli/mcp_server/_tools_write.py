"""Write tools: mutations, hand, and scaffolding (12 tools)."""

from __future__ import annotations

from typing import Literal

from codecks_cli import CliError
from codecks_cli.mcp_server._core import (
    _call,
    _contract_error,
    _finalize_tool_result,
    _slim_card,
    _validate_uuid,
    _validate_uuid_list,
)
from codecks_cli.mcp_server._security import _sanitize_card, _validate_input


def create_card(
    title: str,
    content: str | None = None,
    deck: str | None = None,
    project: str | None = None,
    severity: Literal["critical", "high", "low", "null"] | None = None,
    doc: bool = False,
    allow_duplicate: bool = False,
    parent: str | None = None,
) -> dict:
    """Create a new card. Set deck/project to place it. Use parent to nest as sub-card.

    Args:
        title: Card title (max 500 chars).
        content: Card body/description (max 10000 chars). Use ``- []`` for checkboxes.
        deck: Destination deck name.
        project: Project name.
        severity: Card severity level, or 'null' to clear.
        doc: True to create a doc card instead of a normal card.
        allow_duplicate: True to skip duplicate-title check.
        parent: Parent card UUID to nest this as a sub-card.

    Returns:
        Dict with ok, card_id, and title of the created card.
    """
    try:
        title = _validate_input(title, "title")
        if content is not None:
            content = _validate_input(content, "content")
    except CliError as e:
        return _finalize_tool_result(_contract_error(str(e), "error"))
    return _finalize_tool_result(
        _call(
            "create_card",
            title=title,
            content=content,
            deck=deck,
            project=project,
            severity=severity,
            doc=doc,
            allow_duplicate=allow_duplicate,
            parent=parent,
        )
    )


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
    continue_on_error: bool = False,
) -> dict:
    """Update card properties. Doc cards: only owner/tags/milestone/deck/title/content/hero.

    Args:
        card_ids: Full 36-char UUIDs (short IDs cause 400 errors).
        effort: Integer string, or 'null' to clear.
        title/content: Single card only.
        milestone: Name, or 'none' to clear.
        hero: Parent card UUID, or 'none' to detach.
        owner: Name, or 'none' to unassign.
        tags: Comma-separated, or 'none' to clear all.
        continue_on_error: If True, continue updating remaining cards after a failure.

    Returns:
        Dict with ok, updated count, and per-card results.
    """
    try:
        _validate_uuid_list(card_ids)
        if title is not None:
            title = _validate_input(title, "title")
        if content is not None:
            content = _validate_input(content, "content")
    except CliError as e:
        return _finalize_tool_result(_contract_error(str(e), "error"))
    return _finalize_tool_result(
        _call(
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
            continue_on_error=continue_on_error,
        )
    )


def mark_done(card_ids: list[str]) -> dict:
    """Mark cards as done.

    Args:
        card_ids: Full 36-char UUIDs.

    Returns:
        Dict with ok, count of marked cards.
    """
    try:
        _validate_uuid_list(card_ids)
    except CliError as e:
        return _finalize_tool_result(_contract_error(str(e), "error"))
    return _finalize_tool_result(_call("mark_done", card_ids=card_ids))


def mark_started(card_ids: list[str]) -> dict:
    """Mark cards as started.

    Args:
        card_ids: Full 36-char UUIDs.

    Returns:
        Dict with ok, count of marked cards.
    """
    try:
        _validate_uuid_list(card_ids)
    except CliError as e:
        return _finalize_tool_result(_contract_error(str(e), "error"))
    return _finalize_tool_result(_call("mark_started", card_ids=card_ids))


def archive_card(card_id: str) -> dict:
    """Archive a card (reversible). Use unarchive_card to restore.

    Args:
        card_id: Full 36-char UUID.

    Returns:
        Dict with ok and card_id.
    """
    try:
        _validate_uuid(card_id)
    except CliError as e:
        return _finalize_tool_result(_contract_error(str(e), "error"))
    return _finalize_tool_result(_call("archive_card", card_id=card_id))


def unarchive_card(card_id: str) -> dict:
    """Restore an archived card to active state.

    Args:
        card_id: Full 36-char UUID.

    Returns:
        Dict with ok and card_id.
    """
    try:
        _validate_uuid(card_id)
    except CliError as e:
        return _finalize_tool_result(_contract_error(str(e), "error"))
    return _finalize_tool_result(_call("unarchive_card", card_id=card_id))


def delete_card(card_id: str) -> dict:
    """Permanently delete a card. Cannot be undone — use archive_card if reversibility needed.

    Args:
        card_id: Full 36-char UUID.

    Returns:
        Dict with ok and card_id.
    """
    try:
        _validate_uuid(card_id)
    except CliError as e:
        return _finalize_tool_result(_contract_error(str(e), "error"))
    return _finalize_tool_result(_call("delete_card", card_id=card_id))


def scaffold_feature(
    title: str,
    hero_deck: str,
    code_deck: str,
    design_deck: str,
    art_deck: str | None = None,
    skip_art: bool = False,
    audio_deck: str | None = None,
    skip_audio: bool = False,
    description: str | None = None,
    owner: str | None = None,
    priority: Literal["a", "b", "c", "null"] | None = None,
    effort: int | None = None,
    allow_duplicate: bool = False,
) -> dict:
    """Create a Hero card with Code/Design/Art/Audio sub-cards. Transaction-safe rollback on failure.

    Args:
        art_deck: Required unless skip_art=True.
        audio_deck: Required unless skip_audio=True.
    """
    try:
        title = _validate_input(title, "title")
        if description is not None:
            description = _validate_input(description, "description")
    except CliError as e:
        return _finalize_tool_result(_contract_error(str(e), "error"))
    return _finalize_tool_result(
        _call(
            "scaffold_feature",
            title=title,
            hero_deck=hero_deck,
            code_deck=code_deck,
            design_deck=design_deck,
            art_deck=art_deck,
            skip_art=skip_art,
            audio_deck=audio_deck,
            skip_audio=skip_audio,
            description=description,
            owner=owner,
            priority=priority,
            effort=effort,
            allow_duplicate=allow_duplicate,
        )
    )


def split_features(
    deck: str,
    code_deck: str,
    design_deck: str,
    art_deck: str | None = None,
    skip_art: bool = False,
    audio_deck: str | None = None,
    skip_audio: bool = False,
    priority: Literal["a", "b", "c", "null"] | None = None,
    dry_run: bool = False,
) -> dict:
    """Batch-split unsplit feature cards into lane sub-cards. Use dry_run=True to preview.

    Args:
        deck: Source deck containing feature cards.
        code_deck: Destination deck for Code sub-cards.
        design_deck: Destination deck for Design sub-cards.
        art_deck: Destination deck for Art sub-cards (required unless skip_art=True).
        skip_art: True to skip Art lane entirely.
        audio_deck: Destination deck for Audio sub-cards (required unless skip_audio=True).
        skip_audio: True to skip Audio lane entirely.
        priority: Priority for created sub-cards (a/b/c/null).
        dry_run: True to preview without creating cards.

    Returns:
        Dict with features_processed, features_skipped, subcards_created, details, skipped.
    """
    return _finalize_tool_result(
        _call(
            "split_features",
            deck=deck,
            code_deck=code_deck,
            design_deck=design_deck,
            art_deck=art_deck,
            skip_art=skip_art,
            audio_deck=audio_deck,
            skip_audio=skip_audio,
            priority=priority,
            dry_run=dry_run,
        )
    )


def list_hand() -> dict:
    """List cards in the user's hand (personal work queue), sorted by hand order.

    Returns:
        List of card dicts with id, title, status, priority, effort, deck_name.
    """
    result = _call("list_hand")
    if isinstance(result, list):
        return _finalize_tool_result([_sanitize_card(_slim_card(c)) for c in result])
    return _finalize_tool_result(result)


def add_to_hand(card_ids: list[str]) -> dict:
    """Add cards to the user's hand."""
    try:
        _validate_uuid_list(card_ids)
    except CliError as e:
        return _finalize_tool_result(_contract_error(str(e), "error"))
    return _finalize_tool_result(_call("add_to_hand", card_ids=card_ids))


def remove_from_hand(card_ids: list[str]) -> dict:
    """Remove cards from the user's hand."""
    try:
        _validate_uuid_list(card_ids)
    except CliError as e:
        return _finalize_tool_result(_contract_error(str(e), "error"))
    return _finalize_tool_result(_call("remove_from_hand", card_ids=card_ids))


def register(mcp):
    """Register all write tools with the FastMCP instance."""
    mcp.tool()(create_card)
    mcp.tool()(update_cards)
    mcp.tool()(mark_done)
    mcp.tool()(mark_started)
    mcp.tool()(archive_card)
    mcp.tool()(unarchive_card)
    mcp.tool()(delete_card)
    mcp.tool()(scaffold_feature)
    mcp.tool()(split_features)
    mcp.tool()(list_hand)
    mcp.tool()(add_to_hand)
    mcp.tool()(remove_from_hand)
