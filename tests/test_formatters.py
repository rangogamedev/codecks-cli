"""Tests for formatters.py — _table, _trunc, output formatters."""

import json
import pytest
import config
from formatters import (
    _table, _trunc, mutation_response, format_account_table,
    format_cards_table, format_card_detail, format_stats_table,
    format_decks_table, format_projects_table, format_milestones_table,
    format_gdd_table, format_cards_csv, format_activity_diff,
    resolve_activity_val, output,
)


# ---------------------------------------------------------------------------
# _trunc
# ---------------------------------------------------------------------------

class TestTrunc:
    def test_short_string_unchanged(self):
        assert _trunc("hello", 10) == "hello"

    def test_exact_length(self):
        assert _trunc("hello", 5) == "hello"

    def test_truncates_with_ellipsis(self):
        result = _trunc("hello world", 6)
        assert result == "hello\u2026"
        assert len(result) == 6

    def test_empty_string(self):
        assert _trunc("", 10) == ""

    def test_none(self):
        assert _trunc(None, 10) == ""


# ---------------------------------------------------------------------------
# _table
# ---------------------------------------------------------------------------

class TestTable:
    def test_basic_table(self):
        cols = [("Name", 10), ("Value", 0)]
        rows = [("Alice", "100"), ("Bob", "200")]
        result = _table(cols, rows)
        lines = result.split("\n")
        assert "Name" in lines[0]
        assert "Value" in lines[0]
        assert lines[1].startswith("---")
        assert "Alice" in lines[2]
        assert "Bob" in lines[3]

    def test_footer(self):
        cols = [("A", 5), ("B", 0)]
        rows = [("1", "2")]
        result = _table(cols, rows, footer="Total: 1")
        assert "Total: 1" in result

    def test_empty_rows(self):
        cols = [("A", 5), ("B", 0)]
        result = _table(cols, [])
        lines = result.split("\n")
        assert len(lines) == 2  # header + separator only

    def test_column_widths(self):
        cols = [("X", 10), ("Y", 0)]
        rows = [("hi", "there")]
        result = _table(cols, rows)
        data_line = result.split("\n")[2]
        # "hi" should be padded to width 10
        assert data_line.startswith("hi        ")


# ---------------------------------------------------------------------------
# format_account_table
# ---------------------------------------------------------------------------

class TestFormatAccountTable:
    def test_formats_account(self):
        result = format_account_table({
            "account": {"acc-id-123": {"name": "MyAccount"}}
        })
        assert "MyAccount" in result
        assert "acc-id-123" in result

    def test_no_account_data(self):
        assert "No account" in format_account_table({})
        assert "No account" in format_account_table({"account": {}})


# ---------------------------------------------------------------------------
# format_cards_table
# ---------------------------------------------------------------------------

class TestFormatCardsTable:
    def test_formats_cards(self):
        result = format_cards_table({"card": {
            "c1": {"status": "done", "priority": "a", "effort": 3,
                   "title": "Test Card", "deck_name": "Features",
                   "owner_name": "Thomas", "tags": ["bug"]},
        }})
        assert "done" in result
        assert "high" in result  # PRI_LABELS["a"]
        assert "Test Card" in result
        assert "Features" in result
        assert "bug" in result
        assert "Total: 1 cards" in result

    def test_no_cards(self):
        assert "No cards" in format_cards_table({"card": {}})
        assert "No cards" in format_cards_table({})

    def test_sub_card_count_shown(self):
        result = format_cards_table({"card": {
            "c1": {"title": "Hero", "sub_card_count": 5, "status": "started"},
        }})
        assert "[5 sub]" in result


# ---------------------------------------------------------------------------
# format_card_detail
# ---------------------------------------------------------------------------

class TestFormatCardDetail:
    def test_full_card_detail(self):
        result = format_card_detail({"card": {
            "c1": {
                "title": "Test Card", "status": "started",
                "priority": "b", "effort": 5,
                "deck_name": "Features", "owner_name": "Thomas",
                "milestone_name": "MVP", "tags": ["ui"],
                "in_hand": True, "createdAt": "2026-01-01T00:00:00Z",
                "lastUpdatedAt": "2026-01-02T00:00:00Z",
                "content": "Test Card\nSome description here",
            },
        }})
        assert "Test Card" in result
        assert "started" in result
        assert "b (med)" in result
        assert "Features" in result
        assert "Thomas" in result
        assert "MVP" in result
        assert "ui" in result
        assert "yes" in result  # in_hand
        assert "Some description" in result

    def test_card_not_found(self):
        assert "not found" in format_card_detail({"card": {}})


# ---------------------------------------------------------------------------
# format_stats_table
# ---------------------------------------------------------------------------

class TestFormatStatsTable:
    def test_formats_stats(self):
        stats = {
            "total": 10, "total_effort": 50, "avg_effort": 5.0,
            "by_status": {"done": 7, "started": 3},
            "by_priority": {"a": 5, "none": 5},
            "by_deck": {"Features": 10},
        }
        result = format_stats_table(stats)
        assert "Total cards: 10" in result
        assert "Total effort: 50" in result
        assert "Avg effort: 5.0" in result
        assert "done" in result
        assert "Features" in result


# ---------------------------------------------------------------------------
# format_decks_table
# ---------------------------------------------------------------------------

