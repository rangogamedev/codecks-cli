"""Tests for CodecksClient — the public programmatic API surface.
Mocks at cards.*/api.* boundary. Asserts on returned dicts, not stdout.
"""

from unittest.mock import patch

import pytest

from codecks_cli.client import (
    CodecksClient,
    _analyze_feature_for_lanes,
    _classify_checklist_item,
    _flatten_cards,
    _guard_duplicate_title,
    _sort_cards,
)
from codecks_cli.exceptions import CliError, SetupError

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
# _guard_duplicate_title
# ---------------------------------------------------------------------------


class TestGuardDuplicateTitle:
    @patch("codecks_cli.client.list_cards")
    def test_returns_empty_list_when_no_matches(self, mock_list):
        mock_list.return_value = {"card": {}}
        result = _guard_duplicate_title("Unique Title")
        assert result == []

    def test_returns_empty_when_allowed(self):
        result = _guard_duplicate_title("Any Title", allow_duplicate=True)
        assert result == []

    @patch("codecks_cli.client.list_cards")
    def test_raises_on_exact_match(self, mock_list):
        mock_list.return_value = {"card": {"c1": {"title": "Duplicate", "status": "started"}}}
        with pytest.raises(CliError) as exc_info:
            _guard_duplicate_title("Duplicate")
        assert "Duplicate card title detected" in str(exc_info.value)

    @patch("codecks_cli.client.list_cards")
    def test_returns_warnings_for_similar(self, mock_list):
        mock_list.return_value = {
            "card": {"c1": {"title": "Duplicate Title Here", "status": "started"}}
        }
        result = _guard_duplicate_title("Duplicate Title")
        assert len(result) == 1
        assert "Similar" in result[0]


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
    @patch("codecks_cli.client.list_cards")
    @patch("codecks_cli.client.create_card")
    def test_creates_card_successfully(self, mock_create, mock_list):
        mock_list.return_value = {"card": {}}  # no duplicates
        mock_create.return_value = {"cardId": "new-id"}
        client = _client()
        result = client.create_card("Test Card")
        assert result["ok"] is True
        assert result["card_id"] == "new-id"
        assert result["title"] == "Test Card"

    @patch("codecks_cli.client.list_cards")
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
    @patch("codecks_cli.client.list_cards")
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

    @patch("codecks_cli.client.list_cards")
    def test_blocks_duplicate_title(self, mock_list):
        mock_list.return_value = {"card": {"c1": {"title": "Duplicate Title", "status": "started"}}}
        client = _client()
        with pytest.raises(CliError) as exc_info:
            client.create_card("Duplicate Title")
        assert "Duplicate card title detected" in str(exc_info.value)

    @patch("codecks_cli.client.list_cards")
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

    @patch("codecks_cli.client.list_cards")
    @patch("codecks_cli.client.create_card")
    def test_no_warnings_key_when_clean(self, mock_create, mock_list):
        mock_list.return_value = {"card": {}}
        mock_create.return_value = {"cardId": "new-id"}
        client = _client()
        result = client.create_card("Totally Unique")
        assert "warnings" not in result

    @patch("codecks_cli.client.update_card")
    @patch("codecks_cli.client.list_cards")
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
    @patch("codecks_cli.client.list_cards")
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

    @patch("codecks_cli.client.list_cards")
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
# scaffold_feature
# ---------------------------------------------------------------------------


