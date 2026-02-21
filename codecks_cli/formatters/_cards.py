"""Card-specific formatters: table, detail, conversations, CSV."""

import csv
import io

from codecks_cli import config
from codecks_cli._utils import _get_field, get_card_tags
from codecks_cli.formatters._table import _table, _trunc


def format_account_table(result):
    """Format account info as readable text."""
    acc = result.get("account", {})
    if not acc:
        return "No account data."
    for key, info in acc.items():
        return f"Account: {info.get('name', '?')}\nID:      {key}"


def format_cards_table(result):
    """Format cards as a readable table.

    Accepts {"cards": [flat_dicts], "stats": ...} from CodecksClient.
    """
    cards = result.get("cards", [])
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
    for card in cards:
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
                card.get("id", ""),
            )
        )
    return _table(cols, rows, f"Total: {len(cards)} cards")


def format_card_detail(card):
    """Format a single card with full details.

    Accepts a flat card dict from CodecksClient.get_card() with sub_cards
    and conversations already resolved inline.
    """
    if not card:
        return "Card not found."
    lines = []
    lines.append(f"Card:      {card.get('id', '')}")
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
    # Sub-cards (already resolved by client)
    sub_cards = card.get("sub_cards", [])
    if sub_cards:
        lines.append(f"Sub-cards ({len(sub_cards)}):")
        for sc in sub_cards[:10]:
            lines.append(f"  - [{sc.get('status', '?')}] {sc.get('title', sc.get('id', '?'))}")
        if len(sub_cards) > 10:
            lines.append(f"  ... and {len(sub_cards) - 10} more")
    # Conversations (already resolved by client)
    conversations = card.get("conversations", [])
    if conversations:
        open_count = sum(1 for c in conversations if c.get("status") == "open")
        closed_count = len(conversations) - open_count
        lines.append(
            f"Conversations ({len(conversations)}: {open_count} open, {closed_count} closed):"
        )
        for conv in conversations[:5]:
            status = conv.get("status", "open")
            creator = conv.get("creator", "?")
            cid = conv.get("id", "?")
            lines.append(f"  Thread {cid[:8]}.. ({status}, by {creator}):")
            messages = conv.get("messages", [])
            for msg in messages[:3]:
                author = msg.get("author", "?")
                content = (msg.get("content") or "")[:120]
                lines.append(f"    {author}: {content}")
            if len(messages) > 3:
                lines.append(f"    ... and {len(messages) - 3} more replies")
        if len(conversations) > 5:
            lines.append(f"  ... and {len(conversations) - 5} more threads")
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


def format_cards_csv(result):
    """Format cards as CSV for export.

    Accepts {"cards": [flat_dicts], "stats": ...} from CodecksClient.
    """
    cards = result.get("cards", [])
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["status", "priority", "effort", "deck", "milestone", "owner", "title", "tags", "id"]
    )
    for card in cards:
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
                card.get("id", ""),
            ]
        )
    return buf.getvalue().rstrip()
