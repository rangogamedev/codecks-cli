"""Tests for CodecksClient — the public programmatic API surface.
Mocks at cards.*/api.* boundary. Asserts on returned dicts, not stdout.
"""

from unittest.mock import patch

import pytest

from codecks_cli.client import (
    CodecksClient,
    _flatten_cards,
    _sort_cards,
)
from codecks_cli.exceptions import CliError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client():
    """Create a CodecksClient with token validation skipped."""
    return CodecksClient(validate_token=False)


# ---------------------------------------------------------------------------
# Flatten / legacy format round-trip
# ---------------------------------------------------------------------------


class TestFlattenCards:
    def test_injects_id_into_each_card(self):
        cards_dict = {
            "uuid-1": {"title": "A", "status": "done"},
            "uuid-2": {"title": "B", "status": "started"},
        }
        flat = _flatten_cards(cards_dict)
        assert len(flat) == 2
        assert flat[0]["id"] == "uuid-1"
        assert flat[0]["title"] == "A"
        assert flat[1]["id"] == "uuid-2"

    def test_empty_dict_returns_empty_list(self):
        assert _flatten_cards({}) == []

    def test_preserves_original_values(self):
        cards_dict = {
            "c1": {"title": "X", "status": "done"},
            "c2": {"title": "Y", "status": "started"},
        }
        flat = _flatten_cards(cards_dict)
        assert flat[0]["title"] == "X"
        assert flat[1]["title"] == "Y"


# ---------------------------------------------------------------------------
# Sort helpers
# ---------------------------------------------------------------------------


class TestSortCards:
    def test_sort_by_priority(self):
        cards = {
            "c1": {"title": "B", "priority": "b"},
            "c2": {"title": "A", "priority": "a"},
            "c3": {"title": "C", "priority": None},
        }
        sorted_cards = _sort_cards(cards, "priority")
        keys = list(sorted_cards.keys())
        assert keys[0] == "c2"  # a before b
        assert keys[1] == "c1"
        assert keys[2] == "c3"  # None last

    def test_sort_by_updated_newest_first(self):
        cards = {
            "old": {"title": "Old", "lastUpdatedAt": "2026-01-01"},
            "new": {"title": "New", "lastUpdatedAt": "2026-01-10"},
        }
        sorted_cards = _sort_cards(cards, "updated")
        assert list(sorted_cards.keys()) == ["new", "old"]


# ---------------------------------------------------------------------------
# list_cards
# ---------------------------------------------------------------------------


class TestListCards:
    @patch("codecks_cli.client.enrich_cards", side_effect=lambda c, u: c)
    @patch("codecks_cli.client.list_cards")
    def test_returns_flat_card_list(self, mock_list, mock_enrich):
        mock_list.return_value = {
            "card": {
                "c1": {"title": "Card A", "status": "done"},
                "c2": {"title": "Card B", "status": "started"},
            },
            "user": {},
        }
        client = _client()
        result = client.list_cards()
        assert "cards" in result
        assert len(result["cards"]) == 2
        assert result["cards"][0]["id"] in ("c1", "c2")

    @patch("codecks_cli.client.compute_card_stats")
    @patch("codecks_cli.client.enrich_cards", side_effect=lambda c, u: c)
    @patch("codecks_cli.client.list_cards")
    def test_include_stats(self, mock_list, mock_enrich, mock_stats):
        mock_list.return_value = {"card": {"c1": {"title": "A", "status": "done"}}, "user": {}}
        mock_stats.return_value = {"total": 1, "by_status": {"done": 1}}
        client = _client()
        result = client.list_cards(include_stats=True)
        assert "stats" in result
        assert "cards" in result
        assert result["stats"]["total"] == 1
        assert len(result["cards"]) == 1

    @patch("codecks_cli.client.enrich_cards", side_effect=lambda c, u: c)
    @patch("codecks_cli.client.list_cards")
    def test_stats_null_by_default(self, mock_list, mock_enrich):
        mock_list.return_value = {"card": {"c1": {"title": "A"}}, "user": {}}
        client = _client()
        result = client.list_cards()
        assert result["stats"] is None
        assert "cards" in result

    @patch("codecks_cli.client.enrich_cards", side_effect=lambda c, u: c)
    @patch("codecks_cli.client.list_cards")
    def test_sort_applied(self, mock_list, mock_enrich):
        mock_list.return_value = {
            "card": {
                "c1": {"title": "B", "priority": "b"},
                "c2": {"title": "A", "priority": "a"},
            },
            "user": {},
        }
        client = _client()
        result = client.list_cards(sort="priority")
        titles = [c["title"] for c in result["cards"]]
        assert titles[0] == "A"

    def test_invalid_sort_raises(self):
        client = _client()
        with pytest.raises(CliError) as exc_info:
            client.list_cards(sort="invalid_field")
        assert "Invalid sort field" in str(exc_info.value)

    def test_invalid_card_type_raises(self):
        client = _client()
        with pytest.raises(CliError) as exc_info:
            client.list_cards(card_type="invalid_type")
        assert "Invalid card type" in str(exc_info.value)

    @patch("codecks_cli.client.extract_hand_card_ids")
    @patch("codecks_cli.client.list_hand")
    @patch("codecks_cli.client.enrich_cards", side_effect=lambda c, u: c)
    @patch("codecks_cli.client.list_cards")
    def test_hand_only_filter(self, mock_list, mock_enrich, mock_list_hand, mock_extract):
        mock_list.return_value = {
            "card": {
                "c1": {"title": "In hand", "status": "started"},
                "c2": {"title": "Not in hand", "status": "done"},
            },
            "user": {},
        }
        mock_list_hand.return_value = {}
        mock_extract.return_value = {"c1"}
        client = _client()
        result = client.list_cards(hand_only=True)
        assert len(result["cards"]) == 1
        assert result["cards"][0]["title"] == "In hand"


