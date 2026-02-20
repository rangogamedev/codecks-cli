"""Tests for cards.py — env mappings, filters, enrichment, stats, resolvers."""

import pytest
import config
from config import CliError
from cards import (
    _load_env_mapping, load_project_names, load_milestone_names,
    _filter_cards, compute_card_stats, enrich_cards,
    _build_project_map, get_project_deck_ids,
    resolve_deck_id, resolve_milestone_id,
)


# ---------------------------------------------------------------------------
# _load_env_mapping / load_project_names / load_milestone_names
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
        assert load_project_names() == {"p1": "Tea Shop"}
        assert load_milestone_names() == {"m1": "MVP"}


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
            "a": {"status": "done", "priority": "a", "effort": 3,
                   "deck_name": "Features"},
            "b": {"status": "done", "priority": "b", "effort": 5,
                   "deck_name": "Features"},
            "c": {"status": "started", "priority": "a", "effort": None,
                   "deck_name": "Tasks"},
        }
        stats = compute_card_stats(cards)
        assert stats["total"] == 3
        assert stats["total_effort"] == 8
        assert stats["avg_effort"] == 4.0
        assert stats["by_status"] == {"done": 2, "started": 1}
        assert stats["by_priority"] == {"a": 2, "b": 1}
        assert stats["by_deck"] == {"Features": 2, "Tasks": 1}

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
        monkeypatch.setattr(config, "env",
                            {"CODECKS_MILESTONES": "ms-1=MVP"})
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

    def testget_project_deck_ids_found(self, monkeypatch):
        monkeypatch.setattr(config, "env",
                            {"CODECKS_PROJECTS": "p1=Tea Shop"})
        decks = {"deck": {
            "dk1": {"id": "d1", "title": "Features", "projectId": "p1"},
        }}
        ids = get_project_deck_ids(decks, "Tea Shop")
        assert ids == {"d1"}

    def testget_project_deck_ids_case_insensitive(self, monkeypatch):
        monkeypatch.setattr(config, "env",
                            {"CODECKS_PROJECTS": "p1=Tea Shop"})
        decks = {"deck": {
            "dk1": {"id": "d1", "title": "Features", "projectId": "p1"},
        }}
        ids = get_project_deck_ids(decks, "tea shop")
        assert ids == {"d1"}

    def testget_project_deck_ids_not_found(self, monkeypatch):
        monkeypatch.setattr(config, "env", {"CODECKS_PROJECTS": "p1=Tea Shop"})
        decks = {"deck": {
            "dk1": {"id": "d1", "title": "Features", "projectId": "p1"},
        }}
        assert get_project_deck_ids(decks, "Nonexistent") is None


# ---------------------------------------------------------------------------
# resolve_deck_id / resolve_milestone_id
# ---------------------------------------------------------------------------

class TestResolvers:
    def testresolve_deck_id_found(self):
        config._cache["decks"] = {"deck": {
            "dk1": {"id": "d-id-1", "title": "Features"},
        }}
        assert resolve_deck_id("Features") == "d-id-1"

    def testresolve_deck_id_case_insensitive(self):
        config._cache["decks"] = {"deck": {
            "dk1": {"id": "d-id-1", "title": "Features"},
        }}
        assert resolve_deck_id("features") == "d-id-1"

    def testresolve_deck_id_not_found_exits(self):
        config._cache["decks"] = {"deck": {
            "dk1": {"id": "d-id-1", "title": "Features"},
        }}
        with pytest.raises(CliError) as exc_info:
            resolve_deck_id("Nonexistent")
        assert exc_info.value.exit_code == 1

    def testresolve_milestone_id_found(self, monkeypatch):
        monkeypatch.setattr(config, "env",
                            {"CODECKS_MILESTONES": "ms-1=MVP"})
        assert resolve_milestone_id("MVP") == "ms-1"

    def testresolve_milestone_id_case_insensitive(self, monkeypatch):
        monkeypatch.setattr(config, "env",
                            {"CODECKS_MILESTONES": "ms-1=MVP"})
        assert resolve_milestone_id("mvp") == "ms-1"

    def testresolve_milestone_id_not_found_exits(self, monkeypatch):
        monkeypatch.setattr(config, "env",
                            {"CODECKS_MILESTONES": "ms-1=MVP"})
        with pytest.raises(CliError) as exc_info:
            resolve_milestone_id("Nonexistent")
        assert exc_info.value.exit_code == 1
