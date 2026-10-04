"""Experimental native Journey tools. Workflow actions use internal APIs."""

from codecks_cli.mcp_server._core import _call, _finalize_tool_result
from codecks_cli.mcp_server._security import _sanitize_card, _tag_user_text


def _tag_response(value):
    """Bound user text in nested dispatch responses without changing identifiers."""
    if isinstance(value, list):
        return [_tag_response(item) for item in value]
    if isinstance(value, dict):
        tagged = {key: _tag_response(item) for key, item in value.items()}
        tagged = _sanitize_card(tagged)
        for key in ("label", "name"):
            if isinstance(tagged.get(key), str):
                tagged[key] = _tag_user_text(tagged[key])
        return tagged
    return value


def _finish_write(result: dict) -> dict:
    if result.get("ok") is not False and "response" in result:
        result = {**result, "response": _tag_response(result["response"])}
    return _finalize_tool_result(result)


def get_journey(deck_id: str) -> dict:
    """Read a deck's native Journey steps, zones and ordering. deck_id is a UUID.

    Experimental: internal API fields may reject scoped tokens or change.
    """
    result = _call("get_journey", deck_id=deck_id)
    if result.get("ok") is not False:
        result = _sanitize_card(result)
        result["zones"] = [_tag_user_text(zone) for zone in result.get("zones", [])]
        result["steps"] = [_sanitize_card(step) for step in result.get("steps", [])]
        for step in result["steps"]:
            step["label"] = _tag_user_text(step.get("label"))
        result["target_decks"] = {
            key: _sanitize_card(value) for key, value in result.get("target_decks", {}).items()
        }
        result["assignees"] = {
            key: {**value, "name": _tag_user_text(value.get("name"))}
            for key, value in result.get("assignees", {}).items()
        }
    return _finalize_tool_result(result)


def create_journey_step(
    deck_id: str, content: str, fields: dict | None = None, user_id: str | None = None
) -> dict:
    """Create a native Journey step; does not generate cards. Experimental internal API.

    fields uses Codecks camelCase: targetDeckId, assigneeId, effort, priority,
    masterTags. Use UUIDs for deck/user/tag IDs. user_id defaults to the token's
    user (organization tokens use CODECKS_USER_ID or the existing owner fallback).
    """
    return _finish_write(
        _call(
            "create_journey_step", deck_id=deck_id, content=content, fields=fields, user_id=user_id
        )
    )


def update_journey_step(item_id: str, fields: dict) -> dict:
    """Edit a step, preserving omitted fields. visibility=deleted soft-deletes it.

    Fields: content, targetDeckId, assigneeId, effort, priority, masterTags,
    visibility. Nullable values clear fields. Experimental internal API.
    """
    return _finish_write(_call("update_journey_step", item_id=item_id, fields=fields))


def order_journey_steps(
    deck_id: str, item_ids: list[str], target_id: str | None = None, label: str | None = None
) -> dict:
    """Move unique steps after target_id; None moves to the beginning.

    label selects a Journey zone (None for the unnamed zone). Steps and target
    must belong to this deck. Does not create dependencies. Experimental API.
    """
    return _finish_write(
        _call(
            "order_journey_steps",
            deck_id=deck_id,
            item_ids=item_ids,
            target_id=target_id,
            label=label,
        )
    )


def start_journey(card_id: str) -> dict:
    """Apply a card's native Journey and create its tasks. This is a write.

    Accepts a full UUID, #card number, or $Codecks reference. Repeated calls may
    create duplicate tasks. Experimental internal API; token denials propagate.
    """
    return _finish_write(_call("start_journey", card_id=card_id))


def register(mcp):
    """Register native Journey tools separately from ordinary card operations."""
    mcp.tool()(get_journey)
    mcp.tool()(create_journey_step)
    mcp.tool()(update_journey_step)
    mcp.tool()(order_journey_steps)
    mcp.tool()(start_journey)
