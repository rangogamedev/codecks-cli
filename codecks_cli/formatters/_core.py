"""Core output dispatchers and shared section helpers."""

import json

from codecks_cli import config


def pretty_print(data):
    print(json.dumps(data, indent=2, ensure_ascii=False))


def output(data, formatter=None, fmt="json", csv_formatter=None):
    """Output data in requested format."""
    if fmt == "csv" and csv_formatter:
        print(csv_formatter(data))
    elif fmt == "table" and formatter:
        print(formatter(data))
    else:
        print(json.dumps(data, indent=2, ensure_ascii=False))


def mutation_response(action, card_id=None, details=None, data=None, fmt="json"):
    """Print a mutation confirmation."""
    if fmt == "json" and config.RUNTIME_STRICT:
        payload = {
            "ok": True,
            "mutation": {
                "action": action,
                "card_id": card_id,
                "details": details,
            },
        }
        if data and data != {}:
            if not (
                set(data.keys()) <= {"payload", "actionId"} and data.get("payload") in (None, {})
            ):
                payload["data"] = data
        print(json.dumps(payload, ensure_ascii=False))
        return

    parts = [action]
    if card_id:
        parts.append(f"card {card_id}")
    if details:
        parts.append(details)
    summary = ": ".join(parts)
    print(f"OK: {summary}")
    if fmt == "json" and data and data != {}:
        # Suppress dispatch noise (empty payload + actionId only)
        if set(data.keys()) <= {"payload", "actionId"} and data.get("payload") in (None, {}):
            return
        print(json.dumps(data, indent=2, ensure_ascii=False))


def _card_section(lines, title, items):
    """Append a titled card section to *lines*. Shared by pm-focus and standup."""
    lines.append(f"{title} ({len(items)}):")
    if not items:
        lines.append("  - none")
        lines.append("")
        return
    for c in items:
        pri = c.get("priority") or "-"
        effort = c.get("effort")
        eff = "-" if effort is None else str(effort)
        lines.append(
            f"  - [{pri}] E:{eff} {c['title']} "
            f"({c.get('deck_name') or c.get('deck') or '-'}) {c['id']}"
        )
    lines.append("")