class TestScaffoldFeature:
    @patch("codecks_cli.client.list_cards")
    @patch("codecks_cli.client.update_card")
    @patch("codecks_cli.client.create_card")
    @patch("codecks_cli.client.resolve_deck_id")
    def test_creates_hero_and_subcards(self, mock_resolve, mock_create, mock_update, mock_list):
        mock_list.return_value = {"card": {}}  # no duplicates
        mock_resolve.side_effect = ["d-hero", "d-code", "d-design"]
        mock_create.side_effect = [
            {"cardId": "hero-1"},
            {"cardId": "code-1"},
            {"cardId": "design-1"},
        ]
        mock_update.return_value = {}
        client = _client()
        result = client.scaffold_feature(
            "Inventory 2.0",
            hero_deck="Features",
            code_deck="Code",
            design_deck="Design",
        )
        assert result["ok"] is True
        assert result["hero"]["id"] == "hero-1"
        assert len(result["subcards"]) == 2
        assert mock_create.call_count == 3

    @patch("codecks_cli.client.list_cards")
    @patch("codecks_cli.client.archive_card")
    @patch("codecks_cli.client.update_card")
    @patch("codecks_cli.client.create_card")
    @patch("codecks_cli.client.resolve_deck_id")
    def test_rolls_back_on_failure(
        self, mock_resolve, mock_create, mock_update, mock_archive, mock_list
    ):
        mock_list.return_value = {"card": {}}
        mock_resolve.side_effect = ["d-hero", "d-code", "d-design"]
        mock_create.side_effect = [
            {"cardId": "hero-1"},
            {"cardId": "code-1"},
        ]
        mock_update.side_effect = [None, CliError("[ERROR] update failed")]
        client = _client()
        with pytest.raises(CliError) as exc_info:
            client.scaffold_feature(
                "Test Feature",
                hero_deck="Features",
                code_deck="Code",
                design_deck="Design",
            )
        assert "Feature scaffold failed" in str(exc_info.value)
        assert mock_archive.call_count == 2

    @patch("codecks_cli.client.list_cards")
    @patch("codecks_cli.client.update_card")
    @patch("codecks_cli.client.create_card")
    @patch("codecks_cli.client.resolve_deck_id")
    def test_creates_with_audio_deck(self, mock_resolve, mock_create, mock_update, mock_list):
        mock_list.return_value = {"card": {}}  # no duplicates
        mock_resolve.side_effect = ["d-hero", "d-code", "d-design", "d-audio"]
        mock_create.side_effect = [
            {"cardId": "hero-1"},
            {"cardId": "code-1"},
            {"cardId": "design-1"},
            {"cardId": "audio-1"},
        ]
        mock_update.return_value = {}
        client = _client()
        result = client.scaffold_feature(
            "Inventory 2.0",
            hero_deck="Features",
            code_deck="Code",
            design_deck="Design",
            audio_deck="Audio",
        )
        assert result["ok"] is True
        assert result["hero"]["id"] == "hero-1"
        assert len(result["subcards"]) == 3  # code + design + audio
        assert any(s["lane"] == "audio" for s in result["subcards"])
        assert mock_create.call_count == 4

    @patch("codecks_cli.client.list_cards")
    @patch("codecks_cli.client.archive_card")
    @patch("codecks_cli.client.update_card")
    @patch("codecks_cli.client.create_card")
    @patch("codecks_cli.client.resolve_deck_id")
    def test_preserves_setup_error(
        self, mock_resolve, mock_create, mock_update, mock_archive, mock_list
    ):
        mock_list.return_value = {"card": {}}
        mock_resolve.side_effect = ["d-hero", "d-code", "d-design"]
        mock_create.side_effect = [
            {"cardId": "hero-1"},
            {"cardId": "code-1"},
        ]
        mock_update.side_effect = [None, SetupError("[TOKEN_EXPIRED] expired")]
        client = _client()
        with pytest.raises(SetupError):
            client.scaffold_feature(
                "Test Feature",
                hero_deck="Features",
                code_deck="Code",
                design_deck="Design",
            )


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


# ---------------------------------------------------------------------------
# standup
# ---------------------------------------------------------------------------


