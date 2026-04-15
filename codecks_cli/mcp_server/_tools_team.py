"""Team coordination tools for multi-agent workflows (8 tools).

Provides card claiming, delegation, work partitioning, and team dashboards.
Coordination state is persisted to .pm_claims.json — survives server restarts.
Codecks card fields (status, owner, comments) remain the authoritative source.
"""

import os
from datetime import UTC, datetime
from typing import Literal

from codecks_cli import CliError
from codecks_cli.mcp_server._core import (
    _agent_sessions,
    _call,
    _card_summary,
    _contract_error,
    _finalize_tool_result,
    _get_agent_for_card,
    _get_all_sessions,
    _get_cache_metadata,
    _get_snapshot,
    _is_cache_valid,
    _load_cache_from_disk,
    _register_agent,
    _unregister_agent_card,
    _validate_uuid,
)
from codecks_cli.mcp_server._security import _sanitize_card

_PLAYBOOK_PATH = os.path.join(os.path.dirname(__file__), "..", "pm_playbook.md")


# ---------------------------------------------------------------------------
# Claiming
# ---------------------------------------------------------------------------


def claim_card(card_id: str, agent_name: str, reason: str | None = None) -> dict:
    """Claim a card for exclusive agent work.

    Prevents other agents from working on the same card. Claims are
    persisted to disk and survive server restarts.

    Args:
        card_id: Full 36-char UUID of the card to claim.
        agent_name: Name of the claiming agent (e.g., "code-agent").
        reason: Optional reason (e.g., "Implementing inventory system").

    Returns:
        On success: {ok, card_id, agent_name, claimed_at, reason}.
        On conflict: {ok: false, error, conflict_agent, card_id}.
    """
    try:
        _validate_uuid(card_id)
    except CliError as e:
        return _finalize_tool_result(_contract_error(str(e), "error"))

    if not agent_name or not agent_name.strip():
        return _finalize_tool_result(
            _contract_error("agent_name is required for claim_card.", "error")
        )
    agent_name = agent_name.strip()

    existing = _get_agent_for_card(card_id)
    if existing and existing != agent_name:
        return _finalize_tool_result(
            {
                "ok": False,
                "error": f"Card already claimed by '{existing}'.",
                "conflict_agent": existing,
                "card_id": card_id,
            }
        )

    _register_agent(agent_name, card_id)
    now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    result: dict = {
        "ok": True,
        "card_id": card_id,
        "agent_name": agent_name,
        "claimed_at": now_iso,
    }
    if reason:
        result["reason"] = reason
    return _finalize_tool_result(result)


def release_card(card_id: str, agent_name: str, summary: str | None = None) -> dict:
    """Release a previously claimed card.

    Args:
        card_id: Full 36-char UUID.
        agent_name: Name of the agent releasing the card.
        summary: Optional work summary (e.g., "Implemented and tested").

    Returns:
        {ok, card_id, agent_name, released_at, summary?}.
    """
    try:
        _validate_uuid(card_id)
    except CliError as e:
        return _finalize_tool_result(_contract_error(str(e), "error"))

    if not agent_name or not agent_name.strip():
        return _finalize_tool_result(
            _contract_error("agent_name is required for release_card.", "error")
        )
    agent_name = agent_name.strip()

    removed = _unregister_agent_card(agent_name, card_id)
    if not removed:
        return _finalize_tool_result(
            _contract_error(
                f"Card '{card_id}' not found in agent '{agent_name}' active list.",
                "error",
            )
        )

    now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    result: dict = {
        "ok": True,
        "card_id": card_id,
        "agent_name": agent_name,
        "released_at": now_iso,
    }
    if summary:
        result["summary"] = summary
    return _finalize_tool_result(result)


