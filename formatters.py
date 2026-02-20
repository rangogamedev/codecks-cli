"""
Output formatting functions for codecks-cli.
Table, CSV, and JSON output dispatchers.
"""

import csv
import io
import json
import sys

import config
from cards import _load_project_names, _load_milestone_names, _load_users


# ---------------------------------------------------------------------------
# Core output helpers
# ---------------------------------------------------------------------------

def pretty_print(data):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    print(json.dumps(data, indent=2, ensure_ascii=False))


def output(data, formatter=None, fmt="json", csv_formatter=None):
    """Output data in requested format."""
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if fmt == "csv" and csv_formatter:
        print(csv_formatter(data))
    elif fmt == "table" and formatter:
        print(formatter(data))
    else:
        print(json.dumps(data, indent=2, ensure_ascii=False))


def _mutation_response(action, card_id=None, details=None, data=None, fmt="json"):
    """Print a mutation confirmation."""
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
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


def _trunc(s, maxlen):
    """Truncate string with ellipsis indicator."""
    if not s:
        return ""
    return s[:maxlen - 1] + "\u2026" if len(s) > maxlen else s


# ---------------------------------------------------------------------------
# Table formatters
# ---------------------------------------------------------------------------

def _format_account_table(result):
    """Format account info as readable text."""
    acc = result.get("account", {})
    if not acc:
        return "No account data."
    for key, info in acc.items():
        return f"Account: {info.get('name', '?')}\nID:      {key}"


def _format_cards_table(result):
    """Format cards as a readable table."""
    cards = result.get("card", {})
    if not cards:
        return "No cards found."
    lines = []
    lines.append(f"{'Status':<14} {'Pri':<5} {'Eff':<4} {'Owner':<10} {'Deck':<18} {'Title':<36} {'Tags':<16} {'ID'}")
    lines.append("-" * 140)
    for key, card in cards.items():
        status = card.get("status", "")
        pri = config.PRI_LABELS.get(card.get("priority"), "-")
        effort = str(card.get("effort") or "-")
        owner = _trunc(card.get("owner_name", "") or "-", 10)
        deck = _trunc(card.get("deck_name") or card.get("deck_id", ""), 18)
        title_text = card.get("title", "")
        sub_count = card.get("sub_card_count")
        if sub_count:
            title_text = f"{title_text} [{sub_count} sub]"
        title = _trunc(title_text, 36)
        tags = card.get("tags") or card.get("master_tags") or card.get("masterTags") or []
        tag_str = _trunc(", ".join(tags), 16) if tags else "-"
        lines.append(f"{status:<14} {pri:<5} {effort:<4} {owner:<10} {deck:<18} {title:<36} {tag_str:<16} {key}")
    lines.append(f"\nTotal: {len(cards)} cards")
    return "\n".join(lines)


