"""Native Journey payloads, validation and MCP error/cache contracts."""

import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest

from codecks_cli import config, journeys
from codecks_cli.client import CodecksClient
from codecks_cli.exceptions import CliError

DECK = "00000000-0000-0000-0000-000000000001"
STEP = "00000000-0000-0000-0000-000000000002"
USER = "00000000-0000-0000-0000-000000000003"
CARD = "00000000-0000-0000-0000-000000000004"
ACCOUNT = "00000000-0000-0000-0000-000000000005"


@pytest.fixture(autouse=True)
def clear_pending_starts():
    journeys._pending_starts.clear()
    yield
    journeys._pending_starts.clear()


def test_read_uses_compound_deck_id_and_preserves_step_order():
    data = {
        "deck": {
            DECK: {
                "title": "Characters",
                "workflowItemOrderLabels": ["Produce"],
                "workflowItems": [STEP, CARD],
            }
        },
        "workflowItem": {
            STEP: {"content": "Later", "sortValue": 2},
            CARD: {"content": "Earlier", "sortValue": 1},
        },
    }
    with patch("codecks_cli.journeys.query", return_value=data) as request:
        result = CodecksClient(validate_token=False).get_journey(DECK)
    assert list(request.call_args.args[0]) == [f'deck(["{DECK}"])']
    assert [step["id"] for step in result["steps"]] == [CARD, STEP]
    assert result["zones"] == ["Produce"]


def test_create_update_order_use_native_endpoints_and_preserve_null_clears():
    client = CodecksClient(validate_token=False)
    with (
        patch("codecks_cli.api.session_request", return_value={"actionId": "action"}) as request,
        patch(
            "codecks_cli.journeys.get_journey",
            return_value={"steps": [{"id": STEP, "label": "Produce"}]},
        ),
    ):
        client.create_journey_step(
            DECK,
            "Concept",
            user_id=USER,
            fields={"targetDeckId": CARD, "effort": 0, "masterTags": [STEP]},
        )
        assert request.call_args.args == (
            "/dispatch/workflows/createItem",
            {
                "deckId": DECK,
                "userId": USER,
                "content": "Concept",
                "targetDeckId": CARD,
                "effort": 0,
                "masterTags": [STEP],
            },
        )
        client.update_journey_step(STEP, {"assigneeId": None, "visibility": "deleted"})
        assert request.call_args.args == (
            "/dispatch/workflows/updateItem",
            {"itemId": STEP, "assigneeId": None, "visibility": "deleted"},
        )
        client.order_journey_steps(DECK, [STEP], None, "Produce")
        assert request.call_args.args == (
            "/dispatch/workflows/addItemsAfter",
            {"deckId": DECK, "itemIds": [STEP], "targetId": None, "label": "Produce"},
        )


@pytest.mark.parametrize(
    "fields",
    [
        {},
        {"unknown": 1},
        {"effort": True},
        {"effort": -1},
        {"priority": "high"},
        {"content": " "},
        {"targetDeckId": "bad"},
        {"targetDeckId": "g" * 36},
        {"masterTags": None},
        {"visibility": "archived"},
        {"visibility": None},
        {"inDeps": [STEP]},
    ],
)
def test_invalid_update_never_dispatches(fields):
    with patch("codecks_cli.api.session_request") as request:
        with pytest.raises(CliError) as error:
            journeys.update_journey_step(STEP, fields)
        assert error.value.error_code == "INVALID_INPUT"
        request.assert_not_called()


@pytest.mark.parametrize("response", [None, [], "ok"])
def test_journey_write_rejects_nonobject_dispatch_responses(response):
    with patch("codecks_cli.api.session_request", return_value=response) as request:
        with pytest.raises(CliError, match="expected JSON object"):
            journeys.update_journey_step(STEP, {"content": "Concept"})
    request.assert_called_once_with(
        "/dispatch/workflows/updateItem", {"itemId": STEP, "content": "Concept"}
    )


@pytest.mark.parametrize("response", [{}, {"workflowItem": {STEP: {}}}])
def test_strict_journey_write_requires_shared_dispatch_acknowledgement(monkeypatch, response):
    monkeypatch.setattr(config, "RUNTIME_STRICT", True)
    with patch("codecks_cli.api.session_request", return_value=response) as request:
        with pytest.raises(CliError, match="missing expected ack fields") as error:
            journeys.update_journey_step(STEP, {"content": "Concept"})
    assert error.value.retryable is False
    request.assert_called_once()


