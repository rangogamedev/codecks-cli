"""Shared operations used by both CLI commands and MCP tools.

These functions contain business logic that is independent of the
transport layer (CLI argparse vs MCP FastMCP). Both cli.py commands
and mcp_server/_tools_*.py tools should call these instead of
duplicating logic.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone

from codecks_cli.client import CodecksClient
from codecks_cli.config import _PROJECT_ROOT

# ---------------------------------------------------------------------------
# Checkbox operations
# ---------------------------------------------------------------------------

_UNCHECKED_RE = re.compile(r"^(\s*- \[)\](.*)$")
_CHECKED_RE = re.compile(r"^(\s*- \[)x\](.*)$")


def tick_checkboxes(
    client: CodecksClient,
    card_id: str,
    items: list[str],
    *,
    untick: bool = False,
) -> dict:
    """Tick (or untick) specific checkbox items in a card's content.

    Args:
        client: Authenticated CodecksClient.
        card_id: Full 36-char UUID.
        items: List of text substrings to match against checkbox lines.
        untick: If True, change [x] to [] instead of [] to [x].

    Returns:
        Dict with ok, ticked/unticked, already_done, not_found, checkbox stats.
    """
    card = client.get_card(card_id, include_content=True, include_conversations=False)
    content = card.get("content") or ""
    if not content:
        return {"ok": False, "error": "Card has no content.", "error_code": "NO_CONTENT"}

    lines = content.split("\n")
    ticked: list[str] = []
    already_done: list[str] = []
    not_found: list[str] = list(items)
    changed = False

    for i, line in enumerate(lines):
        for item_text in items:
            if item_text.lower() not in line.lower():
                continue

            if not untick:
                m = _UNCHECKED_RE.match(line)
                if m:
                    lines[i] = m.group(1) + "x]" + m.group(2)
                    ticked.append(item_text)
                    if item_text in not_found:
                        not_found.remove(item_text)
                    changed = True
                    break
                m2 = _CHECKED_RE.match(line)
                if m2:
                    already_done.append(item_text)
                    if item_text in not_found:
                        not_found.remove(item_text)
                    break
            else:
                m = _CHECKED_RE.match(line)
                if m:
                    lines[i] = m.group(1) + "]" + m.group(2)
                    ticked.append(item_text)
                    if item_text in not_found:
                        not_found.remove(item_text)
                    changed = True
                    break
                m2 = _UNCHECKED_RE.match(line)
                if m2:
                    already_done.append(item_text)
                    if item_text in not_found:
                        not_found.remove(item_text)
                    break

    new_content = "\n".join(lines)
    total_checkboxes = len(re.findall(r"^\s*- \[[ x]\]", new_content, re.MULTILINE))
    checked_checkboxes = len(re.findall(r"^\s*- \[x\]", new_content, re.MULTILINE))

    if changed:
        client.update_cards(card_ids=[card_id], content=new_content)

    action = "unticked" if untick else "ticked"
    return {
        "ok": True,
        action: ticked,
        "already_done": already_done,
        "not_found": not_found,
        "total_checkboxes": total_checkboxes,
        "checked_checkboxes": checked_checkboxes,
        "changed": changed,
    }


def tick_all_checkboxes(client: CodecksClient, card_id: str) -> dict:
    """Tick all unchecked checkbox items on a card.

    Args:
        client: Authenticated CodecksClient.
        card_id: Full 36-char UUID.

    Returns:
        Dict with ok, ticked_count, total_checkboxes, already_checked, changed.
    """
    card = client.get_card(card_id, include_content=True, include_conversations=False)
    content = card.get("content") or ""
    if not content:
        return {"ok": False, "error": "Card has no content.", "error_code": "NO_CONTENT"}

    already_checked = len(re.findall(r"^\s*- \[x\]", content, re.MULTILINE))
    total_unchecked = len(re.findall(r"^\s*- \[\]", content, re.MULTILINE))

    if total_unchecked == 0:
        return {
            "ok": True,
            "ticked_count": 0,
            "total_checkboxes": already_checked,
            "already_checked": already_checked,
            "changed": False,
        }

    new_content = re.sub(r"^(\s*- \[)\]", r"\1x]", content, flags=re.MULTILINE)
    client.update_cards(card_ids=[card_id], content=new_content)

    return {
        "ok": True,
        "ticked_count": total_unchecked,
        "total_checkboxes": already_checked + total_unchecked,
        "already_checked": already_checked,
        "changed": True,
    }


# ---------------------------------------------------------------------------
# Overview / aggregation
# ---------------------------------------------------------------------------


def quick_overview(client: CodecksClient, *, project: str | None = None) -> dict:
    """Compact project overview with aggregate counts only.

    Args:
        client: Authenticated CodecksClient.
        project: Optional project name filter.

    Returns:
        Dict with total_cards, by_status, by_priority, effort_stats, etc.
    """
    result = client.list_cards()
    cards = result.get("cards", []) if isinstance(result, dict) else []

    if project:
        project_lower = project.lower()
        cards = [c for c in cards if str(c.get("project", "")).lower() == project_lower]

    by_status: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    deck_counts: dict[str, int] = {}
    total_effort = 0
    estimated_count = 0
    stale_count = 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
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

    return {
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
        "stale_count": stale_count,
        "deck_summary": [{"name": k, "count": v} for k, v in sorted(deck_counts.items())],
    }


# ---------------------------------------------------------------------------
# Partitioning
# ---------------------------------------------------------------------------


def partition_cards(
    client: CodecksClient,
    *,
    by: str = "lane",
    status: str | None = None,
    project: str | None = None,
) -> dict:
    """Partition active cards into work batches for parallel agent execution.

    Args:
        client: Authenticated CodecksClient.
        by: Partition strategy — "lane" (by [Code]/[Design]/etc.) or "owner".
        status: Comma-separated status filter (default: not_started,started).
        project: Optional project name filter.

    Returns:
        Dict with batches (list of {key, card_ids, count}), total_cards, batch_count.
    """
    result = client.list_cards()
    cards = result.get("cards", []) if isinstance(result, dict) else []

    # Filter
    statuses = set((status or "not_started,started").split(","))
    cards = [
        c
        for c in cards
        if isinstance(c, dict) and c.get("status") in statuses and not c.get("is_archived")
    ]
    if project:
        project_lower = project.lower()
        cards = [c for c in cards if str(c.get("project", "")).lower() == project_lower]

    # Partition
    buckets: dict[str, list[str]] = {}

    if by == "lane":
        lane_keywords = {"code": "[Code]", "design": "[Design]", "art": "[Art]", "audio": "[Audio]"}
        for card in cards:
            title = str(card.get("title", ""))
            placed = False
            for lane, keyword in lane_keywords.items():
                if keyword in title:
                    buckets.setdefault(lane, []).append(card.get("id", ""))
                    placed = True
                    break
            if not placed:
                buckets.setdefault("other", []).append(card.get("id", ""))
    elif by == "owner":
        for card in cards:
            owner = card.get("owner_name") or card.get("owner") or "unassigned"
            buckets.setdefault(owner, []).append(card.get("id", ""))
    else:
        return {
            "ok": False,
            "error": f"Unknown partition strategy: {by}",
            "error_code": "INVALID_INPUT",
        }

    batches = [
        {"key": key, "card_ids": ids, "count": len(ids)}
        for key, ids in sorted(buckets.items())
        if ids
    ]

    return {
        "ok": True,
        "by": by,
        "batches": batches,
        "total_cards": sum(b["count"] for b in batches),
        "batch_count": len(batches),
    }


# ---------------------------------------------------------------------------
# Coordination (claim/release via file)
# ---------------------------------------------------------------------------


def _load_claims() -> dict:
    """Load claims from .pm_claims.json."""
    import os

    from codecks_cli.config import _PROJECT_ROOT

    claims_path = os.path.join(_PROJECT_ROOT, ".pm_claims.json")
    try:
        with open(claims_path, encoding="utf-8") as f:
            data = json.load(f)
        return dict(data) if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_claims(claims: dict) -> None:
    """Save claims to .pm_claims.json atomically."""
    import os
    import tempfile

    from codecks_cli.config import _PROJECT_ROOT

    claims_path = os.path.join(_PROJECT_ROOT, ".pm_claims.json")
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(claims_path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(claims, f, indent=2)
        os.replace(tmp, claims_path)
    except BaseException:
        os.unlink(tmp)
        raise


def claim_card(card_id: str, agent_name: str, *, reason: str | None = None) -> dict:
    """Claim a card for exclusive agent work. File-based coordination.

    Args:
        card_id: Full 36-char UUID.
        agent_name: Claiming agent name.
        reason: Optional reason.

    Returns:
        Dict with ok, card_id, agent_name, claimed_at.
    """
    claims = _load_claims()
    existing = claims.get(card_id)
    if existing and existing.get("agent") != agent_name:
        return {
            "ok": False,
            "error": f"Card already claimed by '{existing['agent']}'.",
            "conflict_agent": existing["agent"],
            "card_id": card_id,
        }

    claims[card_id] = {
        "agent": agent_name,
        "claimed_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
    }
    _save_claims(claims)

    return {
        "ok": True,
        "card_id": card_id,
        "agent_name": agent_name,
        "claimed_at": claims[card_id]["claimed_at"],
    }


def release_card(card_id: str, agent_name: str, *, summary: str | None = None) -> dict:
    """Release a previously claimed card.

    Args:
        card_id: Full 36-char UUID.
        agent_name: Agent releasing the card.
        summary: Optional work summary.

    Returns:
        Dict with ok, card_id, agent_name, released_at.
    """
    claims = _load_claims()
    existing = claims.get(card_id)
    if not existing or existing.get("agent") != agent_name:
        return {"ok": False, "error": f"Card '{card_id}' not claimed by '{agent_name}'."}

    del claims[card_id]
    _save_claims(claims)

    return {
        "ok": True,
        "card_id": card_id,
        "agent_name": agent_name,
        "released_at": datetime.now(timezone.utc).isoformat(),
    }


def team_status_from_claims() -> dict:
    """Get team status from file-based claims."""
    claims = _load_claims()

    agents: dict[str, list[str]] = {}
    for card_id, claim in claims.items():
        agent = claim.get("agent", "unknown")
        agents.setdefault(agent, []).append(card_id)

    return {
        "ok": True,
        "agents": [
            {"name": name, "active_cards": cards, "card_count": len(cards)}
            for name, cards in sorted(agents.items())
        ],
        "agent_count": len(agents),
        "total_claimed": len(claims),
    }


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------


def save_feedback(
    message: str,
    *,
    category: str = "improvement",
    tool_name: str | None = None,
    context: str | None = None,
) -> dict:
    """Save a CLI feedback item to .cli_feedback.json.

    Args:
        message: Feedback message.
        category: One of: missing_feature, bug, error, improvement, usability.
        tool_name: Which tool/command this relates to.
        context: Brief session context.

    Returns:
        Dict with saved (bool) and total_items count.
    """
    import os
    import tempfile

    from codecks_cli.config import _PROJECT_ROOT

    valid_categories = {"missing_feature", "bug", "error", "improvement", "usability"}
    if category not in valid_categories:
        return {
            "ok": False,
            "error": f"Invalid category: {category}. Must be one of: {', '.join(sorted(valid_categories))}",
        }

    feedback_path = os.path.join(_PROJECT_ROOT, ".cli_feedback.json")
    items: list[dict] = []
    try:
        with open(feedback_path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            items = data["items"]
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    item: dict = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "category": category,
        "message": message,
    }
    if tool_name:
        item["tool_name"] = tool_name
    if context:
        item["context"] = context

    items.append(item)
    if len(items) > 200:
        items = items[-200:]

    out_data = {"items": items, "updated_at": datetime.now(timezone.utc).isoformat()}
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(feedback_path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(out_data, f, indent=2)
        os.replace(tmp, feedback_path)
    except BaseException:
        os.unlink(tmp)
        raise

    return {"ok": True, "saved": True, "total_items": len(items)}


# ---------------------------------------------------------------------------
# Undo / mutation snapshot
# ---------------------------------------------------------------------------

_UNDO_FILE = ".pm_undo.json"
_UNDO_PATH = os.path.join(_PROJECT_ROOT, _UNDO_FILE)


def snapshot_before_mutation(client: CodecksClient, card_ids: list[str]) -> None:
    """Save current state of cards about to be mutated for undo support.

    Stores status, priority, effort, and deck for each card.
    """
    cards = {}
    for cid in card_ids:
        try:
            card = client.get_card(cid, include_content=False, include_conversations=False)
            if isinstance(card, dict):
                cards[cid] = {
                    "status": card.get("status"),
                    "priority": card.get("priority"),
                    "effort": card.get("effort"),
                    "deck_name": card.get("deck_name") or card.get("deck"),
                }
        except Exception:
            pass  # Best-effort snapshot
    if not cards:
        return
    data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cards": cards,
    }
    try:
        undo_dir = os.path.dirname(_UNDO_PATH) or "."
        fd, tmp = tempfile.mkstemp(dir=undo_dir, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, _UNDO_PATH)
    except OSError:
        pass  # Non-fatal


def undo_last_mutation(client: CodecksClient) -> dict:
    """Revert cards to their state from the last undo snapshot.

    Returns:
        dict with ok, reverted_count, details.
    """
    try:
        with open(_UNDO_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {
            "ok": False,
            "error": "No undo snapshot found. Mutations save snapshots automatically.",
        }

    cards = data.get("cards", {})
    if not cards:
        return {"ok": False, "error": "Undo snapshot is empty."}

    reverted = []
    errors = []
    for cid, prev_state in cards.items():
        try:
            updates = {}
            if prev_state.get("status"):
                updates["status"] = prev_state["status"]
            if prev_state.get("priority"):
                updates["priority"] = prev_state["priority"]
            if prev_state.get("effort") is not None:
                updates["effort"] = prev_state["effort"]
            if updates:
                client.update_cards([cid], **updates)
                reverted.append(cid)
        except Exception as e:
            errors.append({"card_id": cid, "error": str(e)})

    # Remove undo file after use
    try:
        os.unlink(_UNDO_PATH)
    except OSError:
        pass

    return {
        "ok": True,
        "reverted_count": len(reverted),
        "reverted": reverted,
        "errors": errors,
        "snapshot_timestamp": data.get("timestamp"),
    }
