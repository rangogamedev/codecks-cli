"""Tests for cards.py — env mappings, filters, enrichment, stats, resolvers."""

from unittest.mock import patch

import pytest

from codecks_cli import config
from codecks_cli.cards import (
    _build_project_map,
    _filter_cards,
    _get_field,
    _load_env_mapping,
    _parse_date,
    _parse_iso_timestamp,
    _parse_multi_value,
    compute_card_stats,
    enrich_cards,
    get_project_deck_ids,
    load_milestone_names,
    load_project_names,
    resolve_deck_id,
    resolve_milestone_id,
)
from codecks_cli.config import CliError

# ---------------------------------------------------------------------------
# _load_env_mapping / load_project_names / load_milestone_names
# ---------------------------------------------------------------------------


class TestLoadEnvMapping:
    def test_basic(self, monkeypatch):
        monkeypatch.setattr(config, "env", {"MY_KEY": "id1=Alpha,id2=Beta"})
        assert _load_env_mapping("MY_KEY") == {"id1": "Alpha", "id2": "Beta"}

    def test_strips_whitespace(self, monkeypatch):
        monkeypatch.setattr(config, "env", {"K": " id1 = Alpha , id2 = Beta "})
        assert _load_env_mapping("K") == {"id1": "Alpha", "id2": "Beta"}

    def test_missing_key_returns_empty(self, monkeypatch):
        monkeypatch.setattr(config, "env", {})
        assert _load_env_mapping("MISSING") == {}

    def test_empty_value(self, monkeypatch):
        monkeypatch.setattr(config, "env", {"K": ""})
        assert _load_env_mapping("K") == {}

    def test_value_containing_equals(self, monkeypatch):
        """Value part can contain = (split on first only)."""
        monkeypatch.setattr(config, "env", {"K": "id1=Name=With=Equals"})
        assert _load_env_mapping("K") == {"id1": "Name=With=Equals"}

    def test_delegates_correctly(self, monkeypatch):
        monkeypatch.setattr(
            config,
            "env",
            {
                "CODECKS_PROJECTS": "p1=Tea Shop",
                "CODECKS_MILESTONES": "m1=MVP",
            },
        )
        assert load_project_names() == {"p1": "Tea Shop"}
        assert load_milestone_names() == {"m1": "MVP"}


class TestGetField:
    def test_prefers_snake_when_present(self):
        data = {"last_updated_at": "snake", "lastUpdatedAt": "camel"}
        assert _get_field(data, "last_updated_at", "lastUpdatedAt") == "snake"

    def test_uses_camel_when_snake_missing(self):
        data = {"lastUpdatedAt": "camel"}
        assert _get_field(data, "last_updated_at", "lastUpdatedAt") == "camel"

    def test_keeps_falsy_snake_value(self):
        data = {"is_closed": False, "isClosed": True}
        assert _get_field(data, "is_closed", "isClosed") is False


# ---------------------------------------------------------------------------
# _filter_cards
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# _parse_multi_value
# ---------------------------------------------------------------------------


class TestParseMultiValue:
    def test_single_value(self):
        result = _parse_multi_value("started", config.VALID_STATUSES, "status")
        assert result == ["started"]

    def test_multiple_values(self):
        result = _parse_multi_value("started,blocked", config.VALID_STATUSES, "status")
        assert result == ["started", "blocked"]

    def test_strips_whitespace(self):
        result = _parse_multi_value(" started , blocked ", config.VALID_STATUSES, "status")
        assert result == ["started", "blocked"]

    def test_invalid_value_raises(self):
        with pytest.raises(CliError) as exc_info:
            _parse_multi_value("started,invalid", config.VALID_STATUSES, "status")
        assert "Invalid status 'invalid'" in str(exc_info.value)

    def test_priority_values(self):
        result = _parse_multi_value("a,b", config.VALID_PRIORITIES, "priority")
        assert result == ["a", "b"]

    def test_priority_null(self):
        result = _parse_multi_value("null", config.VALID_PRIORITIES, "priority")
        assert result == ["null"]


