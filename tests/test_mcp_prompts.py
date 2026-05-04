"""Tests for MCP prompt helpers without requiring the optional mcp package."""

import importlib.util
from pathlib import Path


def _load_prompts_module():
    path = Path(__file__).resolve().parent.parent / "codecks_cli" / "mcp_server" / "_prompts.py"
    spec = importlib.util.spec_from_file_location("codecks_cli_mcp_prompts_test", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pm_session_reads_playbook():
    mod = _load_prompts_module()
    text = mod.pm_session()
    assert "Session Start" in text
    assert "standup" in text
    assert "get_account" in text


def test_setup_guide_mentions_cli_first_and_setup():
    mod = _load_prompts_module()
    text = mod.setup_guide()
    assert "codecks-cli setup" in text
    assert "codecks-cli agent-init --agent" in text
    assert "Use the CLI first" in text


def test_register_uses_prompt_names_when_available():
    mod = _load_prompts_module()
    seen = []

    class FakeMCP:
        def prompt(self, name=None):
            def decorator(fn):
                seen.append((name, fn.__name__))
                return fn

            return decorator

    mod.register(FakeMCP())
    assert ("pm-session", "pm_session") in seen
    assert ("setup-guide", "setup_guide") in seen