# ---------------------------------------------------------------------------
# get_card
# ---------------------------------------------------------------------------


class TestGetCard:
    @patch("codecks_cli.client.extract_hand_card_ids")
    @patch("codecks_cli.client.list_hand")
    @patch("codecks_cli.client.enrich_cards", side_effect=lambda c, u: c)
    @patch("codecks_cli.client.get_card")
    def test_returns_flat_card_detail(self, mock_get, mock_enrich, mock_hand, mock_extract):
        mock_get.return_value = {
            "card": {
                "uuid-123": {
                    "title": "Test Card",
                    "status": "started",
                    "content": "Test Card\nBody text",
                },
            },
            "user": {},
        }
        mock_hand.return_value = {}
        mock_extract.return_value = set()
        client = _client()
        detail = client.get_card("uuid-123")
        assert detail["id"] == "uuid-123"
        assert detail["title"] == "Test Card"
        assert detail["in_hand"] is False

    @patch("codecks_cli.client.extract_hand_card_ids")
    @patch("codecks_cli.client.list_hand")
    @patch("codecks_cli.client.enrich_cards", side_effect=lambda c, u: c)
    @patch("codecks_cli.client.get_card")
    def test_finds_requested_card_not_first(self, mock_get, mock_enrich, mock_hand, mock_extract):
        """Bug fix regression: get_card() should find the requested card, not the first one."""
        mock_get.return_value = {
            "card": {
                "child-1": {"title": "Child Card", "status": "done"},
                "hero-id": {
                    "title": "Hero Card",
                    "status": "started",
                    "childCards": ["child-1"],
                },
            },
            "user": {},
        }
        mock_hand.return_value = {}
        mock_extract.return_value = set()
        client = _client()
        detail = client.get_card("hero-id")
        assert detail["id"] == "hero-id"
        assert detail["title"] == "Hero Card"
        assert "sub_cards" in detail
        assert len(detail["sub_cards"]) == 1

    @patch("codecks_cli.client.extract_hand_card_ids")
    @patch("codecks_cli.client.list_hand")
    @patch("codecks_cli.client.enrich_cards", side_effect=lambda c, u: c)
    @patch("codecks_cli.client.get_card")
    def test_card_not_found_raises(self, mock_get, mock_enrich, mock_hand, mock_extract):
        mock_get.return_value = {"card": {}, "user": {}}
        mock_hand.return_value = {}
        mock_extract.return_value = set()
        client = _client()
        with pytest.raises(CliError) as exc_info:
            client.get_card("nonexistent")
        assert "not found" in str(exc_info.value)

    @patch("codecks_cli.client.extract_hand_card_ids")
    @patch("codecks_cli.client.list_hand")
    @patch("codecks_cli.client.enrich_cards", side_effect=lambda c, u: c)
    @patch("codecks_cli.client.get_card")
    def test_resolves_conversations(self, mock_get, mock_enrich, mock_hand, mock_extract):
        mock_get.return_value = {
            "card": {
                "c1": {
                    "title": "Card With Comments",
                    "status": "started",
                    "resolvables": ["r1"],
                },
            },
            "resolvable": {
                "r1": {
                    "isClosed": False,
                    "creator": "u1",
                    "createdAt": "2026-01-01",
                    "entries": ["e1"],
                },
            },
            "resolvableEntry": {
                "e1": {
                    "content": "Hello",
                    "createdAt": "2026-01-01",
                    "author": "u1",
                },
            },
            "user": {"u1": {"name": "Alice"}},
        }
        mock_hand.return_value = {}
        mock_extract.return_value = set()
        client = _client()
        detail = client.get_card("c1")
        assert "conversations" in detail
        assert len(detail["conversations"]) == 1
        assert detail["conversations"][0]["status"] == "open"
        assert detail["conversations"][0]["messages"][0]["author"] == "Alice"

    @patch("codecks_cli.client.extract_hand_card_ids")
    @patch("codecks_cli.client.list_hand")
    @patch("codecks_cli.client.enrich_cards", side_effect=lambda c, u: c)
    @patch("codecks_cli.client.get_card")
    def test_get_card_500_fallback_retries_minimal(
        self, mock_get, mock_enrich, mock_hand, mock_extract
    ):
        """When get_card raises HTTP 500, retry with minimal=True."""
        mock_get.side_effect = [
            CliError("HTTP 500 Internal Server Error"),
            {
                "card": {
                    "sub-card-1": {
                        "title": "Sub Card",
                        "status": "started",
                        "content": "Sub Card\nBody",
                    }
                },
                "user": {},
            },
        ]
        mock_hand.return_value = {}
        mock_extract.return_value = set()
        client = _client()
        detail = client.get_card("sub-card-1")
        assert detail["title"] == "Sub Card"
        assert mock_get.call_count == 2
        # First call: normal, second call: minimal=True
        _, kwargs2 = mock_get.call_args_list[1]
        assert kwargs2.get("minimal") is True

    @patch("codecks_cli.client.extract_hand_card_ids")
    @patch("codecks_cli.client.list_hand")
    @patch("codecks_cli.client.enrich_cards", side_effect=lambda c, u: c)
    @patch("codecks_cli.client.get_card")
    def test_get_card_non_500_error_propagates(
        self, mock_get, mock_enrich, mock_hand, mock_extract
    ):
        """Non-500 errors from get_card should propagate, not retry."""
        mock_get.side_effect = CliError("HTTP 404 Not Found")
        mock_hand.return_value = {}
        mock_extract.return_value = set()
        client = _client()
        with pytest.raises(CliError) as exc_info:
            client.get_card("missing-card")
        assert "HTTP 404" in str(exc_info.value)
        assert mock_get.call_count == 1


