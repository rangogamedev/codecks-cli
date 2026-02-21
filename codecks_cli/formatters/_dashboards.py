"""PM dashboard formatters (pm-focus, standup)."""

from codecks_cli.formatters._core import _card_section


def format_pm_focus_table(report):
    """Format pm-focus report for human reading."""
    counts = report.get("counts", {})
    stale_days = report.get("filters", {}).get("stale_days", 14)
    lines = [
        "PM Focus Dashboard",
        "=" * 50,
        f"Started: {counts.get('started', 0)}  "
        f"Blocked: {counts.get('blocked', 0)}  "
        f"In Review: {counts.get('in_review', 0)}  "
        f"In hand: {counts.get('hand', 0)}  "
        f"Stale: {counts.get('stale', 0)}",
        "",
    ]
    _card_section(lines, "Blocked", report.get("blocked", []))
    _card_section(lines, "In Review", report.get("in_review", []))
    _card_section(lines, "In Hand", report.get("hand", []))
    if report.get("stale"):
        _card_section(lines, f"Stale (>{stale_days}d)", report.get("stale", []))
    _card_section(lines, "Suggested Next", report.get("suggested", []))
    return "\n".join(lines)


def format_standup_table(report):
    """Format standup report for human reading."""
    days = report.get("filters", {}).get("days", 2)
    lines = [
        "Standup Summary",
        "=" * 50,
        "",
    ]
    _card_section(lines, f"Done (last {days}d)", report.get("recently_done", []))
    _card_section(lines, "In Progress", report.get("in_progress", []))
    _card_section(lines, "Blocked", report.get("blocked", []))
    _card_section(lines, "In Hand", report.get("hand", []))
    return "\n".join(lines)
