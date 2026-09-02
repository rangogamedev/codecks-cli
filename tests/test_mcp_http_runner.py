"""Tests for scripts/run_mcp_http.py transport-security defaults."""

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_mcp_http.py"


@pytest.fixture(scope="module")
def runner():
    """Import scripts/run_mcp_http.py as a module (it is not a package)."""
    spec = importlib.util.spec_from_file_location("_run_mcp_http_under_test", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(spec.name, None)


def test_default_host_is_loopback(runner):
    assert runner.DEFAULT_HOST == "127.0.0.1"


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_loopback_defers_to_the_sdk(runner, host, monkeypatch):
    """The SDK already turns DNS-rebinding protection on for loopback binds."""
    monkeypatch.delenv("MCP_HTTP_ALLOWED_HOSTS", raising=False)
    monkeypatch.delenv("MCP_HTTP_ALLOWED_ORIGINS", raising=False)

    assert runner.build_transport_security(host) is None


def test_non_loopback_enables_protection_with_defaults(runner, monkeypatch):
    monkeypatch.delenv("MCP_HTTP_ALLOWED_HOSTS", raising=False)
    monkeypatch.delenv("MCP_HTTP_ALLOWED_ORIGINS", raising=False)

    settings = runner.build_transport_security("0.0.0.0")

    assert settings is not None
    assert settings.enable_dns_rebinding_protection is True
    assert settings.allowed_hosts == ["localhost:*", "127.0.0.1:*", "[::1]:*"]
    assert settings.allowed_origins == [
        "http://localhost:*",
        "http://127.0.0.1:*",
        "http://[::1]:*",
    ]


def test_non_loopback_honours_env_allowlists(runner, monkeypatch):
    monkeypatch.setenv("MCP_HTTP_ALLOWED_HOSTS", "mcp.internal:8808, mcp.internal:*")
    monkeypatch.setenv("MCP_HTTP_ALLOWED_ORIGINS", "https://mcp.internal")

    settings = runner.build_transport_security("0.0.0.0")

    assert settings is not None
    assert settings.allowed_hosts == ["mcp.internal:8808", "mcp.internal:*"]
    assert settings.allowed_origins == ["https://mcp.internal"]


def test_blank_env_falls_back_to_the_defaults(runner, monkeypatch):
    monkeypatch.setenv("MCP_HTTP_ALLOWED_HOSTS", "   ")
    monkeypatch.setenv("MCP_HTTP_ALLOWED_ORIGINS", "")

    settings = runner.build_transport_security("10.0.0.5")

    assert settings is not None
    assert settings.allowed_hosts == ["localhost:*", "127.0.0.1:*", "[::1]:*"]
    assert settings.allowed_origins == [
        "http://localhost:*",
        "http://127.0.0.1:*",
        "http://[::1]:*",
    ]


def test_main_binds_loopback_by_default(runner, monkeypatch):
    calls = {}

    def fake_run(**kwargs):
        calls.update(kwargs)

    monkeypatch.delenv("MCP_HTTP_HOST", raising=False)
    monkeypatch.delenv("MCP_HTTP_PORT", raising=False)
    monkeypatch.setattr(runner.mcp, "run", lambda **kw: fake_run(**kw))

    runner.main()

    assert calls["host"] == "127.0.0.1"
    assert calls["port"] == 8808
    assert calls["transport"] == "streamable-http"
    assert calls["transport_security"] is None


def test_main_passes_explicit_security_for_a_non_loopback_bind(runner, monkeypatch):
    calls = {}

    monkeypatch.setenv("MCP_HTTP_HOST", "0.0.0.0")
    monkeypatch.setenv("MCP_HTTP_PORT", "9000")
    monkeypatch.delenv("MCP_HTTP_ALLOWED_HOSTS", raising=False)
    monkeypatch.delenv("MCP_HTTP_ALLOWED_ORIGINS", raising=False)
    monkeypatch.setattr(runner.mcp, "run", lambda **kw: calls.update(kw))

    runner.main()

    assert calls["host"] == "0.0.0.0"
    assert calls["port"] == 9000
    settings = calls["transport_security"]
    assert settings is not None
    assert settings.enable_dns_rebinding_protection is True
