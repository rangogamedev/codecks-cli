"""
Shared pure-utility functions for codecks-cli.

These helpers have no business logic and no side effects.
They are used across cards.py, client.py, formatters.py, and setup_wizard.py.
"""

from datetime import UTC, datetime

from codecks_cli.exceptions import CliError


def _get_field(d, snake, camel):
    """Get a value from a dict trying snake_case then camelCase key."""
    if snake in d:
        return d.get(snake)
    return d.get(camel)


def get_card_tags(card):
    """Get normalized tag list from a card dict (handles API key variants)."""
    return card.get("tags") or card.get("master_tags") or card.get("masterTags") or []


def _parse_multi_value(raw, valid_set, field_name):
    """Parse a comma-separated filter string and validate each value.
    Returns a list of validated values."""
    values = [v.strip() for v in raw.split(",") if v.strip()]
    for v in values:
        if v not in valid_set:
            raise CliError(
                f"[ERROR] Invalid {field_name} '{v}'. Valid: {', '.join(sorted(valid_set))}"
            )
    return values


def _parse_date(date_str):
    """Parse a YYYY-MM-DD date string into a datetime. Raises CliError on bad format."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError as e:
        raise CliError(f"[ERROR] Invalid date '{date_str}'. Use YYYY-MM-DD format.") from e


def _parse_iso_timestamp(ts):
    """Parse an ISO timestamp from the API into a datetime."""
    if not ts:
        return None
    try:
        # Handle both "2026-01-15T10:30:00Z" and "2026-01-15T10:30:00.000Z"
        clean = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(clean)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Flattened-card field accessors
#
# Cards returned by CodecksClient.list_cards() are flattened and enriched:
# they carry deck_name / owner_name / milestone_name / lastUpdatedAt and have
# NO 'project' key. Other producers (tests, MCP snapshots, the CLI) use the
# short spellings deck / owner / milestone / updated_at. These helpers accept
# both so consumers never silently miss data.
# ---------------------------------------------------------------------------


def card_deck_name(card) -> str:
    """Return a card's deck name ('deck' or flattened 'deck_name'), else ""."""
    return str(card.get("deck") or card.get("deck_name") or "")


def card_owner_name(card) -> str:
    """Return a card's owner name ('owner' or flattened 'owner_name'), else ""."""
    return str(card.get("owner") or card.get("owner_name") or "")


def card_milestone_name(card) -> str:
    """Return a card's milestone name ('milestone'/'milestone_name'), else ""."""
    return str(card.get("milestone") or card.get("milestone_name") or "")


def card_updated_at(card) -> str:
    """Return a card's last-updated timestamp string, else "".

    Accepts updated_at / updatedAt / last_updated_at / lastUpdatedAt.
    """
    for key in ("updated_at", "updatedAt", "last_updated_at", "lastUpdatedAt"):
        value = card.get(key)
        if value:
            return str(value)
    return ""


def card_is_doc(card) -> bool:
    """True if *card* is a doc card ('isDoc' / 'is_doc' / cardType == 'doc')."""
    return bool(
        card.get("isDoc") or card.get("is_doc") or str(card.get("cardType", "")).lower() == "doc"
    )


def build_deck_project_map(decks) -> dict[str, str]:
    """Map deck id AND lowercased deck name -> project name.

    *decks* is a list of deck dicts as returned by CodecksClient.list_decks()
    (id / title / project_name). Anything else yields an empty map.
    """
    mapping: dict[str, str] = {}
    if not isinstance(decks, list):
        return mapping
    for deck in decks:
        if not isinstance(deck, dict):
            continue
        project = (
            deck.get("project_name")
            or deck.get("project")
            or _get_field(deck, "project_id", "projectId")
            or ""
        )
        if not project:
            continue
        deck_id = deck.get("id")
        if deck_id:
            mapping[str(deck_id)] = str(project)
        title = deck.get("title") or deck.get("name")
        if title:
            mapping[str(title).lower()] = str(project)
    return mapping


def card_project_name(card, deck_project_map=None) -> str:
    """Resolve a card's project name, else "".

    Flattened cards carry no 'project' key, so fall back to resolving the
    card's deck (by id first, then by name) through *deck_project_map*.
    """
    explicit = card.get("project") or card.get("project_name")
    if explicit:
        return str(explicit)
    mapping: dict[str, str] = deck_project_map or {}
    deck_id = _get_field(card, "deck_id", "deckId")
    if deck_id and str(deck_id) in mapping:
        return str(mapping[str(deck_id)])
    deck_name = card_deck_name(card)
    if deck_name:
        return str(mapping.get(deck_name.lower(), ""))
    return ""


def card_matches_project(card, project, deck_project_map=None) -> bool:
    """True if *card* belongs to *project* (case-insensitive). Empty project matches all."""
    if not project:
        return True
    return card_project_name(card, deck_project_map).lower() == str(project).lower()
