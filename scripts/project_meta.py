"""Scan codebase and emit project metadata as JSON.

Usage:
    py scripts/project_meta.py              # JSON to stdout
    py scripts/project_meta.py --save       # write .project-meta.json
    py scripts/project_meta.py --field tests.count  # single value
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "codecks_cli"
TESTS = ROOT / "tests"


# ---------------------------------------------------------------------------
# Scanners
# ---------------------------------------------------------------------------


def _version_info() -> dict:
    """Read version from config.py and pyproject.toml."""
    config_ver = ""
    config_path = PKG / "config.py"
    if config_path.exists():
        m = re.search(r'^VERSION\s*=\s*"([^"]+)"', config_path.read_text(encoding="utf-8"), re.M)
        if m:
            config_ver = m.group(1)

    pyproject_ver = ""
    pyproject_path = ROOT / "pyproject.toml"
    if pyproject_path.exists():
        m = re.search(r'^version\s*=\s*"([^"]+)"', pyproject_path.read_text(encoding="utf-8"), re.M)
        if m:
            pyproject_ver = m.group(1)

    return {
        "config": config_ver,
        "pyproject": pyproject_ver,
        "match": config_ver == pyproject_ver and config_ver != "",
    }


def _test_info() -> dict:
    """Count tests via pytest --collect-only."""
    test_files = sorted(p.name for p in TESTS.glob("test_*.py"))
    count = 0
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", str(TESTS), "--collect-only", "-q", "--no-header"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(ROOT),
        )
        # Last non-empty line: "588 tests collected"
        for line in reversed(r.stdout.strip().splitlines()):
            m = re.search(r"(\d+)\s+tests?\s+collected", line)
            if m:
                count = int(m.group(1))
                break
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return {"count": count, "file_count": len(test_files), "files": test_files}


def _mcp_info() -> dict:
    """Count MCP tools by scanning @mcp.tool() decorators."""
    mcp_path = PKG / "mcp_server.py"
    tool_names: list[str] = []
    if mcp_path.exists():
        content = mcp_path.read_text(encoding="utf-8")
        # Match @mcp.tool() followed by def <name>(
        for m in re.finditer(r"@mcp\.tool\(\)\s*\ndef\s+(\w+)\s*\(", content):
            tool_names.append(m.group(1))
    return {"tool_count": len(tool_names), "tool_names": tool_names}


def _mypy_info() -> dict:
    """Build the mypy module list from typed source files."""
    # These are the modules that should be type-checked
    modules: list[str] = []
    # Individual .py files in codecks_cli/ that have type annotations
    typed_files = [
        "api.py",
        "cards.py",
        "client.py",
        "commands.py",
        "models.py",
        "exceptions.py",
        "_utils.py",
        "types.py",
        "planning.py",
    ]
    for f in typed_files:
        if (PKG / f).exists():
            modules.append(f"codecks_cli/{f}")
    # formatters/ directory
    if (PKG / "formatters").is_dir():
        modules.append("codecks_cli/formatters/")

    command = f"py -m mypy {' '.join(modules)}"
    return {"modules": modules, "command": command}


def _source_info() -> dict:
    """Count source modules."""
    count = 0
    # codecks_api.py entry point
    if (ROOT / "codecks_api.py").exists():
        count += 1
    # codecks_cli/*.py
    count += len(list(PKG.glob("*.py")))
    # codecks_cli/formatters/*.py
    formatters = PKG / "formatters"
    if formatters.is_dir():
        count += len(list(formatters.glob("*.py")))
    return {"module_count": count}


def _skills_info() -> list[str]:
    """List skill names from .claude/commands/."""
    commands_dir = ROOT / ".claude" / "commands"
    if not commands_dir.is_dir():
        return []
    return sorted(p.stem for p in commands_dir.glob("*.md"))


def _agents_info() -> list[str]:
    """List agent names from .claude/agents/."""
    agents_dir = ROOT / ".claude" / "agents"
    if not agents_dir.is_dir():
        return []
    return sorted(p.stem for p in agents_dir.glob("*.md"))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def collect_meta() -> dict:
    """Collect all project metadata."""
    return {
        "version": _version_info(),
        "tests": _test_info(),
        "mcp": _mcp_info(),
        "mypy": _mypy_info(),
        "source": _source_info(),
        "skills": _skills_info(),
        "agents": _agents_info(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def get_field(data: dict, dotpath: str) -> object:
    """Resolve a dotted field path like 'tests.count'."""
    parts = dotpath.split(".")
    current: object = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def main() -> None:
    parser = argparse.ArgumentParser(description="Project metadata scanner")
    parser.add_argument("--save", action="store_true", help="Write .project-meta.json")
    parser.add_argument("--field", type=str, help="Extract a single field (dot path)")
    args = parser.parse_args()

    meta = collect_meta()

    if args.field:
        value = get_field(meta, args.field)
        if value is None:
            print(f"Field not found: {args.field}", file=sys.stderr)
            sys.exit(1)
        if isinstance(value, (dict, list)):
            print(json.dumps(value, indent=2))
        else:
            print(value)
        return

    output = json.dumps(meta, indent=2)

    if args.save:
        out_path = ROOT / ".project-meta.json"
        out_path.write_text(output + "\n", encoding="utf-8")
        print(f"Saved to {out_path}")
    else:
        print(output)


if __name__ == "__main__":
    main()
