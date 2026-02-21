"""Tests for MCP server tool wrappers.

Mocks at CodecksClient level. Verifies each tool calls the correct
client method and that errors are converted to dicts.
"""

import pytest

mcp_mod = pytest.importorskip("codecks_cli.mcp_server", reason="mcp package not installed")

from unittest.mock import MagicMock, patch  # noqa: E402

from codecks_cli.exceptions import CliError, SetupError  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_client_cache():
    """Reset the cached CodecksClient between tests."""
    mcp_mod._client = None
    yield
    mcp_mod._client = None


def _mock_client(**method_returns):
    """Return a patched CodecksClient whose methods return given values."""
    client = MagicMock()
    for name, val in method_returns.items():
        getattr(client, name).return_value = val
    return client


# ---------------------------------------------------------------------------
# Read tools
# ---------------------------------------------------------------------------


class TestReadTools:
    @patch("codecks_cli.mcp_server.CodecksClient")
    def test_get_account(self, MockClient):
        MockClient.return_value = _mock_client(get_account={"name": "Alice", "id": "u1"})
        result = mcp_mod.get_account()
        assert result["name"] == "Alice"

    @patch("codecks_cli.mcp_server.CodecksClient")
    def test_list_cards(self, MockClient):
        client = _mock_client(list_cards={"cards": [{"id": "c1"}], "stats": None})
        MockClient.return_value = client
        result = mcp_mod.list_cards(status="started", sort="priority")
        assert len(result["cards"]) == 1
        assert result["total_count"] == 1
        assert result["has_more"] is False
        client.list_cards.assert_called_once_with(
            deck=None,
            status="started",
            project=None,
            search=None,
            milestone=None,
            tag=None,
            owner=None,
            priority=None,
            sort="priority",
            card_type=None,
            hero=None,
            hand_only=False,
            stale_days=None,
            updated_after=None,
            updated_before=None,
            archived=False,
            include_stats=False,
        )

    @patch("codecks_cli.mcp_server.CodecksClient")
    def test_get_card(self, MockClient):
        MockClient.return_value = _mock_client(get_card={"id": "c1", "title": "Test"})
        result = mcp_mod.get_card("c1")
        assert result["id"] == "c1"

    @patch("codecks_cli.mcp_server.CodecksClient")
    def test_list_decks(self, MockClient):
        MockClient.return_value = _mock_client(list_decks=[{"id": "d1", "title": "Features"}])
        result = mcp_mod.list_decks()
        assert result[0]["title"] == "Features"

    @patch("codecks_cli.mcp_server.CodecksClient")
    def test_list_projects(self, MockClient):
        MockClient.return_value = _mock_client(list_projects=[{"id": "p1", "name": "Tea"}])
        result = mcp_mod.list_projects()
        assert result[0]["name"] == "Tea"

    @patch("codecks_cli.mcp_server.CodecksClient")
    def test_list_milestones(self, MockClient):
        MockClient.return_value = _mock_client(list_milestones=[{"id": "m1", "name": "MVP"}])
        result = mcp_mod.list_milestones()
        assert result[0]["name"] == "MVP"

    @patch("codecks_cli.mcp_server.CodecksClient")
    def test_list_activity(self, MockClient):
        client = _mock_client(list_activity={"activity": {}})
        MockClient.return_value = client
        result = mcp_mod.list_activity(limit=5)
        client.list_activity.assert_called_once_with(limit=5)
        assert "activity" in result

    @patch("codecks_cli.mcp_server.CodecksClient")
    def test_pm_focus(self, MockClient):
        MockClient.return_value = _mock_client(pm_focus={"counts": {}, "suggested": []})
        result = mcp_mod.pm_focus(project="Tea")
        assert "counts" in result

    @patch("codecks_cli.mcp_server.CodecksClient")
    def test_standup(self, MockClient):
        MockClient.return_value = _mock_client(standup={"recently_done": [], "in_progress": []})
        result = mcp_mod.standup(days=3)
        assert "recently_done" in result


# ---------------------------------------------------------------------------
# Hand tools
# ---------------------------------------------------------------------------


class TestHandTools:
    @patch("codecks_cli.mcp_server.CodecksClient")
    def test_list_hand(self, MockClient):
        MockClient.return_value = _mock_client(list_hand=[{"id": "c1"}])
        result = mcp_mod.list_hand()
        assert len(result) == 1

    @patch("codecks_cli.mcp_server.CodecksClient")
    def test_add_to_hand(self, MockClient):
        client = _mock_client(add_to_hand={"ok": True, "added": 2})
        MockClient.return_value = client
        result = mcp_mod.add_to_hand(["c1", "c2"])
        assert result["added"] == 2
        client.add_to_hand.assert_called_once_with(card_ids=["c1", "c2"])

    @patch("codecks_cli.mcp_server.CodecksClient")
    def test_remove_from_hand(self, MockClient):
        client = _mock_client(remove_from_hand={"ok": True, "removed": 1})
        MockClient.return_value = client
        result = mcp_mod.remove_from_hand(["c1"])
        assert result["removed"] == 1