class TestMultiValueFilter:
    """Multi-value --status and --priority filters."""

    @patch("codecks_cli.cards.query")
    def test_multi_status_client_side_filter(self, mock_query):
        mock_query.return_value = {
            "card": {
                "a": {"status": "done"},
                "b": {"status": "started"},
                "c": {"status": "blocked"},
                "d": {"status": "not_started"},
            },
            "user": {},
        }
        from codecks_cli.cards import list_cards

        result = list_cards(status_filter="started,blocked")
        assert set(result["card"].keys()) == {"b", "c"}

    @patch("codecks_cli.cards.query")
    def test_single_status_still_server_side(self, mock_query):
        mock_query.return_value = {
            "card": {
                "a": {"status": "done"},
            },
            "user": {},
        }
        from codecks_cli.cards import list_cards

        list_cards(status_filter="done")
        # Verify status was in the query (server-side)
        call_q = mock_query.call_args.args[0]
        # The query string should contain "done" in the card filter
        root_key = list(call_q["_root"][0]["account"][0].keys())[0]
        assert '"done"' in root_key

    @patch("codecks_cli.cards.query")
    def test_priority_filter_single(self, mock_query):
        mock_query.return_value = {
            "card": {
                "a": {"status": "done", "priority": "a"},
                "b": {"status": "started", "priority": "b"},
                "c": {"status": "done", "priority": None},
            },
            "user": {},
        }
        from codecks_cli.cards import list_cards

        result = list_cards(priority_filter="a")
        assert set(result["card"].keys()) == {"a"}

    @patch("codecks_cli.cards.query")
    def test_priority_filter_multi(self, mock_query):
        mock_query.return_value = {
            "card": {
                "a": {"status": "done", "priority": "a"},
                "b": {"status": "started", "priority": "b"},
                "c": {"status": "done", "priority": "c"},
            },
            "user": {},
        }
        from codecks_cli.cards import list_cards

        result = list_cards(priority_filter="a,b")
        assert set(result["card"].keys()) == {"a", "b"}

    @patch("codecks_cli.cards.query")
    def test_priority_filter_null(self, mock_query):
        mock_query.return_value = {
            "card": {
                "a": {"status": "done", "priority": "a"},
                "b": {"status": "started", "priority": None},
                "c": {"status": "done"},  # missing priority = None
            },
            "user": {},
        }
        from codecks_cli.cards import list_cards

        result = list_cards(priority_filter="null")
        assert set(result["card"].keys()) == {"b", "c"}

    @patch("codecks_cli.cards.query")
    def test_invalid_status_raises(self, mock_query):
        from codecks_cli.cards import list_cards

        with pytest.raises(CliError) as exc_info:
            list_cards(status_filter="started,oops")
        assert "Invalid status 'oops'" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Date parsing and filtering
# ---------------------------------------------------------------------------


class TestDateParsing:
    def test_parse_date_valid(self):
        dt = _parse_date("2026-01-15")
        assert dt.year == 2026
        assert dt.month == 1
        assert dt.day == 15

    def test_parse_date_invalid(self):
        with pytest.raises(CliError) as exc_info:
            _parse_date("not-a-date")
        assert "Invalid date" in str(exc_info.value)

    def test_parse_iso_timestamp(self):
        dt = _parse_iso_timestamp("2026-01-15T10:30:00Z")
        assert dt.year == 2026
        assert dt.month == 1
        assert dt.hour == 10

    def test_parse_iso_timestamp_with_millis(self):
        dt = _parse_iso_timestamp("2026-01-15T10:30:00.123Z")
        assert dt is not None
        assert dt.day == 15

    def test_parse_iso_timestamp_none(self):
        assert _parse_iso_timestamp(None) is None
        assert _parse_iso_timestamp("") is None

    def test_parse_iso_timestamp_invalid(self):
        assert _parse_iso_timestamp("not-a-timestamp") is None