@pytest.mark.parametrize("response", [{"actionId": "action"}, {"ok": True}, {"payload": {}}])
def test_strict_journey_write_preserves_shared_dispatch_acknowledgement(monkeypatch, response):
    monkeypatch.setattr(config, "RUNTIME_STRICT", True)
    with patch("codecks_cli.api.session_request", return_value=response):
        assert journeys.update_journey_step(STEP, {"content": "Concept"}) == {
            "ok": True,
            "response": response,
        }


@pytest.mark.parametrize(
    "items,target", [([], None), ([STEP, STEP], None), ([STEP], STEP), (["bad"], None)]
)
def test_invalid_order_never_dispatches(items, target):
    with patch("codecks_cli.api.session_request") as request:
        with pytest.raises(CliError):
            journeys.order_journey_steps(DECK, items, target, None)
        request.assert_not_called()


def test_start_resolves_card_reference_before_applying_and_does_not_retry_write():
    with (
        patch(
            "codecks_cli.journeys.resolve_card_ids", return_value={"cards": [{"id": CARD}]}
        ) as resolve,
        patch("codecks_cli.journeys._get_user_id", return_value=USER),
        patch("codecks_cli.journeys.get_account", return_value={"account": {ACCOUNT: {}}}),
        patch(
            "codecks_cli.journeys._read_journey_parent", side_effect=[(DECK, set()), (DECK, {STEP})]
        ),
        patch("codecks_cli.journeys.get_journey", return_value={"steps": [{"id": STEP}]}),
        patch("codecks_cli.api.session_request", return_value={}) as request,
    ):
        assert journeys.start_journey("$1uc")["ok"]
    resolve.assert_called_once_with(["$1uc"])
    request.assert_called_once_with(
        "/dispatch/workflows/apply",
        {"cardId": CARD, "itemIds": [STEP], "userId": USER, "accountId": ACCOUNT},
    )


def test_deleted_and_archived_steps_are_excluded():
    data = {
        "deck": {DECK: {"workflowItems": [STEP, CARD, USER]}},
        "workflowItem": {
            STEP: {"visibility": "default", "sortValue": "U"},
            CARD: {"visibility": "deleted", "sortValue": "j"},
            USER: {"visibility": "archived", "sortValue": "r"},
        },
    }
    with patch("codecks_cli.journeys.query", return_value=data):
        assert [step["id"] for step in journeys.get_journey(DECK)["steps"]] == [STEP]


def test_move_to_beginning_anchors_before_first_unmoved_step_in_zone():
    steps = [
        {"id": USER, "label": "Other"},
        {"id": CARD, "label": "Produce"},
        {"id": STEP, "label": "Produce"},
    ]
    with (
        patch("codecks_cli.journeys.get_journey", return_value={"steps": steps}),
        patch("codecks_cli.api.session_request", return_value={}) as request,
    ):
        journeys.order_journey_steps(DECK, [STEP], None, "Produce")
    request.assert_called_once_with(
        "/dispatch/workflows/addItemsBefore",
        {"deckId": DECK, "itemIds": [STEP], "targetId": CARD, "label": "Produce"},
    )


def test_order_rejects_steps_from_another_deck_before_write():
    with (
        patch("codecks_cli.journeys.get_journey", return_value={"steps": []}),
        patch("codecks_cli.api.session_request") as request,
    ):
        with pytest.raises(CliError, match="this deck"):
            journeys.order_journey_steps(DECK, [STEP], None, None)
    request.assert_not_called()


@pytest.mark.parametrize("fields", [[], "invalid"])
def test_create_rejects_nonobject_fields_before_write(fields):
    with patch("codecks_cli.api.session_request") as request:
        with pytest.raises(CliError) as error:
            journeys.create_journey_step(DECK, "Concept", fields=fields, user_id=USER)
    assert error.value.error_code == "INVALID_INPUT"
    request.assert_not_called()