# ---------------------------------------------------------------------------
# Mutation tools
# ---------------------------------------------------------------------------


class TestMutationTools:
    @patch("codecks_cli.mcp_server.CodecksClient")
    def test_create_card(self, MockClient):
        MockClient.return_value = _mock_client(
            create_card={"ok": True, "card_id": "new-1", "title": "Test"}
        )
        result = mcp_mod.create_card("Test", deck="Features")
        assert result["ok"] is True

    @patch("codecks_cli.mcp_server.CodecksClient")
    def test_update_cards(self, MockClient):
        client = _mock_client(update_cards={"ok": True, "updated": 1})
        MockClient.return_value = client
        result = mcp_mod.update_cards(["c1"], status="done")
        assert result["updated"] == 1
        client.update_cards.assert_called_once()

    @patch("codecks_cli.mcp_server.CodecksClient")
    def test_mark_done(self, MockClient):
        MockClient.return_value = _mock_client(mark_done={"ok": True, "count": 2})
        result = mcp_mod.mark_done(["c1", "c2"])
        assert result["count"] == 2

    @patch("codecks_cli.mcp_server.CodecksClient")
    def test_mark_started(self, MockClient):
        MockClient.return_value = _mock_client(mark_started={"ok": True, "count": 1})
        result = mcp_mod.mark_started(["c1"])
        assert result["count"] == 1

    @patch("codecks_cli.mcp_server.CodecksClient")
    def test_archive_card(self, MockClient):
        MockClient.return_value = _mock_client(archive_card={"ok": True, "card_id": "c1"})
        result = mcp_mod.archive_card("c1")
        assert result["ok"] is True

    @patch("codecks_cli.mcp_server.CodecksClient")
    def test_unarchive_card(self, MockClient):
        MockClient.return_value = _mock_client(unarchive_card={"ok": True, "card_id": "c1"})
        result = mcp_mod.unarchive_card("c1")
        assert result["ok"] is True

    @patch("codecks_cli.mcp_server.CodecksClient")
    def test_delete_card(self, MockClient):
        MockClient.return_value = _mock_client(delete_card={"ok": True, "card_id": "c1"})
        result = mcp_mod.delete_card("c1")
        assert result["ok"] is True

    @patch("codecks_cli.mcp_server.CodecksClient")
    def test_scaffold_feature(self, MockClient):
        MockClient.return_value = _mock_client(
            scaffold_feature={"ok": True, "hero": {"id": "h1"}, "subcards": []}
        )
        result = mcp_mod.scaffold_feature(
            "Inventory", hero_deck="Features", code_deck="Code", design_deck="Design"
        )
        assert result["ok"] is True


# ---------------------------------------------------------------------------
# Comment tools
# ---------------------------------------------------------------------------


class TestCommentTools:
    @patch("codecks_cli.mcp_server.CodecksClient")
    def test_create_comment(self, MockClient):
        MockClient.return_value = _mock_client(create_comment={"ok": True})
        result = mcp_mod.create_comment("c1", "Hello")
        assert result["ok"] is True

    @patch("codecks_cli.mcp_server.CodecksClient")
    def test_reply_comment(self, MockClient):
        client = _mock_client(reply_comment={"ok": True, "thread_id": "t1", "data": {}})
        MockClient.return_value = client
        result = mcp_mod.reply_comment("t1", "Thanks!")
        assert result["ok"] is True
        client.reply_comment.assert_called_once_with(thread_id="t1", message="Thanks!")

    @patch("codecks_cli.mcp_server.CodecksClient")
    def test_close_comment(self, MockClient):
        client = _mock_client(close_comment={"ok": True, "thread_id": "t1", "data": {}})
        MockClient.return_value = client
        result = mcp_mod.close_comment("t1", "c1")
        assert result["ok"] is True
        client.close_comment.assert_called_once_with(thread_id="t1", card_id="c1")

    @patch("codecks_cli.mcp_server.CodecksClient")
    def test_reopen_comment(self, MockClient):
        client = _mock_client(reopen_comment={"ok": True, "thread_id": "t1", "data": {}})
        MockClient.return_value = client
        result = mcp_mod.reopen_comment("t1", "c1")
        assert result["ok"] is True
        client.reopen_comment.assert_called_once_with(thread_id="t1", card_id="c1")

    @patch("codecks_cli.mcp_server.CodecksClient")
    def test_list_conversations(self, MockClient):
        MockClient.return_value = _mock_client(list_conversations={"resolvable": {}})
        result = mcp_mod.list_conversations("c1")
        assert "resolvable" in result


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


