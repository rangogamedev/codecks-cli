"""Check documentation files for stale counts and mismatches.

Usage:
    py scripts/validate_docs.py              # full report (JSON)
    py scripts/validate_docs.py --fix        # auto-fix stale counts in-place
    py scripts/validate_docs.py --fix-list   # show what needs fixing (human-readable)
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "codecks_cli"

# Files that contain historical version-specific counts (don't validate)
_SKIP_FILES = {"CHANGELOG.md"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _doc_files() -> list[Path]:
    """All markdown docs that should have accurate counts."""
    return [p for p in sorted(ROOT.glob("*.md")) if p.name not in _SKIP_FILES]


def _scan_docs(
    pattern: str,
    actual: int,
    field: str,
    *,
    skip_line: re.Pattern[str] | None = None,
) -> list[dict]:
    """Scan all doc files for a numeric pattern and flag mismatches.

    Args:
        pattern: Regex with one capture group for the number.
        actual: The ground-truth count.
        field: Name for the issue report (e.g., "mcp_tool_count").
        skip_line: Optional compiled regex — skip lines that match.

    Returns:
        List of issue dicts for mismatched counts.
    """
    issues: list[dict] = []
    compiled = re.compile(pattern)
    for path in _doc_files():
        for line_num, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if skip_line and skip_line.search(line):
                continue
            for m in compiled.finditer(line):
                found = int(m.group(1))
                if found != actual:
                    issues.append(
                        {
                            "file": f"{path.name}:{line_num}",
                            "field": field,
                            "expected": actual,
                            "found": found,
                        }
                    )
    return issues


def _fix_issues(issues: list[dict]) -> int:
    """Auto-fix stale counts by replacing old values in doc files.

    Returns number of files modified.
    """
    # Group issues by file
    by_file: dict[str, list[dict]] = {}
    for issue in issues:
        fname = issue["file"].split(":")[0]
        by_file.setdefault(fname, []).append(issue)

    modified = 0
    for fname, file_issues in by_file.items():
        path = ROOT / fname
        if not path.exists():
            continue
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        changed = False
        for issue in file_issues:
            line_num = int(issue["file"].split(":")[1])
            old_val = str(issue["found"])
            new_val = str(issue["expected"])
            idx = line_num - 1
            if 0 <= idx < len(lines) and old_val in lines[idx]:
                lines[idx] = lines[idx].replace(old_val, new_val, 1)
                changed = True
        if changed:
            path.write_text("".join(lines), encoding="utf-8")
            modified += 1
    return modified


# ---------------------------------------------------------------------------
# Ground truth scanners
# ---------------------------------------------------------------------------


def _actual_version() -> str:
    m = re.search(
        r'^VERSION\s*=\s*"([^"]+)"',
        (PKG / "config.py").read_text(encoding="utf-8"),
        re.M,
    )
    return m.group(1) if m else ""


def _actual_pyproject_version() -> str:
    m = re.search(
        r'^version\s*=\s*"([^"]+)"',
        (ROOT / "pyproject.toml").read_text(encoding="utf-8"),
        re.M,
    )
    return m.group(1) if m else ""


def _actual_test_count() -> int:
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q", "--no-header"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(ROOT),
        )
        for line in reversed(r.stdout.strip().splitlines()):
            m = re.search(r"(\d+)\s+tests?\s+collected", line)
            if m:
                return int(m.group(1))
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return 0


def _actual_mcp_tool_count() -> int:
    mcp_dir = PKG / "mcp_server"
    if mcp_dir.is_dir():
        count = 0
        for py_file in mcp_dir.glob("*.py"):
            count += len(re.findall(r"mcp\.tool\(\)", py_file.read_text(encoding="utf-8")))
        return count
    mcp_path = PKG / "mcp_server.py"
    if mcp_path.exists():
        return len(re.findall(r"mcp\.tool\(\)", mcp_path.read_text(encoding="utf-8")))
    return 0


def _actual_source_module_count() -> int:
    count = 0
    if (ROOT / "codecks_api.py").exists():
        count += 1
    count += len(list(PKG.glob("*.py")))
    for subpkg in ["formatters", "mcp_server"]:
        subdir = PKG / subpkg
        if subdir.is_dir():
            count += len(list(subdir.glob("*.py")))
    return count


def _actual_client_methods() -> int:
    client_path = PKG / "client.py"
    if not client_path.exists():
        return 0
    content = client_path.read_text(encoding="utf-8")
    return len(re.findall(r"^    def (?!_)[a-z]\w+\(", content, re.M))


def _actual_formatter_count() -> int:
    """Count formatter sub-modules (excluding __init__.py)."""
    fmt_dir = PKG / "formatters"
    if not fmt_dir.is_dir():
        return 0
    return len([f for f in fmt_dir.glob("*.py") if f.name != "__init__.py"])


def _actual_mcp_module_count() -> int:
    """Count MCP tool module files (_tools_*.py)."""
    mcp_dir = PKG / "mcp_server"
    if not mcp_dir.is_dir():
        return 0
    return len(list(mcp_dir.glob("_tools_*.py")))


def _actual_mypy_command() -> str:
    """Build the canonical mypy command from quality_gate.py MYPY_TARGETS."""
    qg_path = ROOT / "scripts" / "quality_gate.py"
    if qg_path.exists():
        content = qg_path.read_text(encoding="utf-8")
        m = re.search(r"MYPY_TARGETS\s*=\s*\[(.*?)\]", content, re.S)
        if m:
            targets = re.findall(r'"([^"]+)"', m.group(1))
            return f"py -m mypy {' '.join(targets)}"
    return "py -m mypy"


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_version_sync() -> list[dict]:
    """Check version consistency across config.py and pyproject.toml."""
    issues = []
    cv = _actual_version()
    pv = _actual_pyproject_version()
    if cv != pv:
        issues.append(
            {
                "file": "config.py vs pyproject.toml",
                "field": "version",
                "expected": cv,
                "found": pv,
            }
        )
    return issues


def check_test_counts() -> list[dict]:
    """Check test counts in all doc files."""
    actual = _actual_test_count()
    if actual == 0:
        return [
            {
                "file": "(pytest)",
                "field": "test_count",
                "expected": "?",
                "found": "0 (collection failed)",
            }
        ]
    return _scan_docs(r"(\d+)\s+tests", actual, "test_count")


def check_mcp_counts() -> list[dict]:
    """Check MCP tool counts in all doc files.

    Skips:
    - Lines about removed tools (historical)
    - Counts < 20 (always sub-counts: category breakdowns, section headers,
      table cells). Total tool count has never been below 28.
    """
    actual = _actual_mcp_tool_count()
    skip = re.compile(r"removed", re.I)

    issues: list[dict] = []
    pattern = re.compile(r"(\d+)\s+(?:MCP\s+)?tools")
    for path in _doc_files():
        for line_num, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if skip.search(line):
                continue
            for m in pattern.finditer(line):
                found = int(m.group(1))
                if found == actual:
                    continue
                # Sub-counts are always < 20 (category breakdowns, section headers)
                if found < 20:
                    continue
                issues.append(
                    {
                        "file": f"{path.name}:{line_num}",
                        "field": "mcp_tool_count",
                        "expected": actual,
                        "found": found,
                    }
                )
    return issues


def check_module_counts() -> list[dict]:
    """Check source module counts in all doc files."""
    return _scan_docs(
        r"(\d+)\s+source modules",
        _actual_source_module_count(),
        "source_module_count",
    )


def check_client_methods() -> list[dict]:
    """Check CodecksClient method count in all doc files."""
    return _scan_docs(
        r"(\d+)\s+(?:core\s+|public\s+|CodecksClient\s+)?methods",
        _actual_client_methods(),
        "client_methods",
    )


def check_formatter_count() -> list[dict]:
    """Check formatter sub-module count in all doc files."""
    return _scan_docs(
        r"(\d+)\s+sub-modules",
        _actual_formatter_count(),
        "formatter_count",
    )


def check_mcp_module_count() -> list[dict]:
    """Check MCP tool module count in all doc files."""
    return _scan_docs(
        r"(\d+)\s+tool modules",
        _actual_mcp_module_count(),
        "mcp_module_count",
    )


def check_mypy_sync() -> list[dict]:
    """Check mypy command consistency across doc/skill files."""
    canonical = _actual_mypy_command()
    issues = []

    files_to_check = [
        ROOT / "CLAUDE.md",
        ROOT / ".claude" / "commands" / "quality.md",
        ROOT / ".claude" / "commands" / "release.md",
        ROOT / ".github" / "workflows" / "test.yml",
    ]

    for path in files_to_check:
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        for m in re.finditer(r"(py -m mypy\s+[^\n]+)", content):
            found = re.sub(r"[`)\s]+$", "", m.group(1)).strip()
            found = re.split(r"\s+&&\s+|\s+\|\s+", found)[0].strip()
            if found != canonical:
                offset = m.start()
                line_num = content[:offset].count("\n") + 1
                issues.append(
                    {
                        "file": f"{path.name}:{line_num}",
                        "field": "mypy_command",
                        "expected": canonical,
                        "found": found,
                    }
                )
    return issues


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate documentation consistency")
    parser.add_argument("--fix-list", action="store_true", help="Show what needs fixing")
    parser.add_argument("--fix", action="store_true", help="Auto-fix stale counts in-place")
    args = parser.parse_args()

    all_issues: list[dict] = []

    checks = [
        ("version_sync", check_version_sync),
        ("test_counts", check_test_counts),
        ("mcp_tool_counts", check_mcp_counts),
        ("module_counts", check_module_counts),
        ("client_methods", check_client_methods),
        ("formatter_count", check_formatter_count),
        ("mcp_module_count", check_mcp_module_count),
        ("mypy_sync", check_mypy_sync),
    ]

    results: dict[str, dict] = {}
    for name, fn in checks:
        issues = fn()
        all_issues.extend(issues)
        results[name] = {
            "status": "pass" if not issues else "mismatch",
            "issues": issues,
        }

    passed = sum(1 for r in results.values() if r["status"] == "pass")
    total = len(results)

    # Auto-fix mode
    if args.fix and all_issues:
        # Only fix numeric count mismatches (skip version_sync and mypy_sync)
        fixable = [i for i in all_issues if isinstance(i.get("expected"), int)]
        if fixable:
            modified = _fix_issues(fixable)
            print(f"Fixed {len(fixable)} issues in {modified} files.", file=sys.stderr)
            # Re-run to verify
            print("Re-validating...", file=sys.stderr)
            main_args = sys.argv
            sys.argv = [sys.argv[0]]  # strip --fix for re-run
            main()
            sys.argv = main_args
            return

    report = {
        "overall": "pass" if not all_issues else "mismatch",
        "summary": f"{passed}/{total} checks passed",
        "total_issues": len(all_issues),
        "checks": results,
    }

    if args.fix_list and all_issues:
        print("Issues to fix:", file=sys.stderr)
        for issue in all_issues:
            print(
                f"  {issue['file']}: {issue['field']} — "
                f"expected {issue['expected']}, found {issue['found']}",
                file=sys.stderr,
            )
        print(file=sys.stderr)

    print(json.dumps(report, indent=2))
    sys.exit(0 if not all_issues else 1)


if __name__ == "__main__":
    main()