def delegate_card(card_id: str, from_agent: str, to_agent: str, message: str | None = None) -> dict:
    """Hand off a card from one agent to another.

    Transfers the in-memory claim. The receiving agent does not need to
    call claim_card separately.

    Args:
        card_id: Full 36-char UUID.
        from_agent: Current owner agent name.
        to_agent: Receiving agent name.
        message: Optional handoff context.

    Returns:
        {ok, card_id, from_agent, to_agent, delegated_at, message?}.
    """
    try:
        _validate_uuid(card_id)
    except CliError as e:
        return _finalize_tool_result(_contract_error(str(e), "error"))

    for name, label in [(from_agent, "from_agent"), (to_agent, "to_agent")]:
        if not name or not name.strip():
            return _finalize_tool_result(
                _contract_error(f"{label} is required for delegate_card.", "error")
            )
    from_agent = from_agent.strip()
    to_agent = to_agent.strip()

    # Verify from_agent actually has the card
    current = _get_agent_for_card(card_id)
    if current != from_agent:
        return _finalize_tool_result(
            _contract_error(
                f"Card '{card_id}' is not claimed by '{from_agent}'"
                + (f" (claimed by '{current}')." if current else " (unclaimed)."),
                "error",
            )
        )

    _unregister_agent_card(from_agent, card_id)
    _register_agent(to_agent, card_id)

    now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    result: dict = {
        "ok": True,
        "card_id": card_id,
        "from_agent": from_agent,
        "to_agent": to_agent,
        "delegated_at": now_iso,
    }
    if message:
        result["message"] = message
    return _finalize_tool_result(result)


# ---------------------------------------------------------------------------
# Status & dashboards
# ---------------------------------------------------------------------------


def team_status() -> dict:
    """Show what each agent is currently working on.

    Returns:
        agents: List of {name, active_cards, last_seen, card_count}.
        total_claimed: Total cards claimed across all agents.
        agent_count: Number of registered agents.
    """
    sessions = _get_all_sessions()
    agents = []
    total_claimed = 0
    for name, session in sessions.items():
        card_count = len(session.get("active_cards", []))
        total_claimed += card_count
        agents.append(
            {
                "name": name,
                "active_cards": session.get("active_cards", []),
                "claimed_at": session.get("claimed_at", {}),
                "last_seen": session.get("last_seen", ""),
                "card_count": card_count,
            }
        )
    return _finalize_tool_result(
        {
            "ok": True,
            "agents": agents,
            "agent_count": len(agents),
            "total_claimed": total_claimed,
        }
    )


def _get_active_cards() -> list[dict]:
    """Get cards from cache or API for partitioning/dashboard tools."""
    _load_cache_from_disk()
    if _is_cache_valid():
        snapshot = _get_snapshot()
        if snapshot:
            cards_result = snapshot.get("cards_result")
            if isinstance(cards_result, dict):
                raw_cards = cards_result.get("cards", [])
                if isinstance(raw_cards, list):
                    return raw_cards
    # Fallback to API
    result = _call("list_cards")
    if isinstance(result, dict) and result.get("ok") is not False:
        cards = result.get("cards", [])
        return cards if isinstance(cards, list) else []
    return []


def _annotate_claims(cards: list[dict]) -> list[dict]:
    """Annotate cards with claimed_by from agent sessions."""
    if not _agent_sessions:
        return cards
    annotated = []
    for card in cards:
        card_id = card.get("id", "")
        claimer = _get_agent_for_card(card_id)
        if claimer:
            card = dict(card)
            card["claimed_by"] = claimer
        annotated.append(card)
    return annotated


def partition_cards(
    by: Literal["lane", "owner"] = "lane",
    project: str | None = None,
    max_cards_per_group: int = 10,
) -> dict:
    """Group active cards by lane tag or Codecks owner for team work distribution.

    Args:
        by: Partition strategy — "lane" groups by lane tags (code, design, art, audio),
            "owner" groups by Codecks card owner.
        project: Optional project name filter.
        max_cards_per_group: Cap cards per group (default 10, 0=unlimited).
            Groups sorted by priority then recency. Includes total_in_group count.

    Returns:
        When by="lane": {ok, lanes: {code: {cards, claimed, unclaimed}, ...}, untagged: {...}}.
        When by="owner": {ok, owners: {name: {cards, claimed, unclaimed}, ...}, unassigned: {...}}.
    """
    cap = max_cards_per_group if max_cards_per_group > 0 else None
    if by == "owner":
        return partition_by_owner(project=project, cap=cap)
    return partition_by_lane(project=project, cap=cap)


