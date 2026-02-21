"""
Shared pure-utility functions for codecks-cli.

These helpers have no business logic and no side effects.
They are used across cards.py, client.py, formatters.py, and setup_wizard.py.
"""

from datetime import datetime, timezone

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
        return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
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
