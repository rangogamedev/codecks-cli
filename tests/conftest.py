"""
Shared test fixtures for codecks-cli tests.
Patches config module to avoid loading real .env and making API calls.
"""

import os

import pytest

_TEST_CACHE_FILE = "__test_no_cache__.json"


@pytest.fixture(autouse=True)
def _isolate_config(monkeypatch):
    """Ensure every test starts with a clean config state.
    Prevents tests from reading the real .env or sharing cached data."""
    from codecks_cli import config

    monkeypatch.setattr(config, "env", {})
    monkeypatch.setattr(config, "SESSION_TOKEN", "fake-token")
    monkeypatch.setattr(config, "ACCESS_KEY", "fake-key")
    monkeypatch.setattr(config, "REPORT_TOKEN", "fake-report")
    monkeypatch.setattr(config, "ACCOUNT", "fake-account")
    monkeypatch.setattr(config, "USER_ID", "fake-user-id")
    monkeypatch.setattr(config, "_cache", {})
    monkeypatch.setattr(config, "RUNTIME_STRICT", False)
    monkeypatch.setattr(config, "RUNTIME_DRY_RUN", False)
    monkeypatch.setattr(config, "RUNTIME_QUIET", False)
    monkeypatch.setattr(config, "RUNTIME_VERBOSE", False)

    # Attachment allowlist must not leak in from the developer's environment
    monkeypatch.delenv("CODECKS_ATTACH_ALLOW_DIRS", raising=False)

    # Reset the client singleton so tests don't share state
    from codecks_cli import commands

    monkeypatch.setattr(commands, "_client_instance", None)

    # Reset MCP snapshot cache, agent sessions, and prevent disk cache from loading
    from codecks_cli.mcp_server import _core

    _core._invalidate_cache()
    _core._reset_sessions()
    monkeypatch.setattr(_core, "CACHE_PATH", _TEST_CACHE_FILE)

    # Delete stale test cache file if a previous test run created it
    try:
        os.unlink(_TEST_CACHE_FILE)
    except OSError:
        pass

    yield

    # Cleanup: remove cache file if warm_cache tests wrote it during this test
    try:
        os.unlink(_TEST_CACHE_FILE)
    except OSError:
        pass
