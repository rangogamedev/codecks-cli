"""Tests for api.py — security helpers, HTTP error handling, token validation."""

import io
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from codecks_cli.api import (
    HTTPError,
    _check_token,
    _http_request,
    _is_sampled_request,
    _mask_token,
    _safe_json_parse,
    _sanitize_error,
    _sanitize_url_for_log,
    _try_call,
    dispatch,
    generate_report_token,
    query,
    session_request,
    warn_if_empty,
)
from codecks_cli.exceptions import CliError, SetupError


class TestMaskToken:
    def test_long_token(self):
        assert _mask_token("abcdef1234567890") == "abcdef..."

    def test_short_token(self):
        assert _mask_token("abc") == "abc"

    def test_exactly_six(self):
        assert _mask_token("abcdef") == "abcdef"

    def test_seven_chars(self):
        assert _mask_token("abcdefg") == "abcdef..."


class TestSanitizeUrlForLog:
    def test_masks_token_and_access_key(self):
        url = (
            "https://api.codecks.io/user-report/v1/create-report"
            "?token=secret-token&accessKey=secret-key&foo=bar"
        )
        safe = _sanitize_url_for_log(url)
        assert "token=%2A%2A%2A" in safe
        assert "accessKey=%2A%2A%2A" in safe
        assert "foo=bar" in safe
        assert "secret-token" not in safe
        assert "secret-key" not in safe


class TestSampling:
    def test_sample_rate_zero_disables(self, monkeypatch):
        monkeypatch.setattr("codecks_cli.api.config.HTTP_LOG_SAMPLE_RATE", 0.0)
        assert _is_sampled_request("req-1") is False

    def test_sample_rate_one_enables(self, monkeypatch):
        monkeypatch.setattr("codecks_cli.api.config.HTTP_LOG_SAMPLE_RATE", 1.0)
        assert _is_sampled_request("req-1") is True

    def test_sampling_is_deterministic(self, monkeypatch):
        monkeypatch.setattr("codecks_cli.api.config.HTTP_LOG_SAMPLE_RATE", 0.5)
        a = _is_sampled_request("req-stable")
        b = _is_sampled_request("req-stable")
        assert a == b


class TestSafeJsonParse:
    def test_valid_json(self):
        assert _safe_json_parse('{"a": 1}') == {"a": 1}

    def test_valid_array(self):
        assert _safe_json_parse("[1, 2, 3]") == [1, 2, 3]

    def test_invalid_json_exits(self):
        with pytest.raises(CliError) as exc_info:
            _safe_json_parse("not json")
        assert exc_info.value.exit_code == 1


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

    def test_catches_cli_error(self):
        def raises():
            raise CliError("test error")

        assert _try_call(raises) is None

    def test_passes_args(self):
        assert _try_call(lambda x, y: x + y, 3, 4) == 7


class TestHTTPError:
    def test_attributes(self):
        e = HTTPError(404, "Not Found", "body")
        assert e.code == 404
        assert e.reason == "Not Found"
        assert e.body == "body"
        assert e.headers == {}


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


class TestSessionRequest429:
    @patch("codecks_cli.api._http_request")
    def test_rate_limit_message(self, mock_http):
        mock_http.side_effect = HTTPError(429, "Too Many Requests", "")
        with pytest.raises(CliError) as exc_info:
            session_request("/", {"query": {}})
        assert "Rate limit" in str(exc_info.value)

    @patch("codecks_cli.api._http_request")
    def test_sends_request_id_header(self, mock_http):
        session_request("/", {"query": {}}, idempotent=True)
        headers = mock_http.call_args.args[2]
        assert headers["Accept"] == "application/json"
        assert "X-Request-Id" in headers
        assert headers["X-Request-Id"]