class TestDateFiltering:
    @patch("codecks_cli.cards.query")
    def test_stale_days_filter(self, mock_query):
        """--stale 30 should find cards not updated in 30 days."""
        mock_query.return_value = {
            "card": {
                "old": {"status": "started", "lastUpdatedAt": "2025-01-01T00:00:00Z"},
                "recent": {"status": "started", "lastUpdatedAt": "2026-02-19T00:00:00Z"},
            },
            "user": {},
        }
        from codecks_cli.cards import list_cards

        result = list_cards(stale_days=30)
        assert "old" in result["card"]
        assert "recent" not in result["card"]

    @patch("codecks_cli.cards.query")
    def test_updated_after_filter(self, mock_query):
        mock_query.return_value = {
            "card": {
                "old": {"status": "done", "lastUpdatedAt": "2025-12-01T00:00:00Z"},
                "new": {"status": "done", "lastUpdatedAt": "2026-02-01T00:00:00Z"},
            },
            "user": {},
        }
        from codecks_cli.cards import list_cards

        result = list_cards(updated_after="2026-01-15")
        assert "new" in result["card"]
        assert "old" not in result["card"]

    @patch("codecks_cli.cards.query")
    def test_updated_before_filter(self, mock_query):
        mock_query.return_value = {
            "card": {
                "old": {"status": "done", "lastUpdatedAt": "2025-12-01T00:00:00Z"},
                "new": {"status": "done", "lastUpdatedAt": "2026-02-01T00:00:00Z"},
            },
            "user": {},
        }
        from codecks_cli.cards import list_cards

        result = list_cards(updated_before="2026-01-15")
        assert "old" in result["card"]
        assert "new" not in result["card"]

    @patch("codecks_cli.cards.query")
    def test_stale_handles_missing_timestamp(self, mock_query):
        """Critical fix #6: Cards with no lastUpdatedAt are excluded from date filters."""
        mock_query.return_value = {
            "card": {
                "no_ts": {"status": "started"},
            },
            "user": {},
        }
        from codecks_cli.cards import list_cards

        result = list_cards(stale_days=30)
        # No timestamp → excluded (not falsely treated as stale)
        assert len(result["card"]) == 0

    @patch("codecks_cli.cards.query")
    def test_updated_after_excludes_missing_timestamp(self, mock_query):
        """Critical fix #6: Cards with no timestamp excluded from --updated-after."""
        mock_query.return_value = {
            "card": {
                "has_ts": {"status": "done", "lastUpdatedAt": "2026-02-01T00:00:00Z"},
                "no_ts": {"status": "done"},
            },
            "user": {},
        }
        from codecks_cli.cards import list_cards

        result = list_cards(updated_after="2026-01-15")
        assert "has_ts" in result["card"]
        assert "no_ts" not in result["card"]

    @patch("codecks_cli.cards.query")
    def test_updated_before_excludes_missing_timestamp(self, mock_query):
        """Critical fix #6: Cards with no timestamp excluded from --updated-before."""
        mock_query.return_value = {
            "card": {
                "has_ts": {"status": "done", "lastUpdatedAt": "2025-12-01T00:00:00Z"},
                "no_ts": {"status": "done"},
            },
            "user": {},
        }
        from codecks_cli.cards import list_cards

        result = list_cards(updated_before="2026-01-15")
        assert "has_ts" in result["card"]
        assert "no_ts" not in result["card"]


# ---------------------------------------------------------------------------
# _filter_cards
# ---------------------------------------------------------------------------


class TestFilterCards:
    def test_filters_by_predicate(self):
        result = {
            "card": {
                "a": {"status": "done"},
                "b": {"status": "started"},
                "c": {"status": "done"},
            }
        }
        _filter_cards(result, lambda k, c: c["status"] == "done")
        assert set(result["card"].keys()) == {"a", "c"}

    def test_empty_cards(self):
        result = {"card": {}}
        _filter_cards(result, lambda k, c: True)
        assert result["card"] == {}

    def test_missing_card_key(self):
        result = {}
        _filter_cards(result, lambda k, c: True)
        assert result["card"] == {}

    def test_returns_result(self):
        result = {"card": {"a": {}}}
        ret = _filter_cards(result, lambda k, c: True)
        assert ret is result