class TestPagination:
    @patch("codecks_cli.mcp_server.CodecksClient")
    def test_pagination_defaults(self, MockClient):
        """Default limit=50, offset=0 returns all cards when under limit."""
        cards = [{"id": f"c{i}"} for i in range(10)]
        MockClient.return_value = _mock_client(list_cards={"cards": cards, "stats": None})
        result = mcp_mod.list_cards()
        assert len(result["cards"]) == 10
        assert result["total_count"] == 10
        assert result["has_more"] is False
        assert result["limit"] == 50
        assert result["offset"] == 0

    @patch("codecks_cli.mcp_server.CodecksClient")
    def test_pagination_limit(self, MockClient):
        """Limit restricts the number of returned cards."""
        cards = [{"id": f"c{i}"} for i in range(10)]
        MockClient.return_value = _mock_client(list_cards={"cards": cards, "stats": None})
        result = mcp_mod.list_cards(limit=3)
        assert len(result["cards"]) == 3
        assert result["cards"][0]["id"] == "c0"
        assert result["total_count"] == 10
        assert result["has_more"] is True

    @patch("codecks_cli.mcp_server.CodecksClient")
    def test_pagination_offset(self, MockClient):
        """Offset skips cards."""
        cards = [{"id": f"c{i}"} for i in range(10)]
        MockClient.return_value = _mock_client(list_cards={"cards": cards, "stats": None})
        result = mcp_mod.list_cards(limit=3, offset=7)
        assert len(result["cards"]) == 3
        assert result["cards"][0]["id"] == "c7"
        assert result["total_count"] == 10
        assert result["has_more"] is False

    @patch("codecks_cli.mcp_server.CodecksClient")
    def test_pagination_offset_past_end(self, MockClient):
        """Offset past end returns empty cards list."""
        cards = [{"id": f"c{i}"} for i in range(5)]
        MockClient.return_value = _mock_client(list_cards={"cards": cards, "stats": None})
        result = mcp_mod.list_cards(limit=10, offset=20)
        assert len(result["cards"]) == 0
        assert result["total_count"] == 5
        assert result["has_more"] is False

    @patch("codecks_cli.mcp_server.CodecksClient")
    def test_pagination_preserves_stats(self, MockClient):
        """Stats are passed through from the client response."""
        stats = {"by_status": {"started": 3}}
        MockClient.return_value = _mock_client(list_cards={"cards": [{"id": "c1"}], "stats": stats})
        result = mcp_mod.list_cards(include_stats=True)
        assert result["stats"] == stats

    @patch("codecks_cli.mcp_server.CodecksClient")
    def test_pagination_not_applied_to_errors(self, MockClient):
        """Error dicts are returned as-is without pagination."""
        client = MagicMock()
        client.list_cards.side_effect = CliError("[ERROR] Bad filter")
        MockClient.return_value = client
        result = mcp_mod.list_cards()
        assert result["ok"] is False
        assert "total_count" not in result


# ---------------------------------------------------------------------------
# Client caching
# ---------------------------------------------------------------------------


class TestClientCaching:
    @patch("codecks_cli.mcp_server.CodecksClient")
    def test_client_is_cached(self, MockClient):
        """CodecksClient is instantiated once and reused across calls."""
        client = _mock_client(
            get_account={"name": "Alice"},
            list_decks=[],
        )
        MockClient.return_value = client
        mcp_mod.get_account()
        mcp_mod.list_decks()
        MockClient.assert_called_once()


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    @patch("codecks_cli.mcp_server.CodecksClient")
    def test_cli_error_returns_error_dict(self, MockClient):
        client = MagicMock()
        client.list_cards.side_effect = CliError("[ERROR] Invalid sort field")
        MockClient.return_value = client
        result = mcp_mod.list_cards()
        assert result["ok"] is False
        assert result["type"] == "error"
        assert "Invalid sort field" in result["error"]

    @patch("codecks_cli.mcp_server.CodecksClient")
    def test_setup_error_returns_setup_dict(self, MockClient):
        MockClient.side_effect = SetupError("[TOKEN_EXPIRED] Session expired")
        result = mcp_mod.get_account()
        assert result["ok"] is False
        assert result["type"] == "setup"
        assert "TOKEN_EXPIRED" in result["error"]

    @patch("codecks_cli.mcp_server.CodecksClient")
    def test_error_result_is_json_serializable(self, MockClient):
        import json

        client = MagicMock()
        client.get_card.side_effect = CliError("[ERROR] Not found")
        MockClient.return_value = client
        result = mcp_mod.get_card("bad-id")
        # Must not raise
        serialized = json.dumps(result)
        assert "Not found" in serialized
