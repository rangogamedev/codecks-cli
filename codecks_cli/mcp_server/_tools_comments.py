"""Comment tools: comment CRUD (5 tools)."""

from __future__ import annotations

from codecks_cli import CliError
from codecks_cli.mcp_server._core import (
    _call,
    _contract_error,
    _finalize_tool_result,
    _validate_uuid,
)
from codecks_cli.mcp_server._security import _sanitize_conversations, _validate_input


def create_comment(card_id: str, message: str) -> dict:
    """Start a new comment thread on a card."""
    try:
        _validate_uuid(card_id)
        message = _validate_input(message, "message")
    except CliError as e:
        return _finalize_tool_result(_contract_error(str(e), "error"))
    return _finalize_tool_result(_call("create_comment", card_id=card_id, message=message))


def reply_comment(thread_id: str, message: str) -> dict:
    """Reply to an existing comment thread.

    Args:
        thread_id: From list_conversations response.
    """
    try:
        message = _validate_input(message, "message")
    except CliError as e:
        return _finalize_tool_result(_contract_error(str(e), "error"))
    return _finalize_tool_result(_call("reply_comment", thread_id=thread_id, message=message))


def close_comment(thread_id: str, card_id: str) -> dict:
    """Close (resolve) a comment thread."""
    try:
        _validate_uuid(card_id)
    except CliError as e:
        return _finalize_tool_result(_contract_error(str(e), "error"))
    return _finalize_tool_result(_call("close_comment", thread_id=thread_id, card_id=card_id))


def reopen_comment(thread_id: str, card_id: str) -> dict:
    """Reopen a closed comment thread."""
    try:
        _validate_uuid(card_id)
    except CliError as e:
        return _finalize_tool_result(_contract_error(str(e), "error"))
    return _finalize_tool_result(_call("reopen_comment", thread_id=thread_id, card_id=card_id))


def list_conversations(card_id: str) -> dict:
    """List all comment threads on a card with messages and thread IDs."""
    try:
        _validate_uuid(card_id)
    except CliError as e:
        return _finalize_tool_result(_contract_error(str(e), "error"))
    result = _call("list_conversations", card_id=card_id)
    if isinstance(result, dict) and result.get("ok") is not False:
        return _finalize_tool_result(_sanitize_conversations(result))
    return _finalize_tool_result(result)


def register(mcp):
    """Register all comment tools with the FastMCP instance."""
    mcp.tool()(create_comment)
    mcp.tool()(reply_comment)
    mcp.tool()(close_comment)
    mcp.tool()(reopen_comment)
    mcp.tool()(list_conversations)
