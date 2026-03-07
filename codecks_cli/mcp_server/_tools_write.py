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

    Tagging: Prefer inline tags in card content body (``Tags: #tag1 #tag2``) over
    the ``tags`` parameter. Inline tags are the project standard. The ``tags``
    parameter sets card-level masterTags and should only be used for system tags
    (hero, feature) applied during scaffolding.

    Args:
        card_ids: Full 36-char UUIDs (short IDs cause 400 errors).
        effort: Integer string, or 'null' to clear.
        title/content: Single card only. Content is full card text (title + body).
            If content already starts with the existing title, it is sent as-is;
            otherwise the existing title is preserved as first line (CLI backward
            compat). Use update_card_body() for body-only edits.
            If both title and content are set, they merge.
        milestone: Name, or 'none' to clear.
        hero: Parent card UUID, or 'none' to detach.
        owner: Name, or 'none' to unassign.
        tags: Card-level masterTags (comma-separated, or 'none'). Prefer inline body tags.
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

    # Doc-card guardrail: reject status/priority/effort on doc cards
    _doc_blocked = {"status": status, "priority": priority, "effort": effort}
    blocked_fields = [k for k, v in _doc_blocked.items() if v is not None]
    if blocked_fields:
        from codecks_cli.mcp_server._tools_read import _try_cache as _read_cache

        cached_cards = _read_cache("cards_result")
        if isinstance(cached_cards, dict):
            for cid in card_ids:
                for card in cached_cards.get("cards", []):
                    if isinstance(card, dict) and card.get("id") == cid:
                        if card.get("cardType") == "doc" or card.get("is_doc"):
                            return _finalize_tool_result(
                                _contract_error(
                                    f"Card '{cid}' is a doc card. Doc cards do not support: "
                                    f"{', '.join(blocked_fields)}. "
                                    "Only owner/tags/milestone/deck/title/content/hero can be set.",
                                    "error",
                                    error_code="DOC_CARD_VIOLATION",
                                )
                            )

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
    code_owner: str | None = None,
    design_owner: str | None = None,
    art_owner: str | None = None,
    audio_owner: str | None = None,
    priority: Literal["a", "b", "c", "null"] | None = None,
    effort: int | None = None,
    allow_duplicate: bool = False,
) -> dict:
    """Create a Hero card with Code/Design/Art/Audio sub-cards. Transaction-safe rollback on failure.

    Args:
        art_deck: Required unless skip_art=True.
        audio_deck: Required unless skip_audio=True.
        owner: Default owner for hero and all sub-cards.
        code_owner: Override owner for Code sub-card (falls back to owner).
        design_owner: Override owner for Design sub-card (falls back to owner).
        art_owner: Override owner for Art sub-card (falls back to owner).
        audio_owner: Override owner for Audio sub-card (falls back to owner).
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
            code_owner=code_owner,
            design_owner=design_owner,
            art_owner=art_owner,
            audio_owner=audio_owner,
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
    # Try cache first
    from codecks_cli.mcp_server import _core

    _core._load_cache_from_disk()
    if _core._is_cache_valid():
        snapshot = _core._get_snapshot()
        if snapshot is not None and "hand" in snapshot and isinstance(snapshot["hand"], list):
            return _finalize_tool_result([_sanitize_card(_slim_card(c)) for c in snapshot["hand"]])

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


def update_card_body(card_id: str, body: str) -> dict:
    """Update only the body/description of a card, preserving its title.

    Use this when you want to change the card description without touching
    the title. For full content replacement, use update_cards with content=.

    Args:
        card_id: Full 36-char UUID.
        body: New body text (replaces everything after the title line).

    Returns:
        Dict with ok and update result.
    """
    try:
        _validate_uuid(card_id)
        body = _validate_input(body, "content")
    except CliError as e:
        return _finalize_tool_result(_contract_error(str(e), "error"))

    from codecks_cli._content import replace_body

    # Read existing card to get current content
    card_result = _call("get_card", card_id=card_id)
    if isinstance(card_result, dict) and card_result.get("ok") is False:
        return _finalize_tool_result(card_result)

    old_content = ""
    if isinstance(card_result, dict):
        old_content = card_result.get("content") or ""

    new_content = replace_body(old_content, body)
    return _finalize_tool_result(_call("update_cards", card_ids=[card_id], content=new_content))


def find_and_update(
    search: str,
    status: Literal["not_started", "started", "done", "blocked", "in_review"] | None = None,
    priority: Literal["a", "b", "c", "null"] | None = None,
    effort: str | None = None,
    deck: str | None = None,
    milestone: str | None = None,
    owner: str | None = None,
    search_deck: str | None = None,
    search_status: str | None = None,
    max_results: int = 10,
    confirm_ids: list[str] | None = None,
) -> dict:
    """Search cards then update in one tool. Two phases:

    Phase 1 (no confirm_ids): Returns matching cards for review. Read-only.
    Phase 2 (confirm_ids set): Applies updates to confirmed card IDs.

    Args:
        search: Text to match in card titles/content.
        search_deck: Narrow search to this deck.
        search_status: Narrow search to these statuses (comma-separated).
        max_results: Max matches in phase 1 (default 10).
        confirm_ids: Full 36-char UUIDs to update (from phase 1 results).
        status/priority/effort/deck/milestone/owner: Fields to update.

    Returns:
        Phase 1: {phase: "confirm", matches: [...], match_count: int}
        Phase 2: {phase: "applied", ok: bool, updated: int}
    """
    try:
        search = _validate_input(search, "title")
    except CliError as e:
        return _finalize_tool_result(_contract_error(str(e), "error"))

    # Phase 2: Apply updates
    if confirm_ids is not None:
        has_update = any(v is not None for v in [status, priority, effort, deck, milestone, owner])
        if not has_update:
            return _finalize_tool_result(
                _contract_error(
                    "No update fields provided. Set status, priority, effort, "
                    "deck, milestone, or owner.",
                    "error",
                )
            )
        try:
            _validate_uuid_list(confirm_ids)
        except CliError as e:
            return _finalize_tool_result(_contract_error(str(e), "error"))
        result = _call(
            "update_cards",
            card_ids=confirm_ids,
            status=status,
            priority=priority,
            effort=effort,
            deck=deck,
            milestone=milestone,
            owner=owner,
        )
        if isinstance(result, dict):
            result["phase"] = "applied"
        return _finalize_tool_result(result)

    # Phase 1: Search
    from codecks_cli.mcp_server._tools_read import _filter_cached_cards, _try_cache

    cached = _try_cache("cards_result")
    if cached is not None and isinstance(cached, dict) and "cards" in cached:
        cards = cached["cards"]
    else:
        api_result = _call("list_cards", search=search)
        if isinstance(api_result, dict) and api_result.get("ok") is False:
            return _finalize_tool_result(api_result)
        cards = api_result.get("cards", []) if isinstance(api_result, dict) else []

    filtered = _filter_cached_cards(
        cards,
        search=search,
        deck=search_deck,
        status=search_status,
    )

    matches = []
    for card in filtered[:max_results]:
        if isinstance(card, dict):
            matches.append(
                _sanitize_card(
                    _slim_card(
                        {
                            "id": card.get("id"),
                            "title": card.get("title"),
                            "status": card.get("status"),
                            "deck": card.get("deck") or card.get("deck_name"),
                            "priority": card.get("priority"),
                            "effort": card.get("effort"),
                        }
                    )
                )
            )

    return _finalize_tool_result(
        {
            "phase": "confirm",
            "matches": matches,
            "match_count": len(filtered),
            "showing": len(matches),
        }
    )


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
    mcp.tool()(update_card_body)
    mcp.tool()(find_and_update)
