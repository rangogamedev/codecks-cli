"""Admin operations — direct dispatch API calls.

Uses Codecks dispatch endpoints discovered via network inspection.
No Playwright dependency required.

Discovered endpoints and their field names:
  - projects/addTag:    {projectId, tag}
  - projects/create:    {name, accountId, defaultUserAccess} (enum: "everyone")
      Returns: {payload: {id: "<uuid>"}}
  - decks/create:       {projectId, title}
      Returns: {payload: {id: "<uuid>"}}
  - decks/delete:       {id}       (NOTE: uses 'id', not 'deckId')
  - milestones/create:  {name, userId, accountId, color, date, isGlobal, projectIds}
      color: one of "blue", "green", "red", "yellow", "purple", "orange", "pink", "teal"
      date: ISO date string (YYYY-MM-DD)
      projectIds: array of project UUIDs
      Returns: {payload: {id: "<uuid>"}}
  - milestones/delete:  {id}
  - cards/update:       {id, ...}  (NOTE: uses 'id', not 'cardId')
"""

from __future__ import annotations

from typing import Any

from codecks_cli import api, config
from codecks_cli.exceptions import CliError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_account_id() -> str:
    """Get the account UUID via the Codecks query API."""
    result = api.query({"_root": [{"account": ["id"]}]})
    for _key, acc in result.get("account", {}).items():
        return acc["id"]
    raise CliError("[ERROR] Could not resolve account ID.")


def _get_user_id() -> str:
    """Get the current user's UUID via the Codecks query API."""
    result = api.query({"_root": [{"account": [{"roles": ["userId", {"user": ["id", "name"]}]}]}]})
    # Return first user (account owner / primary user)
    for _key, user in result.get("user", {}).items():
        return user["id"]
    raise CliError("[ERROR] Could not resolve user ID.")


def _get_primary_project_id() -> str:
    """Resolve the primary project ID by querying decks.

    Returns the projectId that owns the most decks (heuristic for primary).
    """
    from codecks_cli.cards import list_projects

    projects = list_projects()
    if not projects:
        raise CliError("[ERROR] No projects found. Cannot resolve project ID.")

    best_pid = max(projects, key=lambda pid: projects[pid].get("deck_count", 0))
    return best_pid


def _resolve_project_id(project_name: str | None = None) -> str:
    """Resolve a project name to its UUID.

    Args:
        project_name: Project name (case-insensitive). If None, returns primary project.

    Returns:
        Project UUID.
    """
    if project_name is None:
        return _get_primary_project_id()

    from codecks_cli.cards import list_projects, load_project_names

    projects = list_projects()
    for pid, info in projects.items():
        if info.get("name", "").lower() == project_name.lower():
            return pid

    # Fallback: check .env mapping directly (handles zero-deck projects
    # that may not appear in list_projects if cache is stale)
    project_names = load_project_names()
    for pid, pname in project_names.items():
        if pname.lower() == project_name.lower():
            return pid

    raise CliError(
        f"[ERROR] Project '{project_name}' not found. "
        f"Available: {[info.get('name') for info in projects.values()]}"
    )


def _resolve_deck_id(deck_name: str, project: str | None = None) -> str:
    """Resolve a deck name to its UUID.

    Args:
        deck_name: Deck name (case-insensitive).
        project: Optional project name to scope resolution.
    """
    from codecks_cli.cards import resolve_deck_id

    return resolve_deck_id(deck_name, project=project)


# ---------------------------------------------------------------------------
# Admin operations
# ---------------------------------------------------------------------------


def create_tag(name: str, color: str | None = None, project: str | None = None) -> dict[str, Any]:
    """Create a new project-level tag via dispatch API.

    Args:
        name: Tag name.
        color: Optional hex color (reserved for future use).
        project: Project name (defaults to primary project).

    Returns:
        Dict with ok, tag_name, and source.
    """
    project_id = _resolve_project_id(project)
    payload: dict[str, Any] = {"projectId": project_id, "tag": name}

    try:
        api.dispatch("projects/addTag", payload)
        return {"ok": True, "tag_name": name, "source": "api"}
    except CliError as e:
        return {"ok": False, "error": str(e)}


