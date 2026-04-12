"""Tests for _operations.py shared business logic.

Covers: tick_checkboxes (items mode), quick_overview, claims coordination.
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from codecks_cli._operations import (
    _load_claims,
    _save_claims,
    claim_card,
    quick_overview,
    release_card,
    tick_all_checkboxes,
    tick_checkboxes,
)


# ---------------------------------------------------------------------------
# tick_checkboxes (items mode)
# ---------------------------------------------------------------------------


class TestTickCheckboxesItems:
    """tick_checkboxes with explicit items list (not all=True)."""

    def _mock_client(self, content):
        client = MagicMock()
        client.get_card.return_value = {"content": content, "ok": True}
        client.update_cards.return_value = {"ok": True}
        return client

    def test_ticks_matching_item(self):
        client = self._mock_client("Title\n\n- [ ] Deploy to staging\n- [ ] Run tests")
        result = tick_checkboxes(client, "card-1", ["Deploy"])
        assert result["ok"] is True
        assert "Deploy" in result["ticked"]
        assert result["changed"] is True
        client.update_cards.assert_called_once()

    def test_case_insensitive_match(self):
        client = self._mock_client("Title\n\n- [ ] Run Tests")
        result = tick_checkboxes(client, "card-1", ["run tests"])
        assert "run tests" in result["ticked"]

    def test_already_checked_item(self):
        client = self._mock_client("Title\n\n- [x] Already done")
        result = tick_checkboxes(client, "card-1", ["Already done"])
        assert result["changed"] is False
        assert "Already done" in result["already_done"]
        client.update_cards.assert_not_called()

    def test_not_found_item(self):
        client = self._mock_client("Title\n\n- [ ] Task A")
        result = tick_checkboxes(client, "card-1", ["nonexistent"])
        assert "nonexistent" in result["not_found"]
        assert result["changed"] is False

    def test_untick_mode(self):
        client = self._mock_client("Title\n\n- [x] Task A")
        result = tick_checkboxes(client, "card-1", ["Task A"], untick=True)
        assert "Task A" in result["unticked"]
        assert result["changed"] is True

    def test_no_space_checkbox_format(self):
        """Matches both - [] and - [ ] formats."""
        client = self._mock_client("Title\n\n- [] Task A")
        result = tick_checkboxes(client, "card-1", ["Task A"])
        assert "Task A" in result["ticked"]

    def test_no_content_error(self):
        client = self._mock_client("")
        result = tick_checkboxes(client, "card-1", ["anything"])
        assert result["ok"] is False
        assert "NO_CONTENT" in result.get("error_code", "")


class TestTickAllCheckboxes:
    def test_all_already_checked(self):
        client = MagicMock()
        client.get_card.return_value = {"content": "Title\n\n- [x] A\n- [x] B", "ok": True}
        result = tick_all_checkboxes(client, "card-1")
        assert result["ok"] is True
        assert result["ticked_count"] == 0
        assert result["changed"] is False


# ---------------------------------------------------------------------------
# quick_overview
# ---------------------------------------------------------------------------


class TestQuickOverview:
    def _mock_client(self, cards):
        client = MagicMock()
        client.list_cards.return_value = {"cards": cards}
        return client

    def test_basic_counts(self):
        cards = [
            {"status": "started", "priority": "a", "effort": 3, "deck": "Code"},
            {"status": "done", "priority": "b", "effort": 5, "deck": "Code"},
            {"status": "started", "priority": "a", "deck": "Design"},
        ]
        result = quick_overview(self._mock_client(cards))
        assert result["ok"] is True
        assert result["total_cards"] == 3
        assert result["by_status"]["started"] == 2
        assert result["by_status"]["done"] == 1
        assert result["by_priority"]["a"] == 2
        assert result["effort_stats"]["total"] == 8
        assert result["effort_stats"]["estimated"] == 2
        assert result["effort_stats"]["unestimated"] == 1

    def test_project_filter(self):
        cards = [
            {"status": "started", "priority": "a", "project": "Tea Shop"},
            {"status": "started", "priority": "b", "project": "Business"},
        ]
        result = quick_overview(self._mock_client(cards), project="Tea Shop")
        assert result["total_cards"] == 1

    def test_stale_detection(self):
        cards = [
            {
                "status": "started",
                "priority": "a",
                "updated_at": "2020-01-01T00:00:00Z",
            },
            {
                "status": "done",
                "priority": "b",
                "updated_at": "2020-01-01T00:00:00Z",
            },
        ]
        result = quick_overview(self._mock_client(cards))
        # Only started card counts as stale (done cards are excluded)
        assert result["stale_count"] == 1

    def test_empty_cards(self):
        result = quick_overview(self._mock_client([]))
        assert result["total_cards"] == 0
        assert result["effort_stats"]["avg"] == 0.0

    def test_deck_summary_sorted(self):
        cards = [
            {"status": "started", "priority": "a", "deck": "Coding"},
            {"status": "started", "priority": "a", "deck": "Art"},
        ]
        result = quick_overview(self._mock_client(cards))
        names = [d["name"] for d in result["deck_summary"]]
        assert names == ["Art", "Coding"]


# ---------------------------------------------------------------------------
# Claims coordination
# ---------------------------------------------------------------------------


class TestClaims:
    """Claims use _PROJECT_ROOT from config — patch codecks_cli.config._PROJECT_ROOT."""

    def test_load_missing_file(self, tmp_path):
        with patch("codecks_cli.config._PROJECT_ROOT", str(tmp_path)):
            result = _load_claims()
        assert result == {}

    def test_save_and_load_roundtrip(self, tmp_path):
        claims = {"card-1": {"agent": "test", "claimed_at": "2026-01-01"}}
        with patch("codecks_cli.config._PROJECT_ROOT", str(tmp_path)):
            _save_claims(claims)
            loaded = _load_claims()
        assert loaded == claims

    def test_claim_success(self, tmp_path):
        with patch("codecks_cli.config._PROJECT_ROOT", str(tmp_path)):
            result = claim_card("card-1", "agent-a", reason="testing")
        assert result["ok"] is True
        assert result["agent_name"] == "agent-a"

    def test_claim_conflict(self, tmp_path):
        with patch("codecks_cli.config._PROJECT_ROOT", str(tmp_path)):
            claim_card("card-1", "agent-a")
            result = claim_card("card-1", "agent-b")
        assert result["ok"] is False
        assert result["conflict_agent"] == "agent-a"

    def test_claim_same_agent_ok(self, tmp_path):
        with patch("codecks_cli.config._PROJECT_ROOT", str(tmp_path)):
            claim_card("card-1", "agent-a")
            result = claim_card("card-1", "agent-a")
        assert result["ok"] is True

    def test_release_success(self, tmp_path):
        with patch("codecks_cli.config._PROJECT_ROOT", str(tmp_path)):
            claim_card("card-1", "agent-a")
            result = release_card("card-1", "agent-a", summary="done")
        assert result["ok"] is True

    def test_release_not_claimed(self, tmp_path):
        with patch("codecks_cli.config._PROJECT_ROOT", str(tmp_path)):
            result = release_card("card-1", "agent-a")
        assert result["ok"] is False

    def test_load_corrupt_json(self, tmp_path):
        claims_path = tmp_path / ".pm_claims.json"
        claims_path.write_text("not json{{{")
        with patch("codecks_cli.config._PROJECT_ROOT", str(tmp_path)):
            result = _load_claims()
        assert result == {}
