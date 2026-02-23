"""Tests for feature scaffolding — extracted from test_client.py.

Tests _guard_duplicate_title, _classify_checklist_item, _analyze_feature_for_lanes,
scaffold_feature, and split_features.
"""

from unittest.mock import patch

import pytest

from codecks_cli.client import CodecksClient
from codecks_cli.exceptions import CliError, SetupError
from codecks_cli.scaffolding import (
    _analyze_feature_for_lanes,
    _classify_checklist_item,
    _guard_duplicate_title,
)


def _client():
    """Create a CodecksClient with token validation skipped."""
    return CodecksClient(validate_token=False)


# ---------------------------------------------------------------------------
# _guard_duplicate_title
# ---------------------------------------------------------------------------


class TestGuardDuplicateTitle:
    @patch("codecks_cli.scaffolding.list_cards")
    def test_returns_empty_list_when_no_matches(self, mock_list):
        mock_list.return_value = {"card": {}}
        result = _guard_duplicate_title("Unique Title")
        assert result == []

    def test_returns_empty_when_allowed(self):
        result = _guard_duplicate_title("Any Title", allow_duplicate=True)
        assert result == []

    @patch("codecks_cli.scaffolding.list_cards")
    def test_raises_on_exact_match(self, mock_list):
        mock_list.return_value = {"card": {"c1": {"title": "Duplicate", "status": "started"}}}
        with pytest.raises(CliError) as exc_info:
            _guard_duplicate_title("Duplicate")
        assert "Duplicate card title detected" in str(exc_info.value)

    @patch("codecks_cli.scaffolding.list_cards")
    def test_returns_warnings_for_similar(self, mock_list):
        mock_list.return_value = {
            "card": {"c1": {"title": "Duplicate Title Here", "status": "started"}}
        }
        result = _guard_duplicate_title("Duplicate Title")
        assert len(result) == 1
        assert "Similar" in result[0]


# ---------------------------------------------------------------------------
# scaffold_feature
# ---------------------------------------------------------------------------


class TestScaffoldFeature:
    @patch("codecks_cli.scaffolding.list_cards")
    @patch("codecks_cli.scaffolding.update_card")
    @patch("codecks_cli.scaffolding.create_card")
    @patch("codecks_cli.scaffolding.resolve_deck_id")
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

    @patch("codecks_cli.scaffolding.list_cards")
    @patch("codecks_cli.scaffolding.archive_card")
    @patch("codecks_cli.scaffolding.update_card")
    @patch("codecks_cli.scaffolding.create_card")
    @patch("codecks_cli.scaffolding.resolve_deck_id")
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

    @patch("codecks_cli.scaffolding.list_cards")
    @patch("codecks_cli.scaffolding.update_card")
    @patch("codecks_cli.scaffolding.create_card")
    @patch("codecks_cli.scaffolding.resolve_deck_id")
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

    @patch("codecks_cli.scaffolding.list_cards")
    @patch("codecks_cli.scaffolding.archive_card")
    @patch("codecks_cli.scaffolding.update_card")
    @patch("codecks_cli.scaffolding.create_card")
    @patch("codecks_cli.scaffolding.resolve_deck_id")
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
    @patch("codecks_cli.scaffolding.update_card")
    @patch("codecks_cli.scaffolding.create_card")
    @patch("codecks_cli.scaffolding.resolve_deck_id")
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

    @patch("codecks_cli.scaffolding.resolve_deck_id")
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

    @patch("codecks_cli.scaffolding.resolve_deck_id")
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

    @patch("codecks_cli.scaffolding.archive_card")
    @patch("codecks_cli.scaffolding.update_card")
    @patch("codecks_cli.scaffolding.create_card")
    @patch("codecks_cli.scaffolding.resolve_deck_id")
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

    @patch("codecks_cli.scaffolding.resolve_deck_id")
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

    @patch("codecks_cli.scaffolding.update_card")
    @patch("codecks_cli.scaffolding.create_card")
    @patch("codecks_cli.scaffolding.resolve_deck_id")
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
