"""Security: injection detection, output tagging, input validation."""

from __future__ import annotations

import re

from codecks_cli import CliError

_INJECTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"^(system|assistant|user)\s*:", re.IGNORECASE | re.MULTILINE),
        "role label",
    ),
    (
        re.compile(
            r"<\s*/?\s*(system|instruction|admin|prompt|tool_call|function_call)",
            re.IGNORECASE,
        ),
        "XML-like directive tag",
    ),
    (
        re.compile(
            r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts|rules)",
            re.IGNORECASE,
        ),
        "override directive",
    ),
    (
        re.compile(
            r"forget\s+(your|all|the)\s+(rules|instructions|training|guidelines)",
            re.IGNORECASE,
        ),
        "forget directive",
    ),
    (
        re.compile(
            r"you\s+are\s+now\s+(in\s+)?(admin|root|debug|developer|unrestricted|jailbreak)",
            re.IGNORECASE,
        ),
        "mode switching",
    ),
    (
        re.compile(
            r"(execute|call|invoke|run)\s+the\s+(tool|function|command)",
            re.IGNORECASE,
        ),
        "tool invocation directive",
    ),
]


def _check_injection(text: str) -> list[str]:
    """Check text for common prompt injection patterns.

    Returns list of matched pattern descriptions (empty if clean).
    Short strings (< 10 chars) are skipped.
    """
    if len(text) < 10:
        return []
    return [desc for pattern, desc in _INJECTION_PATTERNS if pattern.search(text)]


def _tag_user_text(text: str | None) -> str | None:
    """Wrap user-authored text in [USER_DATA] boundary markers."""
    if text is None:
        return None
    return f"[USER_DATA]{text}[/USER_DATA]"


_USER_TEXT_FIELDS = {"title", "content", "deck_name", "owner_name", "milestone_name"}


def _sanitize_card(card: dict) -> dict:
    """Tag user-editable fields and add _safety_warnings if injection detected."""
    out = dict(card)
    warnings: list[str] = []
    for field in _USER_TEXT_FIELDS:
        if field in out and isinstance(out[field], str):
            for desc in _check_injection(out[field]):
                warnings.append(f"{field}: {desc}")
            out[field] = _tag_user_text(out[field])
    if "sub_cards" in out and isinstance(out["sub_cards"], list):
        tagged_subs: list = []
        for sc in out["sub_cards"]:
            if isinstance(sc, dict):
                sc = dict(sc)
                if "title" in sc and isinstance(sc["title"], str):
                    for desc in _check_injection(sc["title"]):
                        warnings.append(f"sub_card.title: {desc}")
                    sc["title"] = _tag_user_text(sc["title"])
            tagged_subs.append(sc)
        out["sub_cards"] = tagged_subs
    if "conversations" in out and isinstance(out["conversations"], list):
        tagged_convos: list = []
        for conv in out["conversations"]:
            if isinstance(conv, dict):
                conv = dict(conv)
                if "messages" in conv and isinstance(conv["messages"], list):
                    msgs: list = []
                    for msg in conv["messages"]:
                        if isinstance(msg, dict):
                            msg = dict(msg)
                            if "content" in msg and isinstance(msg["content"], str):
                                for desc in _check_injection(msg["content"]):
                                    warnings.append(f"conversation.message: {desc}")
                                msg["content"] = _tag_user_text(msg["content"])
                        msgs.append(msg)
                    conv["messages"] = msgs
            tagged_convos.append(conv)
        out["conversations"] = tagged_convos
    if warnings:
        out["_safety_warnings"] = warnings
    return out


def _sanitize_conversations(data: dict) -> dict:
    """Tag user-authored content in raw conversation data."""
    if not isinstance(data, dict):
        return data
    out = dict(data)
    for key, val in list(out.items()):
        if isinstance(val, dict):
            tagged_entries: dict = {}
            for entry_id, entry in val.items():
                if isinstance(entry, dict):
                    entry = dict(entry)
                    if "content" in entry and isinstance(entry["content"], str):
                        entry["content"] = _tag_user_text(entry["content"])
                tagged_entries[entry_id] = entry
            out[key] = tagged_entries
        elif isinstance(val, list):
            tagged_items: list = []
            for item in val:
                if isinstance(item, dict):
                    item = dict(item)
                    if "content" in item and isinstance(item["content"], str):
                        item["content"] = _tag_user_text(item["content"])
                tagged_items.append(item)
            out[key] = tagged_items
    return out


def _sanitize_activity(data: dict) -> dict:
    """Tag card titles in activity feed referenced cards."""
    if not isinstance(data, dict):
        return data
    out = dict(data)
    if "cards" in out and isinstance(out["cards"], dict):
        tagged_cards: dict = {}
        for card_id, card in out["cards"].items():
            if isinstance(card, dict):
                card = dict(card)
                if "title" in card and isinstance(card["title"], str):
                    card["title"] = _tag_user_text(card["title"])
            tagged_cards[card_id] = card
        out["cards"] = tagged_cards
    return out


_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_INPUT_LIMITS = {
    "title": 500,
    "content": 50_000,
    "message": 10_000,
    "observation": 500,
    "description": 50_000,
    "feedback_message": 1000,
    "feedback_context": 500,
}


def _validate_input(text: str, field: str) -> str:
    """Strip control characters and enforce length limits.

    Raises CliError if text is not a string or exceeds the field limit.
    """
    if not isinstance(text, str):
        raise CliError(f"[ERROR] {field} must be a string")
    cleaned = _CONTROL_RE.sub("", text)
    limit = _INPUT_LIMITS.get(field, 50_000)
    if len(cleaned) > limit:
        raise CliError(f"[ERROR] {field} exceeds maximum length of {limit} characters")
    return cleaned


def _validate_preferences(observations: list[str]) -> list[str]:
    """Validate preference observations: cap at 50 items, 500 chars each."""
    if not isinstance(observations, list):
        raise CliError("[ERROR] observations must be a list of strings")
    return [_validate_input(obs, "observation") for obs in observations[:50]]
