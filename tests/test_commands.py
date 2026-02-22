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
    cmd_completion,
    cmd_create,
    cmd_decks,
    cmd_delete,
    cmd_dispatch,
    cmd_feature,
    cmd_gdd_sync,
    cmd_hand,
    cmd_pm_focus,
    cmd_split_features,
    cmd_standup,
    cmd_update,
)
from codecks_cli.exceptions import CliError, SetupError


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
# Regression: Sort delegation (known bug #3 — sorting tested in test_client)
# ---------------------------------------------------------------------------


class TestSortDelegation:
    """Sorting is delegated to CodecksClient. Verify passthrough."""

    @patch("codecks_cli.commands._get_client")
    def test_sort_param_passed_to_client(self, mock_get_client, capsys):
        mock_client = mock_get_client.return_value
        mock_client.list_cards.return_value = {
            "cards": [
                {"id": "c1", "status": "done", "priority": "a", "effort": 5, "title": "A"},
                {"id": "c3", "status": "done", "priority": "b", "effort": 3, "title": "C"},
                {"id": "c2", "status": "started", "priority": None, "effort": None, "title": "B"},
            ],
            "stats": None,
        }
        cmd_cards(_ns(sort="effort", format="json"))
        mock_client.list_cards.assert_called_once()
        assert mock_client.list_cards.call_args[1]["sort"] == "effort"
        out = json.loads(capsys.readouterr().out)
        assert len(out["cards"]) == 3

    @patch("codecks_cli.commands._get_client")
    def test_all_filter_params_forwarded(self, mock_get_client, capsys):
        mock_client = mock_get_client.return_value
        mock_client.list_cards.return_value = {"cards": [], "stats": None}
        cmd_cards(
            _ns(
                deck="Features",
                status="started",
                project="Tea Shop",
                search="combat",
                milestone="MVP",
                tag="bug",
                owner="Alice",
                sort="priority",
                type="hero",
                hero="hero-id",
                hand=True,
                archived=True,
            )
        )
        kwargs = mock_client.list_cards.call_args[1]
        assert kwargs["deck"] == "Features"
        assert kwargs["status"] == "started"
        assert kwargs["project"] == "Tea Shop"
        assert kwargs["search"] == "combat"
        assert kwargs["milestone"] == "MVP"
        assert kwargs["tag"] == "bug"
        assert kwargs["owner"] == "Alice"
        assert kwargs["sort"] == "priority"
        assert kwargs["card_type"] == "hero"
        assert kwargs["hero"] == "hero-id"
        assert kwargs["hand_only"] is True
        assert kwargs["archived"] is True

    @patch("codecks_cli.commands._get_client")
    def test_stats_mode_outputs_stats(self, mock_get_client, capsys):
        mock_client = mock_get_client.return_value
        mock_client.list_cards.return_value = {
            "cards": [{"id": "c1", "title": "A"}],
            "stats": {
                "total": 1,
                "total_effort": 5,
                "avg_effort": 5.0,
                "by_status": {"done": 1},
                "by_priority": {"a": 1},
                "by_deck": {"Features": 1},
            },
        }
        cmd_cards(_ns(stats=True, format="table"))
        out = capsys.readouterr().out
        assert "Total cards: 1" in out

    @patch("codecks_cli.commands._get_client")
    def test_pagination_applied_in_cmd_cards_json(self, mock_get_client, capsys):
        mock_client = mock_get_client.return_value
        mock_client.list_cards.return_value = {
            "cards": [{"id": f"c{i}", "title": f"Card {i}"} for i in range(6)],
            "stats": None,
        }
        cmd_cards(_ns(format="json", limit=2, offset=3))
        out = json.loads(capsys.readouterr().out)
        assert out["total_count"] == 6
        assert out["limit"] == 2
        assert out["offset"] == 3
        assert out["has_more"] is True
        assert [c["id"] for c in out["cards"]] == ["c3", "c4"]