def _cap_and_summarize(cards: list[dict], cap: int | None) -> tuple[list[dict], int, bool]:
    """Sort by priority+recency, cap, and summarize cards for partition output.

    Returns (summarized_cards, total_in_group, truncated).
    """
    _PRIORITY_ORDER = {"a": 0, "b": 1, "c": 2}
    sorted_cards = sorted(
        cards,
        key=lambda c: (
            _PRIORITY_ORDER.get(c.get("priority"), 3),
            "",  # stable secondary sort
        ),
    )
    total = len(sorted_cards)
    truncated = cap is not None and total > cap
    if cap is not None:
        sorted_cards = sorted_cards[:cap]
    annotated = _annotate_claims(sorted_cards)
    summarized = []
    for c in annotated:
        s = _sanitize_card(_card_summary(c))
        if "claimed_by" in c:
            s["claimed_by"] = c["claimed_by"]
        summarized.append(s)
    return summarized, total, truncated


def partition_by_lane(project: str | None = None, cap: int | None = None) -> dict:
    """Group active cards by lane tag for team work distribution.

    Groups cards by their lane tags (code, design, art, audio).
    Cards without lane tags go to 'untagged'. Annotates each card
    with claimed_by if an agent has claimed it.

    Args:
        project: Optional project name filter.
        cap: Max cards per group (None=unlimited).

    Returns:
        {ok, lanes: {code: {cards, claimed, unclaimed, total_in_group, truncated}, ...}}.
    """
    from codecks_cli.tags import LANE_TAGS

    lane_tag_names = set(LANE_TAGS.keys())
    cards = _get_active_cards()

    cards = [
        c
        for c in cards
        if c.get("status") not in ("done", None)
        and not c.get("is_archived")
        and (project is None or c.get("project_name", "").lower() == project.lower())
    ]

    lanes: dict[str, list[dict]] = {tag: [] for tag in lane_tag_names}
    lanes["untagged"] = []

    for card in cards:
        card_tags = {t.lower() for t in (card.get("tags") or [])}
        placed = False
        for tag_name in lane_tag_names:
            if tag_name in card_tags:
                lanes[tag_name].append(card)
                placed = True
                break
        if not placed:
            lanes["untagged"].append(card)

    result_lanes = {}
    for lane_name, lane_cards in lanes.items():
        summarized, total, truncated = _cap_and_summarize(lane_cards, cap)
        claimed_count = sum(1 for c in summarized if "claimed_by" in c)
        result_lanes[lane_name] = {
            "cards": summarized,
            "count": len(summarized),
            "total_in_group": total,
            "truncated": truncated,
            "claimed": claimed_count,
            "unclaimed": len(summarized) - claimed_count,
        }

    return _finalize_tool_result({"ok": True, "lanes": result_lanes, **_get_cache_metadata()})


def partition_by_owner(project: str | None = None, cap: int | None = None) -> dict:
    """Group active cards by Codecks owner for team work distribution.

    Args:
        project: Optional project name filter.
        cap: Max cards per group (None=unlimited).

    Returns:
        {ok, owners: {name: {cards, claimed, unclaimed, total_in_group, truncated}, ...}}.
    """
    cards = _get_active_cards()

    cards = [
        c
        for c in cards
        if c.get("status") not in ("done", None)
        and not c.get("is_archived")
        and (project is None or c.get("project_name", "").lower() == project.lower())
    ]

    owners: dict[str, list[dict]] = {}
    unassigned: list[dict] = []

    for card in cards:
        owner_name = card.get("owner_name") or card.get("owner")
        if owner_name:
            owners.setdefault(owner_name, []).append(card)
        else:
            unassigned.append(card)

    result_owners = {}
    for owner_name, owner_cards in owners.items():
        summarized, total, truncated = _cap_and_summarize(owner_cards, cap)
        claimed_count = sum(1 for c in summarized if "claimed_by" in c)
        result_owners[owner_name] = {
            "cards": summarized,
            "count": len(summarized),
            "total_in_group": total,
            "truncated": truncated,
            "claimed": claimed_count,
            "unclaimed": len(summarized) - claimed_count,
        }

    summarized_ua, total_ua, trunc_ua = _cap_and_summarize(unassigned, cap)
    claimed_ua = sum(1 for c in summarized_ua if "claimed_by" in c)

    return _finalize_tool_result(
        {
            "ok": True,
            "owners": result_owners,
            "unassigned": {
                "cards": summarized_ua,
                "count": len(summarized_ua),
                "total_in_group": total_ua,
                "truncated": trunc_ua,
                "claimed": claimed_ua,
                "unclaimed": len(summarized_ua) - claimed_ua,
            },
            **_get_cache_metadata(),
        }
    )


