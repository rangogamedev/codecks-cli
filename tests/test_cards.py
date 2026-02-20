"""Tests for cards.py — env mappings, filters, enrichment, stats, resolvers."""

import pytest
import config
from cards import (
    _load_env_mapping, _load_project_names, _load_milestone_names,
    _filter_cards, _compute_card_stats, _enrich_cards,
    _build_project_map, _get_project_deck_ids,
    _resolve_deck_id, _resolve_milestone_id,
)


# ---------------------------------------------------------------------------
# _load_env_mapping / _load_project_names / _load_milestone_names
# ---------------------------------------------------------------------------

class TestLoadEnvMapping:
    def test_basic(self, monkeypatch):
        monkeypatch.setattr(config, "env",
                            {"MY_KEY": "id1=Alpha,id2=Beta"})
        assert _load_env_mapping("MY_KEY") == {"id1": "Alpha", "id2": "Beta"}

    def test_strips_whitespace(self, monkeypatch):
        monkeypatch.setattr(config, "env",
                            {"K": " id1 = Alpha , id2 = Beta "})
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
        monkeypatch.setattr(config, "env", {
            "CODECKS_PROJECTS": "p1=Tea Shop",
            "CODECKS_MILESTONES": "m1=MVP",
        })
        assert _load_project_names() == {"p1": "Tea Shop"}
        assert _load_milestone_names() == {"m1": "MVP"}


# ---------------------------------------------------------------------------
# _filter_cards
# ---------------------------------------------------------------------------

class TestFilterCards:
    def test_filters_by_predicate(self):
        result = {"card": {
            "a": {"status": "done"},
            "b": {"status": "started"},
            "c": {"status": "done"},
        }}
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
# _compute_card_stats
# ---------------------------------------------------------------------------

class TestComputeCardStats:
    def test_empty(self):
        stats = _compute_card_stats({})
        assert stats["total"] == 0
        assert stats["total_effort"] == 0
        assert stats["avg_effort"] == 0

    def test_basic_stats(self):
        cards = {
            "a": {"status": "done", "priority": "a", "effort": 3,
                   "deck_name": "Features"},
            "b": {"status": "done", "priority": "b", "effort": 5,
                   "deck_name": "Features"},
            "c": {"status": "started", "priority": "a", "effort": None,
                   "deck_name": "Tasks"},
        }
        stats = _compute_card_stats(cards)
        assert stats["total"] == 3
        assert stats["total_effort"] == 8
        assert stats["avg_effort"] == 4.0
        assert stats["by_status"] == {"done": 2, "started": 1}
        assert stats["by_priority"] == {"a": 2, "b": 1}
        assert stats["by_deck"] == {"Features": 2, "Tasks": 1}

    def test_none_priority_becomes_none_key(self):
        stats = _compute_card_stats({"a": {"status": "x", "priority": None}})
        assert stats["by_priority"] == {"none": 1}

    def test_effort_none_excluded_from_average(self):
        """Known bug regression: None effort shouldn't crash or skew average."""
        cards = {
            "a": {"status": "x", "effort": 10, "deck_name": "D"},
            "b": {"status": "x", "effort": None, "deck_name": "D"},
        }
        stats = _compute_card_stats(cards)
        assert stats["total_effort"] == 10
        assert stats["avg_effort"] == 10.0


# ---------------------------------------------------------------------------
# _enrich_cards
# ---------------------------------------------------------------------------

class TestEnrichCards:
    def setup_method(self):
        """Set up mock deck cache so _enrich_cards can resolve names."""
        config._cache["decks"] = {
            "deck": {
                "dk1": {"id": "deck-id-1", "title": "Features", "projectId": "p1"},
            }
        }

    def test_resolves_deck_name(self):
        cards = {"c1": {"deckId": "deck-id-1"}}
        result = _enrich_cards(cards)
        assert result["c1"]["deck_name"] == "Features"

    def test_resolves_owner_name(self):
        cards = {"c1": {"assignee": "user-1"}}
        user_data = {"user-1": {"name": "Thomas"}}
        result = _enrich_cards(cards, user_data)
        assert result["c1"]["owner_name"] == "Thomas"

    def test_normalizes_tags(self):
        cards = {"c1": {"masterTags": ["bug", "ui"]}}
        result = _enrich_cards(cards)
        assert result["c1"]["tags"] == ["bug", "ui"]

    def test_handles_missing_tags(self):
        cards = {"c1": {}}
        result = _enrich_cards(cards)
        assert result["c1"]["tags"] == []

    def test_resolves_milestone_name(self, monkeypatch):
        monkeypatch.setattr(config, "env",
                            {"CODECKS_MILESTONES": "ms-1=MVP"})
        cards = {"c1": {"milestoneId": "ms-1"}}
        result = _enrich_cards(cards)
        assert result["c1"]["milestone_name"] == "MVP"

    def test_child_card_info_dict(self):
        cards = {"c1": {"childCardInfo": {"count": 5}}}
        result = _enrich_cards(cards)
        assert result["c1"]["sub_card_count"] == 5

    def test_child_card_info_json_string(self):
        cards = {"c1": {"childCardInfo": '{"count": 3}'}}
        result = _enrich_cards(cards)
        assert result["c1"]["sub_card_count"] == 3


