"""Persistence for @last reference — saves card IDs from the most recent command result."""

from __future__ import annotations

import json
import os

from codecks_cli.config import _PROJECT_ROOT

_LAST_RESULT_FILE = ".pm_last_result.json"
_LAST_RESULT_PATH = os.path.join(_PROJECT_ROOT, _LAST_RESULT_FILE)


def save_last_result(card_ids: list[str]) -> None:
    """Save card IDs from the most recent command result."""
    try:
        with open(_LAST_RESULT_PATH, "w", encoding="utf-8") as f:
            json.dump({"card_ids": card_ids}, f)
    except OSError:
        pass  # Non-fatal


def load_last_result() -> list[str]:
    """Load card IDs from the most recent command result. Returns [] on failure."""
    try:
        with open(_LAST_RESULT_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return list(data.get("card_ids", []))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def resolve_at_refs(args: list[str]) -> list[str]:
    """Expand @last to card IDs from previous command result.

    Example: ["done", "@last"] → ["done", "uuid-1", "uuid-2", ...]
    """
    if "@last" not in args:
        return args
    last_ids = load_last_result()
    if not last_ids:
        return args  # No expansion if no previous result
    result = []
    for arg in args:
        if arg == "@last":
            result.extend(last_ids)
        else:
            result.append(arg)
    return result
