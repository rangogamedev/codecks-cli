"""Tests for commands.py — command handlers and known bug regressions.
Uses mocks to avoid real API calls.
"""

import argparse
import json
from unittest.mock import patch

import pytest

from codecks_cli import config
from codecks_cli.commands import (
    cmd_activity,
    cmd_cards,
    cmd_comment,
    cmd_create,
    cmd_decks,
    cmd_dispatch,
    cmd_feature,
    cmd_hand,
    cmd_pm_focus,
    cmd_standup,
    cmd_update,
)
from codecks_cli.config import CliError, SetupError


def _ns(**kwargs):
    """Build an argparse.Namespace with defaults for cmd_cards."""
    defaults = {
        "deck": None,
        "status": None,
        "project": None,
        "search": None,
        "milestone": None,
        "tag": None,
        "owner": None,
        "sort": None,
        "type": None,
        "hero": None,
        "stats": False,
        "hand": False,
        "archived": False,
        "format": "json",
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
            "c1": {
                "status": "done",
                "priority": "a",
                "effort": 5,
                "title": "A",
                "deck_name": "D",
                "owner_name": "O",
                "createdAt": "2026-01-01",
                "lastUpdatedAt": "2026-01-02",
            },
            "c2": {
                "status": "started",
                "priority": None,
                "effort": None,
                "title": "B",
                "deck_name": "D",
                "owner_name": "",
                "createdAt": "2026-01-03",
                "lastUpdatedAt": "2026-01-04",
            },
            "c3": {
                "status": "done",
                "priority": "b",
                "effort": 3,
                "title": "C",
                "deck_name": "D",
                "owner_name": "P",
                "createdAt": "2026-01-05",
                "lastUpdatedAt": "2026-01-06",
            },
        },
        "user": {},
    }

    @patch("codecks_cli.commands.list_cards")
    @patch("codecks_cli.commands.enrich_cards", side_effect=lambda c, u: c)
    def test_sort_effort_no_crash(self, mock_enrich, mock_list, capsys):
        mock_list.return_value = self.MOCK_CARDS.copy()
        cmd_cards(_ns(sort="effort", format="json"))
        out = json.loads(capsys.readouterr().out)
        # Should not crash — None effort goes last
        card_keys = list(out["card"].keys())
        assert len(card_keys) == 3

    @patch("codecks_cli.commands.list_cards")
    @patch("codecks_cli.commands.enrich_cards", side_effect=lambda c, u: c)
    def test_sort_priority_none_last(self, mock_enrich, mock_list, capsys):
        mock_list.return_value = self.MOCK_CARDS.copy()
        cmd_cards(_ns(sort="priority", format="json"))
        out = json.loads(capsys.readouterr().out)
        keys = list(out["card"].keys())
        # c1 (a) should come before c3 (b), c2 (None) should be last
        assert keys.index("c1") < keys.index("c3")
        assert keys[-1] == "c2"

    @patch("codecks_cli.commands.list_cards")
    @patch("codecks_cli.commands.enrich_cards", side_effect=lambda c, u: c)
    def test_sort_updated_newest_first(self, mock_enrich, mock_list, capsys):
        """Known bug regression: sort by updated should be newest first."""
        mock_list.return_value = self.MOCK_CARDS.copy()
        cmd_cards(_ns(sort="updated", format="json"))
        out = json.loads(capsys.readouterr().out)
        keys = list(out["card"].keys())
        # c2 (2026-01-04) should come before c1 (2026-01-02) — newest first
        assert keys.index("c2") < keys.index("c1")

    @patch("codecks_cli.commands.list_cards")
    @patch("codecks_cli.commands.enrich_cards", side_effect=lambda c, u: c)
    def test_sort_owner_empty_last(self, mock_enrich, mock_list, capsys):
        mock_list.return_value = self.MOCK_CARDS.copy()
        cmd_cards(_ns(sort="owner", format="json"))
        out = json.loads(capsys.readouterr().out)
        keys = list(out["card"].keys())
        # c2 has empty owner -> should be last
        assert keys[-1] == "c2"

    @patch("codecks_cli.commands.list_cards")
    @patch("codecks_cli.commands.enrich_cards", side_effect=lambda c, u: c)
    def test_sort_updated_supports_snake_case(self, mock_enrich, mock_list, capsys):
        mock_cards = {
            "card": {
                "old": {"title": "Old", "last_updated_at": "2026-01-02"},
                "new": {"title": "New", "last_updated_at": "2026-01-04"},
            },
            "user": {},
        }
        mock_list.return_value = mock_cards
        cmd_cards(_ns(sort="updated", format="json"))
        out = json.loads(capsys.readouterr().out)
        keys = list(out["card"].keys())
        assert keys == ["new", "old"]


