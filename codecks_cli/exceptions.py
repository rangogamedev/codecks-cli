"""
codecks-cli exception hierarchy.

All custom exceptions live here to avoid circular imports.
"""


class CliError(Exception):
    """Exit code 1 — validation, not-found, network, parse errors."""

    exit_code = 1


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