class TestStandup:
    @patch("codecks_cli.client.extract_hand_card_ids")
    @patch("codecks_cli.client.list_hand")
    @patch("codecks_cli.client.enrich_cards", side_effect=lambda c, u: c)
    @patch("codecks_cli.client.list_cards")
    def test_categorizes_cards(self, mock_list, mock_enrich, mock_hand, mock_extract):
        mock_list.return_value = {
            "card": {
                "c1": {
                    "title": "Done Yesterday",
                    "status": "done",
                    "lastUpdatedAt": "2026-02-21T12:00:00Z",
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


# ---------------------------------------------------------------------------
# Content analysis helpers
# ---------------------------------------------------------------------------


class TestClassifyChecklistItem:
    def test_code_keyword_matches(self):
        assert _classify_checklist_item("Implement the manager class") == "code"

    def test_art_keyword_matches(self):
        assert _classify_checklist_item("Create sprite animation") == "art"

    def test_design_keyword_matches(self):
        assert _classify_checklist_item("Tune balance and economy") == "design"

    def test_no_match_returns_none(self):
        assert _classify_checklist_item("Do something generic") is None

    def test_audio_keyword_matches(self):
        assert _classify_checklist_item("Add sound sfx for button") == "audio"

    def test_highest_score_wins(self):
        # "implement logic and debug" has 3 code keywords vs 0 others
        assert _classify_checklist_item("implement logic and debug") == "code"


class TestAnalyzeFeatureForLanes:
    def test_parses_checklist_items(self):
        content = (
            "Feature Title\n"
            "- [] Implement core logic\n"
            "- [] Create sprite assets\n"
            "- [] Tune balance curve\n"
        )
        lanes = _analyze_feature_for_lanes(content)
        assert "code" in lanes
        assert "art" in lanes
        assert "design" in lanes
        assert any("Implement" in item for item in lanes["code"])
        assert any("sprite" in item for item in lanes["art"])
        assert any("balance" in item for item in lanes["design"])

    def test_skip_art_excludes_art_lane(self):
        content = "- [] Implement logic\n- [] Create sprite\n"
        lanes = _analyze_feature_for_lanes(content, included_lanes={"code", "design"})
        assert "art" not in lanes
        assert "code" in lanes
        assert "design" in lanes

    def test_empty_lanes_get_defaults(self):
        content = "No checklist here at all"
        lanes = _analyze_feature_for_lanes(content)
        # All lanes should have default items
        assert len(lanes["code"]) > 0
        assert len(lanes["design"]) > 0
        assert len(lanes["art"]) > 0

    def test_unclassified_goes_to_smallest_lane(self):
        content = (
            "- [] Implement logic\n"
            "- [] Build system\n"
            "- [] Handle edge cases\n"
            "- [] Do something generic\n"
        )
        lanes = _analyze_feature_for_lanes(content, included_lanes={"code", "design"})
        # code has 3 items, generic goes to design (smallest)
        assert len(lanes["code"]) == 3
        assert len(lanes["design"]) >= 1
        assert "Do something generic" in lanes["design"]

    def test_markdown_checkbox_format(self):
        content = "- [ ] Implement logic\n- [x] Done item\n"
        lanes = _analyze_feature_for_lanes(content)
        total = sum(len(v) for v in lanes.values())
        # Both items should be parsed (even [x] completed ones)
        assert total >= 2

    def test_include_audio_adds_audio_lane(self):
        content = "- [] Add sound sfx\n- [] Implement logic\n"
        lanes = _analyze_feature_for_lanes(
            content, included_lanes={"code", "design", "art", "audio"}
        )
        assert "audio" in lanes
        assert any("sound" in item for item in lanes["audio"])

    def test_audio_excluded_by_default(self):
        content = "- [] Add sound sfx\n"
        lanes = _analyze_feature_for_lanes(content)
        assert "audio" not in lanes

    def test_audio_defaults_when_empty(self):
        content = "No checklist"
        lanes = _analyze_feature_for_lanes(
            content, included_lanes={"code", "design", "art", "audio"}
        )
        assert len(lanes["audio"]) > 0
        assert "Create required audio assets" in lanes["audio"]


# ---------------------------------------------------------------------------
# split_features
# ---------------------------------------------------------------------------


class TestSplitFeatures:
    @patch("codecks_cli.client.update_card")
    @patch("codecks_cli.client.create_card")
    @patch("codecks_cli.client.resolve_deck_id")
    def test_happy_path(self, mock_resolve, mock_create, mock_update):
        mock_resolve.side_effect = ["d-src", "d-code", "d-design"]
        mock_create.side_effect = [
            {"cardId": "sub-code-1"},
            {"cardId": "sub-design-1"},
        ]
        mock_update.return_value = {}

        client = _client()
        with (
            patch.object(client, "list_cards") as mock_list,
            patch.object(client, "get_card") as mock_get,
        ):
            mock_list.return_value = {
                "cards": [
                    {"id": "feat-1", "title": "Inventory System", "sub_card_count": 0},
                ],
                "stats": None,
            }
            mock_get.return_value = {
                "id": "feat-1",
                "title": "Inventory System",
                "content": "Inventory System\n- [] Implement item slots\n- [] Tune balance\n",
                "priority": "b",
            }
            result = client.split_features(
                deck="Features",
                code_deck="Coding",
                design_deck="Design",
            )

        assert result["ok"] is True
        assert result["features_processed"] == 1
        assert result["subcards_created"] == 2
        assert len(result["details"]) == 1
        assert len(result["details"][0]["subcards"]) == 2

    @patch("codecks_cli.client.resolve_deck_id")
    def test_skips_cards_with_children(self, mock_resolve):
        mock_resolve.side_effect = ["d-src", "d-code", "d-design"]
        client = _client()
        with patch.object(client, "list_cards") as mock_list:
            mock_list.return_value = {
                "cards": [
                    {"id": "feat-1", "title": "Already Split", "sub_card_count": 3},
                ],
                "stats": None,
            }
            result = client.split_features(
                deck="Features",
                code_deck="Coding",
                design_deck="Design",
            )
        assert result["features_processed"] == 0
        assert result["features_skipped"] == 1
        assert result["skipped"][0]["reason"] == "already has sub-cards"

    @patch("codecks_cli.client.resolve_deck_id")
    def test_dry_run_no_creation(self, mock_resolve):
        mock_resolve.side_effect = ["d-src", "d-code", "d-design"]
        client = _client()
        with (
            patch.object(client, "list_cards") as mock_list,
            patch.object(client, "get_card") as mock_get,
        ):
            mock_list.return_value = {
                "cards": [
                    {"id": "feat-1", "title": "Test Feature", "sub_card_count": 0},
                ],
                "stats": None,
            }
            mock_get.return_value = {
                "id": "feat-1",
                "title": "Test Feature",
                "content": "Test Feature\n- [] Implement logic\n",
            }
            result = client.split_features(
                deck="Features",
                code_deck="Coding",
                design_deck="Design",
                dry_run=True,
            )
        assert result["ok"] is True
        assert result["features_processed"] == 1
        assert result["subcards_created"] == 0
        assert result["details"][0]["subcards"][0]["id"] == "(dry-run)"

    @patch("codecks_cli.client.archive_card")
    @patch("codecks_cli.client.update_card")
    @patch("codecks_cli.client.create_card")
    @patch("codecks_cli.client.resolve_deck_id")
    def test_rollback_on_failure(self, mock_resolve, mock_create, mock_update, mock_archive):
        mock_resolve.side_effect = ["d-src", "d-code", "d-design"]
        mock_create.side_effect = [{"cardId": "sub-1"}]
        mock_update.side_effect = CliError("[ERROR] update failed")
        mock_archive.return_value = {}

        client = _client()
        with (
            patch.object(client, "list_cards") as mock_list,
            patch.object(client, "get_card") as mock_get,
        ):
            mock_list.return_value = {
                "cards": [{"id": "feat-1", "title": "Fail Feature", "sub_card_count": 0}],
                "stats": None,
            }
            mock_get.return_value = {
                "id": "feat-1",
                "title": "Fail Feature",
                "content": "- [] Implement logic\n",
            }
            with pytest.raises(CliError) as exc_info:
                client.split_features(
                    deck="Features",
                    code_deck="Coding",
                    design_deck="Design",
                )
        assert "Split-features failed" in str(exc_info.value)
        assert mock_archive.call_count == 1

    @patch("codecks_cli.client.resolve_deck_id")
    def test_empty_deck(self, mock_resolve):
        mock_resolve.side_effect = ["d-src", "d-code", "d-design"]
        client = _client()
        with patch.object(client, "list_cards") as mock_list:
            mock_list.return_value = {"cards": [], "stats": None}
            result = client.split_features(
                deck="Features",
                code_deck="Coding",
                design_deck="Design",
            )
        assert result["ok"] is True
        assert result["features_processed"] == 0
        assert result["features_skipped"] == 0

    @patch("codecks_cli.client.update_card")
    @patch("codecks_cli.client.create_card")
    @patch("codecks_cli.client.resolve_deck_id")
    def test_with_audio_deck(self, mock_resolve, mock_create, mock_update):
        mock_resolve.side_effect = ["d-src", "d-code", "d-design", "d-audio"]
        mock_create.side_effect = [
            {"cardId": "sub-code-1"},
            {"cardId": "sub-design-1"},
            {"cardId": "sub-audio-1"},
        ]
        mock_update.return_value = {}

        client = _client()
        with (
            patch.object(client, "list_cards") as mock_list,
            patch.object(client, "get_card") as mock_get,
        ):
            mock_list.return_value = {
                "cards": [
                    {"id": "feat-1", "title": "Sound Feature", "sub_card_count": 0},
                ],
                "stats": None,
            }
            mock_get.return_value = {
                "id": "feat-1",
                "title": "Sound Feature",
                "content": "Sound Feature\n- [] Add sfx for actions\n- [] Tune balance\n",
                "priority": "b",
            }
            result = client.split_features(
                deck="Features",
                code_deck="Coding",
                design_deck="Design",
                audio_deck="Audio",
            )

        assert result["ok"] is True
        assert result["features_processed"] == 1
        assert result["subcards_created"] == 3
        assert len(result["details"][0]["subcards"]) == 3
        assert any(s["lane"] == "audio" for s in result["details"][0]["subcards"])
