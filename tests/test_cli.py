"""Tests for codecks_api.py — argparse, global flags, command dispatch."""

import json

import pytest

from codecks_cli.cli import (
    _emit_cli_error,
    _error_type_from_message,
    _extract_global_flags,
    build_parser,
)
from codecks_cli.exceptions import CliError

# ---------------------------------------------------------------------------
# _extract_global_flags
# ---------------------------------------------------------------------------


class TestExtractGlobalFlags:
    def test_no_flags(self):
        fmt, strict, dry_run, quiet, verbose, remaining = _extract_global_flags(["cards"])
        assert fmt == "json"
        assert strict is False
        assert dry_run is False
        assert quiet is False
        assert verbose is False
        assert remaining == ["cards"]

    def test_format_before_command(self):
        fmt, strict, dry_run, quiet, verbose, remaining = _extract_global_flags(
            ["--format", "table", "cards"]
        )
        assert fmt == "table"
        assert strict is False
        assert remaining == ["cards"]

    def test_format_after_command(self):
        fmt, strict, dry_run, quiet, verbose, remaining = _extract_global_flags(
            ["cards", "--format", "table"]
        )
        assert fmt == "table"
        assert strict is False
        assert remaining == ["cards"]

    def test_format_between_args(self):
        fmt, strict, dry_run, quiet, verbose, remaining = _extract_global_flags(
            ["cards", "--status", "done", "--format", "csv"]
        )
        assert fmt == "csv"
        assert strict is False
        assert remaining == ["cards", "--status", "done"]

    def test_strict_flag_anywhere(self):
        fmt, strict, dry_run, quiet, verbose, remaining = _extract_global_flags(
            ["cards", "--strict", "--status", "done"]
        )
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
        fmt, strict, dry_run, quiet, verbose, remaining = _extract_global_flags(
            ["cards", "--format"]
        )
        assert fmt == "json"
        assert strict is False
        assert remaining == ["cards", "--format"]

    def test_preserves_other_args(self):
        fmt, strict, dry_run, quiet, verbose, remaining = _extract_global_flags(
            ["update", "abc", "--status", "done", "--format", "table"]
        )
        assert fmt == "table"
        assert strict is False
        assert remaining == ["update", "abc", "--status", "done"]

    def test_dry_run_extracted(self):
        fmt, strict, dry_run, quiet, verbose, remaining = _extract_global_flags(
            ["create", "Card", "--dry-run"]
        )
        assert dry_run is True
        assert remaining == ["create", "Card"]

    def test_dry_run_anywhere(self):
        fmt, strict, dry_run, quiet, verbose, remaining = _extract_global_flags(
            ["--dry-run", "cards", "--status", "done"]
        )
        assert dry_run is True
        assert remaining == ["cards", "--status", "done"]

    def test_dry_run_default_false(self):
        fmt, strict, dry_run, quiet, verbose, remaining = _extract_global_flags(["cards"])
        assert dry_run is False

    def test_quiet_flag(self):
        fmt, strict, dry_run, quiet, verbose, remaining = _extract_global_flags(
            ["cards", "--quiet"]
        )
        assert quiet is True
        assert remaining == ["cards"]

    def test_quiet_short_flag(self):
        fmt, strict, dry_run, quiet, verbose, remaining = _extract_global_flags(["cards", "-q"])
        assert quiet is True
        assert remaining == ["cards"]

    def test_verbose_flag(self):
        fmt, strict, dry_run, quiet, verbose, remaining = _extract_global_flags(
            ["cards", "--verbose"]
        )
        assert verbose is True
        assert remaining == ["cards"]

    def test_verbose_short_flag(self):
        fmt, strict, dry_run, quiet, verbose, remaining = _extract_global_flags(["cards", "-v"])
        assert verbose is True
        assert remaining == ["cards"]

    def test_quiet_verbose_mutually_exclusive(self):
        with pytest.raises(CliError) as exc_info:
            _extract_global_flags(["cards", "--quiet", "--verbose"])
        assert "mutually exclusive" in str(exc_info.value)


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
            ["cards", "--status", "done", "--deck", "Features", "--sort", "priority"]
        )
        assert ns.status == "done"
        assert ns.deck == "Features"
        assert ns.sort == "priority"

    def test_cards_status_accepts_free_form(self):
        """Status validation moved to cards.py to support comma-separated values."""
        ns = self.parser.parse_args(["cards", "--status", "started,blocked"])
        assert ns.status == "started,blocked"

    def test_cards_priority_filter(self):
        ns = self.parser.parse_args(["cards", "--priority", "a,b"])
        assert ns.priority == "a,b"

    def test_cards_stale_flag(self):
        ns = self.parser.parse_args(["cards", "--stale", "14"])
        assert ns.stale == 14

    def test_cards_date_filters(self):
        ns = self.parser.parse_args(
            ["cards", "--updated-after", "2026-01-01", "--updated-before", "2026-02-01"]
        )
        assert ns.updated_after == "2026-01-01"
        assert ns.updated_before == "2026-02-01"

    def test_cards_pagination_flags(self):
        ns = self.parser.parse_args(["cards", "--limit", "25", "--offset", "10"])
        assert ns.limit == 25
        assert ns.offset == 10

    def test_cards_offset_must_be_non_negative(self):
        with pytest.raises(CliError):
            self.parser.parse_args(["cards", "--offset", "-1"])

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
        ns = self.parser.parse_args(["update", "card-1", "--status", "done", "--priority", "a"])
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
        ns = self.parser.parse_args(["create", "My Card", "--deck", "Inbox", "--doc"])
        assert ns.command == "create"
        assert ns.title == "My Card"
        assert ns.deck == "Inbox"
        assert ns.doc is True
        assert ns.allow_duplicate is False

    def test_create_allow_duplicate_flag(self):
        ns = self.parser.parse_args(["create", "My Card", "--allow-duplicate"])
        assert ns.allow_duplicate is True

    def test_feature_command(self):
        ns = self.parser.parse_args(
            [
                "feature",
                "Combat Revamp",
                "--hero-deck",
                "Features",
                "--code-deck",
                "Code",
                "--design-deck",
                "Design",
                "--art-deck",
                "Art",
                "--priority",
                "a",
                "--effort",
                "5",
            ]
        )
        assert ns.command == "feature"
        assert ns.title == "Combat Revamp"
        assert ns.hero_deck == "Features"
        assert ns.code_deck == "Code"
        assert ns.design_deck == "Design"
        assert ns.art_deck == "Art"
        assert ns.skip_art is False
        assert ns.priority == "a"
        assert ns.effort == 5
        assert ns.allow_duplicate is False

    def test_feature_allow_duplicate_flag(self):
        ns = self.parser.parse_args(
            [
                "feature",
                "Combat Revamp",
                "--hero-deck",
                "Features",
                "--code-deck",
                "Code",
                "--design-deck",
                "Design",
                "--allow-duplicate",
            ]
        )
        assert ns.allow_duplicate is True

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

    def test_pm_focus_stale_days(self):
        ns = self.parser.parse_args(["pm-focus", "--stale-days", "30"])
        assert ns.stale_days == 30

    def test_standup_command(self):
        ns = self.parser.parse_args(["standup", "--days", "3", "--project", "Tea"])
        assert ns.command == "standup"
        assert ns.days == 3
        assert ns.project == "Tea"

    def test_standup_defaults(self):
        ns = self.parser.parse_args(["standup"])
        assert ns.command == "standup"
        assert ns.days == 2

    def test_activity_limit_must_be_positive(self):
        with pytest.raises(CliError):
            self.parser.parse_args(["activity", "--limit", "0"])

    def test_comment_command(self):
        ns = self.parser.parse_args(["comment", "card-1", "Hello"])
        assert ns.card_id == "card-1"
        assert ns.message == "Hello"

    def test_comment_with_thread(self):
        ns = self.parser.parse_args(["comment", "card-1", "Reply", "--thread", "thread-1"])
        assert ns.thread == "thread-1"
        assert ns.message == "Reply"

    def test_comment_modes_are_mutually_exclusive(self):
        with pytest.raises(CliError):
            self.parser.parse_args(["comment", "card-1", "--thread", "t1", "--close", "t2"])

    def test_delete_command(self):
        ns = self.parser.parse_args(["delete", "card-1", "--confirm"])
        assert ns.command == "delete"
        assert ns.card_id == "card-1"
        assert ns.confirm is True

    def test_gdd_sync_command(self):
        ns = self.parser.parse_args(["gdd-sync", "--project", "Tea Shop", "--apply"])
        assert ns.command == "gdd-sync"
        assert ns.project == "Tea Shop"
        assert ns.apply is True

    def test_completion_command(self):
        ns = self.parser.parse_args(["completion", "--shell", "bash"])
        assert ns.command == "completion"
        assert ns.shell == "bash"

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

    def test_every_subparser_has_func_default(self):
        """Every subparser must set a func default for dispatch."""
        for action in self.parser._subparsers._actions:
            if hasattr(action, "_name_parser_map"):
                for name, subparser in action._name_parser_map.items():
                    defaults = subparser._defaults
                    assert "func" in defaults, f"Subparser '{name}' missing func default"


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
        assert payload["schema_version"] == "1.0"
        assert payload["error"]["type"] == "error"
        assert payload["error"]["exit_code"] == 1

    def test_emit_table_error(self, capsys):
        _emit_cli_error(CliError("[ERROR] bad input"), "table")
        err = capsys.readouterr().err.strip()
        assert err == "[ERROR] bad input"
