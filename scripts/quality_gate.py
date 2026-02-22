"""Run all quality checks and report results as JSON.

Usage:
    py scripts/quality_gate.py              # run all, JSON output
    py scripts/quality_gate.py --skip-tests # skip pytest (fast)
    py scripts/quality_gate.py --fix        # auto-fix ruff issues first
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Mypy modules — keep in sync with CLAUDE.md
MYPY_TARGETS = [
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
    "codecks_cli/setup_wizard.py",
]


def _run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:
    """Run a subprocess with standard settings."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=300,
        **kwargs,  # type: ignore[arg-type]
    )


def check_ruff_lint(fix: bool = False) -> dict:
    """Run ruff lint check."""
    t0 = time.monotonic()
    if fix:
        _run([sys.executable, "-m", "ruff", "check", "--fix", "."])
    r = _run([sys.executable, "-m", "ruff", "check", "."])
    duration = round(time.monotonic() - t0, 1)

    errors = 0
    if r.returncode != 0:
        # Count error lines (lines starting with a file path)
        for line in r.stdout.splitlines():
            if re.match(r"^\S+:\d+:\d+:", line):
                errors += 1

    return {
        "status": "pass" if r.returncode == 0 else "fail",
        "errors": errors,
        "duration_s": duration,
        "output": r.stdout.strip() if r.returncode != 0 else "",
    }


def check_ruff_format() -> dict:
    """Run ruff format check."""
    t0 = time.monotonic()
    r = _run([sys.executable, "-m", "ruff", "format", "--check", "."])
    duration = round(time.monotonic() - t0, 1)

    files_to_reformat = 0
    if r.returncode != 0:
        # Count lines like "Would reformat: ..."
        for line in r.stderr.splitlines() + r.stdout.splitlines():
            if line.startswith("Would reformat"):
                files_to_reformat += 1

    return {
        "status": "pass" if r.returncode == 0 else "fail",
        "files_to_reformat": files_to_reformat,
        "duration_s": duration,
        "output": r.stderr.strip() if r.returncode != 0 else "",
    }


def check_mypy() -> dict:
    """Run mypy type check."""
    t0 = time.monotonic()
    cmd = [sys.executable, "-m", "mypy"] + MYPY_TARGETS
    r = _run(cmd)
    duration = round(time.monotonic() - t0, 1)

    errors = 0
    if r.returncode != 0:
        # Count lines containing ": error:" pattern
        for line in r.stdout.splitlines():
            if ": error:" in line:
                errors += 1

    return {
        "status": "pass" if r.returncode == 0 else "fail",
        "errors": errors,
        "duration_s": duration,
        "output": r.stdout.strip() if r.returncode != 0 else "",
    }


def check_pytest() -> dict:
    """Run pytest."""
    t0 = time.monotonic()
    r = _run([sys.executable, "-m", "pytest", "tests/", "-q", "--no-header", "--tb=short"])
    duration = round(time.monotonic() - t0, 1)

    passed = 0
    failed = 0
    # Parse summary line: "588 passed" or "3 failed, 585 passed"
    for line in reversed(r.stdout.strip().splitlines()):
        m_passed = re.search(r"(\d+)\s+passed", line)
        m_failed = re.search(r"(\d+)\s+failed", line)
        if m_passed:
            passed = int(m_passed.group(1))
        if m_failed:
            failed = int(m_failed.group(1))
        if m_passed or m_failed:
            break

    result: dict = {
        "status": "pass" if r.returncode == 0 else "fail",
        "passed": passed,
        "failed": failed,
        "duration_s": duration,
    }
    if r.returncode != 0:
        result["output"] = r.stdout.strip()[-2000:]  # Last 2000 chars on failure
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run all quality checks")
    parser.add_argument("--skip-tests", action="store_true", help="Skip pytest")
    parser.add_argument("--fix", action="store_true", help="Auto-fix ruff issues first")
    args = parser.parse_args()

    t0 = time.monotonic()
    checks: dict[str, dict] = {}

    print("Running ruff lint...", file=sys.stderr)
    checks["ruff_lint"] = check_ruff_lint(fix=args.fix)

    print("Running ruff format...", file=sys.stderr)
    checks["ruff_format"] = check_ruff_format()

    print("Running mypy...", file=sys.stderr)
    checks["mypy"] = check_mypy()

    if args.skip_tests:
        checks["pytest"] = {"status": "skip", "reason": "--skip-tests"}
    else:
        print("Running pytest...", file=sys.stderr)
        checks["pytest"] = check_pytest()

    total_duration = round(time.monotonic() - t0, 1)

    # Determine overall status
    statuses = [c["status"] for c in checks.values()]
    if all(s in ("pass", "skip") for s in statuses):
        overall = "pass"
    else:
        overall = "fail"

    # Strip output from passing checks to keep JSON compact
    for check in checks.values():
        if check.get("status") == "pass":
            check.pop("output", None)

    result = {
        "overall": overall,
        "checks": checks,
        "total_duration_s": total_duration,
    }

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