def team_dashboard(
    project: str | None = None,
    summary_only: bool = False,
) -> dict:
    """Combined team dashboard: health data + agent workload + claim map.

    Designed for the team lead to get a single-call overview of project
    health and agent activity. Combines pm_focus data with agent sessions.

    Key metric: unclaimed_in_progress — cards with status=started that
    no agent has claimed (work potentially falling through cracks).

    Args:
        project: Optional project name filter.
        summary_only: If True, return counts only — no card arrays (~2KB vs ~45KB).

    Returns:
        {ok, health, agents, unclaimed_in_progress, lane_distribution}.
        With summary_only=True: counts only, no card arrays.
    """
    # Get pm_focus data for health metrics
    focus_kwargs: dict = {}
    if project:
        focus_kwargs["project"] = project
    health = _call("pm_focus", **focus_kwargs)
    if isinstance(health, dict) and health.get("ok") is False:
        health = {"error": "pm_focus unavailable"}
    elif summary_only and isinstance(health, dict):
        # Strip card arrays, keep only counts + deck_health
        health = {
            "counts": health.get("counts", {}),
            "deck_health": health.get("deck_health", {}),
        }

    # Agent sessions
    sessions = _get_all_sessions()
    agents = []
    all_claimed_ids: set[str] = set()
    for name, session in sessions.items():
        active = session.get("active_cards", [])
        all_claimed_ids.update(active)
        agent_info: dict = {
            "name": name,
            "card_count": len(active),
            "last_seen": session.get("last_seen", ""),
        }
        if not summary_only:
            agent_info["active_cards"] = active
        agents.append(agent_info)

    # Find unclaimed in-progress cards
    cards = _get_active_cards()
    if project:
        cards = [c for c in cards if (c.get("project_name", "").lower() == project.lower())]
    unclaimed_count = 0
    unclaimed_in_progress = []
    for card in cards:
        if card.get("status") == "started" and card.get("id") not in all_claimed_ids:
            unclaimed_count += 1
            if not summary_only:
                unclaimed_in_progress.append(_sanitize_card(_card_summary(card)))

    result: dict = {
        "ok": True,
        "health": health,
        "agents": agents,
        "agent_count": len(agents),
        "total_claimed": len(all_claimed_ids),
        "unclaimed_in_progress_count": unclaimed_count,
        **_get_cache_metadata(),
    }
    if not summary_only:
        result["unclaimed_in_progress"] = unclaimed_in_progress
    if summary_only:
        result["summary_only"] = True
    return _finalize_tool_result(result)


# ---------------------------------------------------------------------------
# Team playbook
# ---------------------------------------------------------------------------


def get_team_playbook() -> dict:
    """Get team coordination guide for multi-agent PM sessions.

    Returns only the 'Agent Team Coordination' section from the PM
    playbook. Smaller than get_pm_playbook() — saves tokens for worker
    agents who only need team-specific guidance.

    Returns:
        {ok, content}.
    """
    try:
        with open(_PLAYBOOK_PATH, encoding="utf-8") as f:
            full = f.read()
    except FileNotFoundError:
        return _finalize_tool_result(_contract_error("pm_playbook.md not found.", "error"))

    marker = "## Agent Team Coordination"
    idx = full.find(marker)
    if idx == -1:
        return _finalize_tool_result(
            _contract_error(
                "Team coordination section not found in playbook. "
                "Use get_pm_playbook() for the full guide.",
                "error",
            )
        )

    # Extract from marker to next ## heading or end of file
    rest = full[idx + len(marker) :]
    next_heading = rest.find("\n## ")
    if next_heading != -1:
        section = marker + rest[:next_heading]
    else:
        section = marker + rest

    return _finalize_tool_result({"ok": True, "content": section.strip()})


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register(mcp):
    """Register team coordination tools with the FastMCP instance.

    Tools removed in v0.5.0:
    - partition_by_lane/partition_by_owner → merged into partition_cards(by=...)
    - get_team_playbook → injected via session_start() / CLAUDE.md
    """
    mcp.tool()(claim_card)
    mcp.tool()(release_card)
    mcp.tool()(delegate_card)
    mcp.tool()(team_status)
    mcp.tool()(partition_cards)
    mcp.tool()(team_dashboard)
