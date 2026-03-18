"""Admin operations — direct dispatch API calls.

Uses Codecks dispatch endpoints discovered via network inspection.
No Playwright dependency required.

Discovered endpoints:
  - projects/addTag:    {projectId, tag}
  - decks/create:       {projectId, title}
  - decks/delete:       {id}
  - milestones/create:  {name, userId, accountId, color, date, isGlobal, projectIds}
  - milestones/delete:  {id}
  - projects/create:    {name, accountId, defaultUserAccess} (enum values TBD)
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
    result = api.query(
        {"_root": [{"account": [{"roles": ["userId", {"user": ["id", "name"]}]}]}]}
    )
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


def _resolve_deck_id(deck_name: str) -> str:
    """Resolve a deck name to its UUID."""
    from codecks_cli.cards import list_decks

    result = list_decks()
    for _key, deck in result.get("deck", {}).items():
        if deck.get("title", "").lower() == deck_name.lower():
            return deck["id"]
    raise CliError(f"[ERROR] Deck '{deck_name}' not found.")


# ---------------------------------------------------------------------------
# Admin operations
# ---------------------------------------------------------------------------


def create_tag(name: str, color: str | None = None) -> dict[str, Any]:
    """Create a new project-level tag via dispatch API.

    Args:
        name: Tag name.
        color: Optional hex color (reserved for future use).

    Returns:
        Dict with ok, tag_name, and source.
    """
    project_id = _get_primary_project_id()
    payload: dict[str, Any] = {"projectId": project_id, "tag": name}

    try:
        api.dispatch("projects/addTag", payload)
        return {"ok": True, "tag_name": name, "source": "api"}
    except CliError as e:
        return {"ok": False, "error": str(e)}


def create_deck(name: str, project: str | None = None) -> dict[str, Any]:
    """Create a new deck in a project via dispatch API.

    Args:
        name: Deck name.
        project: Project name (defaults to primary project).

    Returns:
        Dict with ok, deck_name, project_name, and source.
    """
    project_id = _get_primary_project_id()
    project_name = project or "primary"
    payload = {"projectId": project_id, "title": name}

    try:
        result = api.dispatch("decks/create", payload)
        deck_id = result.get("payload", {}).get("id", "")
        return {
            "ok": True,
            "deck_name": name,
            "deck_id": deck_id,
            "project_name": project_name,
            "source": "api",
        }
    except CliError as e:
        return {"ok": False, "error": str(e)}


def create_milestone(
    name: str, target_date: str | None = None
) -> dict[str, Any]:
    """Create a release milestone via dispatch API.

    Args:
        name: Milestone name.
        target_date: Target date (YYYY-MM-DD). Defaults to 30 days from now.

    Returns:
        Dict with ok, milestone_name, and source.
    """
    import datetime

    account_id = _get_account_id()
    user_id = _get_user_id()
    project_id = _get_primary_project_id()

    if not target_date:
        target_date = (
            datetime.date.today() + datetime.timedelta(days=30)
        ).isoformat()

    payload = {
        "name": name,
        "userId": user_id,
        "accountId": account_id,
        "color": "blue",
        "date": target_date,
        "isGlobal": False,
        "projectIds": [project_id],
    }

    try:
        result = api.dispatch("milestones/create", payload)
        milestone_id = result.get("payload", {}).get("id", "")
        return {
            "ok": True,
            "milestone_name": name,
            "milestone_id": milestone_id,
            "source": "api",
        }
    except CliError as e:
        return {"ok": False, "error": str(e)}


def create_project(name: str) -> dict[str, Any]:
    """Create a new Codecks project via dispatch API.

    Args:
        name: Project name.

    Returns:
        Dict with ok, project_name, and source.
    """
    account_id = _get_account_id()
    payload = {
        "name": name,
        "accountId": account_id,
        "defaultUserAccess": "readWrite",
    }

    try:
        result = api.dispatch("projects/create", payload)
        return {"ok": True, "project_name": name, "source": "api"}
    except CliError as e:
        return {"ok": False, "error": str(e)}


def archive_deck(deck_name: str) -> dict[str, Any]:
    """Delete a deck via dispatch API.

    Note: Codecks dispatch API supports decks/delete but not a separate
    archive action. This deletes the deck (cards are preserved).

    Args:
        deck_name: Name of the deck to delete.

    Returns:
        Dict with ok, deck_name, and source.
    """
    deck_id = _resolve_deck_id(deck_name)
    payload = {"id": deck_id}

    try:
        api.dispatch("decks/delete", payload)
        return {"ok": True, "deck_name": deck_name, "source": "api"}
    except CliError as e:
        return {"ok": False, "error": str(e)}