# ---------------------------------------------------------------------------
# Regression: --title on missing card (the bug we fixed)
# ---------------------------------------------------------------------------


class TestUpdateTitleBug:
    """Bug: --title on nonexistent card silently dropped the title change.
    Now tested via client delegation — client raises CliError."""

    @patch("codecks_cli.commands._get_client")
    def test_title_on_missing_card_exits(self, mock_get_client):
        mock_client = mock_get_client.return_value
        mock_client.update_cards.side_effect = CliError("[ERROR] Card 'nonexistent' not found.")
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

    @patch("codecks_cli.commands._get_client")
    def test_title_passed_to_client(self, mock_get_client, capsys):
        mock_client = mock_get_client.return_value
        mock_client.update_cards.return_value = {
            "ok": True,
            "updated": 1,
            "fields": {"content": "New Title\nBody"},
        }
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
        mock_client.update_cards.assert_called_once()
        assert mock_client.update_cards.call_args[1]["title"] == "New Title"


# ---------------------------------------------------------------------------
# Regression: update_card sends None as JSON null (known bug #4)
# ---------------------------------------------------------------------------


class TestUpdateClearValues:
    """Known bug: clearing fields. Now validated via client delegation."""

    @patch("codecks_cli.commands._get_client")
    def test_priority_null_passed(self, mock_get_client, capsys):
        mock_client = mock_get_client.return_value
        mock_client.update_cards.return_value = {
            "ok": True,
            "updated": 1,
            "fields": {"priority": None},
        }
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
        assert mock_client.update_cards.call_args[1]["priority"] == "null"

    @patch("codecks_cli.commands._get_client")
    def test_milestone_none_passed(self, mock_get_client, capsys):
        mock_client = mock_get_client.return_value
        mock_client.update_cards.return_value = {
            "ok": True,
            "updated": 1,
            "fields": {"milestoneId": None},
        }
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
        assert mock_client.update_cards.call_args[1]["milestone"] == "none"

    @patch("codecks_cli.commands._get_client")
    def test_owner_none_passed(self, mock_get_client, capsys):
        mock_client = mock_get_client.return_value
        mock_client.update_cards.return_value = {
            "ok": True,
            "updated": 1,
            "fields": {"assigneeId": None},
        }
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
        assert mock_client.update_cards.call_args[1]["owner"] == "none"

    @patch("codecks_cli.commands._get_client")
    def test_tag_none_passed(self, mock_get_client, capsys):
        mock_client = mock_get_client.return_value
        mock_client.update_cards.return_value = {
            "ok": True,
            "updated": 1,
            "fields": {"masterTags": []},
        }
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
        assert mock_client.update_cards.call_args[1]["tags"] == "none"

    @patch("codecks_cli.commands._get_client")
    def test_effort_null_passed(self, mock_get_client, capsys):
        mock_client = mock_get_client.return_value
        mock_client.update_cards.return_value = {
            "ok": True,
            "updated": 1,
            "fields": {"effort": None},
        }
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
        assert mock_client.update_cards.call_args[1]["effort"] == "null"


# ---------------------------------------------------------------------------
# Regression: no update flags provided
# ---------------------------------------------------------------------------


class TestUpdateNoFlags:
    @patch("codecks_cli.commands._get_client")
    def test_exits_with_error(self, mock_get_client):
        mock_client = mock_get_client.return_value
        mock_client.update_cards.side_effect = CliError(
            "[ERROR] No update flags provided. Use --status, "
            "--priority, --effort, --owner, --tag, --doc, etc."
        )
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


# ---------------------------------------------------------------------------
# Regression: cmd_create with missing cardId in API response
# ---------------------------------------------------------------------------


