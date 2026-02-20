"""Tests for commands.py — command handlers and known bug regressions.
Uses mocks to avoid real API calls.
"""

import argparse
import json
import pytest
from unittest.mock import patch, MagicMock

import config
from config import CliError
from commands import (cmd_cards, cmd_update, cmd_create, cmd_card,
                      cmd_dispatch, cmd_comment, cmd_activity, cmd_feature,
                      cmd_pm_focus)


def _ns(**kwargs):
    """Build an argparse.Namespace with defaults for cmd_cards."""
    defaults = {
        "deck": None, "status": None, "project": None, "search": None,
        "milestone": None, "tag": None, "owner": None, "sort": None,
        "type": None, "hero": None, "stats": False, "hand": False,
        "archived": False, "format": "json",
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


# ---------------------------------------------------------------------------
# Regression: Sort with None values (known bug #3)
# ---------------------------------------------------------------------------

class TestSortWithNone:
    """Known bug regression: sorting by effort crashed with mixed int/None."""

    MOCK_CARDS = {
        "card": {
            "c1": {"status": "done", "priority": "a", "effort": 5,
                   "title": "A", "deck_name": "D", "owner_name": "O",
                   "createdAt": "2026-01-01", "lastUpdatedAt": "2026-01-02"},
            "c2": {"status": "started", "priority": None, "effort": None,
                   "title": "B", "deck_name": "D", "owner_name": "",
                   "createdAt": "2026-01-03", "lastUpdatedAt": "2026-01-04"},
            "c3": {"status": "done", "priority": "b", "effort": 3,
                   "title": "C", "deck_name": "D", "owner_name": "P",
                   "createdAt": "2026-01-05", "lastUpdatedAt": "2026-01-06"},
        },
        "user": {},
    }

    @patch("commands.list_cards")
    @patch("commands.enrich_cards", side_effect=lambda c, u: c)
    def test_sort_effort_no_crash(self, mock_enrich, mock_list, capsys):
        mock_list.return_value = self.MOCK_CARDS.copy()
        cmd_cards(_ns(sort="effort", format="json"))
        out = json.loads(capsys.readouterr().out)
        # Should not crash — None effort goes last
        card_keys = list(out["card"].keys())
        assert len(card_keys) == 3

    @patch("commands.list_cards")
    @patch("commands.enrich_cards", side_effect=lambda c, u: c)
    def test_sort_priority_none_last(self, mock_enrich, mock_list, capsys):
        mock_list.return_value = self.MOCK_CARDS.copy()
        cmd_cards(_ns(sort="priority", format="json"))
        out = json.loads(capsys.readouterr().out)
        keys = list(out["card"].keys())
        # c1 (a) should come before c3 (b), c2 (None) should be last
        assert keys.index("c1") < keys.index("c3")
        assert keys[-1] == "c2"

    @patch("commands.list_cards")
    @patch("commands.enrich_cards", side_effect=lambda c, u: c)
    def test_sort_updated_newest_first(self, mock_enrich, mock_list, capsys):
        """Known bug regression: sort by updated should be newest first."""
        mock_list.return_value = self.MOCK_CARDS.copy()
        cmd_cards(_ns(sort="updated", format="json"))
        out = json.loads(capsys.readouterr().out)
        keys = list(out["card"].keys())
        # c2 (2026-01-04) should come before c1 (2026-01-02) — newest first
        assert keys.index("c2") < keys.index("c1")

    @patch("commands.list_cards")
    @patch("commands.enrich_cards", side_effect=lambda c, u: c)
    def test_sort_owner_empty_last(self, mock_enrich, mock_list, capsys):
        mock_list.return_value = self.MOCK_CARDS.copy()
        cmd_cards(_ns(sort="owner", format="json"))
        out = json.loads(capsys.readouterr().out)
        keys = list(out["card"].keys())
        # c2 has empty owner -> should be last
        assert keys[-1] == "c2"


# ---------------------------------------------------------------------------
# Regression: --title on missing card (the bug we fixed)
# ---------------------------------------------------------------------------

class TestUpdateTitleBug:
    """Bug: --title on nonexistent card silently dropped the title change."""

    @patch("commands.get_card")
    def test_title_on_missing_card_exits(self, mock_get_card):
        mock_get_card.return_value = {"card": {}}
        ns = argparse.Namespace(
            card_ids=["nonexistent"], status=None, priority=None,
            effort=None, deck=None, title="New Title", content=None,
            milestone=None, hero=None, owner=None, tag=None, doc=None,
            format="json",
        )
        with pytest.raises(CliError) as exc_info:
            cmd_update(ns)
        assert exc_info.value.exit_code == 1

    @patch("commands.update_card")
    @patch("commands.get_card")
    def test_title_preserves_body(self, mock_get_card, mock_update, capsys):
        mock_get_card.return_value = {"card": {
            "c1": {"content": "Old Title\nBody line 1\nBody line 2"}
        }}
        mock_update.return_value = {}
        ns = argparse.Namespace(
            card_ids=["c1"], status=None, priority=None,
            effort=None, deck=None, title="New Title", content=None,
            milestone=None, hero=None, owner=None, tag=None, doc=None,
            format="table",
        )
        cmd_update(ns)
        call_kwargs = mock_update.call_args[1]
        assert call_kwargs["content"] == "New Title\nBody line 1\nBody line 2"


# ---------------------------------------------------------------------------
# Regression: update_card sends None as JSON null (known bug #4)
# ---------------------------------------------------------------------------

class TestUpdateClearValues:
    """Known bug: update_card used to filter out None values, breaking
    --priority null, --milestone none, --owner none, --hero none."""

    @patch("commands.update_card")
    def test_priority_null(self, mock_update, capsys):
        mock_update.return_value = {}
        ns = argparse.Namespace(
            card_ids=["c1"], status=None, priority="null",
            effort=None, deck=None, title=None, content=None,
            milestone=None, hero=None, owner=None, tag=None, doc=None,
            format="table",
        )
        cmd_update(ns)
        call_kwargs = mock_update.call_args[1]
        assert call_kwargs["priority"] is None

    @patch("commands.update_card")
    def test_milestone_none(self, mock_update, capsys):
        mock_update.return_value = {}
        ns = argparse.Namespace(
            card_ids=["c1"], status=None, priority=None,
            effort=None, deck=None, title=None, content=None,
            milestone="none", hero=None, owner=None, tag=None, doc=None,
            format="table",
        )
        cmd_update(ns)
        call_kwargs = mock_update.call_args[1]
        assert call_kwargs["milestoneId"] is None

    @patch("commands.update_card")
    def test_owner_none(self, mock_update, capsys):
        mock_update.return_value = {}
        ns = argparse.Namespace(
            card_ids=["c1"], status=None, priority=None,
            effort=None, deck=None, title=None, content=None,
            milestone=None, hero=None, owner="none", tag=None, doc=None,
            format="table",
        )
        cmd_update(ns)
        call_kwargs = mock_update.call_args[1]
        assert call_kwargs["assigneeId"] is None

    @patch("commands.update_card")
    def test_tag_none(self, mock_update, capsys):
        mock_update.return_value = {}
        ns = argparse.Namespace(
            card_ids=["c1"], status=None, priority=None,
            effort=None, deck=None, title=None, content=None,
            milestone=None, hero=None, owner=None, tag="none", doc=None,
            format="table",
        )
        cmd_update(ns)
        call_kwargs = mock_update.call_args[1]
        assert call_kwargs["masterTags"] == []

    @patch("commands.update_card")
    def test_effort_null(self, mock_update, capsys):
        mock_update.return_value = {}
        ns = argparse.Namespace(
            card_ids=["c1"], status=None, priority=None,
            effort="null", deck=None, title=None, content=None,
            milestone=None, hero=None, owner=None, tag=None, doc=None,
            format="table",
        )
        cmd_update(ns)
        call_kwargs = mock_update.call_args[1]
        assert call_kwargs["effort"] is None


# ---------------------------------------------------------------------------
# Regression: no update flags provided
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Regression: cmd_create with missing cardId in API response
# ---------------------------------------------------------------------------

class TestCreateMissingCardId:
    @patch("commands.create_card")
    def test_raises_on_missing_card_id(self, mock_create):
        mock_create.return_value = {}
        ns = argparse.Namespace(
            title="Test Card", content=None, severity=None,
            deck=None, project=None, doc=False, format="json",
        )
        with pytest.raises(CliError) as exc_info:
            cmd_create(ns)
        assert "cardId" in str(exc_info.value)


class TestUpdateNoFlags:
    def test_exits_with_error(self):
        ns = argparse.Namespace(
            card_ids=["c1"], status=None, priority=None,
            effort=None, deck=None, title=None, content=None,
            milestone=None, hero=None, owner=None, tag=None, doc=None,
            format="table",
        )
        with pytest.raises(CliError) as exc_info:
            cmd_update(ns)
        assert exc_info.value.exit_code == 1


# ---------------------------------------------------------------------------
# Regression: False TOKEN_EXPIRED on filtered empty results (known bug #1)
# ---------------------------------------------------------------------------

class TestFilteredEmptyResults:
    """Known bug: cards --status started returning 0 cards triggered a
    false TOKEN_EXPIRED warning. Fixed by only calling warn_if_empty
    when no server-side filters are applied."""

    @patch("cards.query")
    def test_status_filter_no_false_warning(self, mock_query, capsys):
        mock_query.return_value = {"card": {}}
        from cards import list_cards
        result = list_cards(status_filter="started")
        err = capsys.readouterr().err
        assert "[TOKEN_EXPIRED]" not in err

    @patch("cards.query")
    def test_deck_filter_no_false_warning(self, mock_query, capsys):
        mock_query.return_value = {"card": {}}
        config._cache["decks"] = {"deck": {
            "dk1": {"id": "d1", "title": "Features"},
        }}
        from cards import list_cards
        result = list_cards(deck_filter="Features")
        err = capsys.readouterr().err
        assert "[TOKEN_EXPIRED]" not in err

    @patch("cards.query")
    def test_unfiltered_empty_does_warn(self, mock_query, capsys):
        mock_query.return_value = {"card": {}}
        from cards import list_cards
        result = list_cards()
        err = capsys.readouterr().err
        assert "[TOKEN_EXPIRED]" in err


class TestDispatchPathValidation:
    @patch("commands.output")
    @patch("commands.dispatch")
    def test_normalizes_prefixed_dispatch_path(self, mock_dispatch, mock_output):
        ns = argparse.Namespace(path="/dispatch/cards/update",
                                json_data='{"id":"c1"}', format="json")
        mock_dispatch.return_value = {"ok": True}
        cmd_dispatch(ns)
        mock_dispatch.assert_called_once_with("cards/update", {"id": "c1"})

    def test_rejects_invalid_dispatch_path(self):
        ns = argparse.Namespace(path="dispatch/ bad path",
                                json_data='{"id":"c1"}', format="json")
        with pytest.raises(CliError):
            cmd_dispatch(ns)


class TestCommentValidation:
    def test_rejects_multiple_modes(self):
        ns = argparse.Namespace(card_id="c1", message=None, thread="t1",
                                close="t2", reopen=None, format="json")
        with pytest.raises(CliError):
            cmd_comment(ns)

    def test_rejects_message_with_close(self):
        ns = argparse.Namespace(card_id="c1", message="nope", thread=None,
                                close="t1", reopen=None, format="json")
        with pytest.raises(CliError):
            cmd_comment(ns)

    def test_rejects_message_with_reopen(self):
        ns = argparse.Namespace(card_id="c1", message="nope", thread=None,
                                close=None, reopen="t1", format="json")
        with pytest.raises(CliError):
            cmd_comment(ns)


class TestActivityValidation:
    def test_rejects_non_positive_limit(self):
        ns = argparse.Namespace(limit=0, format="json")
        with pytest.raises(CliError):
            cmd_activity(ns)


class TestPmFocus:
    @patch("commands.output")
    @patch("commands.extract_hand_card_ids")
    @patch("commands.list_hand")
    @patch("commands.enrich_cards")
    @patch("commands.list_cards")
    def test_generates_focus_report(self, mock_list_cards, mock_enrich, mock_list_hand,
                                    mock_extract, mock_output):
        mock_list_cards.return_value = {"card": {
            "c1": {"title": "A", "status": "blocked", "priority": "a", "effort": 5},
            "c2": {"title": "B", "status": "started", "priority": "b", "effort": 3},
            "c3": {"title": "C", "status": "not_started", "priority": "a", "effort": 8},
            "c4": {"title": "D", "status": "not_started", "priority": "c", "effort": 2},
        }, "user": {}}
        mock_enrich.side_effect = lambda cards, user: cards
        mock_list_hand.return_value = {}
        mock_extract.return_value = {"c2"}

        ns = argparse.Namespace(project=None, owner=None, limit=2, format="json")
        cmd_pm_focus(ns)

        report = mock_output.call_args.args[0]
        assert report["counts"]["blocked"] == 1
        assert report["counts"]["started"] == 1
        assert report["counts"]["hand"] == 1
        assert len(report["suggested"]) == 2
        assert report["suggested"][0]["id"] == "c3"


class TestRawCommandValidation:
    def test_query_requires_object_payload(self):
        ns = argparse.Namespace(json_query='[1,2,3]', format="json")
        from commands import cmd_query
        with pytest.raises(CliError) as exc_info:
            cmd_query(ns)
        assert "expected object" in str(exc_info.value)

    def test_query_strict_requires_root(self, monkeypatch):
        monkeypatch.setattr(config, "RUNTIME_STRICT", True)
        ns = argparse.Namespace(json_query='{"foo":"bar"}', format="json")
        from commands import cmd_query
        with pytest.raises(CliError) as exc_info:
            cmd_query(ns)
        assert "non-empty '_root' array" in str(exc_info.value)

    @patch("commands.output")
    @patch("commands.dispatch")
    def test_dispatch_requires_object_payload(self, mock_dispatch, mock_output):
        ns = argparse.Namespace(path="cards/update", json_data='["x"]', format="json")
        with pytest.raises(CliError) as exc_info:
            cmd_dispatch(ns)
        assert "expected object" in str(exc_info.value)
        mock_dispatch.assert_not_called()

    def test_dispatch_strict_requires_action_segment(self, monkeypatch):
        monkeypatch.setattr(config, "RUNTIME_STRICT", True)
        ns = argparse.Namespace(path="cards", json_data='{"id":"c1"}', format="json")
        with pytest.raises(CliError) as exc_info:
            cmd_dispatch(ns)
        assert "dispatch path should include action segment" in str(exc_info.value)

    def test_dispatch_strict_rejects_empty_payload(self, monkeypatch):
        monkeypatch.setattr(config, "RUNTIME_STRICT", True)
        ns = argparse.Namespace(path="cards/update", json_data='{}', format="json")
        with pytest.raises(CliError) as exc_info:
            cmd_dispatch(ns)
        assert "dispatch payload cannot be empty" in str(exc_info.value)


class TestFeatureScaffold:
    @patch("commands.output")
    @patch("commands.update_card")
    @patch("commands.create_card")
    @patch("commands.resolve_deck_id")
    def test_creates_hero_and_subcards(self, mock_resolve_deck, mock_create,
                                       mock_update, mock_output):
        mock_resolve_deck.side_effect = ["d-hero", "d-code", "d-design", "d-art"]
        mock_create.side_effect = [
            {"cardId": "hero-1"},
            {"cardId": "code-1"},
            {"cardId": "design-1"},
            {"cardId": "art-1"},
        ]
        ns = argparse.Namespace(
            title="Inventory 2.0",
            hero_deck="Features",
            code_deck="Code",
            design_deck="Design",
            art_deck="Art",
            skip_art=False,
            description="Improve inventory flow",
            owner=None,
            priority="a",
            effort=5,
            format="json",
        )
        cmd_feature(ns)
        assert mock_create.call_count == 4
        assert mock_update.call_count == 4
        # hero update + 3 sub updates
        hero_kwargs = mock_update.call_args_list[0].kwargs
        assert hero_kwargs["deckId"] == "d-hero"
        assert hero_kwargs["masterTags"] == ["hero", "feature"]
        code_kwargs = mock_update.call_args_list[1].kwargs
        assert code_kwargs["parentCardId"] == "hero-1"
        assert code_kwargs["deckId"] == "d-code"
        design_kwargs = mock_update.call_args_list[2].kwargs
        assert design_kwargs["deckId"] == "d-design"
        art_kwargs = mock_update.call_args_list[3].kwargs
        assert art_kwargs["deckId"] == "d-art"
        mock_output.assert_called_once()

    @patch("commands.output")
    @patch("commands.update_card")
    @patch("commands.create_card")
    @patch("commands.resolve_deck_id")
    def test_auto_skips_art_when_art_deck_missing(self, mock_resolve_deck, mock_create,
                                                  mock_update, mock_output):
        mock_resolve_deck.side_effect = ["d-hero", "d-code", "d-design"]
        mock_create.side_effect = [
            {"cardId": "hero-1"},
            {"cardId": "code-1"},
            {"cardId": "design-1"},
        ]
        ns = argparse.Namespace(
            title="Audio Mix",
            hero_deck="Features",
            code_deck="Code",
            design_deck="Design",
            art_deck=None,
            skip_art=False,
            description=None,
            owner=None,
            priority=None,
            effort=None,
            format="json",
        )
        cmd_feature(ns)
        assert mock_create.call_count == 3
        assert mock_update.call_count == 3
        report = mock_output.call_args.args[0]
        assert report["decks"]["art"] is None

    @patch("commands.output")
    @patch("commands.update_card")
    @patch("commands.create_card")
    @patch("commands.resolve_deck_id")
    def test_skip_art_creates_two_subcards(self, mock_resolve_deck, mock_create,
                                           mock_update, mock_output):
        mock_resolve_deck.side_effect = ["d-hero", "d-code", "d-design"]
        mock_create.side_effect = [
            {"cardId": "hero-1"},
            {"cardId": "code-1"},
            {"cardId": "design-1"},
        ]
        ns = argparse.Namespace(
            title="Economy Tuning",
            hero_deck="Features",
            code_deck="Code",
            design_deck="Design",
            art_deck=None,
            skip_art=True,
            description=None,
            owner=None,
            priority=None,
            effort=None,
            format="json",
        )
        cmd_feature(ns)
        assert mock_create.call_count == 3

    @patch("commands.archive_card")
    @patch("commands.update_card")
    @patch("commands.create_card")
    @patch("commands.resolve_deck_id")
    def test_rolls_back_on_partial_failure(self, mock_resolve_deck, mock_create,
                                           mock_update, mock_archive):
        mock_resolve_deck.side_effect = ["d-hero", "d-code", "d-design"]
        mock_create.side_effect = [
            {"cardId": "hero-1"},
            {"cardId": "code-1"},
            {"cardId": "design-1"},
        ]
        # Hero update succeeds, code update fails -> rollback hero + code created cards.
        mock_update.side_effect = [None, CliError("[ERROR] update failed")]
        ns = argparse.Namespace(
            title="Combat Feel",
            hero_deck="Features",
            code_deck="Code",
            design_deck="Design",
            art_deck=None,
            skip_art=True,
            description=None,
            owner=None,
            priority=None,
            effort=None,
            format="json",
        )
        with pytest.raises(CliError) as exc_info:
            cmd_feature(ns)
        msg = str(exc_info.value)
        assert "Feature scaffold failed" in msg
        assert "Rollback archived" in msg
        # Reversed rollback order: code first, then hero.
        assert mock_archive.call_count == 2
        assert mock_archive.call_args_list[0].args[0] == "code-1"
        assert mock_archive.call_args_list[1].args[0] == "hero-1"
