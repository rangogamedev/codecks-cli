"""Tests for formatters.py — _table, _trunc, output formatters."""

import json

from codecks_cli import config
from codecks_cli.formatters import (
    _sanitize_str,
    _table,
    _trunc,
    format_account_table,
    format_activity_diff,
    format_card_detail,
    format_cards_csv,
    format_cards_table,
    format_conversations_table,
    format_decks_table,
    format_gdd_table,
    format_milestones_table,
    format_pm_focus_table,
    format_projects_table,
    format_standup_table,
    format_stats_table,
    mutation_response,
    output,
    resolve_activity_val,
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
        result = format_account_table({"account": {"acc-id-123": {"name": "MyAccount"}}})
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
        result = format_cards_table(
            {
                "cards": [
                    {
                        "id": "c1",
                        "status": "done",
                        "priority": "a",
                        "effort": 3,
                        "title": "Test Card",
                        "deck_name": "Features",
                        "milestone_name": "MVP",
                        "owner_name": "Thomas",
                        "tags": ["bug"],
                    },
                ],
                "stats": None,
            }
        )
        assert "done" in result
        assert "high" in result  # PRI_LABELS["a"]
        assert "Test Card" in result
        assert "Features" in result
        assert "MVP" in result
        assert "Mstone" in result  # column header
        assert "bug" in result
        assert "Total: 1 cards" in result

    def test_no_cards(self):
        assert "No cards" in format_cards_table({"cards": [], "stats": None})
        assert "No cards" in format_cards_table({})

    def test_sub_card_count_shown(self):
        result = format_cards_table(
            {
                "cards": [
                    {"id": "c1", "title": "Hero", "sub_card_count": 5, "status": "started"},
                ],
                "stats": None,
            }
        )
        assert "[5 sub]" in result


# ---------------------------------------------------------------------------
# format_card_detail
# ---------------------------------------------------------------------------


class TestFormatCardDetail:
    def test_full_card_detail(self):
        result = format_card_detail(
            {
                "id": "c1",
                "title": "Test Card",
                "status": "started",
                "priority": "b",
                "effort": 5,
                "severity": "high",
                "deck_name": "Features",
                "owner_name": "Thomas",
                "milestone_name": "MVP",
                "tags": ["ui"],
                "parentCardId": "hero-uuid-123",
                "in_hand": True,
                "createdAt": "2026-01-01T00:00:00Z",
                "lastUpdatedAt": "2026-01-02T00:00:00Z",
                "content": "Test Card\nSome description here",
            }
        )
        assert "Test Card" in result
        assert "started" in result
        assert "b (med)" in result
        assert "Severity:  high" in result
        assert "Features" in result
        assert "Thomas" in result
        assert "MVP" in result
        assert "ui" in result
        assert "Hero:      hero-uuid-123" in result
        assert "yes" in result  # in_hand
        assert "Some description" in result

    def test_card_not_found(self):
        assert "not found" in format_card_detail({})
        assert "not found" in format_card_detail(None)

    def test_supports_snake_case_created(self):
        result = format_card_detail(
            {
                "id": "c1",
                "title": "Snake Card",
                "status": "started",
                "created_at": "2026-01-03T00:00:00Z",
            }
        )
        assert "Created:   2026-01-03T00:00:00Z" in result

    def test_renders_checklist_and_subcards_and_conversations(self):
        result = format_card_detail(
            {
                "id": "hero",
                "title": "Hero Card",
                "status": "started",
                "checkboxStats": {"total": 4, "checked": 1},
                "sub_cards": [
                    {"id": "sub1", "title": "Sub Task", "status": "done"},
                ],
                "conversations": [
                    {
                        "id": "r1-full-uuid",
                        "status": "open",
                        "creator": "Alice",
                        "created_at": "2026-01-01",
                        "messages": [
                            {
                                "author": "Bob",
                                "content": "Looks good to me",
                                "created_at": "2026-01-02",
                            },
                        ],
                    },
                ],
            }
        )
        assert "Checklist: 1/4 (25%)" in result
        assert "Sub-cards (1):" in result
        assert "[done] Sub Task" in result
        assert "Conversations (1: 1 open, 0 closed):" in result
        assert "Bob: Looks good to me" in result

    def test_closed_conversations(self):
        result = format_card_detail(
            {
                "id": "c1",
                "title": "Card",
                "status": "done",
                "conversations": [
                    {
                        "id": "r1-full-uuid",
                        "status": "closed",
                        "creator": "Alice",
                        "messages": [],
                    },
                ],
            }
        )
        assert "0 open, 1 closed" in result


# ---------------------------------------------------------------------------
# format_stats_table
# ---------------------------------------------------------------------------


class TestFormatStatsTable:
    def test_formats_stats(self):
        stats = {
            "total": 10,
            "total_effort": 50,
            "avg_effort": 5.0,
            "by_status": {"done": 7, "started": 3},
            "by_priority": {"a": 5, "none": 5},
            "by_deck": {"Features": 10},
            "by_owner": {"Alice": 6, "unassigned": 4},
        }
        result = format_stats_table(stats)
        assert "Total cards: 10" in result
        assert "Total effort: 50" in result
        assert "Avg effort: 5.0" in result
        assert "done" in result
        assert "Features" in result
        assert "By Owner:" in result
        assert "Alice" in result
        assert "unassigned" in result


# ---------------------------------------------------------------------------
# format_decks_table
# ---------------------------------------------------------------------------


class TestFormatDecksTable:
    def test_formats_decks(self):
        result = format_decks_table(
            [
                {"id": "d1", "title": "Features", "project_name": "Tea Shop", "card_count": 5},
            ]
        )
        assert "Features" in result
        assert "Tea Shop" in result

    def test_shows_card_counts(self):
        result = format_decks_table(
            [
                {"id": "d1", "title": "Features", "project_name": "Tea Shop", "card_count": 5},
                {"id": "d2", "title": "Tasks", "project_name": "Tea Shop", "card_count": 12},
            ]
        )
        assert "Cards" in result  # column header
        assert "5" in result
        assert "12" in result

    def test_no_decks(self):
        assert "No decks" in format_decks_table([])


# ---------------------------------------------------------------------------
# format_projects_table
# ---------------------------------------------------------------------------


class TestFormatProjectsTable:
    def test_formats_projects(self):
        result = format_projects_table(
            [{"id": "p1", "name": "Tea Shop", "deck_count": 3, "decks": ["A", "B", "C"]}]
        )
        assert "Tea Shop" in result
        assert "p1" in result
        assert "Decks (3)" in result

    def test_no_projects(self):
        assert "No projects" in format_projects_table([])


# ---------------------------------------------------------------------------
# format_milestones_table
# ---------------------------------------------------------------------------


class TestFormatMilestonesTable:
    def test_formats_milestones(self):
        result = format_milestones_table([{"id": "m1", "name": "MVP", "card_count": 5}])
        assert "MVP" in result
        assert "m1" in result
        assert "Cards (5)" in result

    def test_no_milestones(self):
        assert "No milestones" in format_milestones_table([])


# ---------------------------------------------------------------------------
# format_gdd_table
# ---------------------------------------------------------------------------


class TestFormatGddTable:
    def test_formats_sections(self):
        sections = [
            {
                "section": "Gameplay",
                "tasks": [
                    {"title": "Player Movement", "priority": "a", "effort": 5},
                    {"title": "Combat System", "priority": None, "effort": None},
                ],
            },
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
        result = format_cards_csv(
            {
                "cards": [
                    {
                        "id": "c1",
                        "status": "done",
                        "priority": "a",
                        "effort": 3,
                        "title": "Test Card",
                        "deck_name": "Features",
                        "milestone_name": "MVP",
                        "owner_name": "Thomas",
                        "tags": ["bug", "ui"],
                    },
                ],
                "stats": None,
            }
        )
        lines = [line.rstrip("\r") for line in result.strip().split("\n")]
        assert lines[0] == "status,priority,effort,deck,milestone,owner,title,tags,id"
        assert "done" in lines[1]
        assert "high" in lines[1]
        assert "MVP" in lines[1]
        assert "Test Card" in lines[1]
        assert '"bug, ui"' in lines[1]


# ---------------------------------------------------------------------------
# format_activity_table
# ---------------------------------------------------------------------------


class TestFormatActivityTable:
    def test_shows_card_title(self, monkeypatch):
        monkeypatch.setattr(config, "env", {})
        from codecks_cli.formatters import format_activity_table

        result = format_activity_table(
            {
                "activity": {
                    "a1": {
                        "type": "card_update",
                        "createdAt": "2026-01-15T10:30:00Z",
                        "changer": "u1",
                        "deck": "d1",
                        "card": "c1",
                        "data": {"diff": {"status": ["started", "done"]}},
                    },
                },
                "user": {"u1": {"name": "Alice"}},
                "deck": {"d1": {"title": "Features"}},
                "card": {"c1": {"title": "Fix login bug"}},
            }
        )
        assert "Fix login bug" in result
        assert "Card" in result  # column header

    def test_supports_snake_case_created_timestamp(self, monkeypatch):
        monkeypatch.setattr(config, "env", {})
        from codecks_cli.formatters import format_activity_table

        result = format_activity_table(
            {
                "activity": {
                    "a1": {
                        "type": "card_update",
                        "created_at": "2026-01-15T10:30:00Z",
                        "data": {"diff": {}},
                    },
                },
                "user": {},
                "deck": {},
                "card": {},
            }
        )
        assert "2026-01-15 10:30" in result


class TestFormatConversationsTable:
    def test_formats_threads_and_entries(self):
        result = format_conversations_table(
            {
                "card": {
                    "c1": {"title": "Card A", "resolvables": ["r1"]},
                },
                "resolvable": {
                    "r1": {
                        "creator": "u1",
                        "isClosed": True,
                        "createdAt": "2026-01-15T10:30:00Z",
                        "entries": ["e1"],
                    },
                },
                "resolvableEntry": {
                    "e1": {
                        "author": "u2",
                        "createdAt": "2026-01-15T10:31:00Z",
                        "content": "Please update copy.",
                    },
                },
                "user": {
                    "u1": {"name": "Alice"},
                    "u2": {"name": "Bob"},
                },
            }
        )
        assert "Conversations on Card A:" in result
        assert "[closed] Thread r1" in result
        assert "Bob (2026-01-15T10:31:00Z): Please update copy." in result

    def test_handles_no_conversations_and_missing_card(self):
        result = format_conversations_table(
            {
                "card": {"c1": {"title": "Card A", "resolvables": []}},
            }
        )
        assert "No conversations." in result
        assert "Card not found." in format_conversations_table({"card": {}})


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
        mutation_response(
            "Updated", "c1", "status=done", {"payload": None, "actionId": "abc"}, fmt="json"
        )
        out = capsys.readouterr().out
        # Should only have the OK line, not the JSON dump
        assert "OK:" in out
        assert '"actionId"' not in out

    def test_strict_json_output(self, capsys, monkeypatch):
        monkeypatch.setattr(config, "RUNTIME_STRICT", True)
        mutation_response("Updated", "c1", "status=done", {"ok": True}, fmt="json")
        out = capsys.readouterr().out.strip()
        payload = json.loads(out)
        assert payload["ok"] is True
        assert payload["mutation"]["action"] == "Updated"
        assert payload["mutation"]["card_id"] == "c1"
        assert payload["data"]["ok"] is True

    def test_quiet_suppresses_table_output(self, capsys, monkeypatch):
        monkeypatch.setattr(config, "RUNTIME_QUIET", True)
        mutation_response("Updated", "c1", "status=done", fmt="table")
        out = capsys.readouterr().out
        assert out == ""

    def test_quiet_allows_json_output(self, capsys, monkeypatch):
        monkeypatch.setattr(config, "RUNTIME_QUIET", True)
        mutation_response("Updated", "c1", "status=done", fmt="json")
        out = capsys.readouterr().out
        assert "OK:" in out


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


class TestPmFocusTable:
    def test_pm_focus_table(self):
        report = {
            "counts": {"started": 2, "blocked": 1, "in_review": 0, "hand": 1, "stale": 0},
            "blocked": [{"id": "c1", "title": "A", "priority": "a", "effort": 5, "deck": "D"}],
            "in_review": [],
            "hand": [],
            "stale": [],
            "suggested": [{"id": "c2", "title": "B", "priority": "b", "effort": 3, "deck": "D"}],
            "filters": {"stale_days": 14},
        }
        result = format_pm_focus_table(report)
        assert "PM Focus Dashboard" in result
        assert "Blocked (1)" in result
        assert "In Review (0)" in result
        assert "Suggested Next (1)" in result

    def test_pm_focus_shows_stale(self):
        report = {
            "counts": {"started": 1, "blocked": 0, "in_review": 0, "hand": 0, "stale": 1},
            "blocked": [],
            "in_review": [],
            "hand": [],
            "stale": [{"id": "c1", "title": "Old Card", "priority": "b", "effort": 3, "deck": "D"}],
            "suggested": [],
            "filters": {"stale_days": 14},
        }
        result = format_pm_focus_table(report)
        assert "Stale (>14d) (1)" in result
        assert "Old Card" in result

    def test_pm_focus_shows_in_review(self):
        report = {
            "counts": {"started": 0, "blocked": 0, "in_review": 1, "hand": 0, "stale": 0},
            "blocked": [],
            "in_review": [
                {"id": "c1", "title": "Review Me", "priority": "a", "effort": 5, "deck": "D"}
            ],
            "hand": [],
            "stale": [],
            "suggested": [],
            "filters": {"stale_days": 14},
        }
        result = format_pm_focus_table(report)
        assert "In Review: 1" in result
        assert "Review Me" in result


class TestStandupTable:
    def test_standup_sections(self):
        report = {
            "recently_done": [
                {"id": "c1", "title": "Fix Bug", "priority": "a", "effort": 3, "deck": "D"}
            ],
            "in_progress": [
                {"id": "c2", "title": "New Feature", "priority": "b", "effort": 5, "deck": "D"}
            ],
            "blocked": [],
            "hand": [
                {"id": "c3", "title": "Quick Task", "priority": "c", "effort": 1, "deck": "D"}
            ],
            "filters": {"days": 2},
        }
        result = format_standup_table(report)
        assert "Standup Summary" in result
        assert "Done (last 2d) (1)" in result
        assert "In Progress (1)" in result
        assert "Blocked (0)" in result
        assert "In Hand (1)" in result
        assert "Fix Bug" in result
        assert "New Feature" in result
        assert "Quick Task" in result

    def test_standup_empty(self):
        report = {
            "recently_done": [],
            "in_progress": [],
            "blocked": [],
            "hand": [],
            "filters": {"days": 2},
        }
        result = format_standup_table(report)
        assert "Standup Summary" in result
        assert "Done (last 2d) (0)" in result


# ---------------------------------------------------------------------------
# _sanitize_str
# ---------------------------------------------------------------------------


class TestSanitizeStr:
    def test_normal_text_unchanged(self):
        assert _sanitize_str("Hello World") == "Hello World"

    def test_strips_ansi_escape_bold(self):
        assert _sanitize_str("\x1b[1mBold\x1b[0m") == "Bold"

    def test_strips_ansi_color(self):
        assert _sanitize_str("\x1b[31mRed\x1b[0m") == "Red"

    def test_strips_null_and_control_chars(self):
        assert _sanitize_str("A\x00B\x07C\x7fD") == "ABCD"

    def test_preserves_newlines_and_tabs(self):
        assert _sanitize_str("A\nB\tC") == "A\nB\tC"

    def test_none_returns_none(self):
        assert _sanitize_str(None) is None

    def test_empty_returns_empty(self):
        assert _sanitize_str("") == ""

    def test_table_sanitizes_cell_values(self):
        """ANSI sequences in table cells should be stripped."""
        cols = [("Name", 10), ("Title", 0)]
        rows = [("\x1b[1mEvil\x1b[0m", "Normal")]
        result = _table(cols, rows)
        assert "\x1b" not in result
        assert "Evil" in result
        assert "Normal" in result
