"""Codecks reference encoding and exact, account-scoped UUID lookup."""

from unittest.mock import patch

import pytest

from codecks_cli.card_refs import _sequence, _short_code, resolve_card_ids
from codecks_cli.client import CodecksClient
from codecks_cli.exceptions import CliError

CARD_ID = "00000000-0000-0000-0000-000000000001"


@pytest.mark.parametrize("number", [1, 28, 29, 627, 10000, 2**31 - 1])
def test_reference_round_trip(number):
    assert _sequence(_short_code(number)) == number
    assert _sequence(f"#{number}") == number
    assert _short_code(627) == "$1uc"


@pytest.mark.parametrize(
    "reference",
    ["#0", "#-1", "#2147483648", "$", "$abc0", "$11", "627", "00000000", "#" + "9" * 100],
)
def test_invalid_reference_never_queries(reference):
    with patch("codecks_cli.card_refs.query") as request:
        with pytest.raises(CliError) as error:
            resolve_card_ids([reference])
        assert error.value.error_code == "INVALID_INPUT"
        request.assert_not_called()


def test_mixed_references_use_one_exact_query_preserve_order_and_visibility():
    data = {"card": {CARD_ID: {"accountSeq": 627, "title": "Design", "visibility": "archived"}}}
    with patch("codecks_cli.card_refs.query", return_value=data) as request:
        result = CodecksClient(validate_token=False).resolve_card_ids([" $1UC ", "#627", CARD_ID])
    assert [c["id"] for c in result["cards"]] == [CARD_ID] * 3
    assert result["cards"][0]["short_code"] == "$1uc"
    assert result["cards"][0]["visibility"] == "archived"
    request.assert_called_once()
    query_text = str(request.call_args.args[0])
    assert "accountSeq" in query_text and "627" in query_text and CARD_ID in query_text
    assert "visibility" not in query_text.split("cards(", 1)[1].split(")", 1)[0]


def test_missing_reference_fails_the_entire_batch():
    with patch(
        "codecks_cli.card_refs.query", return_value={"card": {CARD_ID: {"accountSeq": 627}}}
    ):
        with pytest.raises(CliError, match="#628"):
            resolve_card_ids(["#627", "#628"])


def test_duplicate_sequence_is_rejected_instead_of_picking_a_card():
    cards = {
        CARD_ID: {"accountSeq": 627},
        "00000000-0000-0000-0000-000000000002": {"accountSeq": 627},
    }
    with patch("codecks_cli.card_refs.query", return_value={"card": cards}):
        with pytest.raises(CliError, match="ambiguous"):
            resolve_card_ids(["#627"])


@pytest.mark.parametrize("references", [[], ["#1"] * 101, [1], "#627"])
def test_batch_validation(references):
    with patch("codecks_cli.card_refs.query") as request:
        with pytest.raises(CliError):
            resolve_card_ids(references)
        request.assert_not_called()


def test_mcp_resolver_preserves_error_code_and_tags_titles():
    from codecks_cli.mcp_server import _core
    from codecks_cli.mcp_server import resolve_card_ids as tool

    client = CodecksClient(validate_token=False)
    with patch.object(_core, "_get_client", return_value=client):
        with patch(
            "codecks_cli.card_refs.query",
            side_effect=CliError("denied", error_code="PERMISSION_DENIED"),
        ):
            assert tool(["#627"])["error_code"] == "PERMISSION_DENIED"
        with patch(
            "codecks_cli.card_refs.query",
            return_value={"card": {CARD_ID: {"accountSeq": 627, "title": "Design"}}},
        ):
            assert "[USER_DATA]" in tool(["$1uc"])["cards"][0]["title"]