@pytest.mark.parametrize(
    "operation,identifier", [(journeys.get_journey, DECK), (journeys.start_journey, CARD)]
)
def test_inaccessible_deck_or_parent_never_dispatches(operation, identifier):
    with (
        patch("codecks_cli.journeys.resolve_card_ids", return_value={"cards": [{"id": CARD}]}),
        patch("codecks_cli.journeys.query", return_value={}) as query,
        patch("codecks_cli.api.session_request") as request,
    ):
        with pytest.raises(CliError, match="missing or inaccessible") as error:
            operation(identifier)
    assert error.value.error_code == "INVALID_INPUT"
    query.assert_called_once()
    request.assert_not_called()


@pytest.mark.parametrize("label", [1, "x" * 201])
def test_order_rejects_invalid_label_before_read_or_write(label):
    with (
        patch("codecks_cli.journeys.get_journey") as read,
        patch("codecks_cli.api.session_request") as request,
    ):
        with pytest.raises(CliError) as error:
            journeys.order_journey_steps(DECK, [STEP], None, label)
    assert error.value.error_code == "INVALID_INPUT"
    read.assert_not_called()
    request.assert_not_called()


@pytest.mark.parametrize("visibility", ["archived", "deleted"])
def test_start_rejects_inactive_parent_before_read_or_write(visibility):
    with (
        patch(
            "codecks_cli.journeys.resolve_card_ids",
            return_value={"cards": [{"id": CARD, "visibility": visibility}]},
        ),
        patch("codecks_cli.journeys.query") as query,
        patch("codecks_cli.api.session_request") as request,
    ):
        with pytest.raises(CliError, match="active card") as error:
            journeys.start_journey(CARD)
    assert error.value.error_code == "INVALID_INPUT"
    query.assert_not_called()
    request.assert_not_called()


@pytest.mark.parametrize("accounts", [{}, {ACCOUNT: {}, USER: {}}])
def test_start_requires_exactly_one_account_before_write(accounts):
    with (
        patch("codecks_cli.journeys.resolve_card_ids", return_value={"cards": [{"id": CARD}]}),
        patch("codecks_cli.journeys._read_journey_parent", return_value=(DECK, set())),
        patch("codecks_cli.journeys.get_journey", return_value={"steps": [{"id": STEP}]}),
        patch("codecks_cli.journeys._get_user_id", return_value=USER),
        patch("codecks_cli.journeys.get_account", return_value={"account": accounts}),
        patch("codecks_cli.api.session_request") as request,
    ):
        with pytest.raises(CliError, match="resolve Journey account") as error:
            journeys.start_journey(CARD)
    assert error.value.error_code == "INVALID_INPUT"
    assert CARD not in journeys._pending_starts
    request.assert_not_called()


