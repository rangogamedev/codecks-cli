"""
HTTP request layer, security helpers, and token validation for codecks-cli.
"""

import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from codecks_cli import config
from codecks_cli.exceptions import CliError, HTTPError, SetupError

_RETRYABLE_HTTP_CODES = frozenset({429, 502, 503, 504})


# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------


def _mask_token(token):
    """Show only first 6 chars of a token for safe logging."""
    return token[:6] + "..." if len(token) > 6 else token


def _safe_json_parse(text, context="input"):
    """Parse JSON with friendly error message on failure."""
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise CliError(f"[ERROR] Invalid JSON in {context}: {e.msg} at position {e.pos}") from None


def _sanitize_error(body, max_len=500):
    """Truncate and clean error body for safe display."""
    if not body:
        return ""
    cleaned = re.sub(r"<[^>]+>", "", body)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) > max_len:
        return cleaned[:max_len] + "... [truncated]"
    return cleaned


def _try_call(fn, *args, **kwargs):
    """Call a function that might raise CliError, returning None on failure."""
    try:
        return fn(*args, **kwargs)
    except CliError:
        return None


# ---------------------------------------------------------------------------
# HTTP request layer
# ---------------------------------------------------------------------------


def _sanitize_url_for_log(url):
    """Mask sensitive query params in URLs before logging."""
    parsed = urllib.parse.urlsplit(url)
    if not parsed.query:
        return url
    pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    masked = []
    for key, value in pairs:
        if key.lower() in {"token", "accesskey"}:
            masked.append((key, "***"))
        else:
            masked.append((key, value))
    safe_query = urllib.parse.urlencode(masked, doseq=True)
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, safe_query, parsed.fragment)
    )


def _log_http_event(**fields):
    """Emit structured HTTP logs to stderr when enabled."""
    if not config.HTTP_LOG_ENABLED:
        return
    print("[HTTP] " + json.dumps(fields, ensure_ascii=False, sort_keys=True), file=sys.stderr)


def _is_sampled_request(request_id):
    """Decide if a request should be logged based on sample rate."""
    rate = config.HTTP_LOG_SAMPLE_RATE
    if rate <= 0:
        return False
    if rate >= 1:
        return True
    if not request_id:
        return False
    digest = hashlib.sha256(request_id.encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:4], "big") / 4294967295.0
    return bucket < rate


def _error_envelope(message, status=None, request_id=None, retryable=None, detail=None):
    """Build a consistent CLI-safe HTTP error message."""
    meta = []
    if status is not None:
        meta.append(f"status={status}")
    if request_id:
        meta.append(f"request_id={request_id}")
    if retryable is not None:
        meta.append(f"retryable={'yes' if retryable else 'no'}")
    suffix = f" ({', '.join(meta)})" if meta else ""
    body = f"[ERROR] {message}{suffix}"
    if detail:
        body += f"\n{detail}"
    return body


def _expect_object_response(result, operation):
    """Ensure API helpers only return JSON objects (dict)."""
    if isinstance(result, dict):
        return result
    raise CliError(
        f"[ERROR] Unexpected {operation} response shape: "
        f"expected JSON object, got {type(result).__name__}."
    )


def _parse_retry_after(headers):
    """Return Retry-After seconds from response headers, or None."""
    if not headers:
        return None
    value = headers.get("Retry-After")
    if value is None:
        return None
    try:
        secs = int(str(value).strip())
    except ValueError:
        return None
    return max(0, secs)