class TestCreateMissingCardId:
    @patch("codecks_cli.commands._get_client")
    def test_raises_on_missing_card_id(self, mock_get_client):
        mock_client = mock_get_client.return_value
        mock_client.create_card.side_effect = CliError(
            "[ERROR] Card creation failed: API response missing 'cardId'."
        )
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
    """Critical fix #2: --project on nonexistent project should raise CliError."""

    @patch("codecks_cli.commands._get_client")
    def test_raises_on_unknown_project(self, mock_get_client):
        mock_client = mock_get_client.return_value
        mock_client.create_card.side_effect = CliError(
            "[ERROR] Project 'Nonexistent' not found. Available: Tea Shop"
        )
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
    @patch("codecks_cli.commands._get_client")
    def test_blocks_exact_duplicate_without_override(self, mock_get_client):
        mock_client = mock_get_client.return_value
        mock_client.create_card.side_effect = CliError(
            "[ERROR] Duplicate card title detected: 'Combat Revamp'.\n"
            "[ERROR] Re-run with --allow-duplicate to bypass this check."
        )
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

    @patch("codecks_cli.commands._get_client")
    def test_allows_duplicate_when_overridden(self, mock_get_client, capsys):
        mock_client = mock_get_client.return_value
        mock_client.create_card.return_value = {
            "ok": True,
            "card_id": "new-card-id",
            "title": "Combat Revamp",
            "deck": None,
            "doc": False,
        }
        ns = argparse.Namespace(
            title="Combat Revamp",
            content=None,
            severity=None,
            deck=None,
            project=None,
            doc=False,
            format="table",
            allow_duplicate=True,
        )
        cmd_create(ns)
        mock_client.create_card.assert_called_once()
        assert mock_client.create_card.call_args[1]["allow_duplicate"] is True

    @patch("codecks_cli.commands._get_client")
    def test_warns_on_similar_title(self, mock_get_client, capsys):
        mock_client = mock_get_client.return_value
        mock_client.create_card.return_value = {
            "ok": True,
            "card_id": "new-card-id",
            "title": "Combat Revamp",
            "deck": None,
            "doc": False,
            "warnings": ["Similar card titles found for 'Combat Revamp': c1 ('Combat Revamp v2')"],
        }
        ns = argparse.Namespace(
            title="Combat Revamp",
            content=None,
            severity=None,
            deck=None,
            project=None,
            doc=False,
            format="table",
            allow_duplicate=False,
        )
        cmd_create(ns)
        captured = capsys.readouterr()
        assert "[WARN] Similar card titles found" in captured.err


class TestCreateParent:
    @patch("codecks_cli.commands._get_client")
    def test_parent_passed_through(self, mock_get_client, capsys):
        mock_client = mock_get_client.return_value
        mock_client.create_card.return_value = {
            "ok": True,
            "card_id": "child-id",
            "title": "Sub Task",
            "deck": None,
            "doc": False,
            "parent": "parent-uuid",
        }
        ns = argparse.Namespace(
            title="Sub Task",
            content=None,
            severity=None,
            deck=None,
            project=None,
            doc=False,
            format="table",
            allow_duplicate=False,
            parent="parent-uuid",
        )
        cmd_create(ns)
        mock_client.create_card.assert_called_once()
        assert mock_client.create_card.call_args[1]["parent"] == "parent-uuid"

    @patch("codecks_cli.commands._get_client")
    def test_parent_shown_in_detail(self, mock_get_client, capsys):
        mock_client = mock_get_client.return_value
        mock_client.create_card.return_value = {
            "ok": True,
            "card_id": "child-id",
            "title": "Sub Task",
            "deck": None,
            "doc": False,
            "parent": "parent-uuid",
        }
        ns = argparse.Namespace(
            title="Sub Task",
            content=None,
            severity=None,
            deck=None,
            project=None,
            doc=False,
            format="table",
            allow_duplicate=False,
            parent="parent-uuid",
        )
        cmd_create(ns)
        captured = capsys.readouterr()
        assert "parent='parent-uuid'" in captured.out