# ---------------------------------------------------------------------------
# compute_card_stats
# ---------------------------------------------------------------------------


class TestComputeCardStats:
    def test_empty(self):
        stats = compute_card_stats({})
        assert stats["total"] == 0
        assert stats["total_effort"] == 0
        assert stats["avg_effort"] == 0

    def test_basic_stats(self):
        cards = {
            "a": {
                "status": "done",
                "priority": "a",
                "effort": 3,
                "deck_name": "Features",
                "owner_name": "Alice",
            },
            "b": {
                "status": "done",
                "priority": "b",
                "effort": 5,
                "deck_name": "Features",
                "owner_name": "Alice",
            },
            "c": {"status": "started", "priority": "a", "effort": None, "deck_name": "Tasks"},
        }
        stats = compute_card_stats(cards)
        assert stats["total"] == 3
        assert stats["total_effort"] == 8
        assert stats["avg_effort"] == 4.0
        assert stats["by_status"] == {"done": 2, "started": 1}
        assert stats["by_priority"] == {"a": 2, "b": 1}
        assert stats["by_deck"] == {"Features": 2, "Tasks": 1}
        assert stats["by_owner"] == {"Alice": 2, "unassigned": 1}

    def test_none_priority_becomes_none_key(self):
        stats = compute_card_stats({"a": {"status": "x", "priority": None}})
        assert stats["by_priority"] == {"none": 1}

    def test_effort_none_excluded_from_average(self):
        """Known bug regression: None effort shouldn't crash or skew average."""
        cards = {
            "a": {"status": "x", "effort": 10, "deck_name": "D"},
            "b": {"status": "x", "effort": None, "deck_name": "D"},
        }
        stats = compute_card_stats(cards)
        assert stats["total_effort"] == 10
        assert stats["avg_effort"] == 10.0


# ---------------------------------------------------------------------------
# enrich_cards
# ---------------------------------------------------------------------------


class TestEnrichCards:
    def setup_method(self):
        """Set up mock deck cache so enrich_cards can resolve names."""
        config._cache["decks"] = {
            "deck": {
                "dk1": {"id": "deck-id-1", "title": "Features", "projectId": "p1"},
            }
        }

    def test_resolves_deck_name(self):
        cards = {"c1": {"deckId": "deck-id-1"}}
        result = enrich_cards(cards)
        assert result["c1"]["deck_name"] == "Features"

    def test_resolves_owner_name(self):
        cards = {"c1": {"assignee": "user-1"}}
        user_data = {"user-1": {"name": "Thomas"}}
        result = enrich_cards(cards, user_data)
        assert result["c1"]["owner_name"] == "Thomas"

    def test_normalizes_tags(self):
        cards = {"c1": {"masterTags": ["bug", "ui"]}}
        result = enrich_cards(cards)
        assert result["c1"]["tags"] == ["bug", "ui"]

    def test_handles_missing_tags(self):
        cards = {"c1": {}}
        result = enrich_cards(cards)
        assert result["c1"]["tags"] == []

    def test_resolves_milestone_name(self, monkeypatch):
        monkeypatch.setattr(config, "env", {"CODECKS_MILESTONES": "ms-1=MVP"})
        cards = {"c1": {"milestoneId": "ms-1"}}
        result = enrich_cards(cards)
        assert result["c1"]["milestone_name"] == "MVP"

    def test_child_card_info_dict(self):
        cards = {"c1": {"childCardInfo": {"count": 5}}}
        result = enrich_cards(cards)
        assert result["c1"]["sub_card_count"] == 5

    def test_child_card_info_json_string(self):
        cards = {"c1": {"childCardInfo": '{"count": 3}'}}
        result = enrich_cards(cards)
        assert result["c1"]["sub_card_count"] == 3


