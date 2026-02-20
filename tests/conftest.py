"""
Shared test fixtures for codecks-cli tests.
Patches config module to avoid loading real .env and making API calls.
"""

import sys
import os
import types
import pytest

# Add project root to path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def _isolate_config(monkeypatch):
    """Ensure every test starts with a clean config state.
    Prevents tests from reading the real .env or sharing cached data."""
    import config
    monkeypatch.setattr(config, "env", {})
    monkeypatch.setattr(config, "SESSION_TOKEN", "fake-token")
    monkeypatch.setattr(config, "ACCESS_KEY", "fake-key")
    monkeypatch.setattr(config, "REPORT_TOKEN", "fake-report")
    monkeypatch.setattr(config, "ACCOUNT", "fake-account")
    monkeypatch.setattr(config, "USER_ID", "fake-user-id")
    monkeypatch.setattr(config, "_cache", {})