def _http_request(url, data=None, headers=None, method="POST", idempotent=False):
    """Make an HTTP request with standard error handling.
    Returns parsed JSON on success.
    Raises HTTPError for HTTP errors (caller handles specific codes).
    Exits on network/timeout/parse errors."""
    body = json.dumps(data).encode("utf-8") if data else None
    request_id = (headers or {}).get("X-Request-Id")
    safe_url = _sanitize_url_for_log(url)
    sampled = _is_sampled_request(request_id)
    max_attempts = 1 + max(0, config.HTTP_MAX_RETRIES)
    timeout = max(1, config.HTTP_TIMEOUT_SECONDS)
    last_timeout = False
    last_url_error = None

    for attempt in range(max_attempts):
        start = time.perf_counter()
        req = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
        if sampled:
            _log_http_event(
                phase="request",
                method=method,
                url=safe_url,
                attempt=attempt + 1,
                max_attempts=max_attempts,
                idempotent=idempotent,
                request_id=request_id,
                timeout_seconds=timeout,
            )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                content_type = resp.headers.get("Content-Type", "")
                raw = resp.read(config.HTTP_MAX_RESPONSE_BYTES + 1)
                if len(raw) > config.HTTP_MAX_RESPONSE_BYTES:
                    raise CliError(
                        "[ERROR] Response too large from Codecks API "
                        f"(>{config.HTTP_MAX_RESPONSE_BYTES} bytes)."
                    )
                if sampled:
                    _log_http_event(
                        phase="response",
                        method=method,
                        url=safe_url,
                        attempt=attempt + 1,
                        status=getattr(resp, "status", 200),
                        content_type=content_type,
                        bytes=len(raw),
                        latency_ms=round((time.perf_counter() - start) * 1000, 2),
                        request_id=request_id,
                    )
                try:
                    return json.loads(raw.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    if content_type and "json" not in content_type.lower():
                        raise CliError(
                            f"[ERROR] Unexpected Content-Type from server "
                            f"({content_type}). This may be a proxy or "
                            "network issue."
                        ) from None
                    raise CliError(
                        "[ERROR] Unexpected response from Codecks API (not valid JSON)."
                    ) from None
        except urllib.error.HTTPError as e:
            error_body = (
                e.read(config.HTTP_MAX_RESPONSE_BYTES).decode("utf-8", errors="replace")
                if e.fp
                else ""
            )
            retryable = e.code in _RETRYABLE_HTTP_CODES
            # 429 = rate limit (request never processed) — always safe to retry.
            # 502/503/504 — only retry if idempotent.
            can_retry = attempt < max_attempts - 1 and retryable and (e.code == 429 or idempotent)
            if sampled:
                _log_http_event(
                    phase="response",
                    method=method,
                    url=safe_url,
                    attempt=attempt + 1,
                    status=e.code,
                    retryable=retryable,
                    will_retry=can_retry,
                    latency_ms=round((time.perf_counter() - start) * 1000, 2),
                    request_id=request_id,
                )
            if can_retry:
                retry_after = _parse_retry_after(getattr(e, "headers", None))
                if retry_after is None:
                    retry_after = config.HTTP_RETRY_BASE_SECONDS * (2**attempt)
                time.sleep(retry_after)
                continue
            raise HTTPError(e.code, e.reason, error_body, headers=e.headers) from e
        except TimeoutError as e:
            last_timeout = True
            if sampled:
                _log_http_event(
                    phase="network_error",
                    method=method,
                    url=safe_url,
                    attempt=attempt + 1,
                    error="timeout",
                    will_retry=idempotent and attempt < max_attempts - 1,
                    request_id=request_id,
                )
            if idempotent and attempt < max_attempts - 1:
                time.sleep(config.HTTP_RETRY_BASE_SECONDS * (2**attempt))
                continue
            raise CliError(
                _error_envelope(
                    f"Request timed out after {timeout} seconds. Is Codecks API reachable?",
                    request_id=request_id,
                    retryable=False,
                )
            ) from e
        except urllib.error.URLError as e:
            last_url_error = e.reason
            if sampled:
                _log_http_event(
                    phase="network_error",
                    method=method,
                    url=safe_url,
                    attempt=attempt + 1,
                    error=f"url_error: {e.reason}",
                    will_retry=idempotent and attempt < max_attempts - 1,
                    request_id=request_id,
                )
            if idempotent and attempt < max_attempts - 1:
                time.sleep(config.HTTP_RETRY_BASE_SECONDS * (2**attempt))
                continue
            raise CliError(
                _error_envelope(
                    f"Connection failed: {e.reason}",
                    request_id=request_id,
                    retryable=False,
                )
            ) from e

    if last_timeout:
        raise CliError(
            _error_envelope(
                f"Request timed out after {timeout} seconds. Is Codecks API reachable?",
                request_id=request_id,
                retryable=False,
            )
        )
    if last_url_error is not None:
        raise CliError(
            _error_envelope(
                f"Connection failed: {last_url_error}",
                request_id=request_id,
                retryable=False,
            )
        )
    raise CliError(_error_envelope("Request failed.", request_id=request_id))


def raw_http_request(url, data=None, headers=None, method="POST"):
    """Make a raw HTTP request and return response bytes.

    Used for S3-style upload endpoints that do not return JSON.
    """
    request_id = (headers or {}).get("X-Request-Id")
    safe_url = _sanitize_url_for_log(url)
    sampled = _is_sampled_request(request_id)
    timeout = max(1, config.HTTP_TIMEOUT_SECONDS)
    start = time.perf_counter()
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    if sampled:
        _log_http_event(
            phase="request",
            method=method,
            url=safe_url,
            request_id=request_id,
            timeout_seconds=timeout,
        )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(config.HTTP_MAX_RESPONSE_BYTES + 1)
            if len(raw) > config.HTTP_MAX_RESPONSE_BYTES:
                raise CliError(
                    "[ERROR] Response too large from upload endpoint "
                    f"(>{config.HTTP_MAX_RESPONSE_BYTES} bytes)."
                )
            if sampled:
                _log_http_event(
                    phase="response",
                    method=method,
                    url=safe_url,
                    status=getattr(resp, "status", 200),
                    bytes=len(raw),
                    latency_ms=round((time.perf_counter() - start) * 1000, 2),
                    request_id=request_id,
                )
            return raw
    except urllib.error.HTTPError as e:
        error_body = (
            e.read(config.HTTP_MAX_RESPONSE_BYTES).decode("utf-8", errors="replace") if e.fp else ""
        )
        raise CliError(
            _error_envelope(
                f"Upload HTTP {e.code}: {e.reason}",
                status=e.code,
                retryable=e.code in _RETRYABLE_HTTP_CODES,
                detail=_sanitize_error(error_body),
            )
        ) from e
    except TimeoutError as e:
        raise CliError(
            _error_envelope(
                f"Upload timed out after {timeout} seconds.",
                request_id=request_id,
                retryable=False,
            )
        ) from e
    except urllib.error.URLError as e:
        raise CliError(
            _error_envelope(
                f"Upload connection failed: {e.reason}",
                request_id=request_id,
                retryable=False,
            )
        ) from e


API_TOKEN_PREFIXES = ("cdxut_", "cdxat_")
TOKEN_HELP = (
    "Create an API token in Codecks under Your Profile > API Tokens "
    "(or Organization Settings > Integrations > API Tokens) and set CODECKS_TOKEN."
)
# A rejected token gets 401; the projects are read so setup can warn when none are visible.
AUTH_PROBE_QUERY = {"_root": [{"account": ["id", "name", {"projects": ["id"]}]}]}


def is_authenticated(result):
    """True if an AUTH_PROBE_QUERY result resolved the account for this token."""
    return bool(result.get("account"))


# 401 error codes from https://manual.codecks.io/api/ ("Token refusal reasons").
_TOKEN_ERRORS = {
    "invalid_token": "Codecks does not recognise the API token (typo, revoked, or cut off).",
    "token_expired": "The API token has passed its expiry date.",
    "not_a_member": "The owner of this personal API token has been disabled in the organization.",
    "user_api_tokens_disabled": "An admin has turned off personal API tokens for this organization.",
}


def _server_error(body):
    """Return (error code, parsed JSON dict) from a Codecks error body, or ("", {})."""
    try:
        info = json.loads(body) if body else {}
    except (TypeError, ValueError):
        return "", {}
    if not isinstance(info, dict):
        return "", {}
    # The manual documents the refusal reason in "message"; live responses also set "error".
    return str(info.get("error") or info.get("message") or ""), info


def looks_like_api_token(token):
    return token.startswith(API_TOKEN_PREFIXES)


def session_request(path="/", data=None, method="POST", idempotent=False):
    """Make an authenticated request using a Codecks API token (Bearer auth).
    Used for reading data and dispatch mutations."""
    url = config.BASE_URL + path
    headers = {
        "Authorization": f"Bearer {config.SESSION_TOKEN}",
        "X-Account": config.ACCOUNT,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Request-Id": str(uuid.uuid4()),
    }
    try:
        return _http_request(url, data, headers, method, idempotent=idempotent)
    except HTTPError as e:
        code, info = _server_error(e.body)
        if e.code == 401:
            reason = _TOKEN_ERRORS.get(code, "Codecks rejected the API token.")
            raise SetupError(f"[TOKEN_EXPIRED] {reason} {TOKEN_HELP}") from e
        if e.code == 400 and code == "token_account_mismatch":
            raise SetupError(
                "[SETUP_NEEDED] CODECKS_ACCOUNT does not match the organization "
                "this API token belongs to. Fix CODECKS_ACCOUNT or use a token from that org."
            ) from e
        if e.code == 403:
            scope = info.get("requiredScope")
            need = f" This token needs the '{scope}' permission." if scope else ""
            raise CliError(
                "[ERROR] Codecks denied this request (HTTP 403). The API token may be "
                f"read-only or lack access to this project.{need} "
                f"Server said: {_sanitize_error(e.body)}"
            ) from e
        if e.code == 429:
            raise CliError(
                "[ERROR] Rate limit reached (Codecks allows ~40 req/5s). "
                "Wait a few seconds and retry."
            ) from e
        server_req_id = e.headers.get("X-Request-Id") if e.headers else None
        raise CliError(
            _error_envelope(
                f"HTTP {e.code}: {e.reason}",
                status=e.code,
                request_id=server_req_id,
                retryable=e.code in _RETRYABLE_HTTP_CODES,
                detail=_sanitize_error(e.body),
            )
        ) from e


# ---------------------------------------------------------------------------
# Query and dispatch helpers
# ---------------------------------------------------------------------------


def query(q):
    """Run a Codecks query (uses API token)."""
    result = _expect_object_response(
        session_request("/", {"query": q}, idempotent=True),
        "query",
    )
    if config.RUNTIME_STRICT and not result:
        raise CliError(
            "[ERROR] Strict mode: query returned an empty object. Treating as ambiguous response."
        )
    result.pop("_root", None)
    return result


def dispatch(path, data):
    """Generic dispatch call for mutations (uses API token)."""
    result = _expect_object_response(
        session_request(f"/dispatch/{path}", data),
        "dispatch",
    )
    if config.RUNTIME_STRICT and not any(k in result for k in ("actionId", "ok", "payload")):
        raise CliError(
            "[ERROR] Strict mode: dispatch response missing expected "
            "ack fields (actionId/ok/payload)."
        )
    return result


def warn_if_empty(result, relation):
    """Warn if a query returned no results — likely means the token is not accepted.
    Codecks silently returns empty data instead of 401 when unauthenticated."""
    if config.RUNTIME_QUIET:
        return
    if relation not in result or not result[relation]:
        print(
            f"[TOKEN_EXPIRED] The Codecks API token may be invalid "
            f"(query returned 0 {relation}s). {TOKEN_HELP}",
            file=sys.stderr,
        )


# ---------------------------------------------------------------------------
# Token validation
# ---------------------------------------------------------------------------


def _check_token():
    """Validate the API token before running a command. Exits if it is not accepted."""
    if not config.SESSION_TOKEN or not config.ACCOUNT:
        raise SetupError("[SETUP_NEEDED] No configuration found.\n  Run: py codecks_api.py setup")
    try:
        result = session_request("/", {"query": AUTH_PROBE_QUERY}, idempotent=True)
    except SetupError as e:
        raise SetupError(str(e) + "\n  Run: py codecks_api.py setup") from e
    if not is_authenticated(result):
        raise SetupError(
            f"[TOKEN_EXPIRED] Codecks did not accept your API token. {TOKEN_HELP}\n"
            "  Run: py codecks_api.py setup\n"
            "  Or update CODECKS_TOKEN in .env manually."
        )