class TestHttpRetries:
    @patch("codecks_cli.api.time.sleep")
    @patch("codecks_cli.api.urllib.request.urlopen")
    def test_retries_429_for_idempotent_request(self, mock_urlopen, mock_sleep):
        first = urllib.error.HTTPError(
            "https://api.codecks.io/",
            429,
            "Too Many Requests",
            {"Retry-After": "0"},
            io.BytesIO(b"busy"),
        )
        success_cm = MagicMock()
        success_resp = success_cm.__enter__.return_value
        success_resp.headers.get.return_value = "application/json"
        success_resp.read.return_value = b'{"ok": true}'
        mock_urlopen.side_effect = [first, success_cm]

        result = _http_request("https://api.codecks.io/", {"query": {}}, idempotent=True)
        assert result["ok"] is True
        assert mock_urlopen.call_count == 2
        mock_sleep.assert_called_once()

    @patch("codecks_cli.api.urllib.request.urlopen")
    def test_does_not_retry_429_for_non_idempotent_request(self, mock_urlopen):
        first = urllib.error.HTTPError(
            "https://api.codecks.io/",
            429,
            "Too Many Requests",
            {"Retry-After": "0"},
            io.BytesIO(b"busy"),
        )
        mock_urlopen.side_effect = first

        with pytest.raises(HTTPError):
            _http_request("https://api.codecks.io/", {"x": 1}, idempotent=False)
        assert mock_urlopen.call_count == 1

    @patch("codecks_cli.api.urllib.request.urlopen")
    def test_response_size_limit(self, mock_urlopen, monkeypatch):
        monkeypatch.setattr("codecks_cli.api.config.HTTP_MAX_RESPONSE_BYTES", 4)
        mock_resp = mock_urlopen.return_value.__enter__.return_value
        mock_resp.headers.get.return_value = "application/json"
        mock_resp.read.return_value = b"12345"

        with pytest.raises(CliError) as exc_info:
            _http_request("https://api.codecks.io/", {"query": {}})
        assert "Response too large" in str(exc_info.value)


class TestResponseShapeValidation:
    @patch("codecks_cli.api.session_request")
    def test_query_rejects_non_object(self, mock_session):
        mock_session.return_value = []
        with pytest.raises(CliError) as exc_info:
            query({"_root": [{"account": ["id"]}]})
        assert "Unexpected query response shape" in str(exc_info.value)

    @patch("codecks_cli.api.session_request")
    def test_dispatch_rejects_non_object(self, mock_session):
        mock_session.return_value = "ok"
        with pytest.raises(CliError) as exc_info:
            dispatch("cards/update", {"id": "x"})
        assert "Unexpected dispatch response shape" in str(exc_info.value)

    @patch("codecks_cli.api.session_request")
    def test_query_strict_rejects_empty_object(self, mock_session, monkeypatch):
        monkeypatch.setattr("codecks_cli.api.config.RUNTIME_STRICT", True)
        mock_session.return_value = {}
        with pytest.raises(CliError) as exc_info:
            query({"_root": [{"account": ["id"]}]})
        assert "Strict mode: query returned an empty object" in str(exc_info.value)

    @patch("codecks_cli.api.session_request")
    def test_dispatch_strict_requires_ack_fields(self, mock_session, monkeypatch):
        monkeypatch.setattr("codecks_cli.api.config.RUNTIME_STRICT", True)
        mock_session.return_value = {"foo": "bar"}
        with pytest.raises(CliError) as exc_info:
            dispatch("cards/update", {"id": "x"})
        assert "Strict mode: dispatch response missing expected ack fields" in str(exc_info.value)