def _format_card_detail(result):
    """Format a single card with full details."""
    cards = result.get("card", {})
    if not cards:
        return "Card not found."
    lines = []
    for key, card in cards.items():
        lines.append(f"Card:      {key}")
        lines.append(f"Title:     {card.get('title', '')}")
        is_doc = card.get("is_doc") or card.get("isDoc")
        if is_doc:
            lines.append(f"Type:      doc card")
        lines.append(f"Status:    {card.get('status', '')}")
        pri_raw = card.get("priority")
        pri_display = f"{pri_raw} ({config.PRI_LABELS[pri_raw]})" if pri_raw in config.PRI_LABELS else "none"
        lines.append(f"Priority:  {pri_display}")
        lines.append(f"Effort:    {card.get('effort') or '-'}")
        lines.append(f"Deck:      {card.get('deck_name', card.get('deck_id', ''))}")
        lines.append(f"Owner:     {card.get('owner_name') or '-'}")
        ms = card.get("milestone_name", card.get("milestone_id"))
        lines.append(f"Milestone: {ms or '-'}")
        tags = card.get("tags") or card.get("master_tags") or card.get("masterTags") or []
        lines.append(f"Tags:      {', '.join(tags) if tags else '-'}")
        lines.append(f"In hand:   {'yes' if card.get('in_hand') else 'no'}")
        lines.append(f"Created:   {card.get('createdAt', '')}")
        updated = card.get("last_updated_at") or card.get("lastUpdatedAt") or ""
        if updated:
            lines.append(f"Updated:   {updated}")
        content = card.get("content", "")
        if content:
            body_lines = content.split("\n", 1)
            body = body_lines[1].strip() if len(body_lines) > 1 else ""
            if body:
                lines.append(f"Content:   {body[:300]}")
        # Checklist progress
        cb_stats = card.get("checkbox_stats") or card.get("checkboxStats")
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
            open_count = sum(1 for rid in resolvables
                             if not (resolvable_data.get(rid, {})
                                     .get("is_closed")
                                     or resolvable_data.get(rid, {})
                                     .get("isClosed")))
            closed_count = len(resolvables) - open_count
            lines.append(f"Conversations ({len(resolvables)}: "
                         f"{open_count} open, {closed_count} closed):")
            for rid in resolvables[:5]:
                r = resolvable_data.get(rid, {})
                creator_id = r.get("creator")
                creator_name = user_data.get(creator_id, {}).get("name", "?") if creator_id else "?"
                status = "closed" if (r.get("is_closed") or r.get("isClosed")) else "open"
                lines.append(f"  Thread {rid[:8]}.. ({status}, by {creator_name}):")
                entries = r.get("entries") or []
                for eid in entries[:3]:
                    e = entry_data.get(eid, {})
                    author_id = e.get("author")
                    author_name = user_data.get(author_id, {}).get("name", "?") if author_id else "?"
                    msg = (e.get("content") or "")[:120]
                    lines.append(f"    {author_name}: {msg}")
                if len(entries) > 3:
                    lines.append(f"    ... and {len(entries) - 3} more replies")
            if len(resolvables) > 5:
                lines.append(f"  ... and {len(resolvables) - 5} more threads")
        lines.append("")
    return "\n".join(lines)


def _format_conversations_table(result):
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
            creator_name = (user_data.get(creator_id, {}).get("name", "?")
                            if creator_id else "?")
            is_closed = r.get("is_closed") or r.get("isClosed")
            status = "closed" if is_closed else "open"
            created = r.get("created_at") or r.get("createdAt") or ""
            lines.append(f"  [{status}] Thread {rid} (by {creator_name}, {created})")
            entries = r.get("entries") or []
            for eid in entries:
                e = entry_data.get(eid, {})
                author_id = e.get("author")
                author_name = (user_data.get(author_id, {}).get("name", "?")
                               if author_id else "?")
                msg = e.get("content") or ""
                ts = e.get("created_at") or e.get("createdAt") or ""
                lines.append(f"    {author_name} ({ts}): {msg[:200]}")
        lines.append("")
    return "\n".join(lines)


def _format_decks_table(result):
    """Format decks as a readable table."""
    decks = result.get("deck", {})
    if not decks:
        return "No decks found."
    project_names = _load_project_names()
    lines = []
    lines.append(f"{'Title':<30} {'Project':<20} {'ID'}")
    lines.append("-" * 90)
    for key, deck in decks.items():
        title = _trunc(deck.get("title", ""), 30)
        pid = deck.get("project_id") or deck.get("projectId") or ""
        proj = project_names.get(pid, pid[:12])
        lines.append(f"{title:<30} {proj:<20} {deck.get('id', key)}")
    lines.append(f"\nTotal: {len(decks)} decks")
    return "\n".join(lines)


def _format_projects_table(result):
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


def _format_milestones_table(result):
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


def _format_stats_table(stats):
    """Format card stats as readable text."""
    lines = [f"Total cards: {stats['total']}"]
    lines.append(f"Total effort: {stats['total_effort']}  "
                 f"Avg effort: {stats['avg_effort']}")
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
    return "\n".join(lines)


def _resolve_activity_val(field, val, ms_names, user_names):
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