# ---------------------------------------------------------------------------
# Regression: --title on missing card (the bug we fixed)
# ---------------------------------------------------------------------------


class TestUpdateTitleBug:
    """Bug: --title on nonexistent card silently dropped the title change."""

    @patch("codecks_cli.commands.get_card")
    def test_title_on_missing_card_exits(self, mock_get_card):
        mock_get_card.return_value = {"card": {}}
        ns = argparse.Namespace(
            card_ids=["nonexistent"],
            status=None,
            priority=None,
            effort=None,
            deck=None,
            title="New Title",
            content=None,
            milestone=None,
            hero=None,
            owner=None,
            tag=None,
            doc=None,
            format="json",
        )
        with pytest.raises(CliError) as exc_info:
            cmd_update(ns)
        assert exc_info.value.exit_code == 1

    @patch("codecks_cli.commands.update_card")
    @patch("codecks_cli.commands.get_card")
    def test_title_preserves_body(self, mock_get_card, mock_update, capsys):
        mock_get_card.return_value = {
            "card": {"c1": {"content": "Old Title\nBody line 1\nBody line 2"}}
        }
        mock_update.return_value = {}
        ns = argparse.Namespace(
            card_ids=["c1"],
            status=None,
            priority=None,
            effort=None,
            deck=None,
            title="New Title",
            content=None,
            milestone=None,
            hero=None,
            owner=None,
            tag=None,
            doc=None,
            format="table",
        )
        cmd_update(ns)
        call_kwargs = mock_update.call_args[1]
        assert call_kwargs["content"] == "New Title\nBody line 1\nBody line 2"

    @patch("codecks_cli.commands.update_card")
    @patch("codecks_cli.commands.get_card")
    def test_title_handles_none_content(self, mock_get_card, mock_update, capsys):
        """Regression: --title crashed with AttributeError when card content is None."""
        mock_get_card.return_value = {"card": {"c1": {"content": None}}}
        mock_update.return_value = {}
        ns = argparse.Namespace(
            card_ids=["c1"],
            status=None,
            priority=None,
            effort=None,
            deck=None,
            title="New Title",
            content=None,
            milestone=None,
            hero=None,
            owner=None,
            tag=None,
            doc=None,
            format="table",
        )
        cmd_update(ns)
        call_kwargs = mock_update.call_args[1]
        assert call_kwargs["content"] == "New Title"


# ---------------------------------------------------------------------------
# Regression: update_card sends None as JSON null (known bug #4)
# ---------------------------------------------------------------------------


