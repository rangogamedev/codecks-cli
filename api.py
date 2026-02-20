"""
HTTP request layer, security helpers, and token validation for codecks-cli.
"""

import json
import re
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request

import config
from config import CliError, SetupError


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
        raise CliError(f"[ERROR] Invalid JSON in {context}: "
                       f"{e.msg} at position {e.pos}")


def _sanitize_error(body, max_len=500):
    """Truncate and clean error body for safe display."""
    if not body:
        return ""
    cleaned = re.sub(r'<[^>]+>', '', body)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
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

class HTTPError(Exception):
    """Raised by _http_request for HTTP errors that callers want to handle."""
    def __init__(self, code, reason, body):
        self.code = code
        self.reason = reason
        self.body = body


def _http_request(url, data=None, headers=None, method="POST"):
    """Make an HTTP request with standard error handling.
    Returns parsed JSON on success.
    Raises HTTPError for HTTP errors (caller handles specific codes).
    Exits on network/timeout/parse errors."""
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers or {},
                                method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            try:
                return json.loads(resp.read().decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise CliError("[ERROR] Unexpected response from Codecks API "
                               "(not valid JSON).")
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        raise HTTPError(e.code, e.reason, error_body)
    except socket.timeout:
        raise CliError("[ERROR] Request timed out after 30 seconds. "
                       "Is Codecks API reachable?")
    except urllib.error.URLError as e:
        raise CliError(f"[ERROR] Connection failed: {e.reason}")


def session_request(path="/", data=None, method="POST"):
    """Make an authenticated request using the session token (at cookie).
    Used for reading data and dispatch mutations."""
    url = config.BASE_URL + path
    headers = {
        "X-Auth-Token": config.SESSION_TOKEN,
        "X-Account": config.ACCOUNT,
        "Content-Type": "application/json",
    }
    try:
        return _http_request(url, data, headers, method)
    except HTTPError as e:
        if e.code in (401, 403):
            raise SetupError(
                "[TOKEN_EXPIRED] The Codecks session token has expired. "
                "Please provide a fresh 'at' cookie from browser DevTools "
                "(Brave > F12 > Network > api.codecks.io request > "
                "Cookie header > at=...).")
        raise CliError(f"[ERROR] HTTP {e.code}: {e.reason}\n"
                       f"{_sanitize_error(e.body)}")


def report_request(content, severity=None, email=None):
    """Create a card via the Report Token endpoint (stable, no expiry)."""
    if not config.REPORT_TOKEN:
        raise CliError("[ERROR] CODECKS_REPORT_TOKEN not set in .env. "
                       "Run: py codecks_api.py generate-token")
    payload = {"content": content}
    if severity:
        payload["severity"] = severity
    if email:
        payload["userEmail"] = email
    # NOTE: Token in URL query param is required by Codecks API design.
    # Mitigate by treating report tokens as rotatable credentials.
    url = (f"{config.BASE_URL}/user-report/v1/create-report"
           f"?token={config.REPORT_TOKEN}")
    headers = {"Content-Type": "application/json"}
    try:
        return _http_request(url, payload, headers)
    except HTTPError as e:
        if e.code == 401:
            raise CliError("[ERROR] Report token is invalid or disabled. "
                           "Generate a new one: py codecks_api.py generate-token")
        raise CliError(f"[ERROR] HTTP {e.code}: {e.reason}\n"
                       f"{_sanitize_error(e.body)}")


def generate_report_token(label="claude-code"):
    """Use the Access Key to create a new Report Token and save it to .env."""
    if not config.ACCESS_KEY:
        raise CliError("[ERROR] CODECKS_ACCESS_KEY not set in .env.")
    # NOTE: Access key in URL query param is required by Codecks API design.
    url = (f"{config.BASE_URL}/user-report/v1/create-report-token"
           f"?accessKey={config.ACCESS_KEY}")
    headers = {"Content-Type": "application/json"}
    try:
        result = _http_request(url, {"label": label}, headers)
    except HTTPError as e:
        raise CliError(f"[ERROR] HTTP {e.code}: {e.reason}\n"
                       f"{_sanitize_error(e.body)}")
    if result.get("ok") and result.get("token"):
        config.save_env_value("CODECKS_REPORT_TOKEN", result["token"])
        return result
    raise CliError(f"[ERROR] Unexpected response: {result}")


# ---------------------------------------------------------------------------
# Query and dispatch helpers
# ---------------------------------------------------------------------------

def query(q):
    """Run a Codecks query (uses session token)."""
    result = session_request("/", {"query": q})
    result.pop("_root", None)
    return result


def dispatch(path, data):
    """Generic dispatch call for mutations (uses session token)."""
    return session_request(f"/dispatch/{path}", data)


def warn_if_empty(result, relation):
    """Warn if a query returned no results — likely means the token expired.
    Codecks silently returns empty data instead of 401 when unauthenticated."""
    if relation not in result or not result[relation]:
        print(f"[TOKEN_EXPIRED] The Codecks session token may have expired "
              f"(query returned 0 {relation}s). Please provide a fresh 'at' "
              "cookie from browser DevTools "
              "(Brave > F12 > Network > api.codecks.io request > "
              "Cookie header > at=...).", file=sys.stderr)


# ---------------------------------------------------------------------------
# Token validation
# ---------------------------------------------------------------------------

def _check_token():
    """Validate session token before running a command. Exits if expired."""
    if not config.SESSION_TOKEN or not config.ACCOUNT:
        raise SetupError("[SETUP_NEEDED] No configuration found.\n"
                         "  Run: py codecks_api.py setup")
    try:
        result = session_request("/",
                                 {"query": {"_root": [{"account": ["id"]}]}})
    except SetupError as e:
        raise SetupError(str(e) + "\n  Run: py codecks_api.py setup") from e
    if "account" not in result or not result["account"]:
        raise SetupError("[TOKEN_EXPIRED] Your session token has expired.\n"
                         "  Run: py codecks_api.py setup\n"
                         "  Or update CODECKS_TOKEN in .env manually.")