class TestFormatDecksTable:
    def test_formats_decks(self, monkeypatch):
        monkeypatch.setattr(config, "env",
                            {"CODECKS_PROJECTS": "p1=Tea Shop"})
        result = format_decks_table({"deck": {
            "dk1": {"id": "d1", "title": "Features", "projectId": "p1"},
        }})
        assert "Features" in result
        assert "Tea Shop" in result

    def test_no_decks(self):
        assert "No decks" in format_decks_table({"deck": {}})


# ---------------------------------------------------------------------------
# format_gdd_table
# ---------------------------------------------------------------------------

class TestFormatGddTable:
    def test_formats_sections(self):
        sections = [
            {"section": "Gameplay", "tasks": [
                {"title": "Player Movement", "priority": "a", "effort": 5},
                {"title": "Combat System", "priority": None, "effort": None},
            ]},
        ]
        result = format_gdd_table(sections)
        assert "Gameplay" in result
        assert "Player Movement" in result
        assert "Combat System" in result
        assert "Total: 2 tasks" in result

    def test_empty_sections(self):
        assert "No tasks" in format_gdd_table([])


# ---------------------------------------------------------------------------
# format_cards_csv
# ---------------------------------------------------------------------------

class TestFormatCardsCsv:
    def test_csv_output(self):
        result = format_cards_csv({"card": {
            "c1": {"status": "done", "priority": "a", "effort": 3,
                   "title": "Test Card", "deck_name": "Features",
                   "owner_name": "Thomas", "tags": ["bug", "ui"]},
        }})
        lines = [l.rstrip("\r") for l in result.strip().split("\n")]
        assert lines[0] == "status,priority,effort,deck,owner,title,tags,id"
        assert "done" in lines[1]
        assert "high" in lines[1]
        assert "Test Card" in lines[1]
        assert '"bug, ui"' in lines[1]


# ---------------------------------------------------------------------------
# resolve_activity_val / format_activity_diff
# ---------------------------------------------------------------------------

class TestActivityHelpers:
    def test_resolve_priority(self):
        assert resolve_activity_val("priority", "a", {}, {}) == "high"
        assert resolve_activity_val("priority", "b", {}, {}) == "med"

    def test_resolve_milestone(self):
        ms = {"ms-1": "MVP"}
        assert resolve_activity_val("milestoneId", "ms-1", ms, {}) == "MVP"

    def test_resolve_assignee(self):
        users = {"u-1": "Thomas"}
        assert resolve_activity_val("assigneeId", "u-1", {}, users) == "Thomas"

    def test_resolve_none(self):
        assert resolve_activity_val("status", None, {}, {}) == "none"

    def test_format_diff_status_change(self):
        diff = {"status": ["not_started", "done"]}
        result = format_activity_diff(diff, {}, {})
        assert "status: not_started -> done" in result

    def test_format_diff_priority_change(self):
        diff = {"priority": [None, "a"]}
        result = format_activity_diff(diff, {}, {})
        assert "none -> high" in result

    def test_format_diff_tags(self):
        diff = {"masterTags": {"+": ["bug"], "-": ["wip"]}}
        result = format_activity_diff(diff, {}, {})
        assert "tags +[bug]" in result
        assert "tags -[wip]" in result

    def test_format_diff_skips_tags_field(self):
        diff = {"tags": {"+": ["should-skip"]}}
        result = format_activity_diff(diff, {}, {})
        assert "should-skip" not in result

    def test_format_empty_diff(self):
        assert format_activity_diff({}, {}, {}) == ""
        assert format_activity_diff(None, {}, {}) == ""


# ---------------------------------------------------------------------------
# mutation_response
# ---------------------------------------------------------------------------

class TestMutationResponse:
    def test_basic_output(self, capsys):
        mutation_response("Created", "card-1", "title='Test'")
        out = capsys.readouterr().out
        assert "OK: Created: card card-1: title='Test'" in out

    def test_no_card_id(self, capsys):
        mutation_response("Updated", details="3 card(s)")
        out = capsys.readouterr().out
        assert "OK: Updated: 3 card(s)" in out

    def test_suppresses_empty_dispatch_data(self, capsys):
        mutation_response("Updated", "c1", "status=done",
                           {"payload": None, "actionId": "abc"}, fmt="json")
        out = capsys.readouterr().out
        # Should only have the OK line, not the JSON dump
        assert "OK:" in out
        assert '"actionId"' not in out


# ---------------------------------------------------------------------------
# output dispatcher
# ---------------------------------------------------------------------------

class TestOutput:
    def test_json_output(self, capsys):
        output({"key": "val"})
        out = capsys.readouterr().out
        assert json.loads(out) == {"key": "val"}

    def test_table_output(self, capsys):
        output({"data": 1}, formatter=lambda d: "TABLE", fmt="table")
        assert "TABLE" in capsys.readouterr().out

    def test_csv_output(self, capsys):
        output({"data": 1}, csv_formatter=lambda d: "CSV", fmt="csv")
        assert "CSV" in capsys.readouterr().out

    def test_json_fallback_when_no_formatter(self, capsys):
        output({"data": 1}, fmt="table")
        out = capsys.readouterr().out
        assert '"data": 1' in out