# ---------------------------------------------------------------------------
# _build_project_map / _get_project_deck_ids
# ---------------------------------------------------------------------------

class TestBuildProjectMap:
    def test_groups_by_project(self, monkeypatch):
        monkeypatch.setattr(config, "env",
                            {"CODECKS_PROJECTS": "p1=Tea Shop"})
        decks = {"deck": {
            "dk1": {"id": "d1", "title": "Features", "projectId": "p1"},
            "dk2": {"id": "d2", "title": "Tasks", "projectId": "p1"},
            "dk3": {"id": "d3", "title": "Other", "projectId": "p2"},
        }}
        result = _build_project_map(decks)
        assert result["p1"]["name"] == "Tea Shop"
        assert result["p1"]["deck_ids"] == {"d1", "d2"}
        assert result["p2"]["name"] == "p2"  # no env name -> falls back to ID

    def test_get_project_deck_ids_found(self, monkeypatch):
        monkeypatch.setattr(config, "env",
                            {"CODECKS_PROJECTS": "p1=Tea Shop"})
        decks = {"deck": {
            "dk1": {"id": "d1", "title": "Features", "projectId": "p1"},
        }}
        ids = _get_project_deck_ids(decks, "Tea Shop")
        assert ids == {"d1"}

    def test_get_project_deck_ids_case_insensitive(self, monkeypatch):
        monkeypatch.setattr(config, "env",
                            {"CODECKS_PROJECTS": "p1=Tea Shop"})
        decks = {"deck": {
            "dk1": {"id": "d1", "title": "Features", "projectId": "p1"},
        }}
        ids = _get_project_deck_ids(decks, "tea shop")
        assert ids == {"d1"}

    def test_get_project_deck_ids_not_found(self, monkeypatch):
        monkeypatch.setattr(config, "env", {"CODECKS_PROJECTS": "p1=Tea Shop"})
        decks = {"deck": {
            "dk1": {"id": "d1", "title": "Features", "projectId": "p1"},
        }}
        assert _get_project_deck_ids(decks, "Nonexistent") is None


# ---------------------------------------------------------------------------
# _resolve_deck_id / _resolve_milestone_id
# ---------------------------------------------------------------------------

class TestResolvers:
    def test_resolve_deck_id_found(self):
        config._cache["decks"] = {"deck": {
            "dk1": {"id": "d-id-1", "title": "Features"},
        }}
        assert _resolve_deck_id("Features") == "d-id-1"

    def test_resolve_deck_id_case_insensitive(self):
        config._cache["decks"] = {"deck": {
            "dk1": {"id": "d-id-1", "title": "Features"},
        }}
        assert _resolve_deck_id("features") == "d-id-1"

    def test_resolve_deck_id_not_found_exits(self):
        config._cache["decks"] = {"deck": {
            "dk1": {"id": "d-id-1", "title": "Features"},
        }}
        with pytest.raises(SystemExit) as exc_info:
            _resolve_deck_id("Nonexistent")
        assert exc_info.value.code == 1

    def test_resolve_milestone_id_found(self, monkeypatch):
        monkeypatch.setattr(config, "env",
                            {"CODECKS_MILESTONES": "ms-1=MVP"})
        assert _resolve_milestone_id("MVP") == "ms-1"

    def test_resolve_milestone_id_case_insensitive(self, monkeypatch):
        monkeypatch.setattr(config, "env",
                            {"CODECKS_MILESTONES": "ms-1=MVP"})
        assert _resolve_milestone_id("mvp") == "ms-1"

    def test_resolve_milestone_id_not_found_exits(self, monkeypatch):
        monkeypatch.setattr(config, "env",
                            {"CODECKS_MILESTONES": "ms-1=MVP"})
        with pytest.raises(SystemExit) as exc_info:
            _resolve_milestone_id("Nonexistent")
        assert exc_info.value.code == 1
