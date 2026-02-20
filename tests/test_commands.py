"""Tests for commands.py — command handlers and known bug regressions.
Uses mocks to avoid real API calls.
"""

import argparse
import json
import pytest
from unittest.mock import patch, MagicMock

import config
from config import CliError
from commands import cmd_cards, cmd_update, cmd_create, cmd_card


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
