"""Activity feed formatters."""

from codecks_cli import config
from codecks_cli._utils import _get_field
from codecks_cli.cards import load_milestone_names, load_users
from codecks_cli.formatters._table import _table, _trunc


def resolve_activity_val(field, val, ms_names, user_names):
    """Resolve a diff value to a human-readable string."""
    if val is None:
        return "none"
    if field == "priority":
        return config.PRI_LABELS.get(val, val)
    if field == "milestoneId" and ms_names:
        return ms_names.get(val, val)
    if field == "assigneeId" and user_names:
        return user_names.get(val, val)
    return val


def format_activity_table(result):
    """Format activity feed as readable text."""
    activities = result.get("activity", {})
    if not activities:
        return "No activity found."
    users = result.get("user", {})
    decks = result.get("deck", {})
    card_data = result.get("card", {})
    ms_names = load_milestone_names()
    user_names = load_users()
    cols = [("Time", 18), ("Type", 18), ("By", 12), ("Deck", 14), ("Card", 20), ("Details", 0)]
    rows = []
    for _key, act in activities.items():
        ts = (_get_field(act, "created_at", "createdAt") or "")[:16].replace("T", " ")
        changer_id = act.get("changer")
        changer = users.get(changer_id, {}).get("name", "") if changer_id else ""
        deck_id = act.get("deck")
        deck_name = decks.get(deck_id, {}).get("title", "") if deck_id else ""
        card_id = act.get("card")
        card_title = ""
        if card_id and card_data:
            card_title = card_data.get(card_id, {}).get("title", "")
        diff = act.get("data", {}).get("diff", {})
        details = format_activity_diff(diff, ms_names, user_names)
        rows.append(
            (
                ts,
                act.get("type", "?"),
                changer,
                _trunc(deck_name, 14),
                _trunc(card_title, 20),
                details,
            )
        )
    return _table(cols, rows, f"Total: {len(activities)} events")


def format_activity_diff(diff, ms_names, user_names):
    """Format an activity diff dict into a human-readable string."""
    if not diff:
        return ""
    parts = []
    for field, change in diff.items():
        if field == "tags":
            continue  # Skip — masterTags is authoritative
        if field == "masterTags":
            if isinstance(change, dict):
                added = change.get("+", [])
                removed = change.get("-", [])
                if added:
                    parts.append(f"tags +[{', '.join(added)}]")
                if removed:
                    parts.append(f"tags -[{', '.join(removed)}]")
            continue
        label = field.replace("Id", "").replace("_", " ")
        if isinstance(change, list) and len(change) == 2:
            old, new = change
            old = resolve_activity_val(field, old, ms_names, user_names)
            new = resolve_activity_val(field, new, ms_names, user_names)
            parts.append(f"{label}: {old} -> {new}")
        elif isinstance(change, dict):
            added = change.get("+", [])
            removed = change.get("-", [])
            if added:
                parts.append(f"{label} +[{', '.join(str(v) for v in added)}]")
            if removed:
                parts.append(f"{label} -[{', '.join(str(v) for v in removed)}]")
        else:
            parts.append(f"{label}: {change}")
    return _trunc("; ".join(parts), 60)