# ---------------------------------------------------------------------------
# create_card
# ---------------------------------------------------------------------------


class TestCreateCard:
    @patch("codecks_cli.scaffolding.list_cards")
    @patch("codecks_cli.client.create_card")
    def test_creates_card_successfully(self, mock_create, mock_list):
        mock_list.return_value = {"card": {}}  # no duplicates
        mock_create.return_value = {"cardId": "new-id"}
        client = _client()
        result = client.create_card("Test Card")
        assert result["ok"] is True
        assert result["card_id"] == "new-id"
        assert result["title"] == "Test Card"

    @patch("codecks_cli.scaffolding.list_cards")
    @patch("codecks_cli.client.create_card")
    def test_missing_card_id_raises(self, mock_create, mock_list):
        mock_list.return_value = {"card": {}}
        mock_create.return_value = {}
        client = _client()
        with pytest.raises(CliError) as exc_info:
            client.create_card("Test Card")
        assert "cardId" in str(exc_info.value)

    @patch("codecks_cli.client.update_card")
    @patch("codecks_cli.client.resolve_deck_id")
    @patch("codecks_cli.scaffolding.list_cards")
    @patch("codecks_cli.client.create_card")
    def test_places_card_in_deck(self, mock_create, mock_list, mock_resolve, mock_update):
        mock_list.return_value = {"card": {}}
        mock_create.return_value = {"cardId": "new-id"}
        mock_resolve.return_value = "deck-uuid"
        mock_update.return_value = {}
        client = _client()
        result = client.create_card("Test Card", deck="Features")
        assert result["deck"] == "Features"
        mock_update.assert_called_once()

    @patch("codecks_cli.scaffolding.list_cards")
    def test_blocks_duplicate_title(self, mock_list):
        mock_list.return_value = {"card": {"c1": {"title": "Duplicate Title", "status": "started"}}}
        client = _client()
        with pytest.raises(CliError) as exc_info:
            client.create_card("Duplicate Title")
        assert "Duplicate card title detected" in str(exc_info.value)

    @patch("codecks_cli.scaffolding.list_cards")
    @patch("codecks_cli.client.create_card")
    def test_returns_warnings_for_similar_titles(self, mock_create, mock_list):
        mock_list.return_value = {
            "card": {"c1": {"title": "My Card Title Extended", "status": "started"}}
        }
        mock_create.return_value = {"cardId": "new-id"}
        client = _client()
        result = client.create_card("My Card Title")
        assert result["ok"] is True
        assert "warnings" in result
        assert len(result["warnings"]) >= 1

    @patch("codecks_cli.scaffolding.list_cards")
    @patch("codecks_cli.client.create_card")
    def test_no_warnings_key_when_clean(self, mock_create, mock_list):
        mock_list.return_value = {"card": {}}
        mock_create.return_value = {"cardId": "new-id"}
        client = _client()
        result = client.create_card("Totally Unique")
        assert "warnings" not in result

    @patch("codecks_cli.client.update_card")
    @patch("codecks_cli.scaffolding.list_cards")
    @patch("codecks_cli.client.create_card")
    def test_parent_sets_parent_card_id(self, mock_create, mock_list, mock_update):
        mock_list.return_value = {"card": {}}
        mock_create.return_value = {"cardId": "child-id"}
        mock_update.return_value = {}
        client = _client()
        result = client.create_card("Sub Card", parent="parent-uuid")
        assert result["ok"] is True
        assert result["parent"] == "parent-uuid"
        mock_update.assert_called_once()
        call_kwargs = mock_update.call_args[1]
        assert call_kwargs["parentCardId"] == "parent-uuid"

    @patch("codecks_cli.client.update_card")
    @patch("codecks_cli.client.resolve_deck_id")
    @patch("codecks_cli.scaffolding.list_cards")
    @patch("codecks_cli.client.create_card")
    def test_parent_with_deck(self, mock_create, mock_list, mock_resolve, mock_update):
        mock_list.return_value = {"card": {}}
        mock_create.return_value = {"cardId": "child-id"}
        mock_resolve.return_value = "deck-uuid"
        mock_update.return_value = {}
        client = _client()
        result = client.create_card("Sub Card", deck="Features", parent="parent-uuid")
        assert result["deck"] == "Features"
        assert result["parent"] == "parent-uuid"
        mock_update.assert_called_once()
        call_kwargs = mock_update.call_args[1]
        assert call_kwargs["parentCardId"] == "parent-uuid"
        assert call_kwargs["deckId"] == "deck-uuid"

    @patch("codecks_cli.scaffolding.list_cards")
    @patch("codecks_cli.client.create_card")
    def test_no_parent_skips_update(self, mock_create, mock_list):
        mock_list.return_value = {"card": {}}
        mock_create.return_value = {"cardId": "new-id"}
        client = _client()
        result = client.create_card("Solo Card")
        assert result["parent"] is None


