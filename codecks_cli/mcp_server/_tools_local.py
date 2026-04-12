"""Local tools: PM session, feedback, planning, registry, cache (15 tools, no API calls)."""

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from codecks_cli import CliError
from codecks_cli.config import _PROJECT_ROOT, CACHE_TTL_SECONDS
from codecks_cli.mcp_server._core import _contract_error, _finalize_tool_result
from codecks_cli.mcp_server._security import _tag_user_text, _validate_input, _validate_preferences
from codecks_cli.planning import (
    get_planning_status,
    init_planning,
    measure_planning,
    update_planning,
)

_PLAYBOOK_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pm_playbook.md")
_PREFS_PATH = os.path.join(_PROJECT_ROOT, ".pm_preferences.json")
_FEEDBACK_PATH = os.path.join(_PROJECT_ROOT, ".cli_feedback.json")
_FEEDBACK_MAX_ITEMS = 200
_FEEDBACK_CATEGORIES = {"missing_feature", "bug", "error", "improvement", "usability"}
_PLANNING_DIR = Path(_PROJECT_ROOT)


def get_pm_playbook() -> dict:
    """Get PM session methodology guide. No auth needed."""
    try:
        with open(_PLAYBOOK_PATH, encoding="utf-8") as f:
            return _finalize_tool_result({"playbook": f.read()})
    except OSError as e:
        return _finalize_tool_result(_contract_error(f"Cannot read playbook: {e}", "error"))


def get_workflow_preferences(agent_name: str | None = None) -> dict:
    """Load user workflow preferences from past sessions. No auth needed.

    Args:
        agent_name: If set, returns agent-specific prefs merged with global.
            If None, returns only global observations (backward compat).
    """
    try:
        with open(_PREFS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        raw_prefs = data.get("observations", [])
        tagged = [_tag_user_text(p) if isinstance(p, str) else p for p in raw_prefs]

        if agent_name:
            agent_prefs = data.get("agent_prefs", {}).get(agent_name, [])
            tagged_agent = [_tag_user_text(p) if isinstance(p, str) else p for p in agent_prefs]
            return _finalize_tool_result(
                {
                    "found": True,
                    "agent_name": agent_name,
                    "agent_preferences": tagged_agent,
                    "global_preferences": tagged,
                }
            )
        return _finalize_tool_result(
            {
                "found": True,
                "preferences": tagged,
            }
        )
    except FileNotFoundError:
        return _finalize_tool_result({"found": False, "preferences": []})
    except (json.JSONDecodeError, OSError) as e:
        return _finalize_tool_result(_contract_error(f"Cannot read preferences: {e}", "error"))


def save_workflow_preferences(observations: list[str], agent_name: str | None = None) -> dict:
    """Save observed workflow patterns from current session. No auth needed.

    Args:
        observations: List of observation strings.
        agent_name: If set, saves to agent-specific prefs (alongside global).
            If None, saves to global observations (backward compat).
    """
    try:
        observations = _validate_preferences(observations)
    except CliError as e:
        return _finalize_tool_result(_contract_error(str(e), "error"))

    # Load existing data to preserve other sections
    existing: dict = {}
    try:
        with open(_PREFS_PATH, encoding="utf-8") as f:
            existing = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass

    if agent_name:
        # Agent-scoped: update only this agent's prefs, keep global intact
        agent_prefs = existing.get("agent_prefs", {})
        agent_prefs[agent_name] = observations
        existing["agent_prefs"] = agent_prefs
    else:
        # Global: replace observations, keep agent_prefs intact
        existing["observations"] = observations

    existing["updated_at"] = datetime.now(UTC).isoformat()

    try:
        fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(_PREFS_PATH), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2)
            os.replace(tmp_path, _PREFS_PATH)
        except BaseException:
            os.unlink(tmp_path)
            raise
        scope = f"agent:{agent_name}" if agent_name else "global"
        return _finalize_tool_result({"saved": len(observations), "scope": scope})
    except OSError as e:
        return _finalize_tool_result(_contract_error(f"Cannot save preferences: {e}", "error"))


def clear_workflow_preferences() -> dict:
    """Clear all saved workflow preferences. Use to reset learned patterns. No auth needed."""
    try:
        os.remove(_PREFS_PATH)
        return _finalize_tool_result({"cleared": True})
    except FileNotFoundError:
        return _finalize_tool_result({"cleared": False, "message": "No preferences file found"})
    except OSError as e:
        return _finalize_tool_result(_contract_error(f"Cannot clear preferences: {e}", "error"))


