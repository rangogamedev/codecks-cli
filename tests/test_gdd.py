"""Tests for gdd.py — parse_gdd, _fuzzy_match, _extract_google_doc_id, sync_gdd."""

from unittest.mock import mock_open, patch

import pytest

from codecks_cli import config
from codecks_cli.exceptions import CliError, SetupError
from codecks_cli.gdd import (
    _extract_google_doc_id,
    _fuzzy_match,
    _save_gdd_cache,
    fetch_gdd,
    parse_gdd,
    sync_gdd,
)

# ---------------------------------------------------------------------------
# _extract_google_doc_id
# ---------------------------------------------------------------------------


class TestExtractGoogleDocId:
    def test_full_url(self):
        url = "https://docs.google.com/document/d/1aBcDeFgHiJkLmNoPqRs/edit"
        assert _extract_google_doc_id(url) == "1aBcDeFgHiJkLmNoPqRs"

    def test_bare_id(self):
        assert (
            _extract_google_doc_id("1aBcDeFgHiJkLmNoPqRsTuVwXyZ") == "1aBcDeFgHiJkLmNoPqRsTuVwXyZ"
        )

    def test_short_string_returns_none(self):
        assert _extract_google_doc_id("short") is None

    def test_url_with_params(self):
        url = "https://docs.google.com/document/d/ABC123_def-456/edit?usp=sharing"
        assert _extract_google_doc_id(url) == "ABC123_def-456"


# ---------------------------------------------------------------------------
# _fuzzy_match
# ---------------------------------------------------------------------------


class TestFuzzyMatch:
    def test_exact_match(self):
        titles = {"customer system": "c1", "economy": "c2"}
        assert _fuzzy_match("Customer System", titles) == "customer system"

    def test_substring_match(self):
        titles = {"flavor map system": "c1"}
        assert _fuzzy_match("Flavor Map System (2D)", titles) == "flavor map system"

    def test_reverse_substring(self):
        """Needle substring of haystack title — should match when both > 5 chars."""
        titles = {"complete customer system (arrival queue, requests, rating)": "c1"}
        assert (
            _fuzzy_match("Customer System", titles)
            == "complete customer system (arrival queue, requests, rating)"
        )

    def test_no_match(self):
        titles = {"something else": "c1"}
        assert _fuzzy_match("Totally Different", titles) is None

    def test_short_strings_exact_only(self):
        """Strings <= 5 chars should only match exactly, not by substring."""
        titles = {"abc": "c1", "abcdef": "c2"}
        assert _fuzzy_match("abc", titles) == "abc"
        assert _fuzzy_match("ab", titles) is None

    def test_case_insensitive(self):
        titles = {"dialogue system": "c1"}
        assert _fuzzy_match("DIALOGUE SYSTEM", titles) == "dialogue system"


# ---------------------------------------------------------------------------
# parse_gdd
# ---------------------------------------------------------------------------


class TestParseGdd:
    def test_basic_structure(self):
        content = """# Game Design Doc

## Core Gameplay
- Player movement
- Combat system

## Economy
- Currency
"""
        sections = parse_gdd(content)
        assert len(sections) == 2
        assert sections[0]["section"] == "Core Gameplay"
        assert len(sections[0]["tasks"]) == 2
        assert sections[0]["tasks"][0]["title"] == "Player movement"
        assert sections[0]["tasks"][1]["title"] == "Combat system"
        assert sections[1]["section"] == "Economy"
        assert len(sections[1]["tasks"]) == 1

    def test_priority_tag(self):
        sections = parse_gdd("## S\n- Task [P:a]\n")
        assert sections[0]["tasks"][0]["priority"] == "a"
        assert sections[0]["tasks"][0]["title"] == "Task"

    def test_effort_tag(self):
        sections = parse_gdd("## S\n- Task [E:5]\n")
        assert sections[0]["tasks"][0]["effort"] == 5

    def test_combined_tag(self):
        sections = parse_gdd("## S\n- Task [P:b E:3]\n")
        task = sections[0]["tasks"][0]
        assert task["priority"] == "b"
        assert task["effort"] == 3
        assert task["title"] == "Task"

    def test_separate_tags(self):
        sections = parse_gdd("## S\n- Task [P:c] [E:8]\n")
        task = sections[0]["tasks"][0]
        assert task["priority"] == "c"
        assert task["effort"] == 8

    def test_sub_items_become_content(self):
        content = """## S
- Main task
  - Sub item 1
  - Sub item 2
"""
        sections = parse_gdd(content)
        task = sections[0]["tasks"][0]
        assert task["title"] == "Main task"
        assert "Sub item 1" in task["content"]
        assert "Sub item 2" in task["content"]

    def test_blank_lines_separate_tasks(self):
        content = """## S
- Task A

- Task B
"""
        sections = parse_gdd(content)
        assert len(sections[0]["tasks"]) == 2

    def test_asterisk_bullets(self):
        content = """## S
* Task with asterisk
"""
        sections = parse_gdd(content)
        assert sections[0]["tasks"][0]["title"] == "Task with asterisk"

    def test_h1_ignored(self):
        content = """# Title
## Section
- Task
"""
        sections = parse_gdd(content)
        assert len(sections) == 1
        assert sections[0]["section"] == "Section"

    def test_empty_content(self):
        assert parse_gdd("") == []

    def test_no_sections(self):
        assert parse_gdd("Just some text\nNo structure here") == []

    def test_tasks_before_section_go_to_uncategorized(self):
        content = "- Orphan task\n## Real Section\n- Normal task\n"
        sections = parse_gdd(content)
        assert sections[0]["section"] == "Uncategorized"
        assert sections[0]["tasks"][0]["title"] == "Orphan task"
        assert sections[1]["section"] == "Real Section"

    def test_plain_text_after_task_appended_to_content(self):
        content = """## S
- Main task
Some continuation text
More text
"""
        sections = parse_gdd(content)
        task = sections[0]["tasks"][0]
        assert "continuation text" in task["content"]
        assert "More text" in task["content"]

    def test_priority_case_insensitive(self):
        sections = parse_gdd("## S\n- Task [P:A]\n")
        assert sections[0]["tasks"][0]["priority"] == "a"

    def test_empty_section_no_crash(self):
        content = "## Empty Section\n## Another\n- Task\n"
        sections = parse_gdd(content)
        assert sections[0]["section"] == "Empty Section"
        assert sections[0]["tasks"] == []
        assert sections[1]["tasks"][0]["title"] == "Task"

    def test_tag_stripped_from_title(self):
        """Tags should be removed from the title text."""
        sections = parse_gdd("## S\n- Build system [P:a E:5]\n")
        assert sections[0]["tasks"][0]["title"] == "Build system"
        assert "[P:" not in sections[0]["tasks"][0]["title"]
        assert "[E:" not in sections[0]["tasks"][0]["title"]