class TestUpdateValidation:
    @patch("codecks_cli.commands._get_client")
    def test_rejects_invalid_effort_value(self, mock_get_client):
        mock_client = mock_get_client.return_value
        mock_client.update_cards.side_effect = CliError(
            "[ERROR] Invalid effort value 'abc': must be a number or 'null'"
        )
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

    @patch("codecks_cli.commands._get_client")
    def test_rejects_invalid_doc_value(self, mock_get_client):
        mock_client = mock_get_client.return_value
        mock_client.update_cards.side_effect = CliError(
            "[ERROR] Invalid --doc value 'maybe'. Use true or false."
        )
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

    @patch("codecks_cli.commands._get_client")
    def test_rejects_title_with_multiple_cards(self, mock_get_client):
        mock_client = mock_get_client.return_value
        mock_client.update_cards.side_effect = CliError(
            "[ERROR] --title can only be used with a single card."
        )
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

    @patch("codecks_cli.commands._get_client")
    def test_rejects_content_with_multiple_cards(self, mock_get_client):
        mock_client = mock_get_client.return_value
        mock_client.update_cards.side_effect = CliError(
            "[ERROR] --content can only be used with a single card."
        )
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


# ---------------------------------------------------------------------------
# Regression: False TOKEN_EXPIRED on filtered empty results (known bug #1)
# (Tests cards.py directly — no change needed)
# ---------------------------------------------------------------------------


class TestFilteredEmptyResults:
    """Known bug: cards --status started returning 0 cards triggered a
    false TOKEN_EXPIRED warning. Fixed by only calling warn_if_empty
    when no server-side filters are applied."""

    @patch("codecks_cli.cards.query")
    def test_status_filter_no_false_warning(self, mock_query, capsys):
        mock_query.return_value = {"card": {}}
        from codecks_cli.cards import list_cards

        list_cards(status_filter="started")
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

        list_cards(deck_filter="Features")
        err = capsys.readouterr().err
        assert "[TOKEN_EXPIRED]" not in err

    @patch("codecks_cli.cards.query")
    def test_unfiltered_empty_does_warn(self, mock_query, capsys):
        mock_query.return_value = {"card": {}}
        from codecks_cli.cards import list_cards

        list_cards()
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
    @patch("codecks_cli.commands._get_client")
    def test_rejects_non_positive_limit(self, mock_get_client):
        mock_client = mock_get_client.return_value
        mock_client.list_activity.side_effect = CliError(
            "[ERROR] --limit must be a positive integer."
        )
        ns = argparse.Namespace(limit=0, format="json")
        with pytest.raises(CliError):
            cmd_activity(ns)

    @patch("codecks_cli.commands._get_client")
    def test_forwards_limit_to_client(self, mock_get_client, capsys):
        mock_client = mock_get_client.return_value
        mock_client.list_activity.return_value = {"activity": {}}
        ns = argparse.Namespace(limit=5, format="json")
        cmd_activity(ns)
        mock_client.list_activity.assert_called_once_with(limit=5)


