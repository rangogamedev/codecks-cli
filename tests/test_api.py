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
    query,
    raw_http_request,
    session_request,
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

    @patch("codecks_cli.api._http_request")
    def test_sends_bearer_token(self, mock_http, monkeypatch):
        monkeypatch.setattr("codecks_cli.api.config.SESSION_TOKEN", "cdxut_id_secret")
        session_request("/", {"query": {}}, idempotent=True)
        headers = mock_http.call_args.args[2]
        assert headers["Authorization"] == "Bearer cdxut_id_secret"
        assert "X-Auth-Token" not in headers

    @patch("codecks_cli.api._http_request")
    def test_401_is_token_expired(self, mock_http):
        mock_http.side_effect = HTTPError(401, "Unauthorized", "")
        with pytest.raises(SetupError) as exc_info:
            session_request("/", {"query": {}})
        assert str(exc_info.value).startswith("[TOKEN_EXPIRED]")

    @patch("codecks_cli.api._http_request")
    def test_401_names_the_documented_reason(self, mock_http):
        mock_http.side_effect = HTTPError(401, "Unauthorized", '{"error":"token_expired"}')
        with pytest.raises(SetupError, match="expiry date"):
            session_request("/", {"query": {}})

    @patch("codecks_cli.api._http_request")
    def test_401_reason_read_from_message_field(self, mock_http):
        """The manual documents the refusal reason in `message`."""
        mock_http.side_effect = HTTPError(401, "Unauthorized", '{"message":"not_a_member"}')
        with pytest.raises(SetupError, match="disabled"):
            session_request("/", {"query": {}})

    @patch("codecks_cli.api._http_request")
    def test_403_missing_scope_names_the_scope(self, mock_http):
        body = '{"error":"missing_scope","requiredScope":"card:write"}'
        mock_http.side_effect = HTTPError(403, "Forbidden", body)
        with pytest.raises(CliError, match="card:write"):
            session_request("/dispatch/cards/create", {})

    @patch("codecks_cli.api._http_request")
    def test_400_account_mismatch_points_at_config(self, mock_http):
        body = '{"error":"token_account_mismatch"}'
        mock_http.side_effect = HTTPError(400, "Bad Request", body)
        with pytest.raises(SetupError, match="CODECKS_ACCOUNT"):
            session_request("/", {"query": {}})

    @patch("codecks_cli.api._http_request")
    def test_403_is_permission_error_with_server_message(self, mock_http):
        mock_http.side_effect = HTTPError(403, "Forbidden", "token is read-only")
        with pytest.raises(CliError) as exc_info:
            session_request("/dispatch/cards/create", {})
        assert not isinstance(exc_info.value, SetupError)
        assert "read-only" in str(exc_info.value)


