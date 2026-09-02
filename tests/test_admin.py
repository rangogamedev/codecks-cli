"""Tests for admin.py dispatch operations (deck creation, cache seeding)."""

from unittest.mock import patch

from codecks_cli import config
from codecks_cli.admin import create_deck

_PID = "project-1"


def _caching_list_decks(decks):
    """Mimic cards.list_decks(): populate config._cache["decks"] and return it."""

    result = {"deck": dict(decks)}

    def _call():
        config._cache["decks"] = result
        return result

    return _call


class TestCreateDeckExistingCheck:
    """The duplicate check must read the deck's project id in either spelling."""

    @patch("codecks_cli.admin.api.dispatch")
    @patch("codecks_cli.cards.list_decks")
    @patch("codecks_cli.admin._resolve_project_id", return_value=_PID)
    def test_detects_existing_deck_snake_case_project_id(self, _pid, mock_decks, mock_dispatch):
        mock_decks.return_value = {
            "deck": {"d-1": {"id": "d-1", "title": "Code", "project_id": _PID}}
        }
        result = create_deck("code", project="Tea Shop")
        assert result["ok"] is True
        assert result["already_existed"] is True
        assert result["deck_id"] == "d-1"
        mock_dispatch.assert_not_called()

    @patch("codecks_cli.admin.api.dispatch")
    @patch("codecks_cli.cards.list_decks")
    @patch("codecks_cli.admin._resolve_project_id", return_value=_PID)
    def test_detects_existing_deck_camel_case_project_id(self, _pid, mock_decks, mock_dispatch):
        mock_decks.return_value = {
            "deck": {"d-1": {"id": "d-1", "title": "Code", "projectId": _PID}}
        }
        result = create_deck("Code", project="Tea Shop")
        assert result["already_existed"] is True
        mock_dispatch.assert_not_called()

    @patch("codecks_cli.admin.api.dispatch")
    @patch("codecks_cli.cards.list_decks")
    @patch("codecks_cli.admin._resolve_project_id", return_value=_PID)
    def test_same_name_other_project_still_creates(self, _pid, mock_decks, mock_dispatch):
        mock_decks.return_value = {
            "deck": {"d-1": {"id": "d-1", "title": "Code", "project_id": "other-project"}}
        }
        mock_dispatch.return_value = {"payload": {"id": "d-new"}}
        result = create_deck("Code", project="Tea Shop")
        assert result["already_existed"] is False
        mock_dispatch.assert_called_once()


class TestCreateDeckCacheSeeding:
    """A freshly created deck must land in the deck cache, not be popped away."""

    @patch("codecks_cli.admin.api.dispatch")
    @patch("codecks_cli.cards.list_decks")
    @patch("codecks_cli.admin._resolve_project_id", return_value=_PID)
    def test_new_deck_seeded_into_cache(self, _pid, mock_decks, mock_dispatch):
        mock_decks.side_effect = _caching_list_decks(
            {"d-1": {"id": "d-1", "title": "Code", "projectId": _PID}}
        )
        mock_dispatch.return_value = {"payload": {"id": "d-new"}}

        result = create_deck("Audio", project="Tea Shop")

        assert result["ok"] is True
        assert result["deck_id"] == "d-new"
        seeded = config._cache["decks"]["deck"]["d-new"]
        assert seeded == {"id": "d-new", "title": "Audio", "projectId": _PID}
        # Pre-existing decks survive the seed.
        assert "d-1" in config._cache["decks"]["deck"]

    @patch("codecks_cli.admin.api.dispatch")
    @patch("codecks_cli.cards.list_decks")
    @patch("codecks_cli.admin._resolve_project_id", return_value=_PID)
    def test_resolve_deck_id_finds_new_deck_immediately(self, _pid, mock_decks, mock_dispatch):
        from codecks_cli.cards import resolve_deck_id

        mock_decks.side_effect = _caching_list_decks({})
        mock_dispatch.return_value = {"payload": {"id": "d-new"}}

        create_deck("Audio", project="Tea Shop")

        # resolve_deck_id goes through the real list_decks(), which returns the
        # seeded config._cache["decks"] without another API round-trip.
        assert resolve_deck_id("Audio") == "d-new"

    @patch("codecks_cli.admin.api.dispatch")
    @patch("codecks_cli.cards.list_decks")
    @patch("codecks_cli.admin._resolve_project_id", return_value=_PID)
    def test_seeds_even_when_cache_absent(self, _pid, mock_decks, mock_dispatch):
        mock_decks.return_value = {"deck": {}}  # does not populate the cache
        config._cache.pop("decks", None)
        mock_dispatch.return_value = {"payload": {"id": "d-new"}}

        create_deck("Audio", project="Tea Shop")

        assert config._cache["decks"]["deck"]["d-new"]["title"] == "Audio"

    @patch("codecks_cli.admin.api.dispatch")
    @patch("codecks_cli.cards.list_decks")
    @patch("codecks_cli.admin._resolve_project_id", return_value=_PID)
    def test_missing_deck_id_invalidates_cache(self, _pid, mock_decks, mock_dispatch):
        mock_decks.side_effect = _caching_list_decks(
            {"d-1": {"id": "d-1", "title": "Code", "projectId": _PID}}
        )
        mock_dispatch.return_value = {"payload": {}}

        result = create_deck("Audio", project="Tea Shop")

        assert result["ok"] is True
        assert "decks" not in config._cache