class TestPmFocus:
    @patch("codecks_cli.commands._get_client")
    def test_generates_focus_report(self, mock_get_client, capsys):
        mock_client = mock_get_client.return_value
        mock_client.pm_focus.return_value = {
            "counts": {
                "started": 1,
                "blocked": 1,
                "in_review": 1,
                "hand": 1,
                "stale": 0,
            },
            "blocked": [{"id": "c1", "title": "A", "priority": "a", "effort": 5}],
            "in_review": [{"id": "c5", "title": "E", "priority": "b", "effort": 2}],
            "hand": [{"id": "c2", "title": "B", "priority": "b", "effort": 3}],
            "stale": [],
            "suggested": [
                {"id": "c3", "title": "C", "priority": "a", "effort": 8},
                {"id": "c4", "title": "D", "priority": "c", "effort": 2},
            ],
            "filters": {"project": None, "owner": None, "limit": 2, "stale_days": 14},
        }
        ns = argparse.Namespace(project=None, owner=None, limit=2, stale_days=14, format="json")
        cmd_pm_focus(ns)
        out = json.loads(capsys.readouterr().out)
        assert out["counts"]["blocked"] == 1
        assert out["counts"]["started"] == 1
        assert out["counts"]["in_review"] == 1
        assert out["counts"]["hand"] == 1
        assert len(out["suggested"]) == 2
        assert out["suggested"][0]["id"] == "c3"

    @patch("codecks_cli.commands._get_client")
    def test_detects_stale_cards(self, mock_get_client, capsys):
        mock_client = mock_get_client.return_value
        mock_client.pm_focus.return_value = {
            "counts": {"started": 2, "blocked": 0, "in_review": 0, "hand": 0, "stale": 1},
            "blocked": [],
            "in_review": [],
            "hand": [],
            "stale": [{"id": "stale", "title": "Old", "priority": "a"}],
            "suggested": [],
            "filters": {"stale_days": 14},
        }
        ns = argparse.Namespace(project=None, owner=None, limit=5, stale_days=14, format="json")
        cmd_pm_focus(ns)
        out = json.loads(capsys.readouterr().out)
        assert out["counts"]["stale"] == 1
        assert out["stale"][0]["title"] == "Old"