# ---------------------------------------------------------------------------
# update_cards
# ---------------------------------------------------------------------------


class TestUpdateCards:
    @patch("codecks_cli.client.update_card")
    def test_updates_single_card(self, mock_update):
        mock_update.return_value = {}
        client = _client()
        result = client.update_cards(["c1"], status="done")
        assert result["ok"] is True
        assert result["updated"] == 1
        assert result["failed"] == 0
        assert "per_card" not in result
        mock_update.assert_called_once()

    @patch("codecks_cli.client.update_card")
    def test_clears_priority_with_null(self, mock_update):
        mock_update.return_value = {}
        client = _client()
        result = client.update_cards(["c1"], priority="null")
        assert result["fields"]["priority"] is None

    @patch("codecks_cli.client.update_card")
    def test_clears_effort_with_null(self, mock_update):
        mock_update.return_value = {}
        client = _client()
        result = client.update_cards(["c1"], effort="null")
        assert result["fields"]["effort"] is None

    def test_no_fields_raises(self):
        client = _client()
        with pytest.raises(CliError) as exc_info:
            client.update_cards(["c1"])
        assert "No update flags" in str(exc_info.value)

    def test_invalid_effort_raises(self):
        client = _client()
        with pytest.raises(CliError) as exc_info:
            client.update_cards(["c1"], effort="abc")
        assert "Invalid effort value" in str(exc_info.value)

    @patch("codecks_cli.client.get_card")
    def test_title_rejects_multiple_cards(self, mock_get):
        client = _client()
        with pytest.raises(CliError) as exc_info:
            client.update_cards(["c1", "c2"], title="New Title")
        assert "--title can only be used with a single card" in str(exc_info.value)

    @patch("codecks_cli.client.update_card")
    def test_clears_owner(self, mock_update):
        mock_update.return_value = {}
        client = _client()
        result = client.update_cards(["c1"], owner="none")
        assert result["fields"]["assigneeId"] is None

    @patch("codecks_cli.client.update_card")
    def test_clears_tags(self, mock_update):
        mock_update.return_value = {}
        client = _client()
        result = client.update_cards(["c1"], tags="none")
        assert result["fields"]["masterTags"] == []

    @patch("codecks_cli.client.update_card")
    def test_invalid_doc_raises(self, mock_update):
        client = _client()
        with pytest.raises(CliError) as exc_info:
            client.update_cards(["c1"], doc="maybe")
        assert "Invalid --doc value" in str(exc_info.value)

    @patch("codecks_cli.client.update_card")
    def test_continue_on_error_reports_partial_results(self, mock_update):
        mock_update.side_effect = [
            {},
            CliError("[ERROR] bad id"),
            {},
        ]
        client = _client()
        result = client.update_cards(["c1", "c2", "c3"], status="done", continue_on_error=True)
        assert result["ok"] is False
        assert result["updated"] == 2
        assert result["failed"] == 1
        assert result["per_card"][1]["card_id"] == "c2"
        assert result["per_card"][1]["ok"] is False
        assert "bad id" in result["per_card"][1]["error"]


# ---------------------------------------------------------------------------
# mark_done / mark_started
# ---------------------------------------------------------------------------