def _format_activity_table(result):
    """Format activity feed as readable text."""
    activities = result.get("activity", {})
    if not activities:
        return "No activity found."
    users = result.get("user", {})
    decks = result.get("deck", {})
    ms_names = _load_milestone_names()
    user_names = _load_users()
    cards = result.get("card", {})
    lines = []
    lines.append(f"{'Time':<18} {'Type':<18} {'By':<12} {'Deck':<16} {'Details'}")
    lines.append("-" * 120)
    for key, act in activities.items():
        ts = (act.get("createdAt") or "")[:16].replace("T", " ")
        atype = act.get("type", "?")
        changer_id = act.get("changer")
        changer = users.get(changer_id, {}).get("name", "") if changer_id else ""
        deck_id = act.get("deck")
        deck_name = decks.get(deck_id, {}).get("title", "") if deck_id else ""
        data = act.get("data", {})
        diff = data.get("diff", {})
        # Build details string
        details = ""
        if diff:
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
                    old = _resolve_activity_val(field, old, ms_names, user_names)
                    new = _resolve_activity_val(field, new, ms_names, user_names)
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
            details = "; ".join(parts)
        details = _trunc(details, 60) if details else ""
        lines.append(f"{ts:<18} {atype:<18} {changer:<12} {_trunc(deck_name, 16):<16} {details}")
    lines.append(f"\nTotal: {len(activities)} events")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# GDD formatters
# ---------------------------------------------------------------------------

def _format_gdd_table(sections):
    """Format parsed GDD sections as a readable table."""
    if not sections:
        return "No tasks found in GDD."
    lines = []
    lines.append(f"{'Section':<24} {'Pri':<5} {'Eff':<5} {'Title'}")
    lines.append("-" * 90)
    total_tasks = 0
    for section in sections:
        for task in section["tasks"]:
            total_tasks += 1
            sec = _trunc(section["section"], 24)
            pri = task.get("priority") or "-"
            eff = str(task.get("effort") or "-")
            title = _trunc(task["title"], 50)
            lines.append(f"{sec:<24} {pri:<5} {eff:<5} {title}")
    lines.append(f"\nTotal: {total_tasks} tasks across {len(sections)} sections")
    return "\n".join(lines)


def _format_sync_report(report):
    """Format GDD sync report as readable text."""
    lines = []
    project = report.get("project", "?")
    applied = report.get("applied", False)
    quiet = report.get("quiet", False)

    lines.append(f"GDD Sync Report for \"{project}\"")
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
            lines.append(f"\n  WARNING: These GDD sections don't match any deck: "
                         f"{', '.join(unmatched)}")
            lines.append("  Create these decks first, or use --section to sync selectively.")

    if existing_items:
        lines.append(f"\nALREADY TRACKED ({len(existing_items)}):")
        if not quiet:
            for t in existing_items:
                sym = "=" if t["match_type"] == "exact" else "\u2248"
                lines.append(f"  {t['title']:<40} {sym} \"{t['matched_to']}\"")

    if error_items:
        lines.append(f"\nERRORS ({len(error_items)}):")
        for t in error_items:
            lines.append(f"  {t['title']}: {t.get('error', '?')}")

    lines.append("")
    total = report.get("total_gdd", 0)
    n_new = len(created_items) if applied else len(new_items)
    n_existing = len(existing_items)
    action = "created" if applied else "to create"
    lines.append(f"Summary: {n_new} {action}, {n_existing} existing, "
                 f"{total} total in GDD")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CSV formatters
# ---------------------------------------------------------------------------

def _format_cards_csv(result):
    """Format cards as CSV for export."""
    cards = result.get("card", {})
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["status", "priority", "effort", "deck", "owner", "title",
                     "tags", "id"])
    for key, card in cards.items():
        tags = card.get("tags") or card.get("master_tags") or card.get("masterTags") or []
        writer.writerow([
            card.get("status", ""),
            config.PRI_LABELS.get(card.get("priority"), ""),
            card.get("effort") or "",
            card.get("deck_name") or card.get("deck_id", ""),
            card.get("owner_name", ""),
            card.get("title", ""),
            ", ".join(tags) if tags else "",
            key,
        ])
    return buf.getvalue().rstrip()
