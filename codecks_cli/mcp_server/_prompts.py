"""Prompt helpers for MCP clients.

Prompts are an enhancement layer for MCP-native editors. The CLI remains the
recommended default for low-token agent workflows.
"""

from collections.abc import Callable
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_PLAYBOOK_PATH = _ROOT / "pm_playbook.md"


def _read_playbook() -> str:
    """Read the packaged PM playbook, with a small fallback on failure."""
    try:
        return _PLAYBOOK_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        return (
            "PM playbook is unavailable.\n"
            f"Error: {exc}\n"
            "Fallback: start with `codecks-cli agent-init --agent`."
        )


def pm_session() -> str:
    """CLI-first PM session prompt for connected MCP clients."""
    return _read_playbook()


def setup_guide() -> str:
    """Compact setup prompt for connected MCP clients."""
    return (
        "Set up codecks-cli with a CLI-first workflow.\n\n"
        "1. Install: `py -m pip install codecks-cli`\n"
        "2. Configure auth: `codecks-cli setup`\n"
        "3. Verify: `codecks-cli agent-init --agent`\n"
        '4. Optional MCP: `py -m pip install "codecks-cli[mcp]"`\n\n'
        "Rules:\n"
        "- Never ask the user to paste tokens into chat.\n"
        "- Prefer `codecks-cli setup` over manual secret entry in conversation.\n"
        "- Use the CLI first for routine PM work.\n"
        "- Use MCP when you need cache-heavy reads, prompts, or team coordination.\n"
    )


def _register_prompt(mcp: object, name: str, fn: Callable[[], str]) -> None:
    """Register a prompt if the FastMCP instance supports prompt decorators."""
    prompt = getattr(mcp, "prompt", None)
    if prompt is None:
        return
    try:
        decorator = prompt(name=name)
    except TypeError:
        decorator = prompt()
    decorator(fn)


def register(mcp: object) -> None:
    """Register prompts with the FastMCP instance when supported."""
    _register_prompt(mcp, "pm-session", pm_session)
    _register_prompt(mcp, "setup-guide", setup_guide)