class TestBulkStatus:
    @patch("codecks_cli.client.bulk_status")
    def test_mark_done(self, mock_bulk):
        mock_bulk.return_value = {}
        client = _client()
        result = client.mark_done(["c1", "c2"])
        assert result["ok"] is True
        assert result["count"] == 2
        assert result["failed"] == 0
        assert "per_card" not in result
        mock_bulk.assert_called_once_with(["c1", "c2"], "done")

    @patch("codecks_cli.client.bulk_status")
    def test_mark_started(self, mock_bulk):
        mock_bulk.return_value = {}
        client = _client()
        result = client.mark_started(["c1"])
        assert result["count"] == 1
        assert "per_card" not in result
        mock_bulk.assert_called_once_with(["c1"], "started")


# ---------------------------------------------------------------------------
# archive / unarchive / delete
# ---------------------------------------------------------------------------


class TestArchiveOps:
    @patch("codecks_cli.client.archive_card")
    def test_archive(self, mock_archive):
        mock_archive.return_value = {}
        client = _client()
        result = client.archive_card("c1")
        assert result["ok"] is True
        assert result["card_id"] == "c1"
        assert "per_card" not in result

    @patch("codecks_cli.client.unarchive_card")
    def test_unarchive(self, mock_unarchive):
        mock_unarchive.return_value = {}
        client = _client()
        result = client.unarchive_card("c1")
        assert result["ok"] is True
        assert "per_card" not in result

    @patch("codecks_cli.client.delete_card")
    def test_delete(self, mock_delete):
        mock_delete.return_value = {}
        client = _client()
        result = client.delete_card("c1")
        assert result["ok"] is True
        assert "per_card" not in result


# ---------------------------------------------------------------------------
# pm_focus
# ---------------------------------------------------------------------------


class TestPMFocus:
    @patch("codecks_cli.client.extract_hand_card_ids")
    @patch("codecks_cli.client.list_hand")
    @patch("codecks_cli.client.enrich_cards", side_effect=lambda c, u: c)
    @patch("codecks_cli.client.list_cards")
    def test_generates_report(self, mock_list, mock_enrich, mock_hand, mock_extract):
        mock_list.return_value = {
            "card": {
                "c1": {"title": "Blocked", "status": "blocked", "priority": "a", "effort": 3},
                "c2": {
                    "title": "In Review",
                    "status": "in_review",
                    "priority": "b",
                    "effort": 2,
                    "lastUpdatedAt": "2026-02-19T00:00:00Z",
                },
                "c3": {"title": "Candidate", "status": "not_started", "priority": "a", "effort": 5},
            },
            "user": {},
        }
        mock_hand.return_value = {}
        mock_extract.return_value = set()
        client = _client()
        result = client.pm_focus()
        assert result["counts"]["blocked"] == 1
        assert result["counts"]["in_review"] == 1
        assert len(result["suggested"]) == 1
        assert result["suggested"][0]["title"] == "Candidate"

    @patch("codecks_cli.client.extract_hand_card_ids")
    @patch("codecks_cli.client.list_hand")
    @patch("codecks_cli.client.enrich_cards", side_effect=lambda c, u: c)
    @patch("codecks_cli.client.list_cards")
    def test_deck_health_aggregation(self, mock_list, mock_enrich, mock_hand, mock_extract):
        from datetime import datetime, timezone

        mock_list.return_value = {
            "card": {
                "c1": {
                    "title": "Blocked Code",
                    "status": "blocked",
                    "deck_name": "Code",
                    "owner_name": "Thomas",
                },
                "c2": {
                    "title": "Stale Art",
                    "status": "started",
                    "deck_name": "Art",
                    "owner_name": "Thomas",
                    "lastUpdatedAt": "2025-01-01T00:00:00Z",
                },
                "c3": {
                    "title": "Active Code",
                    "status": "started",
                    "deck_name": "Code",
                    "owner_name": None,
                    "lastUpdatedAt": datetime.now(timezone.utc).isoformat(),
                },
            },
            "user": {},
        }
        mock_hand.return_value = {}
        mock_extract.return_value = set()
        client = _client()
        result = client.pm_focus()

        health = result["deck_health"]
        assert "by_deck" in health
        assert "by_owner" in health

        # Code deck: 2 cards, 1 blocked, 1 in_progress
        assert health["by_deck"]["Code"]["total"] == 2
        assert health["by_deck"]["Code"]["blocked"] == 1
        assert health["by_deck"]["Code"]["in_progress"] == 1

        # Art deck: 1 card, stale
        assert health["by_deck"]["Art"]["total"] == 1
        assert health["by_deck"]["Art"]["stale"] == 1

        # Owner aggregation
        assert health["by_owner"]["Thomas"]["total"] == 2
        assert health["by_owner"]["unassigned"]["total"] == 1


# ---------------------------------------------------------------------------
# standup
# ---------------------------------------------------------------------------


