"""
codecks-cli exception hierarchy.

All custom exceptions live here to avoid circular imports.
"""


class CliError(Exception):
    """Exit code 1 — validation, not-found, network, parse errors."""

    exit_code = 1

    def __init__(self, message, *, recovery_hint=None, error_code=None, retryable=False):
        super().__init__(message)
        self.recovery_hint = recovery_hint
        # Machine-readable code for JSON/MCP errors (e.g. RATE_LIMITED); None = generic.
        self.error_code = error_code
        self.retryable = retryable


class SetupError(CliError):
    """Exit code 2 — token expired, no config."""

    exit_code = 2


class HTTPError(Exception):
    """Raised by _http_request for HTTP errors that callers want to handle."""

    def __init__(self, code, reason, body, headers=None):
        self.code = code
        self.reason = reason
        self.body = body
        self.headers = headers or {}