# ---------------------------------------------------------------------------
# _build_project_map / get_project_deck_ids
# ---------------------------------------------------------------------------


class TestBuildProjectMap:
    def test_groups_by_project(self, monkeypatch):
        monkeypatch.setattr(config, "env", {"CODECKS_PROJECTS": "p1=Tea Shop"})
        decks = {
            "deck": {
                "dk1": {"id": "d1", "title": "Features", "projectId": "p1"},
                "dk2": {"id": "d2", "title": "Tasks", "projectId": "p1"},
                "dk3": {"id": "d3", "title": "Other", "projectId": "p2"},
            }
        }
        result = _build_project_map(decks)
        assert result["p1"]["name"] == "Tea Shop"
        assert result["p1"]["deck_ids"] == {"d1", "d2"}
        assert result["p2"]["name"] == "p2"  # no env name -> falls back to ID

    def testget_project_deck_ids_found(self, monkeypatch):
        monkeypatch.setattr(config, "env", {"CODECKS_PROJECTS": "p1=Tea Shop"})
        decks = {
            "deck": {
                "dk1": {"id": "d1", "title": "Features", "projectId": "p1"},
            }
        }
        ids = get_project_deck_ids(decks, "Tea Shop")
        assert ids == {"d1"}

    def testget_project_deck_ids_case_insensitive(self, monkeypatch):
        monkeypatch.setattr(config, "env", {"CODECKS_PROJECTS": "p1=Tea Shop"})
        decks = {
            "deck": {
                "dk1": {"id": "d1", "title": "Features", "projectId": "p1"},
            }
        }
        ids = get_project_deck_ids(decks, "tea shop")
        assert ids == {"d1"}

    def testget_project_deck_ids_not_found(self, monkeypatch):
        monkeypatch.setattr(config, "env", {"CODECKS_PROJECTS": "p1=Tea Shop"})
        decks = {
            "deck": {
                "dk1": {"id": "d1", "title": "Features", "projectId": "p1"},
            }
        }
        assert get_project_deck_ids(decks, "Nonexistent") is None


# ---------------------------------------------------------------------------
# resolve_deck_id / resolve_milestone_id
# ---------------------------------------------------------------------------


class TestResolvers:
    def testresolve_deck_id_found(self):
        config._cache["decks"] = {
            "deck": {
                "dk1": {"id": "d-id-1", "title": "Features"},
            }
        }
        assert resolve_deck_id("Features") == "d-id-1"

    def testresolve_deck_id_case_insensitive(self):
        config._cache["decks"] = {
            "deck": {
                "dk1": {"id": "d-id-1", "title": "Features"},
            }
        }
        assert resolve_deck_id("features") == "d-id-1"

    def testresolve_deck_id_not_found_exits(self):
        config._cache["decks"] = {
            "deck": {
                "dk1": {"id": "d-id-1", "title": "Features"},
            }
        }
        with pytest.raises(CliError) as exc_info:
            resolve_deck_id("Nonexistent")
        assert exc_info.value.exit_code == 1

    def testresolve_milestone_id_found(self, monkeypatch):
        monkeypatch.setattr(config, "env", {"CODECKS_MILESTONES": "ms-1=MVP"})
        assert resolve_milestone_id("MVP") == "ms-1"

    def testresolve_milestone_id_case_insensitive(self, monkeypatch):
        monkeypatch.setattr(config, "env", {"CODECKS_MILESTONES": "ms-1=MVP"})
        assert resolve_milestone_id("mvp") == "ms-1"

    def testresolve_milestone_id_not_found_exits(self, monkeypatch):
        monkeypatch.setattr(config, "env", {"CODECKS_MILESTONES": "ms-1=MVP"})
        with pytest.raises(CliError) as exc_info:
            resolve_milestone_id("Nonexistent")
        assert exc_info.value.exit_code == 1