def save_cli_feedback(
    category: Literal["missing_feature", "bug", "error", "improvement", "usability"],
    message: str,
    tool_name: str | None = None,
    context: str | None = None,
) -> dict:
    """Save a CLI feedback item for the codecks-cli development team.

    Use when you notice missing features, encounter errors, or identify
    improvements during a PM session. Appends to .cli_feedback.json.
    No auth needed.

    Args:
        category: Type of feedback.
        message: The feedback itself (max 1000 chars).
        tool_name: Which MCP tool or CLI command this relates to.
        context: Brief session context (max 500 chars).
    """
    # Validate inputs
    try:
        message = _validate_input(message, "feedback_message")
        if context is not None:
            context = _validate_input(context, "feedback_context")
    except CliError as e:
        return _finalize_tool_result(_contract_error(str(e), "error"))

    if category not in _FEEDBACK_CATEGORIES:
        return _finalize_tool_result(
            _contract_error(
                f"Invalid category: {category!r}. "
                f"Must be one of: {', '.join(sorted(_FEEDBACK_CATEGORIES))}",
                "error",
            )
        )

    # Build the feedback item
    item: dict = {
        "timestamp": datetime.now(UTC).isoformat(),
        "category": category,
        "message": message,
    }
    if tool_name is not None:
        item["tool_name"] = tool_name
    if context is not None:
        item["context"] = context

    # Load existing feedback (or start fresh)
    items: list[dict] = []
    try:
        with open(_FEEDBACK_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            items = data["items"]
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass  # Start with empty list

    # Append and cap at max items (remove oldest if over limit)
    items.append(item)
    if len(items) > _FEEDBACK_MAX_ITEMS:
        items = items[-_FEEDBACK_MAX_ITEMS:]

    # Atomic write
    out_data = {
        "items": items,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    try:
        fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(_FEEDBACK_PATH), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(out_data, f, indent=2)
            os.replace(tmp_path, _FEEDBACK_PATH)
        except BaseException:
            os.unlink(tmp_path)
            raise
        return _finalize_tool_result({"saved": True, "total_items": len(items)})
    except OSError as e:
        return _finalize_tool_result(_contract_error(f"Cannot save feedback: {e}", "error"))


def get_cli_feedback(
    category: Literal["missing_feature", "bug", "error", "improvement", "usability"] | None = None,
) -> dict:
    """Read saved CLI feedback items. Optionally filter by category. No auth needed.

    Args:
        category: Filter to a specific feedback category.

    Returns:
        Dict with found (bool), items (list), and count.
    """
    try:
        with open(_FEEDBACK_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            return _finalize_tool_result({"found": False, "items": [], "count": 0})
        items = data["items"]
        if category is not None:
            items = [i for i in items if i.get("category") == category]
        return _finalize_tool_result({"found": bool(items), "items": items, "count": len(items)})
    except FileNotFoundError:
        return _finalize_tool_result({"found": False, "items": [], "count": 0})
    except (json.JSONDecodeError, OSError) as e:
        return _finalize_tool_result(_contract_error(f"Cannot read feedback: {e}", "error"))


def clear_cli_feedback(
    category: Literal["missing_feature", "bug", "error", "improvement", "usability"] | None = None,
) -> dict:
    """Clear resolved CLI feedback items. Optionally filter by category. No auth needed.

    Use after fixing issues reported in .cli_feedback.json to keep the file tidy.

    Args:
        category: Clear only this category (default: clear all items).

    Returns:
        Dict with cleared (int) and remaining (int) counts.
    """
    if category is not None and category not in _FEEDBACK_CATEGORIES:
        return _finalize_tool_result(
            _contract_error(
                f"Invalid category: {category!r}. "
                f"Must be one of: {', '.join(sorted(_FEEDBACK_CATEGORIES))}",
                "error",
            )
        )

    # Load existing feedback
    items: list[dict] = []
    try:
        with open(_FEEDBACK_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            items = data["items"]
    except FileNotFoundError:
        return _finalize_tool_result({"cleared": 0, "remaining": 0})
    except (json.JSONDecodeError, OSError) as e:
        return _finalize_tool_result(_contract_error(f"Cannot read feedback: {e}", "error"))

    original_count = len(items)
    if category is not None:
        remaining = [i for i in items if i.get("category") != category]
    else:
        remaining = []

    cleared = original_count - len(remaining)

    # Atomic write
    out_data = {
        "items": remaining,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    try:
        fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(_FEEDBACK_PATH), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(out_data, f, indent=2)
            os.replace(tmp_path, _FEEDBACK_PATH)
        except BaseException:
            os.unlink(tmp_path)
            raise
        return _finalize_tool_result({"cleared": cleared, "remaining": len(remaining)})
    except OSError as e:
        return _finalize_tool_result(_contract_error(f"Cannot write feedback: {e}", "error"))


def planning_init(force: bool = False) -> dict:
    """Create lean planning files (task_plan.md, findings.md, progress.md) in project root.

    Token-optimized templates for AI agent sessions. No auth needed.

    Args:
        force: Overwrite existing files (default False, skips existing).
    """
    return _finalize_tool_result(init_planning(_PLANNING_DIR, force=force))


def planning_status() -> dict:
    """Get compact planning status: goal, phases, decisions, errors, token count.

    Cheaper than reading raw planning files. No auth needed.
    """
    return _finalize_tool_result(get_planning_status(_PLANNING_DIR))


def planning_update(
    operation: Literal[
        "goal",
        "advance",
        "phase_status",
        "error",
        "decision",
        "finding",
        "issue",
        "log",
        "file_changed",
        "test",
    ],
    text: str | None = None,
    phase: int | None = None,
    status: str | None = None,
    rationale: str | None = None,
    section: str | None = None,
    resolution: str | None = None,
    test_name: str | None = None,
    expected: str | None = None,
    actual: str | None = None,
    result: str | None = None,
    agent_name: str | None = None,
) -> dict:
    """Update planning files mechanically (saves tokens vs reading/writing).

    No auth needed. Operations and required args:
        goal:         text (the goal description)
        advance:      phase (optional int, auto-advances if omitted)
        phase_status: phase (int), status (pending/in_progress/complete)
        error:        text (error message)
        decision:     text (decision), rationale
        finding:      section (e.g. Requirements, Research), text
        issue:        text (issue description), resolution
        log:          text (action taken)
        file_changed: text (file path)
        test:         test_name, expected, actual, result (pass/fail)

    Optional:
        agent_name: If set, prefixes log/error entries with [agent_name].
    """
    # Prefix text with agent name for log/error operations
    if agent_name and text and operation in ("log", "error", "file_changed"):
        text = f"[{agent_name}] {text}"

    return _finalize_tool_result(
        update_planning(
            _PLANNING_DIR,
            operation,
            text=text,
            phase=phase,
            status=status,
            rationale=rationale,
            section=section,
            resolution=resolution,
            test_name=test_name,
            expected=expected,
            actual=actual,
            result=result,
        )
    )


def planning_measure(
    operation: Literal["snapshot", "report", "compare_templates"],
) -> dict:
    """Track token usage of planning files over time.

    No auth needed. Operations:
        snapshot:          Measure current files, save to .plan_metrics.jsonl.
        report:            Current state + historical peak/growth + savings.
        compare_templates: Old (commented) vs new (lean) template comparison.
    """
    return _finalize_tool_result(measure_planning(_PLANNING_DIR, operation))


def get_tag_registry(
    category: Literal["system", "discipline"] | None = None,
) -> dict:
    """Get the local tag taxonomy (definitions, hero tags, lane-tag mappings).

    Returns all TagDefinitions as dicts plus pre-built sets.
    Use list_tags() for live API tags; this tool reads the local registry.
    No auth needed.

    Note: Tag *creation* is not supported via the API. To add new project-level
    tags, use the Codecks web UI. This registry defines the CLI's known tags.

    Args:
        category: Filter to 'system' or 'discipline' tags only.
    """
    from codecks_cli.tags import HERO_TAGS, LANE_TAGS, TAGS, tags_by_category

    if category is not None:
        tags = tags_by_category(category)
    else:
        tags = TAGS
    tag_dicts = [
        {
            "name": t.name,
            "display_name": t.display_name,
            "category": t.category,
            "description": t.description,
        }
        for t in tags
    ]
    return _finalize_tool_result(
        {
            "tags": tag_dicts,
            "count": len(tag_dicts),
            "hero_tags": list(HERO_TAGS),
            "lane_tags": {k: list(v) for k, v in LANE_TAGS.items()},
        }
    )


def get_lane_registry(
    required_only: bool = False,
) -> dict:
    """Get the local lane (deck category) definitions and metadata.

    Returns all LaneDefinitions as dicts plus required/optional lane name lists.
    No auth needed.

    Args:
        required_only: If True, return only required lanes (code, design).
    """
    from codecks_cli.lanes import LANES, optional_lanes, required_lanes

    if required_only:
        lanes = required_lanes()
    else:
        lanes = LANES
    lane_dicts = [
        {
            "name": ln.name,
            "display_name": ln.display_name,
            "required": ln.required,
            "keywords": list(ln.keywords),
            "default_checklist": list(ln.default_checklist),
            "tags": list(ln.tags),
            "cli_help": ln.cli_help,
        }
        for ln in lanes
    ]
    return _finalize_tool_result(
        {
            "lanes": lane_dicts,
            "count": len(lane_dicts),
            "required_lanes": [ln.name for ln in required_lanes()],
            "optional_lanes": [ln.name for ln in optional_lanes()],
        }
    )


def warm_cache(force: bool = False) -> dict:
    """Prefetch project snapshot for fast reads. Call at session start.

    Fetches all cards, hand, account, decks, pm_focus, standup and caches
    in memory + disk. Subsequent read tools serve from cache (~5ms vs ~1.5s).

    Skips if cache is already valid (unless force=True). In a team, only
    the lead agent needs to call this — other agents benefit automatically.

    Args:
        force: Always re-fetch even if cache is valid (default: False).

    Returns:
        Dict with card_count, hand_size, deck_count, fetched_at.
        If skipped: {ok, skipped, message, cache_age_seconds, ...}.
    """
    from codecks_cli.mcp_server._core import (
        _get_cache_metadata,
        _is_cache_valid,
        _warm_cache_impl,
    )

    try:
        if not force and _is_cache_valid():
            meta = _get_cache_metadata()
            return _finalize_tool_result(
                {"ok": True, "skipped": True, "message": "Cache already valid", **meta}
            )
        return _finalize_tool_result(_warm_cache_impl())
    except Exception as e:
        return _finalize_tool_result(_contract_error(f"Cache warming failed: {e}", "error"))


def cache_status() -> dict:
    """Check snapshot cache status without fetching. No auth needed.

    Returns:
        Dict with cached, cache_age_seconds, card_count, hand_size,
        ttl_seconds, ttl_remaining_seconds, expired.
    """
    from codecks_cli.mcp_server import _core

    _core._load_cache_from_disk()
    meta = _core._get_cache_metadata()
    if meta.get("cached"):
        snapshot = _core._get_snapshot()
        if snapshot:
            cards_result = snapshot.get("cards_result")
            meta["card_count"] = len(
                cards_result.get("cards", []) if isinstance(cards_result, dict) else []
            )
            meta["hand_size"] = len(snapshot.get("hand", []))
        meta["ttl_seconds"] = CACHE_TTL_SECONDS
        age = meta.get("cache_age_seconds", 0)
        meta["ttl_remaining_seconds"] = max(0, round(CACHE_TTL_SECONDS - age, 1))
        meta["expired"] = age >= CACHE_TTL_SECONDS
    return _finalize_tool_result(meta)


def session_start(agent_name: str | None = None) -> dict:
    """One-call session initialization. Replaces warm_cache + standup + get_account + get_workflow_preferences.

    Call this FIRST in every session. Warms the cache, then assembles a complete
    session context from cached data. Returns everything an agent needs to start working.

    Args:
        agent_name: If set, loads agent-specific prefs and registers the agent session.

    Returns:
        Dict with account, standup, preferences, project_context (deck_names, tag_names,
        lane_names, card_count, hand_size), and cache metadata.
    """
    from codecks_cli.mcp_server import _core

    # Step 1: Ensure cache is warm
    try:
        if not _core._is_cache_valid():
            _core._warm_cache_impl()
    except Exception as e:
        return _finalize_tool_result(_contract_error(f"Session start failed (cache): {e}", "error"))

    snapshot = _core._get_snapshot()
    if snapshot is None:
        return _finalize_tool_result(_contract_error("Cache unavailable after warming", "error"))

    # Step 2: Extract account and standup from cache
    account = snapshot.get("account", {})
    standup_data = snapshot.get("standup", {})

    # Step 3: Load preferences inline (no tool call)
    prefs_result: dict = {"found": False, "preferences": []}
    try:
        with open(_PREFS_PATH, encoding="utf-8") as f:
            pdata = json.load(f)
        raw_prefs = pdata.get("observations", [])
        prefs_result = {"found": True, "preferences": raw_prefs}
        if agent_name:
            agent_prefs = pdata.get("agent_prefs", {}).get(agent_name, [])
            prefs_result["agent_preferences"] = agent_prefs
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass

    # Step 4: Build project context from cache + registries
    from codecks_cli.lanes import LANES
    from codecks_cli.tags import HERO_TAGS, LANE_TAGS, TAGS

    decks = snapshot.get("decks", [])
    deck_names = []
    if isinstance(decks, list):
        for d in decks:
            if isinstance(d, dict):
                deck_names.append(d.get("title", ""))

    cards_result = snapshot.get("cards_result", {})
    card_count = len(cards_result.get("cards", []) if isinstance(cards_result, dict) else [])
    hand = snapshot.get("hand", [])
    hand_size = len(hand) if isinstance(hand, list) else 0

    # Tag registry (replaces get_tag_registry tool)
    tag_registry = [
        {"name": t.name, "display_name": t.display_name, "category": t.category} for t in TAGS
    ]

    # Lane registry (replaces get_lane_registry tool)
    lane_registry = [
        {"name": ln.name, "display_name": ln.display_name, "required": ln.required} for ln in LANES
    ]

    project_context = {
        "deck_names": deck_names,
        "tag_names": [t.name for t in TAGS],
        "lane_names": [ln.name for ln in LANES],
        "card_count": card_count,
        "hand_size": hand_size,
        "tag_registry": tag_registry,
        "lane_registry": lane_registry,
        "hero_tags": list(HERO_TAGS),
        "lane_tags": {k: list(v) for k, v in LANE_TAGS.items()},
    }

    # Compact playbook rules (replaces get_pm_playbook/get_team_playbook tools)
    playbook_rules = [
        "Call session_start() first in every session",
        "Use summary_only=True on pm_focus/standup for quick checks",
        "Use find_and_update() for search+update workflows (2 calls, not 5+)",
        "Use quick_overview() for aggregate counts (no card details)",
        "Doc cards: no status/priority/effort changes",
        "Card IDs must be full 36-char UUIDs",
        "Rate limit: 40 req/5s",
        "Use claim_card/release_card for multi-agent coordination",
    ]

    # Step 5: Register agent if named
    if agent_name:
        _core._register_agent(agent_name)

    # Removed tools migration guide (helps agents discover new patterns)
    removed_tools = {
        "get_pm_playbook": "Rules injected in session_start().playbook_rules",
        "get_team_playbook": "Rules injected in session_start().playbook_rules",
        "get_tag_registry": "Included in session_start().project_context.tag_registry",
        "get_lane_registry": "Included in session_start().project_context.lane_registry",
        "planning_init": "CLI: py codecks_api.py plan init",
        "planning_status": "CLI: py codecks_api.py plan status",
        "planning_update": "CLI: py codecks_api.py plan update",
        "planning_measure": "CLI: py codecks_api.py plan measure",
        "save_cli_feedback": "CLI: py codecks_api.py feedback save",
        "get_cli_feedback": "CLI: py codecks_api.py feedback list",
        "clear_cli_feedback": "CLI: py codecks_api.py feedback clear",
        "warm_cache": "session_start() already warms cache",
        "cache_status": "CLI: py codecks_api.py cache status",
        "partition_by_lane": "Use partition_cards(by='lane')",
        "partition_by_owner": "Use partition_cards(by='owner')",
        "tick_all_checkboxes": "Use tick_checkboxes(all=True)",
    }

    result = {
        "ok": True,
        "account": account,
        "standup": standup_data,
        "preferences": prefs_result,
        "project_context": project_context,
        "playbook_rules": playbook_rules,
        "removed_tools": removed_tools,
    }
    result.update(_core._get_cache_metadata())
    return _finalize_tool_result(result)


def register(mcp):
    """Register local tools with the FastMCP instance.

    Tools removed in v0.5.0 (available via CLI or session_start):
    - get_pm_playbook → injected via session_start() / CLAUDE.md
    - get_tag_registry → included in session_start() project_context
    - get_lane_registry → included in session_start() project_context
    - planning_init/status/update/measure → CLI: py codecks_api.py plan <cmd>
    - save/get/clear_cli_feedback → CLI: py codecks_api.py feedback <cmd>
    - warm_cache → session_start() already warms cache
    - cache_status → CLI: py codecks_api.py cache status
    """
    mcp.tool()(session_start)
    mcp.tool()(get_workflow_preferences)
    mcp.tool()(save_workflow_preferences)
    mcp.tool()(clear_workflow_preferences)
