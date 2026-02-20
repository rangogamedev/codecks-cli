"""Tests for codecks_api.py — argparse, global flags, command dispatch."""

import pytest
import sys
import json
from config import CliError
from codecks_api import (_extract_global_flags, build_parser,
                         _error_type_from_message, _emit_cli_error)


# ---------------------------------------------------------------------------
# _extract_global_flags
# ---------------------------------------------------------------------------

class TestExtractGlobalFlags:
    def test_no_flags(self):
        fmt, strict, remaining = _extract_global_flags(["cards"])
        assert fmt == "json"
        assert strict is False
        assert remaining == ["cards"]

    def test_format_before_command(self):
        fmt, strict, remaining = _extract_global_flags(["--format", "table", "cards"])
        assert fmt == "table"
        assert strict is False
        assert remaining == ["cards"]

    def test_format_after_command(self):
        fmt, strict, remaining = _extract_global_flags(["cards", "--format", "table"])
        assert fmt == "table"
        assert strict is False
        assert remaining == ["cards"]

    def test_format_between_args(self):
        fmt, strict, remaining = _extract_global_flags(
            ["cards", "--status", "done", "--format", "csv"])
        assert fmt == "csv"
        assert strict is False
        assert remaining == ["cards", "--status", "done"]

    def test_strict_flag_anywhere(self):
        fmt, strict, remaining = _extract_global_flags(
            ["cards", "--strict", "--status", "done"])
        assert fmt == "json"
        assert strict is True
        assert remaining == ["cards", "--status", "done"]

    def test_version_exits(self):
        with pytest.raises(SystemExit) as exc_info:
            _extract_global_flags(["--version"])
        assert exc_info.value.code == 0

    def test_invalid_format_exits(self):
        with pytest.raises(CliError) as exc_info:
            _extract_global_flags(["--format", "xml"])
        assert exc_info.value.exit_code == 1

    def test_format_without_value(self):
        """--format at end of argv with no value should be kept as-is."""
        fmt, strict, remaining = _extract_global_flags(["cards", "--format"])
        assert fmt == "json"
        assert strict is False
        assert remaining == ["cards", "--format"]

    def test_preserves_other_args(self):
        fmt, strict, remaining = _extract_global_flags(
            ["update", "abc", "--status", "done", "--format", "table"])
        assert fmt == "table"
        assert strict is False
        assert remaining == ["update", "abc", "--status", "done"]


# ---------------------------------------------------------------------------
# build_parser — subcommand parsing
# ---------------------------------------------------------------------------

