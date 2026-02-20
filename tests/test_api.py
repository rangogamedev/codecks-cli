"""Tests for api.py — security helpers, HTTP error handling, token validation."""

import json
import pytest
import sys

from api import (_mask_token, _safe_json_parse, _sanitize_error, _try_call,
                 HTTPError, warn_if_empty)


class TestMaskToken:
    def test_long_token(self):
        assert _mask_token("abcdef1234567890") == "abcdef..."

    def test_short_token(self):
        assert _mask_token("abc") == "abc"

    def test_exactly_six(self):
        assert _mask_token("abcdef") == "abcdef"

    def test_seven_chars(self):
        assert _mask_token("abcdefg") == "abcdef..."


class TestSafeJsonParse:
    def test_valid_json(self):
        assert _safe_json_parse('{"a": 1}') == {"a": 1}

    def test_valid_array(self):
        assert _safe_json_parse('[1, 2, 3]') == [1, 2, 3]

    def test_invalid_json_exits(self):
        with pytest.raises(SystemExit) as exc_info:
            _safe_json_parse("not json")
        assert exc_info.value.code == 1


class TestSanitizeError:
    def test_strips_html(self):
        assert _sanitize_error("<h1>Error</h1><p>Details</p>") == "ErrorDetails"

    def test_truncates_long_body(self):
        result = _sanitize_error("x" * 1000)
        assert result.endswith("... [truncated]")
        assert len(result) <= 520

    def test_empty_body(self):
        assert _sanitize_error("") == ""
        assert _sanitize_error(None) == ""

    def test_collapses_whitespace(self):
        assert _sanitize_error("a   b\n\n  c") == "a b c"


class TestTryCall:
    def test_returns_value(self):
        assert _try_call(lambda: 42) == 42

    def test_catches_sys_exit(self):
        def exits():
            sys.exit(1)
        assert _try_call(exits) is None

    def test_passes_args(self):
        assert _try_call(lambda x, y: x + y, 3, 4) == 7


class TestHTTPError:
    def test_attributes(self):
        e = HTTPError(404, "Not Found", "body")
        assert e.code == 404
        assert e.reason == "Not Found"
        assert e.body == "body"


class TestWarnIfEmpty:
    def test_no_warning_with_data(self, capsys):
        warn_if_empty({"card": {"id1": {}}}, "card")
        assert "[TOKEN_EXPIRED]" not in capsys.readouterr().err

    def test_warns_on_empty(self, capsys):
        warn_if_empty({}, "card")
        assert "[TOKEN_EXPIRED]" in capsys.readouterr().err

    def test_warns_on_empty_dict(self, capsys):
        warn_if_empty({"card": {}}, "card")
        assert "[TOKEN_EXPIRED]" in capsys.readouterr().err
