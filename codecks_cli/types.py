"""Typed response definitions for CodecksClient methods.

These TypedDicts document the shape of dicts returned by public API methods.
They are optional — runtime behavior is unchanged (plain dicts).
"""

from __future__ import annotations

from typing import TypedDict

# ---------------------------------------------------------------------------
# Card types
# ---------------------------------------------------------------------------


class CardRow(TypedDict, total=False):
    """Flat card summary returned in list results."""

    id: str
    title: str
    status: str | None
    priority: str | None
    effort: int | None
    severity: str | None
    deck_id: str | None
    deck_name: str | None
    owner_name: str | None
    milestone_id: str | None
    milestone_name: str | None
    tags: list[str]
    sub_card_count: int | None
    is_doc: bool | None
    created_at: str | None
    last_updated_at: str | None


class CardListResult(TypedDict):
    """Return type of CodecksClient.list_cards()."""

    cards: list[CardRow]
    stats: CardStats | None


class ConversationMessage(TypedDict):
    author: str
    content: str
    created_at: str


class Conversation(TypedDict):
    id: str
    status: str
    creator: str
    created_at: str
    messages: list[ConversationMessage]


class SubCard(TypedDict):
    id: str
    title: str
    status: str


class CardDetail(TypedDict, total=False):
    """Return type of CodecksClient.get_card()."""

    id: str
    title: str
    status: str | None
    priority: str | None
    effort: int | None
    severity: str | None
    content: str | None
    deck_id: str | None
    deck_name: str | None
    owner_name: str | None
    milestone_id: str | None
    milestone_name: str | None
    tags: list[str]
    is_doc: bool | None
    in_hand: bool
    created_at: str | None
    last_updated_at: str | None
    checkbox_stats: dict | None
    parent_card_id: str | None
    sub_cards: list[SubCard]
    conversations: list[Conversation]


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class CardStats(TypedDict):
    """Aggregate stats returned by list_cards(include_stats=True)."""

    total: int
    total_effort: int | float
    avg_effort: float
    by_status: dict[str, int]
    by_priority: dict[str, int]
    by_deck: dict[str, int]
    by_owner: dict[str, int]


# ---------------------------------------------------------------------------
# Entity types
# ---------------------------------------------------------------------------


class DeckRow(TypedDict):
    id: str
    title: str
    project_name: str
    card_count: int


class ProjectRow(TypedDict):
    id: str
    name: str
    deck_count: int
    decks: list[str]


class MilestoneRow(TypedDict):
    id: str
    name: str
    card_count: int


# ---------------------------------------------------------------------------
# Mutation results
# ---------------------------------------------------------------------------


class MutationResult(TypedDict, total=False):
    """Common shape for mutation responses."""

    ok: bool
    card_id: str
    data: dict


class CreateCardResult(TypedDict, total=False):
    ok: bool
    card_id: str
    title: str
    deck: str | None
    doc: bool
    warnings: list[str]


class UpdateCardsResult(TypedDict, total=False):
    ok: bool
    updated: int
    fields: dict
    data: dict


class HandResult(TypedDict, total=False):
    ok: bool
    added: int
    removed: int
    data: dict


# ---------------------------------------------------------------------------
# Dashboard types
# ---------------------------------------------------------------------------


class PmFocusResult(TypedDict):
    counts: dict[str, int]
    blocked: list[CardRow]
    in_review: list[CardRow]
    hand: list[CardRow]
    stale: list[CardRow]
    suggested: list[CardRow]
    filters: dict


class StandupResult(TypedDict):
    recently_done: list[CardRow]
    in_progress: list[CardRow]
    blocked: list[CardRow]
    hand: list[CardRow]
    filters: dict