class TestStandup:
    @patch("codecks_cli.client.extract_hand_card_ids")
    @patch("codecks_cli.client.list_hand")
    @patch("codecks_cli.client.enrich_cards", side_effect=lambda c, u: c)
    @patch("codecks_cli.client.list_cards")
    def test_categorizes_cards(self, mock_list, mock_enrich, mock_hand, mock_extract):
        from datetime import datetime, timedelta, timezone

        yesterday = (datetime.now(timezone.utc) - timedelta(hours=12)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        mock_list.return_value = {
            "card": {
                "c1": {
                    "title": "Done Yesterday",
                    "status": "done",
                    "lastUpdatedAt": yesterday,
                },
                "c2": {"title": "Working On", "status": "started"},
                "c3": {"title": "Stuck", "status": "blocked"},
            },
            "user": {},
        }
        mock_hand.return_value = {}
        mock_extract.return_value = set()
        client = _client()
        result = client.standup()
        assert len(result["recently_done"]) == 1
        assert len(result["in_progress"]) == 1
        assert len(result["blocked"]) == 1


# ---------------------------------------------------------------------------
# Hand operations
# ---------------------------------------------------------------------------


class TestHandOperations:
    @patch("codecks_cli.client.enrich_cards", side_effect=lambda c, u: c)
    @patch("codecks_cli.client.list_cards")
    @patch("codecks_cli.client.extract_hand_card_ids")
    @patch("codecks_cli.client.list_hand")
    def test_list_hand_sorted(self, mock_hand, mock_extract, mock_list, mock_enrich):
        mock_hand.return_value = {
            "queueEntry": {
                "e1": {"card": "c1", "sortIndex": 200},
                "e2": {"card": "c2", "sortIndex": 100},
            }
        }
        mock_extract.return_value = {"c1", "c2"}
        mock_list.return_value = {
            "card": {
                "c1": {"title": "Second", "status": "started"},
                "c2": {"title": "First", "status": "done"},
            },
            "user": {},
        }
        client = _client()
        result = client.list_hand()
        assert len(result) == 2
        assert result[0]["title"] == "First"  # lower sortIndex first

    @patch("codecks_cli.client.extract_hand_card_ids")
    @patch("codecks_cli.client.list_hand")
    def test_list_hand_empty(self, mock_hand, mock_extract):
        mock_hand.return_value = {}
        mock_extract.return_value = set()
        client = _client()
        result = client.list_hand()
        assert result == []

    @patch("codecks_cli.client.add_to_hand")
    def test_add_to_hand(self, mock_add):
        mock_add.return_value = {}
        client = _client()
        result = client.add_to_hand(["c1", "c2"])
        assert result["ok"] is True
        assert result["added"] == 2
        assert result["failed"] == 0
        assert "per_card" not in result

    @patch("codecks_cli.client.remove_from_hand")
    def test_remove_from_hand(self, mock_remove):
        mock_remove.return_value = {}
        client = _client()
        result = client.remove_from_hand(["c1"])
        assert result["ok"] is True
        assert result["removed"] == 1
        assert "per_card" not in result


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------


class TestComments:
    @patch("codecks_cli.client.create_comment")
    def test_create_comment(self, mock_create):
        mock_create.return_value = {}
        client = _client()
        result = client.create_comment("c1", "Hello")
        assert result["ok"] is True

    def test_create_comment_empty_message_raises(self):
        client = _client()
        with pytest.raises(CliError) as exc_info:
            client.create_comment("c1", "")
        assert "Comment message is required" in str(exc_info.value)

    @patch("codecks_cli.client.reply_comment")
    def test_reply_comment(self, mock_reply):
        mock_reply.return_value = {}
        client = _client()
        result = client.reply_comment("t1", "Reply text")
        assert result["ok"] is True

    def test_reply_empty_message_raises(self):
        client = _client()
        with pytest.raises(CliError) as exc_info:
            client.reply_comment("t1", "")
        assert "Reply message is required" in str(exc_info.value)

    @patch("codecks_cli.client.close_comment")
    def test_close_comment(self, mock_close):
        mock_close.return_value = {}
        client = _client()
        result = client.close_comment("t1", "c1")
        assert result["ok"] is True

    @patch("codecks_cli.client.reopen_comment")
    def test_reopen_comment(self, mock_reopen):
        mock_reopen.return_value = {}
        client = _client()
        result = client.reopen_comment("t1", "c1")
        assert result["ok"] is True


# ---------------------------------------------------------------------------
# Token validation
# ---------------------------------------------------------------------------


class TestTokenValidation:
    @patch("codecks_cli.client._check_token")
    def test_validates_token_by_default(self, mock_check):
        CodecksClient()
        mock_check.assert_called_once()

    @patch("codecks_cli.client._check_token")
    def test_skip_validation(self, mock_check):
        CodecksClient(validate_token=False)
        mock_check.assert_not_called()


# ---------------------------------------------------------------------------
# List decks / projects / milestones
# ---------------------------------------------------------------------------


class TestGetAccount:
    @patch("codecks_cli.client.get_account")
    def test_get_account(self, mock_get):
        mock_get.return_value = {"account": {"a1": {"name": "My Account"}}}
        client = _client()
        result = client.get_account()
        assert result["account"]["a1"]["name"] == "My Account"


class TestListConversations:
    @patch("codecks_cli.client.get_conversations")
    def test_list_conversations(self, mock_get):
        mock_get.return_value = {
            "card": {"c1": {"title": "Card A", "resolvables": ["r1"]}},
            "resolvable": {"r1": {"creator": "u1", "isClosed": False, "entries": []}},
            "user": {"u1": {"name": "Alice"}},
        }
        client = _client()
        result = client.list_conversations("c1")
        assert "card" in result
        mock_get.assert_called_once_with("c1")


class TestListDecksProjectsMilestones:
    @patch("codecks_cli.client.load_project_names")
    @patch("codecks_cli.client.list_cards")
    @patch("codecks_cli.client.list_decks")
    def test_list_decks(self, mock_decks, mock_cards, mock_proj_names):
        mock_decks.return_value = {
            "deck": {
                "dk1": {"id": "d1", "title": "Features", "projectId": "p1"},
            }
        }
        mock_cards.return_value = {"card": {"c1": {"deckId": "d1"}, "c2": {"deckId": "d1"}}}
        mock_proj_names.return_value = {"p1": "Tea Shop"}
        client = _client()
        result = client.list_decks()
        assert len(result) == 1
        assert result[0]["title"] == "Features"
        assert result[0]["card_count"] == 2
        assert result[0]["project_name"] == "Tea Shop"

    @patch("codecks_cli.client.list_projects")
    def test_list_projects(self, mock_projects):
        mock_projects.return_value = {
            "p1": {"name": "Tea Shop", "deck_count": 3, "decks": ["A", "B", "C"]}
        }
        client = _client()
        result = client.list_projects()
        assert len(result) == 1
        assert result[0]["name"] == "Tea Shop"

    @patch("codecks_cli.client.list_milestones")
    def test_list_milestones(self, mock_milestones):
        mock_milestones.return_value = {"m1": {"name": "MVP", "cards": ["c1", "c2"]}}
        client = _client()
        result = client.list_milestones()
        assert len(result) == 1
        assert result[0]["name"] == "MVP"
        assert result[0]["card_count"] == 2

    @patch("codecks_cli.client.list_tags")
    def test_list_tags(self, mock_tags):
        mock_tags.return_value = {
            "masterTag": {
                "t1": {"title": "Feature", "color": "#ff0000", "emoji": "🚀"},
                "t2": {"title": "Bug"},
            }
        }
        client = _client()
        result = client.list_tags()
        assert len(result) == 2
        titles = {t["title"] for t in result}
        assert titles == {"Feature", "Bug"}
        feature = next(t for t in result if t["title"] == "Feature")
        assert feature["color"] == "#ff0000"
        assert feature["emoji"] == "🚀"
        bug = next(t for t in result if t["title"] == "Bug")
        assert "color" not in bug
        assert "emoji" not in bug

    @patch("codecks_cli.client.list_tags")
    def test_list_tags_empty(self, mock_tags):
        mock_tags.return_value = {"masterTag": {}}
        client = _client()
        result = client.list_tags()
        assert result == []

    @patch("codecks_cli.client.list_activity")
    def test_list_activity(self, mock_activity):
        mock_activity.return_value = {"activity": {"a1": {"type": "card_created"}}}
        client = _client()
        result = client.list_activity(limit=5)
        assert "activity" in result

    def test_list_activity_invalid_limit(self):
        client = _client()
        with pytest.raises(CliError):
            client.list_activity(limit=0)

    @patch("codecks_cli.client.load_project_names")
    @patch("codecks_cli.client.list_decks")
    def test_list_decks_no_card_counts(self, mock_decks, mock_proj_names):
        mock_decks.return_value = {
            "deck": {
                "dk1": {"id": "d1", "title": "Features", "projectId": "p1"},
            }
        }
        mock_proj_names.return_value = {"p1": "Tea Shop"}
        client = _client()
        result = client.list_decks(include_card_counts=False)
        assert len(result) == 1
        assert result[0]["title"] == "Features"
        assert result[0]["card_count"] is None


# ---------------------------------------------------------------------------
# get_card field control
# ---------------------------------------------------------------------------


class TestGetCardFieldControl:
    @patch("codecks_cli.client.extract_hand_card_ids")
    @patch("codecks_cli.client.list_hand")
    @patch("codecks_cli.client.enrich_cards", side_effect=lambda c, u: c)
    @patch("codecks_cli.client.get_card")
    def test_include_content_false_strips_content(
        self, mock_get, mock_enrich, mock_hand, mock_extract
    ):
        mock_get.return_value = {
            "card": {
                "uuid-123": {
                    "title": "Test Card",
                    "status": "started",
                    "content": "Test Card\nLong body text here",
                },
            },
            "user": {},
        }
        mock_hand.return_value = {}
        mock_extract.return_value = set()
        client = _client()
        detail = client.get_card("uuid-123", include_content=False)
        assert detail["id"] == "uuid-123"
        assert detail["title"] == "Test Card"
        assert "content" not in detail

    @patch("codecks_cli.client.extract_hand_card_ids")
    @patch("codecks_cli.client.list_hand")
    @patch("codecks_cli.client.enrich_cards", side_effect=lambda c, u: c)
    @patch("codecks_cli.client.get_card")
    def test_include_conversations_false_skips_conversations(
        self, mock_get, mock_enrich, mock_hand, mock_extract
    ):
        mock_get.return_value = {
            "card": {
                "c1": {
                    "title": "Card With Comments",
                    "status": "started",
                    "resolvables": ["r1"],
                },
            },
            "resolvable": {
                "r1": {
                    "isClosed": False,
                    "creator": "u1",
                    "createdAt": "2026-01-01",
                    "entries": ["e1"],
                },
            },
            "resolvableEntry": {
                "e1": {
                    "content": "Hello",
                    "createdAt": "2026-01-01",
                    "author": "u1",
                },
            },
            "user": {"u1": {"name": "Alice"}},
        }
        mock_hand.return_value = {}
        mock_extract.return_value = set()
        client = _client()
        detail = client.get_card("c1", include_conversations=False)
        assert "conversations" not in detail


# ---------------------------------------------------------------------------
# Hand cache
# ---------------------------------------------------------------------------


class TestHandCache:
    @patch("codecks_cli.client.extract_hand_card_ids")
    @patch("codecks_cli.client.list_hand")
    @patch("codecks_cli.client.enrich_cards", side_effect=lambda c, u: c)
    @patch("codecks_cli.client.get_card")
    def test_second_get_card_reuses_cached_hand(
        self, mock_get, mock_enrich, mock_hand, mock_extract
    ):
        mock_get.return_value = {
            "card": {"c1": {"title": "Card", "status": "started"}},
            "user": {},
        }
        mock_hand.return_value = {}
        mock_extract.return_value = set()
        client = _client()
        client.get_card("c1")
        client.get_card("c1")
        # list_hand should only be called once (cached on second call)
        mock_hand.assert_called_once()

    @patch("codecks_cli.client.extract_hand_card_ids")
    @patch("codecks_cli.client.list_hand")
    @patch("codecks_cli.client.add_to_hand")
    @patch("codecks_cli.client.enrich_cards", side_effect=lambda c, u: c)
    @patch("codecks_cli.client.get_card")
    def test_add_to_hand_invalidates_cache(
        self, mock_get, mock_enrich, mock_add, mock_hand, mock_extract
    ):
        mock_get.return_value = {
            "card": {"c1": {"title": "Card", "status": "started"}},
            "user": {},
        }
        mock_hand.return_value = {}
        mock_extract.return_value = set()
        mock_add.return_value = {}
        client = _client()
        client.get_card("c1")
        assert mock_hand.call_count == 1
        client.add_to_hand(["c1"])
        client.get_card("c1")
        # After add_to_hand invalidates cache, list_hand called again
        assert mock_hand.call_count == 2


# ---------------------------------------------------------------------------
# Mutation returns no "data" key
# ---------------------------------------------------------------------------


class TestMutationReturnsNoData:
    @patch("codecks_cli.client.add_to_hand")
    def test_add_to_hand_no_data(self, mock_add):
        mock_add.return_value = {}
        client = _client()
        result = client.add_to_hand(["c1"])
        assert "data" not in result

    @patch("codecks_cli.client.remove_from_hand")
    def test_remove_from_hand_no_data(self, mock_remove):
        mock_remove.return_value = {}
        client = _client()
        result = client.remove_from_hand(["c1"])
        assert "data" not in result

    @patch("codecks_cli.client.update_card")
    def test_update_cards_no_data(self, mock_update):
        mock_update.return_value = {}
        client = _client()
        result = client.update_cards(["c1"], status="done")
        assert "data" not in result

    @patch("codecks_cli.client.bulk_status")
    def test_mark_done_no_data(self, mock_bulk):
        mock_bulk.return_value = {}
        client = _client()
        result = client.mark_done(["c1"])
        assert "data" not in result

    @patch("codecks_cli.client.archive_card")
    def test_archive_no_data(self, mock_archive):
        mock_archive.return_value = {}
        client = _client()
        result = client.archive_card("c1")
        assert "data" not in result

    @patch("codecks_cli.client.delete_card")
    def test_delete_no_data(self, mock_delete):
        mock_delete.return_value = {}
        client = _client()
        result = client.delete_card("c1")
        assert "data" not in result

    @patch("codecks_cli.client.create_comment")
    def test_create_comment_no_data(self, mock_create):
        mock_create.return_value = {}
        client = _client()
        result = client.create_comment("c1", "Hello")
        assert "data" not in result