class TestStandup:
    @patch("codecks_cli.commands._get_client")
    def test_categorizes_cards(self, mock_get_client, capsys):
        mock_client = mock_get_client.return_value
        mock_client.standup.return_value = {
            "recently_done": [{"id": "c1", "title": "Done Yesterday"}],
            "in_progress": [
                {"id": "c3", "title": "Working On"},
                {"id": "c5", "title": "In Hand"},
            ],
            "blocked": [{"id": "c4", "title": "Stuck"}],
            "hand": [{"id": "c5", "title": "In Hand"}],
            "filters": {"project": None, "owner": None, "days": 2},
        }
        ns = argparse.Namespace(project=None, owner=None, days=2, format="json")
        cmd_standup(ns)
        out = json.loads(capsys.readouterr().out)
        assert len(out["recently_done"]) == 1
        assert out["recently_done"][0]["title"] == "Done Yesterday"
        assert len(out["in_progress"]) == 2
        assert len(out["blocked"]) == 1
        assert len(out["hand"]) == 1


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
    @patch("codecks_cli.commands._get_client")
    def test_creates_hero_and_subcards(self, mock_get_client, capsys):
        mock_client = mock_get_client.return_value
        mock_client.scaffold_feature.return_value = {
            "ok": True,
            "hero": {"id": "hero-1", "title": "Feature: Inventory 2.0"},
            "subcards": [
                {"lane": "code", "id": "code-1"},
                {"lane": "design", "id": "design-1"},
                {"lane": "art", "id": "art-1"},
            ],
            "decks": {"hero": "Features", "code": "Code", "design": "Design", "art": "Art"},
        }
        ns = argparse.Namespace(
            title="Inventory 2.0",
            hero_deck="Features",
            code_deck="Code",
            design_deck="Design",
            art_deck="Art",
            skip_art=False,
            audio_deck=None,
            skip_audio=False,
            description="Improve inventory flow",
            owner=None,
            priority="a",
            effort=5,
            format="json",
        )
        cmd_feature(ns)
        mock_client.scaffold_feature.assert_called_once()
        out = json.loads(capsys.readouterr().out)
        assert out["ok"] is True
        assert out["hero"]["id"] == "hero-1"
        assert len(out["subcards"]) == 3

    @patch("codecks_cli.commands._get_client")
    def test_auto_skips_art_when_art_deck_missing(self, mock_get_client, capsys):
        mock_client = mock_get_client.return_value
        mock_client.scaffold_feature.return_value = {
            "ok": True,
            "hero": {"id": "hero-1", "title": "Feature: Audio Mix"},
            "subcards": [
                {"lane": "code", "id": "code-1"},
                {"lane": "design", "id": "design-1"},
            ],
            "decks": {"hero": "Features", "code": "Code", "design": "Design", "art": None},
            "notes": ["Art lane auto-skipped (no --art-deck provided)."],
        }
        ns = argparse.Namespace(
            title="Audio Mix",
            hero_deck="Features",
            code_deck="Code",
            design_deck="Design",
            art_deck=None,
            skip_art=False,
            audio_deck=None,
            skip_audio=False,
            description=None,
            owner=None,
            priority=None,
            effort=None,
            format="json",
        )
        cmd_feature(ns)
        mock_client.scaffold_feature.assert_called_once()
        out = json.loads(capsys.readouterr().out)
        assert out["decks"]["art"] is None
        assert len(out["subcards"]) == 2

    @patch("codecks_cli.commands._get_client")
    def test_skip_art_creates_two_subcards(self, mock_get_client, capsys):
        mock_client = mock_get_client.return_value
        mock_client.scaffold_feature.return_value = {
            "ok": True,
            "hero": {"id": "hero-1", "title": "Feature: Economy Tuning"},
            "subcards": [
                {"lane": "code", "id": "code-1"},
                {"lane": "design", "id": "design-1"},
            ],
            "decks": {"hero": "Features", "code": "Code", "design": "Design", "art": None},
        }
        ns = argparse.Namespace(
            title="Economy Tuning",
            hero_deck="Features",
            code_deck="Code",
            design_deck="Design",
            art_deck=None,
            skip_art=True,
            audio_deck=None,
            skip_audio=False,
            description=None,
            owner=None,
            priority=None,
            effort=None,
            format="json",
        )
        cmd_feature(ns)
        out = json.loads(capsys.readouterr().out)
        assert len(out["subcards"]) == 2

    @patch("codecks_cli.commands._get_client")
    def test_rolls_back_on_partial_failure(self, mock_get_client):
        mock_client = mock_get_client.return_value
        mock_client.scaffold_feature.side_effect = CliError(
            "[ERROR] Feature scaffold failed: update failed\n"
            "[ERROR] Rollback archived 2/2 created cards."
        )
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

    @patch("codecks_cli.commands._get_client")
    def test_preserves_setup_error_during_rollback(self, mock_get_client):
        mock_client = mock_get_client.return_value
        mock_client.scaffold_feature.side_effect = SetupError(
            "[TOKEN_EXPIRED] expired\n[ERROR] Rollback archived 2/2 created cards."
        )
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

    @patch("codecks_cli.commands._get_client")
    def test_blocks_duplicate_feature_hero_by_default(self, mock_get_client):
        mock_client = mock_get_client.return_value
        mock_client.scaffold_feature.side_effect = CliError(
            "[ERROR] Duplicate feature hero title detected: 'Feature: Combat Revamp'.\n"
            "[ERROR] Re-run with --allow-duplicate to bypass this check."
        )
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

    @patch("codecks_cli.commands._get_client")
    def test_table_format_output(self, mock_get_client, capsys):
        mock_client = mock_get_client.return_value
        mock_client.scaffold_feature.return_value = {
            "ok": True,
            "hero": {"id": "hero-1", "title": "Feature: Test"},
            "subcards": [
                {"lane": "code", "id": "code-1"},
                {"lane": "design", "id": "design-1"},
            ],
            "decks": {"hero": "Features", "code": "Code", "design": "Design", "art": None},
        }
        ns = argparse.Namespace(
            title="Test",
            hero_deck="Features",
            code_deck="Code",
            design_deck="Design",
            art_deck=None,
            skip_art=True,
            description=None,
            owner=None,
            priority=None,
            effort=None,
            format="table",
        )
        cmd_feature(ns)
        out = capsys.readouterr().out
        assert "Hero created: hero-1" in out
        assert "Sub-cards created: 2" in out
        assert "[code] code-1" in out