def test_concurrent_starts_re_read_inside_parent_lock():
    entered = threading.Event()
    release = threading.Event()
    second_resolved = threading.Event()
    applied = set()

    def resolve(refs):
        if refs == ["#4"]:
            second_resolved.set()
        return {"cards": [{"id": CARD}]}

    def dispatch(*args):
        entered.set()
        assert release.wait(5)
        applied.add(STEP)
        return {}

    with (
        patch("codecks_cli.journeys.resolve_card_ids", side_effect=resolve),
        patch(
            "codecks_cli.journeys._read_journey_parent",
            side_effect=lambda _: (DECK, applied.copy()),
        ),
        patch("codecks_cli.journeys.get_journey", return_value={"steps": [{"id": STEP}]}),
        patch("codecks_cli.journeys._get_user_id", return_value=USER),
        patch("codecks_cli.journeys.get_account", return_value={"account": {ACCOUNT: {}}}),
        patch("codecks_cli.api.session_request", side_effect=dispatch) as request,
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        first = pool.submit(journeys.start_journey, CARD)
        try:
            assert entered.wait(5)
            second = pool.submit(journeys.start_journey, "#4")
            assert second_resolved.wait(5)
            assert not second.done()
        finally:
            release.set()
        assert first.result(timeout=5)["ok"]
        assert second.result(timeout=5)["created"] == 0
    request.assert_called_once()


@pytest.mark.parametrize(
    "failure",
    ["timeout", "native_timeout", "verification_read", "missing_children", "strict_response"],
)
def test_uncertain_start_blocks_writes_until_submitted_steps_are_visible(monkeypatch, failure):
    monkeypatch.setattr(config, "RUNTIME_STRICT", failure == "strict_response")
    applied = set()
    read_count = 0

    def read(_):
        nonlocal read_count
        read_count += 1
        if failure == "verification_read" and read_count == 2:
            raise CliError("read failed", error_code="NETWORK_ERROR")
        return DECK, applied.copy()

    with (
        patch("codecks_cli.journeys.resolve_card_ids", return_value={"cards": [{"id": CARD}]}),
        patch("codecks_cli.journeys._read_journey_parent", side_effect=read),
        patch("codecks_cli.journeys.get_journey", return_value={"steps": [{"id": STEP}]}),
        patch("codecks_cli.journeys._get_user_id", return_value=USER),
        patch("codecks_cli.journeys.get_account", return_value={"account": {ACCOUNT: {}}}),
        patch("codecks_cli.api.session_request", return_value={}) as request,
    ):
        if failure == "timeout":
            request.side_effect = CliError("timed out", error_code="NETWORK_ERROR")
        elif failure == "native_timeout":
            request.side_effect = TimeoutError("timed out")
        for _ in range(2):
            with pytest.raises(CliError) as error:
                journeys.start_journey(CARD)
            assert error.value.error_code == "JOURNEY_OUTCOME_UNKNOWN"
            assert error.value.retryable is False
        request.assert_called_once()
        applied.add(STEP)
        assert journeys.start_journey(CARD)["created"] == 0
        assert CARD not in journeys._pending_starts
        request.assert_called_once()


@pytest.mark.parametrize(
    "error_code", ["TOKEN_EXPIRED", "PERMISSION_DENIED", "RATE_LIMITED", "INVALID_INPUT"]
)
def test_definite_rejection_clears_pending_and_preserves_error(error_code):
    rejection = CliError("rejected", error_code=error_code, retryable=error_code == "RATE_LIMITED")
    with (
        patch("codecks_cli.journeys.resolve_card_ids", return_value={"cards": [{"id": CARD}]}),
        patch(
            "codecks_cli.journeys._read_journey_parent",
            side_effect=[(DECK, set()), (DECK, set()), (DECK, {STEP})],
        ),
        patch("codecks_cli.journeys.get_journey", return_value={"steps": [{"id": STEP}]}),
        patch("codecks_cli.journeys._get_user_id", return_value=USER),
        patch("codecks_cli.journeys.get_account", return_value={"account": {ACCOUNT: {}}}),
        patch("codecks_cli.api.session_request", side_effect=rejection) as request,
    ):
        with pytest.raises(CliError) as error:
            journeys.start_journey(CARD)
        assert error.value is rejection
        assert CARD not in journeys._pending_starts
        request.assert_called_once()
        request.side_effect = None
        request.return_value = {"actionId": "accepted"}
        assert journeys.start_journey(CARD)["ok"]
        assert request.call_count == 2
        assert CARD not in journeys._pending_starts


def test_start_skips_previously_applied_steps_and_is_noop_when_complete():
    data = {
        "card": {
            CARD: {"deckId": DECK, "childCards": [USER]},
            USER: {"sourceWorkflowItemId": STEP},
        }
    }
    with (
        patch("codecks_cli.journeys.resolve_card_ids", return_value={"cards": [{"id": CARD}]}),
        patch("codecks_cli.journeys.query", return_value=data),
        patch("codecks_cli.journeys.get_journey", return_value={"steps": [{"id": STEP}]}),
        patch("codecks_cli.api.session_request") as request,
    ):
        assert journeys.start_journey(CARD)["created"] == 0
    request.assert_not_called()


def test_mcp_denial_preserves_scope_error_without_falling_back():
    from codecks_cli.mcp_server import _core, update_journey_step

    with (
        patch.object(_core, "_get_client", return_value=CodecksClient(validate_token=False)),
        patch(
            "codecks_cli.api.session_request",
            side_effect=CliError("requires workflowTemplate:write", error_code="PERMISSION_DENIED"),
        ) as request,
    ):
        result = update_journey_step(STEP, {"content": "Concept"})
    assert result["error_code"] == "PERMISSION_DENIED"
    assert result["retryable"] is False
    request.assert_called_once()


def test_successful_journey_write_invalidates_card_snapshot():
    from codecks_cli.mcp_server import _core, update_journey_step

    _core._snapshot_cache = {"cards_result": {"cards": []}}
    with (
        patch.object(_core, "_get_client", return_value=CodecksClient(validate_token=False)),
        patch("codecks_cli.api.session_request", return_value={}),
    ):
        assert update_journey_step(STEP, {"content": "Concept"})["ok"]
    assert "cards_result" not in _core._snapshot_cache


def test_uncertain_journey_write_invalidates_snapshot_and_is_not_retryable():
    from codecks_cli.mcp_server import _core, start_journey

    _core._snapshot_cache = {"cards_result": {"cards": []}}
    with (
        patch.object(_core, "_get_client", return_value=CodecksClient(validate_token=False)),
        patch("codecks_cli.journeys.start_journey", side_effect=journeys._uncertain_start(CARD)),
    ):
        result = start_journey(CARD)
    assert result["error_code"] == "JOURNEY_OUTCOME_UNKNOWN"
    assert result["retryable"] is False
    assert "cards_result" not in _core._snapshot_cache


def test_mcp_read_tags_user_content_and_labels():
    from codecks_cli.mcp_server import _core, get_journey

    data = {
        "deck": {
            DECK: {
                "title": "Characters",
                "workflowItems": [STEP],
                "workflowItemOrderLabels": ["Produce"],
            }
        },
        "workflowItem": {STEP: {"content": "Concept", "label": "Produce"}},
    }
    with (
        patch.object(_core, "_get_client", return_value=CodecksClient(validate_token=False)),
        patch("codecks_cli.journeys.query", return_value=data),
    ):
        result = get_journey(DECK)
    assert result["steps"][0]["content"] == "[USER_DATA]Concept[/USER_DATA]"
    assert result["zones"] == ["[USER_DATA]Produce[/USER_DATA]"]


def test_mcp_write_tags_nested_dispatch_content():
    from codecks_cli.mcp_server import _core, update_journey_step

    with (
        patch.object(_core, "_get_client", return_value=CodecksClient(validate_token=False)),
        patch(
            "codecks_cli.api.session_request",
            return_value={"workflowItem": {STEP: {"content": "Concept", "label": "Produce"}}},
        ),
    ):
        result = update_journey_step(STEP, {"content": "Concept"})
    assert result["response"]["workflowItem"][STEP]["content"] == "[USER_DATA]Concept[/USER_DATA]"
    assert result["response"]["workflowItem"][STEP]["label"] == "[USER_DATA]Produce[/USER_DATA]"


def test_mcp_create_and_order_invalidate_cache_and_sanitize_nested_lists():
    from codecks_cli.mcp_server import _core, create_journey_step, order_journey_steps

    response = {
        "actionId": "accepted",
        "payload": {"items": [{"content": "Concept", "name": "Artist", "label": "Produce"}]},
    }
    with (
        patch.object(_core, "_get_client", return_value=CodecksClient(validate_token=False)),
        patch("codecks_cli.api.session_request", return_value=response) as request,
        patch(
            "codecks_cli.journeys.get_journey",
            return_value={
                "steps": [{"id": STEP, "label": "Produce"}, {"id": CARD, "label": "Produce"}]
            },
        ),
    ):
        _core._snapshot_cache = {"cards_result": {"cards": []}}
        created = create_journey_step(DECK, "Concept", fields={"targetDeckId": CARD}, user_id=USER)
        assert created["ok"]
        assert "cards_result" not in _core._snapshot_cache
        request.assert_called_once_with(
            "/dispatch/workflows/createItem",
            {"deckId": DECK, "userId": USER, "content": "Concept", "targetDeckId": CARD},
        )
        _core._snapshot_cache = {"cards_result": {"cards": []}}
        ordered = order_journey_steps(DECK, [CARD], label="Produce")
        assert ordered["ok"]
        assert "cards_result" not in _core._snapshot_cache
        assert request.call_count == 2
        assert request.call_args.args == (
            "/dispatch/workflows/addItemsBefore",
            {"deckId": DECK, "itemIds": [CARD], "targetId": STEP, "label": "Produce"},
        )
    expected = {
        "content": "[USER_DATA]Concept[/USER_DATA]",
        "name": "[USER_DATA]Artist[/USER_DATA]",
        "label": "[USER_DATA]Produce[/USER_DATA]",
    }
    assert created["response"]["payload"]["items"] == [expected]
    assert ordered["response"]["payload"]["items"] == [expected]
    assert response["payload"]["items"] == [
        {"content": "Concept", "name": "Artist", "label": "Produce"}
    ]
