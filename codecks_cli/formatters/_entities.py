"""Formatters for decks, projects, milestones, and stats."""

from codecks_cli.formatters._table import _table, _trunc


def format_decks_table(decks):
    """Format decks as a readable table.

    Accepts list of flat dicts from CodecksClient.list_decks().
    """
    if not decks:
        return "No decks found."
    cols = [("Title", 30), ("Project", 20), ("Cards", 6), ("ID", 0)]
    rows = []
    for deck in decks:
        rows.append(
            (
                _trunc(deck.get("title", ""), 30),
                deck.get("project_name", ""),
                str(deck.get("card_count", 0)),
                deck.get("id", ""),
            )
        )
    return _table(cols, rows, f"Total: {len(decks)} decks")


def format_projects_table(projects):
    """Format projects as a readable table.

    Accepts list of flat dicts from CodecksClient.list_projects().
    """
    if not projects:
        return "No projects found."
    lines = []
    for p in projects:
        lines.append(f"Project: {p.get('name', p.get('id', '?'))}")
        lines.append(f"  ID:    {p.get('id', '')}")
        lines.append(f"  Decks ({p.get('deck_count', 0)}): {', '.join(p.get('decks', []))}")
        lines.append("")
    return "\n".join(lines)


def format_milestones_table(milestones):
    """Format milestones as a readable table.

    Accepts list of flat dicts from CodecksClient.list_milestones().
    """
    if not milestones:
        return "No milestones found."
    lines = []
    for m in milestones:
        name = m.get("name", m.get("id", "?"))
        card_count = m.get("card_count", 0)
        lines.append(f"Milestone: {name}  (ID: {m.get('id', '')})")
        lines.append(f"  Cards ({card_count})")
        lines.append("")
    return "\n".join(lines)


def format_stats_table(stats):
    """Format card stats as readable text."""
    lines = [f"Total cards: {stats['total']}"]
    lines.append(f"Total effort: {stats['total_effort']}  Avg effort: {stats['avg_effort']}")
    lines.append("")
    lines.append("By Status:")
    for status, count in sorted(stats["by_status"].items()):
        lines.append(f"  {status:<16} {count}")
    lines.append("")
    lines.append("By Priority:")
    pri_labels = {"a": "a (high)", "b": "b (medium)", "c": "c (low)", "none": "none"}
    for pri, count in sorted(stats["by_priority"].items()):
        lines.append(f"  {pri_labels.get(pri, pri):<16} {count}")
    lines.append("")
    lines.append("By Deck:")
    for deck, count in sorted(stats["by_deck"].items()):
        lines.append(f"  {deck:<24} {count}")
    if stats.get("by_owner"):
        lines.append("")
        lines.append("By Owner:")
        for owner, count in sorted(stats["by_owner"].items()):
            lines.append(f"  {owner:<24} {count}")
    return "\n".join(lines)
