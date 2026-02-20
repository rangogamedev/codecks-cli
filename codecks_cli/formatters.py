"""
Output formatting functions for codecks-cli.
Table, CSV, and JSON output dispatchers.
"""

import csv
import io
import json
import re

from codecks_cli import config
from codecks_cli.cards import (
    _get_field,
    get_card_tags,
    load_milestone_names,
    load_project_names,
    load_users,
)

# ---------------------------------------------------------------------------
# Core output helpers
# ---------------------------------------------------------------------------


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


def _trunc(s, maxlen):
    """Truncate string with ellipsis indicator."""
    if not s:
        return ""
    return s[: maxlen - 1] + "\u2026" if len(s) > maxlen else s


_CONTROL_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _sanitize_str(s):
    """Strip ANSI escape sequences and control chars from table output.
    Preserves newlines (\\n) and tabs (\\t)."""
    if not s:
        return s
    return _CONTROL_RE.sub("", str(s))


def _table(columns, rows, footer=None):
    """Build a formatted table string.
    columns: list of (name, width) tuples. Last column has no width (fills).
    rows: list of tuples matching columns.
    footer: optional footer line."""
    # Header
    parts = []
    for i, (name, width) in enumerate(columns):
        if i == len(columns) - 1:
            parts.append(name)
        else:
            parts.append(f"{name:<{width}}")
    header = " ".join(parts)
    sep = "-" * max(len(header), 90)
    # Rows
    lines = [header, sep]
    for row in rows:
        parts = []
        for i, val in enumerate(row):
            safe = _sanitize_str(val) if isinstance(val, str) else str(val)
            if i == len(columns) - 1:
                parts.append(safe)
            else:
                parts.append(f"{safe:<{columns[i][1]}}")
        lines.append(" ".join(parts))
    if footer:
        lines.append(f"\n{footer}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Table formatters
# ---------------------------------------------------------------------------


def format_account_table(result):
    """Format account info as readable text."""
    acc = result.get("account", {})
    if not acc:
        return "No account data."
    for key, info in acc.items():
        return f"Account: {info.get('name', '?')}\nID:      {key}"


def format_cards_table(result):
    """Format cards as a readable table."""
    cards = result.get("card", {})
    if not cards:
        return "No cards found."
    cols = [
        ("Status", 14),
        ("Pri", 5),
        ("Eff", 4),
        ("Owner", 10),
        ("Deck", 16),
        ("Mstone", 10),
        ("Title", 34),
        ("Tags", 14),
        ("ID", 0),
    ]
    rows = []
    for key, card in cards.items():
        title_text = card.get("title", "")
        sub_count = card.get("sub_card_count")
        if sub_count:
            title_text = f"{title_text} [{sub_count} sub]"
        tags = get_card_tags(card)
        rows.append(
            (
                card.get("status", ""),
                config.PRI_LABELS.get(card.get("priority"), "-"),
                str(card.get("effort") or "-"),
                _trunc(card.get("owner_name", "") or "-", 10),
                _trunc(card.get("deck_name") or card.get("deck_id", ""), 16),
                _trunc(card.get("milestone_name") or "-", 10),
                _trunc(title_text, 34),
                _trunc(", ".join(tags), 14) if tags else "-",
                key,
            )
        )
    return _table(cols, rows, f"Total: {len(cards)} cards")


def format_card_detail(result):
    """Format a single card with full details."""
    cards = result.get("card", {})
    if not cards:
        return "Card not found."
    lines = []
    for key, card in cards.items():
        lines.append(f"Card:      {key}")
        lines.append(f"Title:     {card.get('title', '')}")
        is_doc = _get_field(card, "is_doc", "isDoc")
        if is_doc:
            lines.append("Type:      doc card")
        lines.append(f"Status:    {card.get('status', '')}")
        pri_raw = card.get("priority")
        pri_display = (
            f"{pri_raw} ({config.PRI_LABELS[pri_raw]})" if pri_raw in config.PRI_LABELS else "none"
        )
        lines.append(f"Priority:  {pri_display}")
        sev = card.get("severity")
        if sev:
            lines.append(f"Severity:  {sev}")
        lines.append(f"Effort:    {card.get('effort') or '-'}")
        lines.append(f"Deck:      {card.get('deck_name', card.get('deck_id', ''))}")
        lines.append(f"Owner:     {card.get('owner_name') or '-'}")
        ms = card.get("milestone_name", card.get("milestone_id"))
        lines.append(f"Milestone: {ms or '-'}")
        tags = get_card_tags(card)
        lines.append(f"Tags:      {', '.join(tags) if tags else '-'}")
        parent = _get_field(card, "parent_card_id", "parentCardId")
        if parent:
            lines.append(f"Hero:      {parent}")
        lines.append(f"In hand:   {'yes' if card.get('in_hand') else 'no'}")
        created = _get_field(card, "created_at", "createdAt") or ""
        lines.append(f"Created:   {created}")
        updated = _get_field(card, "last_updated_at", "lastUpdatedAt") or ""
        if updated:
            lines.append(f"Updated:   {updated}")
        content = card.get("content", "")
        if content:
            body_lines = content.split("\n", 1)
            body = body_lines[1].strip() if len(body_lines) > 1 else ""
            if body:
                lines.append(f"Content:   {body[:300]}")
        # Checklist progress
        cb_stats = _get_field(card, "checkbox_stats", "checkboxStats")
        if cb_stats and isinstance(cb_stats, dict) and cb_stats.get("total", 0) > 0:
            total = cb_stats["total"]
            checked = cb_stats.get("checked", 0)
            pct = int(100 * checked / total) if total else 0
            lines.append(f"Checklist: {checked}/{total} ({pct}%)")
        # Sub-cards
        child_cards = card.get("childCards")
        if child_cards:
            child_data = result.get("card", {})
            lines.append(f"Sub-cards ({len(child_cards)}):")
            for ckey in child_cards[:10]:
                child = child_data.get(ckey, {})
                lines.append(f"  - [{child.get('status', '?')}] {child.get('title', ckey)}")
            if len(child_cards) > 10:
                lines.append(f"  ... and {len(child_cards) - 10} more")
        # Conversations
        resolvables = card.get("resolvables") or []
        if resolvables:
            resolvable_data = result.get("resolvable", {})
            entry_data = result.get("resolvableEntry", {})
            user_data = result.get("user", {})
            open_count = sum(
                1
                for rid in resolvables
                if not _get_field(resolvable_data.get(rid, {}), "is_closed", "isClosed")
            )
            closed_count = len(resolvables) - open_count
            lines.append(
                f"Conversations ({len(resolvables)}: {open_count} open, {closed_count} closed):"
            )
            for rid in resolvables[:5]:
                r = resolvable_data.get(rid, {})
                creator_id = r.get("creator")
                creator_name = user_data.get(creator_id, {}).get("name", "?") if creator_id else "?"
                status = "closed" if _get_field(r, "is_closed", "isClosed") else "open"
                lines.append(f"  Thread {rid[:8]}.. ({status}, by {creator_name}):")
                entries = r.get("entries") or []
                for eid in entries[:3]:
                    e = entry_data.get(eid, {})
                    author_id = e.get("author")
                    author_name = (
                        user_data.get(author_id, {}).get("name", "?") if author_id else "?"
                    )
                    msg = (e.get("content") or "")[:120]
                    lines.append(f"    {author_name}: {msg}")
                if len(entries) > 3:
                    lines.append(f"    ... and {len(entries) - 3} more replies")
            if len(resolvables) > 5:
                lines.append(f"  ... and {len(resolvables) - 5} more threads")
        lines.append("")
    return "\n".join(lines)


def format_conversations_table(result):
    """Format conversations on a card as readable text."""
    cards = result.get("card", {})
    if not cards:
        return "Card not found."
    resolvable_data = result.get("resolvable", {})
    entry_data = result.get("resolvableEntry", {})
    user_data = result.get("user", {})
    lines = []
    for card_key, card in cards.items():
        lines.append(f"Conversations on {card.get('title', card_key)}:")
        resolvables = card.get("resolvables") or []
        if not resolvables:
            lines.append("  No conversations.")
            continue
        for rid in resolvables:
            r = resolvable_data.get(rid, {})
            creator_id = r.get("creator")
            creator_name = user_data.get(creator_id, {}).get("name", "?") if creator_id else "?"
            is_closed = _get_field(r, "is_closed", "isClosed")
            status = "closed" if is_closed else "open"
            created = _get_field(r, "created_at", "createdAt") or ""
            lines.append(f"  [{status}] Thread {rid} (by {creator_name}, {created})")
            entries = r.get("entries") or []
            for eid in entries:
                e = entry_data.get(eid, {})
                author_id = e.get("author")
                author_name = user_data.get(author_id, {}).get("name", "?") if author_id else "?"
                msg = e.get("content") or ""
                ts = _get_field(e, "created_at", "createdAt") or ""
                lines.append(f"    {author_name} ({ts}): {msg[:200]}")
        lines.append("")
    return "\n".join(lines)


def format_decks_table(result):
    """Format decks as a readable table."""
    decks = result.get("deck", {})
    if not decks:
        return "No decks found."
    project_names = load_project_names()
    deck_counts = result.get("_deck_counts", {})
    cols = [("Title", 30), ("Project", 20), ("Cards", 6), ("ID", 0)]
    rows = []
    for key, deck in decks.items():
        pid = _get_field(deck, "project_id", "projectId") or ""
        did = deck.get("id", key)
        count = deck_counts.get(did, 0)
        rows.append(
            (
                _trunc(deck.get("title", ""), 30),
                project_names.get(pid, pid[:12]),
                str(count) if deck_counts else "-",
                did,
            )
        )
    return _table(cols, rows, f"Total: {len(decks)} decks")


def format_projects_table(result):
    """Format projects as a readable table."""
    if not result:
        return "No projects found."
    lines = []
    for pid, info in result.items():
        lines.append(f"Project: {info.get('name', pid)}")
        lines.append(f"  ID:    {pid}")
        lines.append(f"  Decks ({info.get('deck_count', 0)}): {', '.join(info.get('decks', []))}")
        lines.append("")
    return "\n".join(lines)


def format_milestones_table(result):
    """Format milestones as a readable table."""
    if not result:
        return "No milestones found."
    lines = []
    for mid, info in result.items():
        name = info.get("name", mid)
        cards = info.get("cards", [])
        lines.append(f"Milestone: {name}  (ID: {mid})")
        lines.append(f"  Cards ({len(cards)}):")
        for c in cards[:8]:
            lines.append(f"    - {c}")
        if len(cards) > 8:
            lines.append(f"    ... and {len(cards) - 8} more")
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
    for key, act in activities.items():
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


# ---------------------------------------------------------------------------
# GDD formatters
# ---------------------------------------------------------------------------


def format_gdd_table(sections):
    """Format parsed GDD sections as a readable table."""
    if not sections:
        return "No tasks found in GDD."
    cols = [("Section", 24), ("Pri", 5), ("Eff", 5), ("Title", 0)]
    rows = []
    for section in sections:
        for task in section["tasks"]:
            rows.append(
                (
                    _trunc(section["section"], 24),
                    task.get("priority") or "-",
                    str(task.get("effort") or "-"),
                    _trunc(task["title"], 50),
                )
            )
    return _table(cols, rows, f"Total: {len(rows)} tasks across {len(sections)} sections")


def format_sync_report(report):
    """Format GDD sync report as readable text."""
    lines = []
    project = report.get("project", "?")
    applied = report.get("applied", False)
    quiet = report.get("quiet", False)

    lines.append(f'GDD Sync Report for "{project}"')
    lines.append("=" * 50)

    new_items = report.get("new", [])
    created_items = report.get("created", [])
    existing_items = report.get("existing", [])
    error_items = report.get("errors", [])

    if applied and created_items:
        lines.append(f"\nCREATED ({len(created_items)}):")
        if not quiet:
            for t in created_items:
                pri = f"[{t['priority']}]" if t.get("priority") else ""
                eff = f" E:{t['effort']}" if t.get("effort") else ""
                cid = t.get("card_id", "")[:12]
                lines.append(f"  {pri}{eff} {t['title']:<40} {cid}")
    elif new_items:
        lines.append(f"\nNEW (will be created with --apply) ({len(new_items)}):")
        if not quiet:
            for t in new_items:
                pri = f"[{t['priority']}]" if t.get("priority") else ""
                eff = f" E:{t['effort']}" if t.get("effort") else ""
                deck = t.get("deck", "?")
                exists = "" if t.get("deck_exists") else " (new deck)"
                lines.append(f"  {pri}{eff} {t['title']:<40} -> {deck}{exists}")
        unmatched = sorted(set(t["deck"] for t in new_items if not t.get("deck_exists")))
        if unmatched:
            lines.append(
                f"\n  WARNING: These GDD sections don't match any deck: {', '.join(unmatched)}"
            )
            lines.append("  Create these decks first, or use --section to sync selectively.")

    if existing_items:
        lines.append(f"\nALREADY TRACKED ({len(existing_items)}):")
        if not quiet:
            for t in existing_items:
                sym = "=" if t["match_type"] == "exact" else "\u2248"
                lines.append(f'  {t["title"]:<40} {sym} "{t["matched_to"]}"')

    if error_items:
        lines.append(f"\nERRORS ({len(error_items)}):")
        for t in error_items:
            lines.append(f"  {t['title']}: {t.get('error', '?')}")

    lines.append("")
    total = report.get("total_gdd", 0)
    n_new = len(created_items) if applied else len(new_items)
    n_existing = len(existing_items)
    action = "created" if applied else "to create"
    lines.append(f"Summary: {n_new} {action}, {n_existing} existing, {total} total in GDD")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CSV formatters
# ---------------------------------------------------------------------------


def format_cards_csv(result):
    """Format cards as CSV for export."""
    cards = result.get("card", {})
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["status", "priority", "effort", "deck", "milestone", "owner", "title", "tags", "id"]
    )
    for key, card in cards.items():
        tags = get_card_tags(card)
        writer.writerow(
            [
                card.get("status", ""),
                config.PRI_LABELS.get(card.get("priority"), ""),
                card.get("effort") or "",
                card.get("deck_name") or card.get("deck_id", ""),
                card.get("milestone_name", ""),
                card.get("owner_name", ""),
                card.get("title", ""),
                ", ".join(tags) if tags else "",
                key,
            ]
        )
    return buf.getvalue().rstrip()