# ---------------------------------------------------------------------------
# Hand sort order
# ---------------------------------------------------------------------------


class TestHandSortOrder:
    @patch("codecks_cli.commands._get_client")
    def test_hand_sorted_by_sort_index(self, mock_get_client, capsys):
        mock_client = mock_get_client.return_value
        mock_client.list_hand.return_value = [
            {"id": "c2", "title": "First", "status": "done"},
            {"id": "c3", "title": "Second", "status": "started"},
            {"id": "c1", "title": "Third", "status": "started"},
        ]
        ns = argparse.Namespace(card_ids=None, format="json")
        cmd_hand(ns)
        out = json.loads(capsys.readouterr().out)
        card_ids = [c["id"] for c in out["cards"]]
        assert card_ids == ["c2", "c3", "c1"]

    @patch("codecks_cli.commands._get_client")
    def test_hand_sort_handles_missing_sort_index(self, mock_get_client, capsys):
        mock_client = mock_get_client.return_value
        mock_client.list_hand.return_value = [
            {"id": "c2", "title": "A", "status": "done"},
            {"id": "c1", "title": "B", "status": "started"},
        ]
        ns = argparse.Namespace(card_ids=None, format="json")
        cmd_hand(ns)
        out = json.loads(capsys.readouterr().out)
        card_ids = [c["id"] for c in out["cards"]]
        assert card_ids == ["c2", "c1"]


# ---------------------------------------------------------------------------
# Hand empty
# ---------------------------------------------------------------------------


class TestHandEmptyReturns:
    """Critical fix #5: cmd_hand with empty hand should return, not sys.exit(0)."""

    @patch("codecks_cli.commands._get_client")
    def test_empty_hand_returns_without_exit(self, mock_get_client, capsys):
        mock_client = mock_get_client.return_value
        mock_client.list_hand.return_value = []
        ns = argparse.Namespace(card_ids=None, format="json")
        cmd_hand(ns)
        err = capsys.readouterr().err
        assert "empty" in err.lower()


# ---------------------------------------------------------------------------
# Deck card counts
# ---------------------------------------------------------------------------


class TestDeckCardCounts:
    @patch("codecks_cli.commands._get_client")
    def test_deck_counts_in_output(self, mock_get_client, capsys):
        mock_client = mock_get_client.return_value
        mock_client.list_decks.return_value = [
            {"id": "d1", "title": "Features", "project_name": "Tea Shop", "card_count": 2},
            {"id": "d2", "title": "Tasks", "project_name": "Tea Shop", "card_count": 1},
        ]
        ns = argparse.Namespace(format="json")
        cmd_decks(ns)
        out = json.loads(capsys.readouterr().out)
        assert len(out) == 2
        counts = {d["id"]: d["card_count"] for d in out}
        assert counts == {"d1": 2, "d2": 1}


# ---------------------------------------------------------------------------
# Dry-run mode
# ---------------------------------------------------------------------------


class TestDryRunMode:
    def test_create_skipped_in_dry_run(self, monkeypatch, capsys):
        monkeypatch.setattr(config, "RUNTIME_DRY_RUN", True)
        ns = argparse.Namespace(
            title="Test Card",
            content=None,
            severity=None,
            deck=None,
            project=None,
            doc=False,
            format="json",
            allow_duplicate=False,
        )
        cmd_create(ns)
        err = capsys.readouterr().err
        assert "[DRY-RUN]" in err
        assert "create card" in err

    def test_delete_skipped_in_dry_run(self, monkeypatch, capsys):
        monkeypatch.setattr(config, "RUNTIME_DRY_RUN", True)
        ns = argparse.Namespace(card_id="c1", confirm=True, format="json")
        cmd_delete(ns)
        err = capsys.readouterr().err
        assert "[DRY-RUN]" in err
        assert "delete card" in err


