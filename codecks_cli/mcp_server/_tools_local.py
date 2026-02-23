"""Local tools: PM session, feedback, planning, registry (12 tools, no API calls)."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from codecks_cli import CliError
from codecks_cli.config import _PROJECT_ROOT
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


def get_workflow_preferences() -> dict:
    """Load user workflow preferences from past sessions. No auth needed."""
    try:
        with open(_PREFS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        raw_prefs = data.get("observations", [])
        return _finalize_tool_result(
            {
                "found": True,
                "preferences": [_tag_user_text(p) if isinstance(p, str) else p for p in raw_prefs],
            }
        )
    except FileNotFoundError:
        return _finalize_tool_result({"found": False, "preferences": []})
    except (json.JSONDecodeError, OSError) as e:
        return _finalize_tool_result(_contract_error(f"Cannot read preferences: {e}", "error"))


def save_workflow_preferences(observations: list[str]) -> dict:
    """Save observed workflow patterns from current session. No auth needed."""
    try:
        observations = _validate_preferences(observations)
    except CliError as e:
        return _finalize_tool_result(_contract_error(str(e), "error"))
    data = {
        "observations": observations,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(_PREFS_PATH), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, _PREFS_PATH)
        except BaseException:
            os.unlink(tmp_path)
            raise
        return _finalize_tool_result({"saved": len(observations)})
    except OSError as e:
        return _finalize_tool_result(_contract_error(f"Cannot save preferences: {e}", "error"))


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
        "timestamp": datetime.now(timezone.utc).isoformat(),
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
        "updated_at": datetime.now(timezone.utc).isoformat(),
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
        "updated_at": datetime.now(timezone.utc).isoformat(),
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
    """
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


def register(mcp):
    """Register all local tools with the FastMCP instance."""
    mcp.tool()(get_pm_playbook)
    mcp.tool()(get_workflow_preferences)
    mcp.tool()(save_workflow_preferences)
    mcp.tool()(save_cli_feedback)
    mcp.tool()(get_cli_feedback)
    mcp.tool()(clear_cli_feedback)
    mcp.tool()(planning_init)
    mcp.tool()(planning_status)
    mcp.tool()(planning_update)
    mcp.tool()(planning_measure)
    mcp.tool()(get_tag_registry)
    mcp.tool()(get_lane_registry)
