"""Tests for content parsing helpers (codecks_cli/_content.py)."""

from codecks_cli._content import (
    has_title,
    parse_content,
    replace_body,
    replace_title,
    serialize_content,
)


class TestParseContent:
    def test_none_returns_empty(self):
        assert parse_content(None) == ("", "")

    def test_empty_string_returns_empty(self):
        assert parse_content("") == ("", "")

    def test_title_only(self):
        assert parse_content("My Title") == ("My Title", "")

    def test_title_and_body(self):
        assert parse_content("My Title\nSome body text") == ("My Title", "Some body text")

    def test_title_blank_line_body(self):
        assert parse_content("My Title\n\nSome body text") == ("My Title", "Some body text")

    def test_windows_line_endings(self):
        assert parse_content("My Title\r\nBody text\r\nMore") == ("My Title", "Body text\nMore")

    def test_whitespace_only_title(self):
        assert parse_content("   \nBody text") == ("   ", "Body text")

    def test_multiline_body(self):
        title, body = parse_content("Title\nLine 1\nLine 2\nLine 3")
        assert title == "Title"
        assert body == "Line 1\nLine 2\nLine 3"

    def test_trailing_newline(self):
        title, body = parse_content("Title\nBody\n")
        assert title == "Title"
        assert body == "Body\n"


class TestSerializeContent:
    def test_title_and_body(self):
        assert serialize_content("Title", "Body") == "Title\n\nBody"

    def test_empty_body(self):
        assert serialize_content("Title", "") == "Title"

    def test_empty_title(self):
        assert serialize_content("", "Body") == "\n\nBody"

    def test_both_empty(self):
        assert serialize_content("", "") == ""

    def test_roundtrip(self):
        original = "My Title\n\nBody content here"
        title, body = parse_content(original)
        assert serialize_content(title, body) == original


class TestReplaceBody:
    def test_basic(self):
        assert replace_body("Old Title\nOld body", "New body") == "Old Title\n\nNew body"

    def test_empty_original(self):
        assert replace_body(None, "New body") == "\n\nNew body"

    def test_empty_string_original(self):
        assert replace_body("", "New body") == "\n\nNew body"

    def test_preserves_title(self):
        result = replace_body("Keep This Title\nOld stuff", "Brand new content")
        assert result.startswith("Keep This Title\n")
        assert "Old stuff" not in result

    def test_title_only_original(self):
        assert replace_body("Just Title", "New body") == "Just Title\n\nNew body"


class TestReplaceTitle:
    def test_basic(self):
        assert replace_title("Old Title\nKeep body", "New Title") == "New Title\n\nKeep body"

    def test_empty_original(self):
        assert replace_title(None, "New Title") == "New Title"

    def test_empty_string_original(self):
        assert replace_title("", "New Title") == "New Title"

    def test_preserves_body(self):
        result = replace_title("Old Title\nBody line 1\nBody line 2", "New Title")
        assert result == "New Title\n\nBody line 1\nBody line 2"

    def test_title_only_original(self):
        assert replace_title("Old Title", "New Title") == "New Title"


class TestHasTitle:
    def test_none(self):
        assert has_title(None) is False

    def test_empty(self):
        assert has_title("") is False

    def test_has_title(self):
        assert has_title("My Title\nBody") is True

    def test_title_only(self):
        assert has_title("My Title") is True

    def test_newline_only(self):
        assert has_title("\nBody") is False