# ---------------------------------------------------------------------------
# Quiet mode — gdd-sync uses config.RUNTIME_QUIET
# ---------------------------------------------------------------------------


class TestGddSyncQuiet:
    @patch("codecks_cli.commands.sync_gdd")
    @patch("codecks_cli.commands.parse_gdd")
    @patch("codecks_cli.commands.fetch_gdd")
    def test_uses_config_quiet(self, mock_fetch, mock_parse, mock_sync, monkeypatch, capsys):
        monkeypatch.setattr(config, "RUNTIME_QUIET", True)
        mock_fetch.return_value = "# doc"
        mock_parse.return_value = [{"section": "A", "tasks": []}]
        mock_sync.return_value = {"applied": False, "quiet": True, "sections": []}
        ns = argparse.Namespace(
            project="Tea Shop",
            section=None,
            apply=False,
            refresh=False,
            file=None,
            save_cache=False,
            format="json",
        )
        cmd_gdd_sync(ns)
        _, kwargs = mock_sync.call_args
        assert kwargs["quiet"] is True


# ---------------------------------------------------------------------------
# Shell completion
# ---------------------------------------------------------------------------


class TestCompletion:
    def test_bash_output_contains_subcommands(self, capsys):
        ns = argparse.Namespace(shell="bash", format="json")
        cmd_completion(ns)
        out = capsys.readouterr().out
        assert "cards" in out
        assert "create" in out
        assert "codecks-cli" in out

    def test_zsh_output_contains_subcommands(self, capsys):
        ns = argparse.Namespace(shell="zsh", format="json")
        cmd_completion(ns)
        out = capsys.readouterr().out
        assert "cards" in out
        assert "create" in out
        assert "#compdef" in out


# ---------------------------------------------------------------------------
# split-features
# ---------------------------------------------------------------------------


class TestCmdSplitFeatures:
    @patch("codecks_cli.commands._get_client")
    def test_json_output(self, mock_get_client, capsys):
        mock_client = mock_get_client.return_value
        mock_client.split_features.return_value = {
            "ok": True,
            "features_processed": 2,
            "features_skipped": 1,
            "subcards_created": 4,
            "details": [
                {
                    "feature_id": "f1",
                    "feature_title": "Feature A",
                    "subcards": [
                        {"lane": "code", "id": "s1"},
                        {"lane": "design", "id": "s2"},
                    ],
                },
            ],
            "skipped": [{"id": "f2", "title": "Skip", "reason": "already has sub-cards"}],
        }
        ns = argparse.Namespace(
            deck="Features",
            code_deck="Coding",
            design_deck="Design",
            art_deck=None,
            skip_art=False,
            audio_deck=None,
            skip_audio=False,
            priority=None,
            dry_run=False,
            format="json",
        )
        cmd_split_features(ns)
        out = json.loads(capsys.readouterr().out)
        assert out["ok"] is True
        assert out["features_processed"] == 2

    @patch("codecks_cli.commands._get_client")
    def test_table_output(self, mock_get_client, capsys):
        mock_client = mock_get_client.return_value
        mock_client.split_features.return_value = {
            "ok": True,
            "features_processed": 1,
            "features_skipped": 0,
            "subcards_created": 2,
            "details": [
                {
                    "feature_id": "f1",
                    "feature_title": "Feature A",
                    "subcards": [
                        {"lane": "code", "id": "s1"},
                        {"lane": "design", "id": "s2"},
                    ],
                },
            ],
            "skipped": [],
        }
        ns = argparse.Namespace(
            deck="Features",
            code_deck="Coding",
            design_deck="Design",
            art_deck=None,
            skip_art=False,
            audio_deck=None,
            skip_audio=False,
            priority=None,
            dry_run=False,
            format="table",
        )
        cmd_split_features(ns)
        out = capsys.readouterr().out
        assert "Features processed: 1" in out
        assert "Sub-cards created: 2" in out
