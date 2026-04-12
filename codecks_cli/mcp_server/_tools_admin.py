"""Admin tools: project, deck, milestone, tag creation and deck deletion (5 tools).

Uses direct Codecks dispatch API endpoints. All calls are offloaded to a worker
thread via asyncio.to_thread() since the MCP server runs in an asyncio event loop.
"""

import asyncio

from codecks_cli import CliError
from codecks_cli.mcp_server._core import (
    _contract_error,
    _finalize_tool_result,
    _invalidate_cache,
)
from codecks_cli.mcp_server._security import _validate_input


def _run_admin(func, *args, **kwargs):
    """Call an admin function (sync, may use Playwright) and return its result."""
    result = func(*args, **kwargs)
    if result.get("ok"):
        _invalidate_cache()
    return _finalize_tool_result(result)


async def create_project(name: str) -> dict:
    """Create a new Codecks project.

    Uses direct Codecks dispatch API.

    Args:
        name: Project name (e.g., "Hafu Games Studio").

    Returns:
        Dict with ok, project_name, source.
    """
    try:
        name = _validate_input(name, "name")
    except CliError as e:
        return _finalize_tool_result(_contract_error(str(e), "error"))

    from codecks_cli import admin

    return await asyncio.to_thread(_run_admin, admin.create_project, name)


async def create_deck(name: str, project: str | None = None) -> dict:
    """Create a new deck in a project.

    Uses direct Codecks dispatch API.

    Args:
        name: Deck name (e.g., "Publishing").
        project: Project name. Defaults to the primary project.

    Returns:
        Dict with ok, deck_name, project_name, source.
    """
    try:
        name = _validate_input(name, "name")
        if project is not None:
            project = _validate_input(project, "project")
    except CliError as e:
        return _finalize_tool_result(_contract_error(str(e), "error"))

    from codecks_cli import admin

    return await asyncio.to_thread(_run_admin, admin.create_deck, name, project=project)


async def create_milestone(
    name: str,
    target_date: str | None = None,
    project: str | None = None,
    color: str = "blue",
) -> dict:
    """Create a release milestone.

    Uses direct Codecks dispatch API. Auto-registers in .env for immediate
    name resolution without server restart.

    Args:
        name: Milestone name (e.g., "Alpha").
        target_date: Optional target date (YYYY-MM or YYYY-MM-DD).
        project: Project name. Defaults to the primary project.
        color: Milestone color. Valid values: blue, green, red, yellow.
               Default: blue.

    Returns:
        Dict with ok, milestone_name, milestone_id, color, source.
    """
    # Pre-flight color validation (Codecks API is more restrictive than Python code)
    _API_VALID_COLORS = {"blue", "green", "red", "yellow"}
    if color and color.lower().strip() not in _API_VALID_COLORS:
        return _finalize_tool_result(
            _contract_error(
                f"Invalid milestone color '{color}'. "
                f"Valid: {', '.join(sorted(_API_VALID_COLORS))}. Default: blue.",
                "error",
                error_code="INVALID_INPUT",
            )
        )

    try:
        name = _validate_input(name, "name")
        if target_date is not None:
            target_date = _validate_input(target_date, "target_date")
        if project is not None:
            project = _validate_input(project, "project")
    except CliError as e:
        return _finalize_tool_result(_contract_error(str(e), "error"))

    from codecks_cli import admin

    return await asyncio.to_thread(
        _run_admin,
        admin.create_milestone,
        name,
        target_date=target_date,
        project=project,
        color=color,
    )


async def create_tag(name: str, color: str | None = None, project: str | None = None) -> dict:
    """Create a new project-level tag.

    Uses direct Codecks dispatch API.

    Args:
        name: Tag name (e.g., "legal").
        color: Optional hex color (e.g., "#ff0000").
        project: Project name. Defaults to the primary project.

    Returns:
        Dict with ok, tag_name, source.
    """
    try:
        name = _validate_input(name, "name")
        if color is not None:
            color = _validate_input(color, "color")
        if project is not None:
            project = _validate_input(project, "project")
    except CliError as e:
        return _finalize_tool_result(_contract_error(str(e), "error"))

    from codecks_cli import admin

    return await asyncio.to_thread(_run_admin, admin.create_tag, name, color=color, project=project)


async def archive_deck(deck: str) -> dict:
    """Archive a deck (reversible).

    Uses direct Codecks dispatch API.

    Args:
        deck: Deck name to archive.

    Returns:
        Dict with ok, deck_name, source.
    """
    try:
        deck = _validate_input(deck, "deck")
    except CliError as e:
        return _finalize_tool_result(_contract_error(str(e), "error"))

    from codecks_cli import admin

    return await asyncio.to_thread(_run_admin, admin.archive_deck, deck)


def register(mcp):
    """Register all admin tools with the FastMCP instance."""
    mcp.tool()(create_project)
    mcp.tool()(create_deck)
    mcp.tool()(create_milestone)
    mcp.tool()(create_tag)
    mcp.tool()(archive_deck)