class TestSessionRequestErrorCodes:
    """Documented API errors (manual.codecks.io/api) carry machine-readable codes."""

    @pytest.mark.parametrize(
        ("status", "body", "exc", "code", "retryable"),
        [
            (401, '{"error":"invalid_token"}', SetupError, "TOKEN_EXPIRED", False),
            (400, '{"error":"token_account_mismatch"}', SetupError, "SETUP_NEEDED", False),
            (403, '{"error":"missing_scope"}', CliError, "PERMISSION_DENIED", False),
            (429, "", CliError, "RATE_LIMITED", True),
            (503, "", CliError, "HTTP_ERROR", True),
            (500, "", CliError, "HTTP_ERROR", False),
        ],
    )
    @patch("codecks_cli.api._http_request")
    def test_codes(self, mock_http, status, body, exc, code, retryable):
        mock_http.side_effect = HTTPError(status, "x", body)
        with pytest.raises(exc) as exc_info:
            session_request("/", {"query": {}})
        assert exc_info.value.error_code == code
        assert exc_info.value.retryable is retryable

    @patch("codecks_cli.api._http_request")
    def test_graph_400_shows_code_path_and_message(self, mock_http):
        body = (
            '{"error":"unknown_relation","message":"unknown relation \'queueEntries\' '
            'for model \'user\'","statusCode":400,"path":"_root.loggedInUser.queueEntries"}'
        )
        mock_http.side_effect = HTTPError(400, "Bad Request", body)
        with pytest.raises(CliError) as exc_info:
            session_request("/", {"query": {}})
        msg = str(exc_info.value)
        assert "unknown_relation at _root.loggedInUser.queueEntries" in msg
        assert "unknown relation 'queueEntries' for model 'user'" in msg
        assert exc_info.value.error_code == "INVALID_QUERY"

    @patch("codecks_cli.api._http_request")
    def test_429_names_retry_after(self, mock_http):
        mock_http.side_effect = HTTPError(429, "x", "", headers={"Retry-After": "3"})
        with pytest.raises(CliError, match="Wait 3 seconds"):
            session_request("/", {"query": {}})

    @patch("codecks_cli.api._http_request")
    def test_graph_400_includes_hint(self, mock_http):
        body = '{"error":"invalid_limit","message":"bad","path":"_root.x","hint":"add $order"}'
        mock_http.side_effect = HTTPError(400, "Bad Request", body)
        with pytest.raises(CliError, match=r"\(invalid_limit at _root.x\): bad Hint: add \$order"):
            session_request("/", {"query": {}})

    @patch("codecks_cli.api._http_request")
    def test_400_without_error_code_is_plain_http_error(self, mock_http):
        mock_http.side_effect = HTTPError(400, "Bad Request", '{"message":"x","path":"_root"}')
        with pytest.raises(CliError) as exc_info:
            session_request("/", {"query": {}})
        assert exc_info.value.error_code == "HTTP_ERROR"

    @patch("codecks_cli.api._http_request")
    def test_429_retry_after_zero(self, mock_http):
        mock_http.side_effect = HTTPError(429, "x", "", headers={"Retry-After": "0"})
        with pytest.raises(CliError, match="Wait 0 seconds"):
            session_request("/", {"query": {}})

    @patch("codecks_cli.api.urllib.request.urlopen", side_effect=TimeoutError())
    def test_timeout_is_network_error(self, _mock_urlopen, monkeypatch):
        monkeypatch.setattr("codecks_cli.api.config.HTTP_MAX_RETRIES", 0)
        with pytest.raises(CliError) as exc_info:
            _http_request("https://example.invalid/", {"q": 1})
        assert exc_info.value.error_code == "NETWORK_ERROR"

    @patch("codecks_cli.api.session_request")
    def test_check_token_keeps_code_when_wrapping(self, mock_request, monkeypatch):
        monkeypatch.setattr("codecks_cli.api.config.SESSION_TOKEN", "cdxut_x")
        monkeypatch.setattr("codecks_cli.api.config.ACCOUNT", "acct")
        mock_request.side_effect = SetupError("[TOKEN_EXPIRED] x", error_code="TOKEN_EXPIRED")
        with pytest.raises(SetupError) as exc_info:
            _check_token()
        assert exc_info.value.error_code == "TOKEN_EXPIRED"


class TestRawHttpRequest:
    @patch("codecks_cli.api.urllib.request.urlopen")
    def test_sends_raw_body_and_returns_bytes(self, mock_urlopen):
        mock_resp = mock_urlopen.return_value.__enter__.return_value
        mock_resp.read.return_value = b"ok"

        result = raw_http_request(
            "https://s3.example/upload",
            data=b"raw-body",
            headers={"Content-Type": "multipart/form-data"},
            method="POST",
        )

        assert result == b"ok"
        req = mock_urlopen.call_args.args[0]
        assert req.data == b"raw-body"
        assert req.get_method() == "POST"


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

    @patch("codecks_cli.api.time.sleep")
    @patch("codecks_cli.api.urllib.request.urlopen")
    def test_retries_429_for_non_idempotent_request(self, mock_urlopen, mock_sleep):
        """429 = rate limit (request never processed), safe to retry even for mutations."""
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

        result = _http_request("https://api.codecks.io/", {"x": 1}, idempotent=False)
        assert result["ok"] is True
        assert mock_urlopen.call_count == 2
        mock_sleep.assert_called_once()

    @patch("codecks_cli.api.urllib.request.urlopen")
    def test_does_not_retry_502_for_non_idempotent_request(self, mock_urlopen):
        """502/503/504 should NOT retry for mutations (may have been processed)."""
        first = urllib.error.HTTPError(
            "https://api.codecks.io/",
            502,
            "Bad Gateway",
            {},
            io.BytesIO(b"error"),
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
        mock_session.return_value = {
            "account": {"id1": {"id": "id1"}},
            "project": {"p1": {"id": "p1"}},
        }
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
    def test_accepts_token_that_sees_no_projects(self, mock_session, monkeypatch):
        """A new org, or an org token with no projects selected, is still a valid token."""
        monkeypatch.setattr("codecks_cli.api.config.SESSION_TOKEN", "tok")
        monkeypatch.setattr("codecks_cli.api.config.ACCOUNT", "acct")
        mock_session.return_value = {"account": {"id1": {"id": "id1"}}}
        _check_token()

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