def create_deck(name: str, project: str | None = None) -> dict[str, Any]:
    """Create a new deck in a project via dispatch API.

    Idempotent: if a deck with the same name already exists in the project,
    returns success with ``already_existed: True`` instead of creating a duplicate.

    Args:
        name: Deck name.
        project: Project name (defaults to primary project).

    Returns:
        Dict with ok, deck_name, project_name, and source.
    """
    project_id = _resolve_project_id(project)
    project_name = project or "primary"

    # Check for existing deck with the same name in the same project.
    config._cache.pop("decks", None)  # Force fresh query
    from codecks_cli.cards import list_decks

    existing = list_decks()
    for _key, deck in existing.get("deck", {}).items():
        if deck.get("title", "").lower() == name.lower() and deck.get("projectId") == project_id:
            return {
                "ok": True,
                "already_existed": True,
                "deck_name": deck.get("title", name),
                "deck_id": deck.get("id", _key),
                "project_name": project_name,
                "source": "cache",
            }

    payload = {"projectId": project_id, "title": name}

    try:
        result = api.dispatch("decks/create", payload)
        deck_id = result.get("payload", {}).get("id", "")
        config._cache.pop("decks", None)  # Invalidate so next query sees new deck
        # Seed the deck into cache so immediate resolve_deck_id() calls find it
        # without waiting for the API to be consistent
        cached = config._cache.get("decks")
        if cached and isinstance(cached.get("deck"), dict):
            cached["deck"][deck_id] = {
                "id": deck_id,
                "title": name,
                "projectId": project_id,
            }
        return {
            "ok": True,
            "already_existed": False,
            "deck_name": name,
            "deck_id": deck_id,
            "project_name": project_name,
            "source": "api",
        }
    except CliError as e:
        return {"ok": False, "error": str(e)}


VALID_MILESTONE_COLORS = {"blue", "green", "red", "yellow", "purple", "orange", "pink", "teal"}


def create_milestone(
    name: str,
    target_date: str | None = None,
    project: str | None = None,
    color: str = "blue",
) -> dict[str, Any]:
    """Create a release milestone via dispatch API.

    Auto-registers the new milestone in ``.env`` and in-memory config so it's
    immediately resolvable by name without a server restart.

    Args:
        name: Milestone name.
        target_date: Target date (YYYY-MM-DD). Defaults to 30 days from now.
        project: Project name (defaults to primary project).
        color: Milestone color. One of: blue, green, red, yellow, purple,
               orange, pink, teal. Default: blue.

    Returns:
        Dict with ok, milestone_name, milestone_id, and source.
    """
    import datetime

    # Validate color
    color = color.lower().strip()
    if color not in VALID_MILESTONE_COLORS:
        return {
            "ok": False,
            "error": (
                f"Invalid milestone color '{color}'. "
                f"Valid colors: {', '.join(sorted(VALID_MILESTONE_COLORS))}"
            ),
        }

    account_id = _get_account_id()
    user_id = _get_user_id()
    project_id = _resolve_project_id(project)

    if not target_date:
        target_date = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()

    payload = {
        "name": name,
        "userId": user_id,
        "accountId": account_id,
        "color": color,
        "date": target_date,
        "isGlobal": False,
        "projectIds": [project_id],
    }

    try:
        result = api.dispatch("milestones/create", payload)
        milestone_id = result.get("payload", {}).get("id", "")

        # Auto-register in .env and in-memory config
        if milestone_id:
            existing = config.env.get("CODECKS_MILESTONES", "")
            new_entry = f"{milestone_id}={name}"
            updated = f"{existing},{new_entry}" if existing else new_entry
            config.save_env_value("CODECKS_MILESTONES", updated)
            config.env["CODECKS_MILESTONES"] = updated

        return {
            "ok": True,
            "milestone_name": name,
            "milestone_id": milestone_id,
            "color": color,
            "source": "api",
        }
    except CliError as e:
        return {"ok": False, "error": str(e)}


def create_project(name: str) -> dict[str, Any]:
    """Create a new Codecks project via dispatch API.

    Auto-registers the new project in ``.env`` and in-memory config so it's
    immediately resolvable by name without a server restart.

    Args:
        name: Project name.

    Returns:
        Dict with ok, project_name, project_id, and source.
    """
    account_id = _get_account_id()
    payload = {
        "name": name,
        "accountId": account_id,
        "defaultUserAccess": "everyone",
    }

    try:
        result = api.dispatch("projects/create", payload)
        project_id = result.get("payload", {}).get("id", "")

        # Auto-register in .env and in-memory config
        if project_id:
            existing = config.env.get("CODECKS_PROJECTS", "")
            new_entry = f"{project_id}={name}"
            updated = f"{existing},{new_entry}" if existing else new_entry
            config.save_env_value("CODECKS_PROJECTS", updated)
            config.env["CODECKS_PROJECTS"] = updated

        return {
            "ok": True,
            "project_name": name,
            "project_id": project_id,
            "source": "api",
        }
    except CliError as e:
        return {"ok": False, "error": str(e)}


def archive_deck(deck_name: str, project: str | None = None) -> dict[str, Any]:
    """Delete a deck via dispatch API.

    Note: Codecks dispatch API supports decks/delete but not a separate
    archive action. This deletes the deck (cards are preserved).

    Args:
        deck_name: Name of the deck to delete.
        project: Optional project name to scope deck resolution.

    Returns:
        Dict with ok, deck_name, and source.
    """
    deck_id = _resolve_deck_id(deck_name, project=project)
    payload = {"id": deck_id}

    try:
        api.dispatch("decks/delete", payload)
        return {"ok": True, "deck_name": deck_name, "source": "api"}
    except CliError as e:
        return {"ok": False, "error": str(e)}