class TestBuildParser:
    def setup_method(self):
        self.parser = build_parser()

    def test_cards_command(self):
        ns = self.parser.parse_args(["cards"])
        assert ns.command == "cards"
        assert ns.status is None
        assert ns.deck is None
        assert ns.sort is None
        assert ns.stats is False

    def test_cards_with_filters(self):
        ns = self.parser.parse_args(
            ["cards", "--status", "done", "--deck", "Features",
             "--sort", "priority"])
        assert ns.status == "done"
        assert ns.deck == "Features"
        assert ns.sort == "priority"

    def test_cards_status_validation(self):
        with pytest.raises(CliError):
            self.parser.parse_args(["cards", "--status", "invalid"])

    def test_cards_sort_validation(self):
        with pytest.raises(CliError):
            self.parser.parse_args(["cards", "--sort", "invalid"])

    def test_create_severity_validation(self):
        with pytest.raises(CliError):
            self.parser.parse_args(["create", "title", "--severity", "urgent"])

    def test_create_severity_valid(self):
        ns = self.parser.parse_args(["create", "title", "--severity", "critical"])
        assert ns.severity == "critical"

    def test_update_command(self):
        ns = self.parser.parse_args(
            ["update", "card-1", "--status", "done", "--priority", "a"])
        assert ns.command == "update"
        assert ns.card_ids == ["card-1"]
        assert ns.status == "done"
        assert ns.priority == "a"

    def test_update_multiple_ids(self):
        ns = self.parser.parse_args(["update", "id1", "id2", "id3"])
        assert ns.card_ids == ["id1", "id2", "id3"]

    def test_update_priority_validation(self):
        with pytest.raises(CliError):
            self.parser.parse_args(["update", "id", "--priority", "x"])

    def test_create_command(self):
        ns = self.parser.parse_args(
            ["create", "My Card", "--deck", "Inbox", "--doc"])
        assert ns.command == "create"
        assert ns.title == "My Card"
        assert ns.deck == "Inbox"
        assert ns.doc is True

    def test_feature_command(self):
        ns = self.parser.parse_args([
            "feature", "Combat Revamp",
            "--hero-deck", "Features",
            "--code-deck", "Code",
            "--design-deck", "Design",
            "--art-deck", "Art",
            "--priority", "a",
            "--effort", "5",
        ])
        assert ns.command == "feature"
        assert ns.title == "Combat Revamp"
        assert ns.hero_deck == "Features"
        assert ns.code_deck == "Code"
        assert ns.design_deck == "Design"
        assert ns.art_deck == "Art"
        assert ns.skip_art is False
        assert ns.priority == "a"
        assert ns.effort == 5

    def test_card_command(self):
        ns = self.parser.parse_args(["card", "abc-123"])
        assert ns.command == "card"
        assert ns.card_id == "abc-123"

    def test_hand_no_args(self):
        ns = self.parser.parse_args(["hand"])
        assert ns.command == "hand"
        assert ns.card_ids == []

    def test_hand_with_ids(self):
        ns = self.parser.parse_args(["hand", "id1", "id2"])
        assert ns.card_ids == ["id1", "id2"]

    def test_done_command(self):
        ns = self.parser.parse_args(["done", "id1", "id2"])
        assert ns.command == "done"
        assert ns.card_ids == ["id1", "id2"]

    def test_activity_default_limit(self):
        ns = self.parser.parse_args(["activity"])
        assert ns.limit == 20

    def test_activity_custom_limit(self):
        ns = self.parser.parse_args(["activity", "--limit", "5"])
        assert ns.limit == 5

    def test_pm_focus_command(self):
        ns = self.parser.parse_args(["pm-focus", "--project", "Tea", "--limit", "7"])
        assert ns.command == "pm-focus"
        assert ns.project == "Tea"
        assert ns.limit == 7

    def test_activity_limit_must_be_positive(self):
        with pytest.raises(CliError):
            self.parser.parse_args(["activity", "--limit", "0"])

    def test_comment_command(self):
        ns = self.parser.parse_args(["comment", "card-1", "Hello"])
        assert ns.card_id == "card-1"
        assert ns.message == "Hello"

    def test_comment_with_thread(self):
        ns = self.parser.parse_args(
            ["comment", "card-1", "Reply", "--thread", "thread-1"])
        assert ns.thread == "thread-1"
        assert ns.message == "Reply"

    def test_comment_modes_are_mutually_exclusive(self):
        with pytest.raises(CliError):
            self.parser.parse_args(
                ["comment", "card-1", "--thread", "t1", "--close", "t2"])

    def test_delete_command(self):
        ns = self.parser.parse_args(["delete", "card-1", "--confirm"])
        assert ns.command == "delete"
        assert ns.card_id == "card-1"
        assert ns.confirm is True

    def test_gdd_sync_command(self):
        ns = self.parser.parse_args(
            ["gdd-sync", "--project", "Tea Shop", "--apply", "--quiet"])
        assert ns.command == "gdd-sync"
        assert ns.project == "Tea Shop"
        assert ns.apply is True
        assert ns.quiet is True

    def test_dispatch_command(self):
        ns = self.parser.parse_args(["dispatch", "cards/update", '{"id":"c1"}'])
        assert ns.command == "dispatch"
        assert ns.path == "cards/update"
        assert ns.json_data == '{"id":"c1"}'

    def test_archive_and_remove_alias(self):
        ns1 = self.parser.parse_args(["archive", "card-1"])
        ns2 = self.parser.parse_args(["remove", "card-1"])
        assert ns1.command == "archive"
        assert ns2.command == "remove"
        assert ns1.card_id == ns2.card_id == "card-1"


class TestCliErrorOutput:
    def test_error_type_mapping(self):
        assert _error_type_from_message("[TOKEN_EXPIRED] x") == "token_expired"
        assert _error_type_from_message("[SETUP_NEEDED] x") == "setup_needed"
        assert _error_type_from_message("[ERROR] x") == "error"
        assert _error_type_from_message("plain") == "cli_error"

    def test_emit_json_error(self, capsys):
        _emit_cli_error(CliError("[ERROR] bad input"), "json")
        err = capsys.readouterr().err.strip()
        payload = json.loads(err)
        assert payload["ok"] is False
        assert payload["error"]["type"] == "error"
        assert payload["error"]["exit_code"] == 1

    def test_emit_table_error(self, capsys):
        _emit_cli_error(CliError("[ERROR] bad input"), "table")
        err = capsys.readouterr().err.strip()
        assert err == "[ERROR] bad input"
