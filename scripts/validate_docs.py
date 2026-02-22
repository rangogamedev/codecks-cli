"""Check documentation files for stale counts and mismatches.

Usage:
    py scripts/validate_docs.py              # full report
    py scripts/validate_docs.py --fix-list   # show what needs fixing
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "codecks_cli"


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
    mcp_path = PKG / "mcp_server.py"
    if not mcp_path.exists():
        return 0
    return len(re.findall(r"@mcp\.tool\(\)", mcp_path.read_text(encoding="utf-8")))


def _actual_test_file_count() -> int:
    return len(list((ROOT / "tests").glob("test_*.py")))


def _actual_source_module_count() -> int:
    count = 0
    if (ROOT / "codecks_api.py").exists():
        count += 1
    count += len(list(PKG.glob("*.py")))
    formatters = PKG / "formatters"
    if formatters.is_dir():
        count += len(list(formatters.glob("*.py")))
    return count


def _actual_client_methods() -> int:
    client_path = PKG / "client.py"
    if not client_path.exists():
        return 0
    content = client_path.read_text(encoding="utf-8")
    # Count public methods — handles multi-line signatures (self on next line)
    return len(re.findall(r"^    def [a-z]\w+\(", content, re.M))


def _actual_mypy_command() -> str:
    """Build the canonical mypy command."""
    modules = [
        "codecks_cli/api.py",
        "codecks_cli/cards.py",
        "codecks_cli/client.py",
        "codecks_cli/commands.py",
        "codecks_cli/formatters/",
        "codecks_cli/models.py",
        "codecks_cli/exceptions.py",
        "codecks_cli/_utils.py",
        "codecks_cli/types.py",
        "codecks_cli/planning.py",
    ]
    return f"py -m mypy {' '.join(modules)}"


# ---------------------------------------------------------------------------
# Doc scanners
# ---------------------------------------------------------------------------


def _find_numbers_in_file(path: Path, patterns: dict[str, str]) -> dict[str, list[tuple[int, str]]]:
    """Find occurrences of numeric patterns in a file.

    Returns {pattern_name: [(line_number, matched_value), ...]}.
    """
    results: dict[str, list[tuple[int, str]]] = {k: [] for k in patterns}
    if not path.exists():
        return results
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        for name, pat in patterns.items():
            for m in re.finditer(pat, line):
                results[name].append((i, m.group(1)))
    return results


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
    """Check test counts in doc files."""
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

    issues = []
    doc_files = {
        "CLAUDE.md": r"(\d+)\s+tests",
        "HANDOFF.md": r"(\d+)\s+tests",
        "CONTRIBUTING.md": r"\*\*(\d+)\s+tests\*\*",
        "README.md": r"(\d+)\s+(?:pytest\s+)?tests",
    }

    for fname, pattern in doc_files.items():
        path = ROOT / fname
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        for m in re.finditer(pattern, content):
            found = int(m.group(1))
            if found != actual:
                # Find line number
                offset = m.start()
                line_num = content[:offset].count("\n") + 1
                issues.append(
                    {
                        "file": f"{fname}:{line_num}",
                        "field": "test_count",
                        "expected": actual,
                        "found": found,
                    }
                )
    return issues


def check_mcp_counts() -> list[dict]:
    """Check MCP tool counts in doc files."""
    actual = _actual_mcp_tool_count()
    issues = []

    doc_files = ["CLAUDE.md", "HANDOFF.md", "README.md"]
    pattern = r"(\d+)\s+tools"

    for fname in doc_files:
        path = ROOT / fname
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        for m in re.finditer(pattern, content):
            found = int(m.group(1))
            if found != actual:
                offset = m.start()
                line_num = content[:offset].count("\n") + 1
                issues.append(
                    {
                        "file": f"{fname}:{line_num}",
                        "field": "mcp_tool_count",
                        "expected": actual,
                        "found": found,
                    }
                )
    return issues


def check_module_counts() -> list[dict]:
    """Check source module counts in doc files."""
    actual = _actual_source_module_count()
    issues = []

    scan = {
        "HANDOFF.md": r"(\d+)\s+source modules",
        "CONTRIBUTING.md": r"(\d+)\s+source modules",
    }

    for fname, pattern in scan.items():
        path = ROOT / fname
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        for m in re.finditer(pattern, content):
            found = int(m.group(1))
            if found != actual:
                offset = m.start()
                line_num = content[:offset].count("\n") + 1
                issues.append(
                    {
                        "file": f"{fname}:{line_num}",
                        "field": "source_module_count",
                        "expected": actual,
                        "found": found,
                    }
                )
    return issues


def check_client_methods() -> list[dict]:
    """Check CodecksClient method count in doc files."""
    actual = _actual_client_methods()
    issues = []

    scan = {"HANDOFF.md": r"(\d+)\s+(?:CodecksClient\s+)?methods"}
    for fname, pattern in scan.items():
        path = ROOT / fname
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        for m in re.finditer(pattern, content):
            found = int(m.group(1))
            if found != actual:
                offset = m.start()
                line_num = content[:offset].count("\n") + 1
                issues.append(
                    {
                        "file": f"{fname}:{line_num}",
                        "field": "client_methods",
                        "expected": actual,
                        "found": found,
                    }
                )
    return issues


def check_mypy_sync() -> list[dict]:
    """Check mypy command consistency across doc/skill files."""
    canonical = _actual_mypy_command()
    issues = []

    files_to_check = [
        ROOT / "CLAUDE.md",
        ROOT / "PROJECT_INDEX.md",
        ROOT / ".claude" / "commands" / "quality.md",
        ROOT / ".claude" / "commands" / "release.md",
        ROOT / ".github" / "workflows" / "test.yml",
    ]

    for path in files_to_check:
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        # Look for mypy invocations (strip trailing markdown like ` or ))
        for m in re.finditer(r"(py -m mypy\s+[^\n]+)", content):
            found = re.sub(r"[`)\s]+$", "", m.group(1)).strip()
            # Stop at && or | (chained commands)
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
    args = parser.parse_args()

    all_issues: list[dict] = []

    checks = [
        ("version_sync", check_version_sync),
        ("test_counts", check_test_counts),
        ("mcp_tool_counts", check_mcp_counts),
        ("module_counts", check_module_counts),
        ("client_methods", check_client_methods),
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
