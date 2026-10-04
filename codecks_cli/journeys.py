"""Native Journey operations using Codecks' internal workflows endpoints.

These endpoints are not in the public API stability contract. A scoped API
token may reject them; errors propagate without falling back to browser auth.
"""

import json
from uuid import UUID

from codecks_cli.api import query, session_request
from codecks_cli.card_refs import resolve_card_ids
from codecks_cli.cards import _get_user_id, get_account
from codecks_cli.exceptions import CliError


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
    response = session_request(f"/dispatch/workflows/{action}", data)
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
        if item_id in items
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
    return _dispatch(
        "addItemsAfter",
        {"deckId": deck_id, "itemIds": item_ids, "targetId": target_id, "label": label},
    )


def start_journey(card_id: str) -> dict:
    """Apply a deck's Journey, creating tasks. Resolve the card reference first."""
    card_id = resolve_card_ids([card_id])["cards"][0]["id"]
    user_id = _uuid(_get_user_id(), "user_id")
    accounts = get_account().get("account", {})
    if len(accounts) != 1:
        raise CliError("[ERROR] Unable to resolve Journey account.", error_code="INVALID_INPUT")
    account_id = _uuid(next(iter(accounts)), "account_id")
    return _dispatch("apply", {"cardId": card_id, "userId": user_id, "accountId": account_id})