class TestContentTypeCheck:
    @patch("codecks_cli.api.urllib.request.urlopen")
    def test_html_content_type_gives_proxy_message(self, mock_urlopen):
        mock_resp = mock_urlopen.return_value.__enter__.return_value
        mock_resp.headers.get.return_value = "text/html; charset=utf-8"
        mock_resp.read.return_value = b"<html>Error</html>"
        with pytest.raises(CliError) as exc_info:
            _http_request("https://api.codecks.io/", {})
        assert "Content-Type" in str(exc_info.value)
        assert "proxy" in str(exc_info.value)

    @patch("codecks_cli.api.urllib.request.urlopen")
    def test_json_content_type_gives_json_message(self, mock_urlopen):
        mock_resp = mock_urlopen.return_value.__enter__.return_value
        mock_resp.headers.get.return_value = "application/json"
        mock_resp.read.return_value = b"not valid json{{"
        with pytest.raises(CliError) as exc_info:
            _http_request("https://api.codecks.io/", {})
        assert "not valid JSON" in str(exc_info.value)


class TestGenerateReportTokenLeak:
    """Error message must not leak raw API response values."""

    @patch("codecks_cli.api._http_request")
    def test_error_shows_keys_not_values(self, mock_http, monkeypatch):
        monkeypatch.setattr("codecks_cli.config.ACCESS_KEY", "fake-key")
        mock_http.return_value = {"ok": False, "secret_field": "s3cret"}
        with pytest.raises(CliError) as exc_info:
            generate_report_token()
        msg = str(exc_info.value)
        assert "s3cret" not in msg
        assert "keys:" in msg
        assert "ok" in msg

    @patch("codecks_cli.api._http_request")
    def test_error_on_missing_token_field(self, mock_http, monkeypatch):
        monkeypatch.setattr("codecks_cli.config.ACCESS_KEY", "fake-key")
        mock_http.return_value = {"ok": True}
        with pytest.raises(CliError) as exc_info:
            generate_report_token()
        msg = str(exc_info.value)
        assert "generate-token" in msg


class TestCheckToken:
    @patch("codecks_cli.api.session_request")
    def test_raises_setup_needed_when_missing_config(self, mock_session, monkeypatch):
        monkeypatch.setattr("codecks_cli.api.config.SESSION_TOKEN", "")
        monkeypatch.setattr("codecks_cli.api.config.ACCOUNT", "")
        with pytest.raises(SetupError) as exc_info:
            _check_token()
        assert "[SETUP_NEEDED]" in str(exc_info.value)
        assert "setup" in str(exc_info.value).lower()
        mock_session.assert_not_called()

    @patch("codecks_cli.api.session_request")
    def test_accepts_valid_account_payload(self, mock_session, monkeypatch):
        monkeypatch.setattr("codecks_cli.api.config.SESSION_TOKEN", "tok")
        monkeypatch.setattr("codecks_cli.api.config.ACCOUNT", "acct")
        mock_session.return_value = {"account": {"id1": {"id": "id1"}}}
        _check_token()
        mock_session.assert_called_once()

    @patch("codecks_cli.api.session_request")
    def test_raises_token_expired_on_empty_account(self, mock_session, monkeypatch):
        monkeypatch.setattr("codecks_cli.api.config.SESSION_TOKEN", "tok")
        monkeypatch.setattr("codecks_cli.api.config.ACCOUNT", "acct")
        mock_session.return_value = {"account": {}}
        with pytest.raises(SetupError) as exc_info:
            _check_token()
        msg = str(exc_info.value)
        assert "[TOKEN_EXPIRED]" in msg
        assert "setup" in msg.lower()

    @patch("codecks_cli.api.session_request")
    def test_wraps_setup_error_with_setup_hint(self, mock_session, monkeypatch):
        monkeypatch.setattr("codecks_cli.api.config.SESSION_TOKEN", "tok")
        monkeypatch.setattr("codecks_cli.api.config.ACCOUNT", "acct")
        mock_session.side_effect = SetupError("[TOKEN_EXPIRED] expired")
        with pytest.raises(SetupError) as exc_info:
            _check_token()
        msg = str(exc_info.value)
        assert "[TOKEN_EXPIRED]" in msg
        assert "Run: py codecks_api.py setup" in msg