# ---------------------------------------------------------------------------
# sync_gdd error handling
# ---------------------------------------------------------------------------


class TestSyncGddErrorHandling:
    """Structured exception handling in sync_gdd batch loop."""

    SECTIONS = [{"section": "Test", "tasks": [{"title": "Task 1"}]}]
    MOCK_DECKS = {"deck": {"dk1": {"id": "d1", "title": "Test"}}}

    @patch("codecks_cli.gdd.list_cards", return_value={"card": {}})
    @patch("codecks_cli.gdd.list_decks")
    @patch("codecks_cli.gdd.create_card")
    def test_setup_error_propagates(self, mock_create, mock_decks, mock_list):
        """SetupError (token expired) should abort the batch, not be swallowed."""
        mock_decks.return_value = self.MOCK_DECKS
        mock_create.side_effect = SetupError("[TOKEN_EXPIRED] expired")
        with pytest.raises(SetupError):
            sync_gdd(self.SECTIONS, "TestProject", apply=True)

    @patch("codecks_cli.gdd.list_cards", return_value={"card": {}})
    @patch("codecks_cli.gdd.list_decks")
    @patch("codecks_cli.gdd.create_card")
    def test_cli_error_caught_in_report(self, mock_create, mock_decks, mock_list):
        """CliError should be caught and logged to report['errors']."""
        mock_decks.return_value = self.MOCK_DECKS
        mock_create.side_effect = CliError("[ERROR] some API error")
        report = sync_gdd(self.SECTIONS, "TestProject", apply=True)
        assert len(report["errors"]) == 1
        assert "some API error" in report["errors"][0]["error"]


class TestSaveGddCache:
    """_save_gdd_cache writes content and chmods to 0o600."""

    @patch("codecks_cli.gdd.os.chmod")
    def test_writes_and_chmods(self, mock_chmod, tmp_path, monkeypatch):
        cache_path = str(tmp_path / ".gdd_cache.md")
        monkeypatch.setattr(config, "GDD_CACHE_PATH", cache_path)
        _save_gdd_cache("# GDD content")
        with open(cache_path, encoding="utf-8") as f:
            assert f.read() == "# GDD content"
        mock_chmod.assert_called_once_with(cache_path, 0o600)


class TestFetchGdd:
    def test_reads_local_file(self):
        with (
            patch("codecks_cli.gdd.os.path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data="## Core\n- Task A\n")),
        ):
            content = fetch_gdd(local_file="gdd.md")
        assert "Task A" in content

    def test_local_file_missing_raises(self):
        with pytest.raises(CliError) as exc_info:
            fetch_gdd(local_file="does-not-exist.md")
        assert "File not found" in str(exc_info.value)

    def test_uses_cache_when_available(self, monkeypatch):
        monkeypatch.setattr(config, "GDD_DOC_URL", "")
        monkeypatch.setattr(config, "GDD_CACHE_PATH", ".gdd_cache.md")
        with (
            patch("codecks_cli.gdd.os.path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data="# cached")),
        ):
            content = fetch_gdd()
        assert content == "# cached"

    @patch("codecks_cli.gdd._save_gdd_cache")
    def test_refresh_uses_google_fetch_and_saves_cache(self, mock_save, monkeypatch):
        monkeypatch.setattr(
            config, "GDD_DOC_URL", "https://docs.google.com/document/d/ABC123_def-456/edit"
        )
        monkeypatch.setattr("codecks_cli.gdd.os.path.exists", lambda p: False)
        with patch(
            "codecks_cli.gdd._fetch_google_doc_content", return_value="# remote"
        ) as mock_fetch:
            content = fetch_gdd(force_refresh=True)
        assert content == "# remote"
        mock_fetch.assert_called_once_with("ABC123_def-456")
        mock_save.assert_called_once_with("# remote")

    def test_chmod_error_does_not_crash(self, tmp_path, monkeypatch):
        cache_path = str(tmp_path / ".gdd_cache.md")
        monkeypatch.setattr(config, "GDD_CACHE_PATH", cache_path)
        with patch("codecks_cli.gdd.os.chmod", side_effect=OSError("not supported")):
            _save_gdd_cache("# GDD content")
        with open(cache_path, encoding="utf-8") as f:
            assert f.read() == "# GDD content"
