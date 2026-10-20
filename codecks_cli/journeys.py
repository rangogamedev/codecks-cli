"""Native Journey operations using Codecks' internal workflows endpoints.

These endpoints are not in the public API stability contract. A scoped API
token may reject them; errors propagate without falling back to browser auth.
"""

import json
import threading
from _thread import LockType
from uuid import UUID
from weakref import WeakValueDictionary

from codecks_cli import api
from codecks_cli._utils import _get_field
from codecks_cli.api import query
from codecks_cli.card_refs import resolve_card_ids
from codecks_cli.cards import _get_user_id, get_account
from codecks_cli.exceptions import CliError

_start_locks: WeakValueDictionary[str, LockType] = WeakValueDictionary()
_start_locks_guard = threading.Lock()
_pending_starts: dict[str, set[str]] = {}


def _uuid(value: str, field: str) -> str:
    try:
        if isinstance(value, str) and len(value) == 36 and str(UUID(value)) == value.lower():
            return value.lower()
    except ValueError:
        pass
    raise CliError(f"[ERROR] {field} must be a full UUID.", error_code="INVALID_INPUT")


def _fields(fields: dict | None) -> dict:
    if fields is not None and not isinstance(fields, dict):
        raise CliError("[ERROR] Journey fields must be an object.", error_code="INVALID_INPUT")
    values = dict(fields or {})
    allowed = {"content", "targetDeckId", "assigneeId", "effort", "priority", "masterTags"}
    if values.keys() - allowed:
        raise CliError("[ERROR] Unknown Journey step fields.", error_code="INVALID_INPUT")
    for field in ("targetDeckId", "assigneeId"):
        if field in values and values[field] is not None:
            values[field] = _uuid(values[field], field)
    if "content" in values:
        content = values["content"]
        if not isinstance(content, str) or not content.strip() or len(content) > 50000:
            raise CliError(
                "[ERROR] Provide nonempty Journey content (up to 50000 characters).",
                error_code="INVALID_INPUT",
            )
    effort = values.get("effort")
    if effort is not None and (type(effort) is not int or not 0 <= effort <= 2**31 - 1):
        raise CliError(
            "[ERROR] Journey effort must be a nonnegative int32 or null.",
            error_code="INVALID_INPUT",
        )
    if values.get("priority") not in (None, "a", "b", "c"):
        raise CliError(
            "[ERROR] Journey priority must be a, b, c, or null.", error_code="INVALID_INPUT"
        )
    if "masterTags" in values:
        tags = values["masterTags"]
        if not isinstance(tags, list) or len(tags) > 100:
            raise CliError(
                "[ERROR] masterTags must contain up to 100 UUIDs.", error_code="INVALID_INPUT"
            )
        values["masterTags"] = [_uuid(tag, "masterTags") for tag in tags]
    return values


def _dispatch(action: str, data: dict) -> dict:
    response = api.dispatch(f"workflows/{action}", data)
    return {"ok": True, "response": response}


def get_journey(deck_id: str) -> dict:
    deck_id = _uuid(deck_id, "deck_id")
    data = query(
        {
            f"deck({json.dumps([deck_id])})": [
                "title",
                "workflowItemOrderLabels",
                {
                    "workflowItems": [
                        "content",
                        "visibility",
                        "label",
                        "sortValue",
                        "effort",
                        "priority",
                        {"targetDeck": ["title"], "assignee": ["name"]},
                    ]
                },
            ]
        }
    )
    deck = data.get("deck", {}).get(deck_id)
    if not isinstance(deck, dict):
        raise CliError(
            "[ERROR] Journey deck is missing or inaccessible.", error_code="INVALID_INPUT"
        )
    items = data.get("workflowItem", data.get("workflow_item", {}))
    steps = [
        {"id": item_id, **items[item_id]}
        for item_id in (deck.get("workflowItems", deck.get("workflow_items", [])) or [])
        if item_id in items and items[item_id].get("visibility", "default") == "default"
    ]
    return {
        "deck_id": deck_id,
        "title": deck.get("title", ""),
        "zones": deck.get("workflowItemOrderLabels", deck.get("workflow_item_order_labels", [])),
        "steps": sorted(
            steps, key=lambda step: (step.get("sortValue", step.get("sort_value")) or 0, step["id"])
        ),
        "target_decks": data.get("deck", {}),
        "assignees": data.get("user", {}),
    }


def create_journey_step(
    deck_id: str, content: str, *, fields: dict | None = None, user_id: str | None = None
) -> dict:
    deck_id = _uuid(deck_id, "deck_id")
    values = _fields(fields)
    values = _fields({**values, "content": content})
    creator = _uuid(user_id or _get_user_id(), "user_id")
    return _dispatch("createItem", {**values, "deckId": deck_id, "userId": creator})


def update_journey_step(item_id: str, fields: dict) -> dict:
    item_id = _uuid(item_id, "item_id")
    if not isinstance(fields, dict) or not fields:
        raise CliError(
            "[ERROR] Provide at least one Journey step field.", error_code="INVALID_INPUT"
        )
    fields = dict(fields)
    visibility = fields.pop("visibility", None)
    if visibility not in (None, "default", "deleted"):
        raise CliError(
            "[ERROR] Journey visibility must be default or deleted.", error_code="INVALID_INPUT"
        )
    values = _fields(fields)
    if visibility is not None:
        values["visibility"] = visibility
    if not values:
        raise CliError(
            "[ERROR] Provide at least one Journey step field.", error_code="INVALID_INPUT"
        )
    return _dispatch("updateItem", {"itemId": item_id, **values})