class TestUpdateClearValues:
    """Known bug: update_card used to filter out None values, breaking
    --priority null, --milestone none, --owner none, --hero none."""

    @patch("codecks_cli.commands.update_card")
    def test_priority_null(self, mock_update, capsys):
        mock_update.return_value = {}
        ns = argparse.Namespace(
            card_ids=["c1"],
            status=None,
            priority="null",
            effort=None,
            deck=None,
            title=None,
            content=None,
            milestone=None,
            hero=None,
            owner=None,
            tag=None,
            doc=None,
            format="table",
        )
        cmd_update(ns)
        call_kwargs = mock_update.call_args[1]
        assert call_kwargs["priority"] is None

    @patch("codecks_cli.commands.update_card")
    def test_milestone_none(self, mock_update, capsys):
        mock_update.return_value = {}
        ns = argparse.Namespace(
            card_ids=["c1"],
            status=None,
            priority=None,
            effort=None,
            deck=None,
            title=None,
            content=None,
            milestone="none",
            hero=None,
            owner=None,
            tag=None,
            doc=None,
            format="table",
        )
        cmd_update(ns)
        call_kwargs = mock_update.call_args[1]
        assert call_kwargs["milestoneId"] is None

    @patch("codecks_cli.commands.update_card")
    def test_owner_none(self, mock_update, capsys):
        mock_update.return_value = {}
        ns = argparse.Namespace(
            card_ids=["c1"],
            status=None,
            priority=None,
            effort=None,
            deck=None,
            title=None,
            content=None,
            milestone=None,
            hero=None,
            owner="none",
            tag=None,
            doc=None,
            format="table",
        )
        cmd_update(ns)
        call_kwargs = mock_update.call_args[1]
        assert call_kwargs["assigneeId"] is None

    @patch("codecks_cli.commands.update_card")
    def test_tag_none(self, mock_update, capsys):
        mock_update.return_value = {}
        ns = argparse.Namespace(
            card_ids=["c1"],
            status=None,
            priority=None,
            effort=None,
            deck=None,
            title=None,
            content=None,
            milestone=None,
            hero=None,
            owner=None,
            tag="none",
            doc=None,
            format="table",
        )
        cmd_update(ns)
        call_kwargs = mock_update.call_args[1]
        assert call_kwargs["masterTags"] == []

    @patch("codecks_cli.commands.update_card")
    def test_effort_null(self, mock_update, capsys):
        mock_update.return_value = {}
        ns = argparse.Namespace(
            card_ids=["c1"],
            status=None,
            priority=None,
            effort="null",
            deck=None,
            title=None,
            content=None,
            milestone=None,
            hero=None,
            owner=None,
            tag=None,
            doc=None,
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
    @patch("codecks_cli.commands._guard_duplicate_title")
    @patch("codecks_cli.commands.create_card")
    def test_raises_on_missing_card_id(self, mock_create, _mock_guard):
        mock_create.return_value = {}
        ns = argparse.Namespace(
            title="Test Card",
            content=None,
            severity=None,
            deck=None,
            project=None,
            doc=False,
            format="json",
        )
        with pytest.raises(CliError) as exc_info:
            cmd_create(ns)
        assert "cardId" in str(exc_info.value)


class TestCreateProjectNotFound:
    """Critical fix #2: --project on nonexistent project should raise CliError,
    not silently print to stderr."""

    @patch("codecks_cli.commands._guard_duplicate_title")
    @patch("codecks_cli.commands.load_project_names")
    @patch("codecks_cli.commands.get_project_deck_ids")
    @patch("codecks_cli.commands.list_decks")
    @patch("codecks_cli.commands.create_card")
    def test_raises_on_unknown_project(
        self, mock_create, mock_list_decks, mock_get_project, mock_proj_names, _mock_guard
    ):
        mock_create.return_value = {"cardId": "new-card-id"}
        mock_list_decks.return_value = {"deck": {}}
        mock_get_project.return_value = None
        mock_proj_names.return_value = {"p1": "Tea Shop"}
        ns = argparse.Namespace(
            title="Test Card",
            content=None,
            severity=None,
            deck=None,
            project="Nonexistent",
            doc=False,
            format="json",
        )
        with pytest.raises(CliError) as exc_info:
            cmd_create(ns)
        assert "Nonexistent" in str(exc_info.value)
        assert "Tea Shop" in str(exc_info.value)


class TestCreateDuplicateGuard:
    @patch("codecks_cli.client.list_cards")
    @patch("codecks_cli.commands.create_card")
    def test_blocks_exact_duplicate_without_override(self, mock_create, mock_list_cards):
        mock_list_cards.return_value = {
            "card": {
                "c1": {"title": "Combat Revamp", "status": "started"},
            }
        }
        ns = argparse.Namespace(
            title="Combat Revamp",
            content=None,
            severity=None,
            deck=None,
            project=None,
            doc=False,
            format="json",
            allow_duplicate=False,
        )
        with pytest.raises(CliError) as exc_info:
            cmd_create(ns)
        assert "Duplicate card title detected" in str(exc_info.value)
        assert "--allow-duplicate" in str(exc_info.value)
        mock_create.assert_not_called()

    @patch("codecks_cli.commands.mutation_response")
    @patch("codecks_cli.commands.create_card")
    @patch("codecks_cli.client.list_cards")
    def test_allows_duplicate_when_overridden(self, mock_list_cards, mock_create, mock_mutation):
        mock_list_cards.return_value = {
            "card": {
                "c1": {"title": "Combat Revamp", "status": "started"},
            }
        }
        mock_create.return_value = {"cardId": "new-card-id"}
        ns = argparse.Namespace(
            title="Combat Revamp",
            content=None,
            severity=None,
            deck=None,
            project=None,
            doc=False,
            format="json",
            allow_duplicate=True,
        )
        cmd_create(ns)
        mock_create.assert_called_once()
        mock_mutation.assert_called_once()

    @patch("codecks_cli.commands.mutation_response")
    @patch("codecks_cli.commands.create_card")
    @patch("codecks_cli.client.list_cards")
    def test_warns_on_similar_title(self, mock_list_cards, mock_create, mock_mutation, capsys):
        mock_list_cards.return_value = {
            "card": {
                "c1": {"title": "Combat Revamp v2", "status": "not_started"},
            }
        }
        mock_create.return_value = {"cardId": "new-card-id"}
        ns = argparse.Namespace(
            title="Combat Revamp",
            content=None,
            severity=None,
            deck=None,
            project=None,
            doc=False,
            format="json",
            allow_duplicate=False,
        )
        cmd_create(ns)
        captured = capsys.readouterr()
        assert "[WARN] Similar card titles found" in captured.err
        mock_mutation.assert_called_once()


class TestUpdateNoFlags:
    def test_exits_with_error(self):
        ns = argparse.Namespace(
            card_ids=["c1"],
            status=None,
            priority=None,
            effort=None,
            deck=None,
            title=None,
            content=None,
            milestone=None,
            hero=None,
            owner=None,
            tag=None,
            doc=None,
            format="table",
        )
        with pytest.raises(CliError) as exc_info:
            cmd_update(ns)
        assert exc_info.value.exit_code == 1


class TestUpdateValidation:
    @patch("codecks_cli.commands.update_card")
    def test_rejects_invalid_effort_value(self, mock_update):
        ns = argparse.Namespace(
            card_ids=["c1"],
            status=None,
            priority=None,
            effort="abc",
            deck=None,
            title=None,
            content=None,
            milestone=None,
            hero=None,
            owner=None,
            tag=None,
            doc=None,
            format="json",
        )
        with pytest.raises(CliError) as exc_info:
            cmd_update(ns)
        assert "Invalid effort value" in str(exc_info.value)
        mock_update.assert_not_called()

    @patch("codecks_cli.commands.update_card")
    def test_rejects_invalid_doc_value(self, mock_update):
        ns = argparse.Namespace(
            card_ids=["c1"],
            status=None,
            priority=None,
            effort=None,
            deck=None,
            title=None,
            content=None,
            milestone=None,
            hero=None,
            owner=None,
            tag=None,
            doc="maybe",
            format="json",
        )
        with pytest.raises(CliError) as exc_info:
            cmd_update(ns)
        assert "Invalid --doc value" in str(exc_info.value)
        mock_update.assert_not_called()

    @patch("codecks_cli.commands.update_card")
    def test_rejects_title_with_multiple_cards(self, mock_update):
        ns = argparse.Namespace(
            card_ids=["c1", "c2"],
            status=None,
            priority=None,
            effort=None,
            deck=None,
            title="Rename",
            content=None,
            milestone=None,
            hero=None,
            owner=None,
            tag=None,
            doc=None,
            format="json",
        )
        with pytest.raises(CliError) as exc_info:
            cmd_update(ns)
        assert "--title can only be used with a single card" in str(exc_info.value)
        mock_update.assert_not_called()

    @patch("codecks_cli.commands.update_card")
    def test_rejects_content_with_multiple_cards(self, mock_update):
        ns = argparse.Namespace(
            card_ids=["c1", "c2"],
            status=None,
            priority=None,
            effort=None,
            deck=None,
            title=None,
            content="new body",
            milestone=None,
            hero=None,
            owner=None,
            tag=None,
            doc=None,
            format="json",
        )
        with pytest.raises(CliError) as exc_info:
            cmd_update(ns)
        assert "--content can only be used with a single card" in str(exc_info.value)
        mock_update.assert_not_called()


# ---------------------------------------------------------------------------
# Regression: False TOKEN_EXPIRED on filtered empty results (known bug #1)
# ---------------------------------------------------------------------------


class TestFilteredEmptyResults:
    """Known bug: cards --status started returning 0 cards triggered a
    false TOKEN_EXPIRED warning. Fixed by only calling warn_if_empty
    when no server-side filters are applied."""

    @patch("codecks_cli.cards.query")
    def test_status_filter_no_false_warning(self, mock_query, capsys):
        mock_query.return_value = {"card": {}}
        from codecks_cli.cards import list_cards

        result = list_cards(status_filter="started")
        err = capsys.readouterr().err
        assert "[TOKEN_EXPIRED]" not in err

    @patch("codecks_cli.cards.query")
    def test_deck_filter_no_false_warning(self, mock_query, capsys):
        mock_query.return_value = {"card": {}}
        config._cache["decks"] = {
            "deck": {
                "dk1": {"id": "d1", "title": "Features"},
            }
        }
        from codecks_cli.cards import list_cards

        result = list_cards(deck_filter="Features")
        err = capsys.readouterr().err
        assert "[TOKEN_EXPIRED]" not in err

    @patch("codecks_cli.cards.query")
    def test_unfiltered_empty_does_warn(self, mock_query, capsys):
        mock_query.return_value = {"card": {}}
        from codecks_cli.cards import list_cards

        result = list_cards()
        err = capsys.readouterr().err
        assert "[TOKEN_EXPIRED]" in err


class TestOwnerNoneFilter:
    """--owner none should find unassigned cards."""

    @patch("codecks_cli.cards.query")
    def test_owner_none_filters_to_unassigned(self, mock_query):
        mock_query.return_value = {
            "card": {
                "a": {"status": "done", "assignee": "u1"},
                "b": {"status": "started", "assignee": None},
                "c": {"status": "started"},
            },
            "user": {"u1": {"name": "Alice"}},
        }
        from codecks_cli.cards import list_cards

        result = list_cards(owner_filter="none")
        assert "a" not in result["card"]
        assert "b" in result["card"]
        assert "c" in result["card"]

    @patch("codecks_cli.cards.query")
    def test_owner_name_still_works(self, mock_query):
        mock_query.return_value = {
            "card": {
                "a": {"status": "done", "assignee": "u1"},
                "b": {"status": "started", "assignee": None},
            },
            "user": {"u1": {"name": "Alice"}},
        }
        from codecks_cli.cards import list_cards

        result = list_cards(owner_filter="Alice")
        assert "a" in result["card"]
        assert "b" not in result["card"]


class TestDispatchPathValidation:
    @patch("codecks_cli.commands.output")
    @patch("codecks_cli.commands.dispatch")
    def test_normalizes_prefixed_dispatch_path(self, mock_dispatch, mock_output):
        ns = argparse.Namespace(
            path="/dispatch/cards/update", json_data='{"id":"c1"}', format="json"
        )
        mock_dispatch.return_value = {"ok": True}
        cmd_dispatch(ns)
        mock_dispatch.assert_called_once_with("cards/update", {"id": "c1"})

    def test_rejects_invalid_dispatch_path(self):
        ns = argparse.Namespace(path="dispatch/ bad path", json_data='{"id":"c1"}', format="json")
        with pytest.raises(CliError):
            cmd_dispatch(ns)


class TestCommentValidation:
    def test_rejects_multiple_modes(self):
        ns = argparse.Namespace(
            card_id="c1", message=None, thread="t1", close="t2", reopen=None, format="json"
        )
        with pytest.raises(CliError):
            cmd_comment(ns)

    def test_rejects_message_with_close(self):
        ns = argparse.Namespace(
            card_id="c1", message="nope", thread=None, close="t1", reopen=None, format="json"
        )
        with pytest.raises(CliError):
            cmd_comment(ns)

    def test_rejects_message_with_reopen(self):
        ns = argparse.Namespace(
            card_id="c1", message="nope", thread=None, close=None, reopen="t1", format="json"
        )
        with pytest.raises(CliError):
            cmd_comment(ns)


class TestActivityValidation:
    def test_rejects_non_positive_limit(self):
        ns = argparse.Namespace(limit=0, format="json")
        with pytest.raises(CliError):
            cmd_activity(ns)

    @patch("codecks_cli.commands.output")
    @patch("codecks_cli.commands.list_activity")
    def test_forwards_limit_to_list_activity(self, mock_list_activity, mock_output):
        ns = argparse.Namespace(limit=5, format="json")
        mock_list_activity.return_value = {"activity": {}}
        cmd_activity(ns)
        mock_list_activity.assert_called_once_with(5)
        mock_output.assert_called_once()


class TestPmFocus:
    @patch("codecks_cli.commands.output")
    @patch("codecks_cli.commands.extract_hand_card_ids")
    @patch("codecks_cli.commands.list_hand")
    @patch("codecks_cli.commands.enrich_cards")
    @patch("codecks_cli.commands.list_cards")
    def test_generates_focus_report(
        self, mock_list_cards, mock_enrich, mock_list_hand, mock_extract, mock_output
    ):
        mock_list_cards.return_value = {
            "card": {
                "c1": {"title": "A", "status": "blocked", "priority": "a", "effort": 5},
                "c2": {
                    "title": "B",
                    "status": "started",
                    "priority": "b",
                    "effort": 3,
                    "lastUpdatedAt": "2026-02-19T00:00:00Z",
                },
                "c3": {"title": "C", "status": "not_started", "priority": "a", "effort": 8},
                "c4": {"title": "D", "status": "not_started", "priority": "c", "effort": 2},
                "c5": {
                    "title": "E",
                    "status": "in_review",
                    "priority": "b",
                    "effort": 2,
                    "lastUpdatedAt": "2026-02-19T00:00:00Z",
                },
            },
            "user": {},
        }
        mock_enrich.side_effect = lambda cards, user: cards
        mock_list_hand.return_value = {}
        mock_extract.return_value = {"c2"}

        ns = argparse.Namespace(project=None, owner=None, limit=2, stale_days=14, format="json")
        cmd_pm_focus(ns)

        report = mock_output.call_args.args[0]
        assert report["counts"]["blocked"] == 1
        assert report["counts"]["started"] == 1
        assert report["counts"]["in_review"] == 1
        assert report["counts"]["hand"] == 1
        assert len(report["suggested"]) == 2
        assert report["suggested"][0]["id"] == "c3"

    @patch("codecks_cli.commands.output")
    @patch("codecks_cli.commands.extract_hand_card_ids")
    @patch("codecks_cli.commands.list_hand")
    @patch("codecks_cli.commands.enrich_cards")
    @patch("codecks_cli.commands.list_cards")
    def test_detects_stale_cards(
        self, mock_list_cards, mock_enrich, mock_list_hand, mock_extract, mock_output
    ):
        mock_list_cards.return_value = {
            "card": {
                "stale": {
                    "title": "Old",
                    "status": "started",
                    "priority": "a",
                    "lastUpdatedAt": "2025-01-01T00:00:00Z",
                },
                "fresh": {
                    "title": "New",
                    "status": "started",
                    "priority": "a",
                    "lastUpdatedAt": "2026-02-19T00:00:00Z",
                },
            },
            "user": {},
        }
        mock_enrich.side_effect = lambda cards, user: cards
        mock_list_hand.return_value = {}
        mock_extract.return_value = set()

        ns = argparse.Namespace(project=None, owner=None, limit=5, stale_days=14, format="json")
        cmd_pm_focus(ns)

        report = mock_output.call_args.args[0]
        assert report["counts"]["stale"] == 1
        assert report["stale"][0]["title"] == "Old"


class TestStandup:
    @patch("codecks_cli.commands.output")
    @patch("codecks_cli.commands.extract_hand_card_ids")
    @patch("codecks_cli.commands.list_hand")
    @patch("codecks_cli.commands.enrich_cards")
    @patch("codecks_cli.commands.list_cards")
    def test_categorizes_cards(
        self, mock_list_cards, mock_enrich, mock_list_hand, mock_extract, mock_output
    ):
        mock_list_cards.return_value = {
            "card": {
                "c1": {
                    "title": "Done Yesterday",
                    "status": "done",
                    "lastUpdatedAt": "2026-02-19T12:00:00Z",
                },
                "c2": {
                    "title": "Done Long Ago",
                    "status": "done",
                    "lastUpdatedAt": "2025-01-01T00:00:00Z",
                },
                "c3": {"title": "Working On", "status": "started"},
                "c4": {"title": "Stuck", "status": "blocked"},
                "c5": {"title": "In Hand", "status": "started"},
            },
            "user": {},
        }
        mock_enrich.side_effect = lambda cards, user: cards
        mock_list_hand.return_value = {}
        mock_extract.return_value = {"c5"}

        ns = argparse.Namespace(project=None, owner=None, days=2, format="json")
        cmd_standup(ns)

        report = mock_output.call_args.args[0]
        assert len(report["recently_done"]) == 1
        assert report["recently_done"][0]["title"] == "Done Yesterday"
        assert len(report["in_progress"]) == 2  # c3 + c5
        assert len(report["blocked"]) == 1
        assert len(report["hand"]) == 1  # c5 (not done)


class TestRawCommandValidation:
    def test_query_requires_object_payload(self):
        ns = argparse.Namespace(json_query="[1,2,3]", format="json")
        from codecks_cli.commands import cmd_query

        with pytest.raises(CliError) as exc_info:
            cmd_query(ns)
        assert "expected object" in str(exc_info.value)

    def test_query_strict_requires_root(self, monkeypatch):
        monkeypatch.setattr(config, "RUNTIME_STRICT", True)
        ns = argparse.Namespace(json_query='{"foo":"bar"}', format="json")
        from codecks_cli.commands import cmd_query

        with pytest.raises(CliError) as exc_info:
            cmd_query(ns)
        assert "non-empty '_root' array" in str(exc_info.value)

    @patch("codecks_cli.commands.output")
    @patch("codecks_cli.commands.dispatch")
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
        ns = argparse.Namespace(path="cards/update", json_data="{}", format="json")
        with pytest.raises(CliError) as exc_info:
            cmd_dispatch(ns)
        assert "dispatch payload cannot be empty" in str(exc_info.value)


class TestFeatureScaffold:
    @patch("codecks_cli.commands._guard_duplicate_title")
    @patch("codecks_cli.commands.output")
    @patch("codecks_cli.commands.update_card")
    @patch("codecks_cli.commands.create_card")
    @patch("codecks_cli.commands.resolve_deck_id")
    def test_creates_hero_and_subcards(
        self, mock_resolve_deck, mock_create, mock_update, mock_output, _mock_guard
    ):
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

    @patch("codecks_cli.commands._guard_duplicate_title")
    @patch("codecks_cli.commands.output")
    @patch("codecks_cli.commands.update_card")
    @patch("codecks_cli.commands.create_card")
    @patch("codecks_cli.commands.resolve_deck_id")
    def test_auto_skips_art_when_art_deck_missing(
        self, mock_resolve_deck, mock_create, mock_update, mock_output, _mock_guard
    ):
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

    @patch("codecks_cli.commands._guard_duplicate_title")
    @patch("codecks_cli.commands.output")
    @patch("codecks_cli.commands.update_card")
    @patch("codecks_cli.commands.create_card")
    @patch("codecks_cli.commands.resolve_deck_id")
    def test_skip_art_creates_two_subcards(
        self, mock_resolve_deck, mock_create, mock_update, mock_output, _mock_guard
    ):
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

    @patch("codecks_cli.commands._guard_duplicate_title")
    @patch("codecks_cli.commands.archive_card")
    @patch("codecks_cli.commands.update_card")
    @patch("codecks_cli.commands.create_card")
    @patch("codecks_cli.commands.resolve_deck_id")
    def test_rolls_back_on_partial_failure(
        self, mock_resolve_deck, mock_create, mock_update, mock_archive, _mock_guard
    ):
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

    @patch("codecks_cli.commands._guard_duplicate_title")
    @patch("codecks_cli.commands.archive_card")
    @patch("codecks_cli.commands.update_card")
    @patch("codecks_cli.commands.create_card")
    @patch("codecks_cli.commands.resolve_deck_id")
    def test_preserves_setup_error_during_rollback(
        self, mock_resolve_deck, mock_create, mock_update, mock_archive, _mock_guard
    ):
        mock_resolve_deck.side_effect = ["d-hero", "d-code", "d-design"]
        mock_create.side_effect = [
            {"cardId": "hero-1"},
            {"cardId": "code-1"},
            {"cardId": "design-1"},
        ]
        mock_update.side_effect = [None, SetupError("[TOKEN_EXPIRED] expired")]
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
        with pytest.raises(SetupError) as exc_info:
            cmd_feature(ns)
        msg = str(exc_info.value)
        assert msg.startswith("[TOKEN_EXPIRED]")
        assert "Rollback archived" in msg
        assert mock_archive.call_count == 2
        assert mock_archive.call_args_list[0].args[0] == "code-1"
        assert mock_archive.call_args_list[1].args[0] == "hero-1"

    @patch("codecks_cli.client.list_cards")
    @patch("codecks_cli.commands.create_card")
    def test_blocks_duplicate_feature_hero_by_default(self, mock_create, mock_list_cards):
        mock_list_cards.return_value = {
            "card": {
                "h1": {"title": "Feature: Combat Revamp", "status": "started"},
            }
        }
        ns = argparse.Namespace(
            title="Combat Revamp",
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
            allow_duplicate=False,
        )
        with pytest.raises(CliError) as exc_info:
            cmd_feature(ns)
        assert "Duplicate feature hero title detected" in str(exc_info.value)
        mock_create.assert_not_called()


# ---------------------------------------------------------------------------
# Hand sort order (item 1.7)
# ---------------------------------------------------------------------------


class TestHandSortOrder:
    @patch("codecks_cli.commands.output")
    @patch("codecks_cli.commands.enrich_cards")
    @patch("codecks_cli.commands.list_cards")
    @patch("codecks_cli.commands.extract_hand_card_ids")
    @patch("codecks_cli.commands.list_hand")
    def test_hand_sorted_by_sort_index(
        self, mock_list_hand, mock_extract, mock_list_cards, mock_enrich, mock_output
    ):
        mock_list_hand.return_value = {
            "queueEntry": {
                "e1": {"card": "c1", "sortIndex": 300},
                "e2": {"card": "c2", "sortIndex": 100},
                "e3": {"card": "c3", "sortIndex": 200},
            }
        }
        mock_extract.return_value = {"c1", "c2", "c3"}
        mock_list_cards.return_value = {
            "card": {
                "c1": {"title": "Third", "status": "started"},
                "c2": {"title": "First", "status": "done"},
                "c3": {"title": "Second", "status": "started"},
            },
            "user": {},
        }
        mock_enrich.side_effect = lambda cards, user: cards
        ns = argparse.Namespace(card_ids=None, format="json")
        cmd_hand(ns)
        # Check the order passed to output
        result = mock_output.call_args.args[0]
        card_keys = list(result["card"].keys())
        assert card_keys == ["c2", "c3", "c1"]

    @patch("codecks_cli.commands.output")
    @patch("codecks_cli.commands.enrich_cards")
    @patch("codecks_cli.commands.list_cards")
    @patch("codecks_cli.commands.extract_hand_card_ids")
    @patch("codecks_cli.commands.list_hand")
    def test_hand_sort_handles_missing_sort_index(
        self, mock_list_hand, mock_extract, mock_list_cards, mock_enrich, mock_output
    ):
        mock_list_hand.return_value = {
            "queueEntry": {
                "e1": {"card": "c1", "sortIndex": 200},
                "e2": {"card": "c2"},  # no sortIndex
            }
        }
        mock_extract.return_value = {"c1", "c2"}
        mock_list_cards.return_value = {
            "card": {
                "c1": {"title": "B", "status": "started"},
                "c2": {"title": "A", "status": "done"},
            },
            "user": {},
        }
        mock_enrich.side_effect = lambda cards, user: cards
        ns = argparse.Namespace(card_ids=None, format="json")
        cmd_hand(ns)
        result = mock_output.call_args.args[0]
        card_keys = list(result["card"].keys())
        # c2 has sortIndex 0 (default), c1 has 200
        assert card_keys == ["c2", "c1"]


# ---------------------------------------------------------------------------
# Deck card counts (item 1.8)
# ---------------------------------------------------------------------------


class TestHandEmptyReturns:
    """Critical fix #5: cmd_hand with empty hand should return, not sys.exit(0)."""

    @patch("codecks_cli.commands.extract_hand_card_ids")
    @patch("codecks_cli.commands.list_hand")
    def test_empty_hand_returns_without_exit(self, mock_list_hand, mock_extract, capsys):
        mock_list_hand.return_value = {"queueEntry": {}}
        mock_extract.return_value = set()
        ns = argparse.Namespace(card_ids=None, format="json")
        # Should return normally, not raise SystemExit
        cmd_hand(ns)
        err = capsys.readouterr().err
        assert "empty" in err.lower()


class TestDeckCardCounts:
    @patch("codecks_cli.commands.output")
    @patch("codecks_cli.commands.list_cards")
    @patch("codecks_cli.commands.list_decks")
    def test_deck_counts_passed_to_formatter(self, mock_list_decks, mock_list_cards, mock_output):
        mock_list_decks.return_value = {
            "deck": {
                "dk1": {"id": "d1", "title": "Features", "projectId": "p1"},
                "dk2": {"id": "d2", "title": "Tasks", "projectId": "p1"},
            }
        }
        mock_list_cards.return_value = {
            "card": {
                "c1": {"deckId": "d1"},
                "c2": {"deckId": "d1"},
                "c3": {"deckId": "d2"},
            }
        }
        ns = argparse.Namespace(format="json")
        cmd_decks(ns)
        result = mock_output.call_args.args[0]
        assert result["_deck_counts"] == {"d1": 2, "d2": 1}