def order_journey_steps(
    deck_id: str, item_ids: list[str], target_id: str | None, label: str | None
) -> dict:
    deck_id = _uuid(deck_id, "deck_id")
    if not isinstance(item_ids, list) or not 1 <= len(item_ids) <= 100:
        raise CliError("[ERROR] Provide 1-100 Journey step UUIDs.", error_code="INVALID_INPUT")
    item_ids = [_uuid(item, "item_ids") for item in item_ids]
    target_id = _uuid(target_id, "target_id") if target_id is not None else None
    if len(set(item_ids)) != len(item_ids) or target_id in item_ids:
        raise CliError(
            "[ERROR] Step IDs must be unique and exclude the target.", error_code="INVALID_INPUT"
        )
    if label is not None and (not isinstance(label, str) or len(label) > 200):
        raise CliError(
            "[ERROR] Journey label must be a string (up to 200 characters) or null.",
            error_code="INVALID_INPUT",
        )
    steps = get_journey(deck_id)["steps"]
    ids = {step["id"] for step in steps}
    if not set(item_ids) <= ids or (target_id is not None and target_id not in ids):
        raise CliError(
            "[ERROR] Steps and target must be active steps in this deck.",
            error_code="INVALID_INPUT",
        )
    action = "addItemsAfter"
    if target_id is None:
        # Codecks uses a before-first anchor; addItemsAfter(null) appends.
        target_id = next(
            (
                step["id"]
                for step in steps
                if step.get("label") == label and step["id"] not in item_ids
            ),
            None,
        )
        if target_id is not None:
            action = "addItemsBefore"
    return _dispatch(
        action,
        {"deckId": deck_id, "itemIds": item_ids, "targetId": target_id, "label": label},
    )


def start_journey(card_id: str) -> dict:
    """Apply active steps not yet represented by this card's children."""
    resolved = resolve_card_ids([card_id])["cards"][0]
    card_id = resolved["id"]
    if resolved.get("visibility", "default") != "default":
        raise CliError("[ERROR] Journey parent must be an active card.", error_code="INVALID_INPUT")
    # shortcut: process-local protection, covering processes/restarts needs confirmed server idempotency.
    with _start_locks_guard:
        lock = _start_locks.setdefault(card_id, threading.Lock())
    with lock:
        return _start_journey_locked(card_id)


def _read_journey_parent(card_id: str) -> tuple[str, set[str]]:
    data = query(
        {
            "_root": [
                {
                    "account": [
                        {
                            f"cards({json.dumps({'cardId': card_id, 'visibility': 'default'})})": [
                                "deckId",
                                {"childCards": ["sourceWorkflowItemId"]},
                            ]
                        }
                    ]
                }
            ]
        }
    )
    card = data.get("card", {}).get(card_id)
    if not isinstance(card, dict):
        raise CliError(
            "[ERROR] Journey parent is missing or inaccessible.", error_code="INVALID_INPUT"
        )
    deck_id = _uuid(_get_field(card, "deck_id", "deckId"), "deck_id")
    children = _get_field(card, "child_cards", "childCards") or []
    applied = {
        _get_field(
            data.get("card", {}).get(child_id, {}),
            "source_workflow_item_id",
            "sourceWorkflowItemId",
        )
        for child_id in children
    }
    return deck_id, applied


def _uncertain_start(card_id: str) -> CliError:
    return CliError(
        f"[ERROR] Journey start outcome is uncertain for {card_id}. "
        "Reconcile its children before retrying. This process will not submit another "
        "start until all previously submitted steps are visible.",
        error_code="JOURNEY_OUTCOME_UNKNOWN",
        retryable=False,
    )


def _start_journey_locked(card_id: str) -> dict:
    deck_id, applied = _read_journey_parent(card_id)
    pending = _pending_starts.get(card_id)
    if pending is not None:
        if not pending <= applied:
            raise _uncertain_start(card_id)
        del _pending_starts[card_id]
    item_ids = [step["id"] for step in get_journey(deck_id)["steps"] if step["id"] not in applied]
    if not item_ids:
        return {
            "ok": True,
            "card_id": card_id,
            "created": 0,
            "message": "No unapplied Journey steps.",
        }
    user_id = _uuid(_get_user_id(), "user_id")
    accounts = get_account().get("account", {})
    if len(accounts) != 1:
        raise CliError("[ERROR] Unable to resolve Journey account.", error_code="INVALID_INPUT")
    account_id = _uuid(next(iter(accounts)), "account_id")
    _pending_starts[card_id] = set(item_ids)
    try:
        result = _dispatch(
            "apply",
            {"cardId": card_id, "itemIds": item_ids, "userId": user_id, "accountId": account_id},
        )
    except CliError as error:
        if error.error_code in {
            "TOKEN_EXPIRED",
            "PERMISSION_DENIED",
            "RATE_LIMITED",
            "INVALID_INPUT",
        }:
            del _pending_starts[card_id]
            raise
        raise _uncertain_start(card_id) from error
    except Exception as error:
        raise _uncertain_start(card_id) from error
    try:
        _, applied = _read_journey_parent(card_id)
    except Exception as error:
        raise _uncertain_start(card_id) from error
    if not _pending_starts[card_id] <= applied:
        raise _uncertain_start(card_id)
    del _pending_starts[card_id]
    return result
