"""Run all quality checks and report results as JSON.

Usage:
    py scripts/quality_gate.py              # run all, JSON output
    py scripts/quality_gate.py --skip-tests # skip pytest (fast)
    py scripts/quality_gate.py --fix        # auto-fix ruff issues first
    py scripts/quality_gate.py --coverage   # include coverage XML output
    py scripts/quality_gate.py --docker-smoke # run Docker smoke checks too
    py scripts/quality_gate.py --mypy-only  # run just mypy (raw output)
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Mypy modules — keep in sync with CLAUDE.md
MYPY_TARGETS = [
    "codecks_cli/api.py",
    "codecks_cli/attachments.py",
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
    "codecks_cli/lanes.py",
    "codecks_cli/tags.py",
    "codecks_cli/scaffolding.py",
    "codecks_cli/_content.py",
    "codecks_cli/cli.py",
    "codecks_cli/config.py",
    "codecks_cli/_operations.py",
    "codecks_cli/_last_result.py",
    "codecks_cli/admin.py",
    "codecks_cli/gdd.py",
    "codecks_cli/store.py",
    "codecks_cli/mcp_server/",
]


def _run(cmd: list[str], timeout: int = 300, **kwargs: object) -> subprocess.CompletedProcess:
    """Run a subprocess with standard settings."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(ROOT),
        timeout=timeout,
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


def check_docs() -> dict:
    """Run documentation consistency checks."""
    t0 = time.monotonic()
    r = _run([sys.executable, "scripts/validate_docs.py"])
    duration = round(time.monotonic() - t0, 1)

    issues = 0
    if r.stdout:
        try:
            data = json.loads(r.stdout)
            issues = int(data.get("total_issues", 0))
        except (json.JSONDecodeError, TypeError, ValueError):
            issues = 0

    return {
        "status": "pass" if r.returncode == 0 else "fail",
        "issues": issues,
        "duration_s": duration,
        "output": (r.stdout or r.stderr).strip() if r.returncode != 0 else "",
    }


def check_pytest(coverage: bool = False) -> dict:
    """Run pytest."""
    t0 = time.monotonic()
    basetemp_root = ROOT / ".tmp" / "quality-gate" / "pytest"
    temp_root = ROOT / ".tmp" / "quality-gate" / "temp"
    basetemp_root.mkdir(parents=True, exist_ok=True)
    temp_root.mkdir(parents=True, exist_ok=True)
    basetemp = basetemp_root / f"run-{time.strftime('%Y%m%d%H%M%S')}-{os.getpid()}"
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/",
        "-q",
        "--no-header",
        "--tb=short",
        "--basetemp",
        str(basetemp),
    ]
    if coverage:
        cmd.extend(["--cov=codecks_cli", "--cov-report=xml"])
    env = os.environ.copy()
    # Windows-native runs benefit from keeping temp on the project NTFS volume.
    # Linux/macOS (including WSL, which reports sys.platform == "linux") must
    # use the system temp dir — pointing TMPDIR at a WSL bind-mount path
    # breaks pytest's capture system (FileNotFoundError on tmpfile.truncate).
    if sys.platform == "win32":
        temp_root_str = str(temp_root)
        env.update({"TEMP": temp_root_str, "TMP": temp_root_str, "TMPDIR": temp_root_str})
    r = _run(cmd, env=env)
    duration = round(time.monotonic() - t0, 1)

    passed = 0
    failed = 0
    errors = 0
    # Parse summary line: "588 passed" or "3 failed, 585 passed" or "2 errors".
    for line in reversed(r.stdout.strip().splitlines()):
        m_passed = re.search(r"(\d+)\s+passed", line)
        m_failed = re.search(r"(\d+)\s+failed", line)
        m_errors = re.search(r"(\d+)\s+errors?", line)
        if m_passed:
            passed = int(m_passed.group(1))
        if m_failed:
            failed = int(m_failed.group(1))
        if m_errors:
            errors = int(m_errors.group(1))
        if m_passed or m_failed or m_errors:
            break

    result: dict = {
        "status": "pass" if r.returncode == 0 else "fail",
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "duration_s": duration,
        "coverage": coverage,
        "basetemp": str(basetemp.relative_to(ROOT)),
    }
    if r.returncode != 0:
        output = "\n".join(part for part in (r.stdout.strip(), r.stderr.strip()) if part)
        result["output"] = output[-4000:]  # Last 4000 chars on failure
    return result


def check_docker_smoke() -> dict:
    """Run the Docker smoke checks used by CI."""
    t0 = time.monotonic()
    commands = [
        ["docker", "compose", "build"],
        ["docker", "compose", "run", "--rm", "test"],
        ["docker", "compose", "run", "--rm", "cli", "--version"],
    ]
    outputs: list[str] = []
    for cmd in commands:
        r = _run(cmd, timeout=900)
        if r.stdout:
            outputs.append(r.stdout.strip())
        if r.stderr:
            outputs.append(r.stderr.strip())
        if r.returncode != 0:
            return {
                "status": "fail",
                "command": " ".join(cmd),
                "duration_s": round(time.monotonic() - t0, 1),
                "output": "\n".join(outputs)[-2000:],
            }
    return {
        "status": "pass",
        "duration_s": round(time.monotonic() - t0, 1),
    }


def run_mypy_only() -> None:
    """Run just mypy with raw output and propagate exit code."""
    cmd = [sys.executable, "-m", "mypy"] + MYPY_TARGETS
    r = subprocess.run(cmd, cwd=str(ROOT))
    sys.exit(r.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run all quality checks")
    parser.add_argument("--skip-tests", action="store_true", help="Skip pytest")
    parser.add_argument("--fix", action="store_true", help="Auto-fix ruff issues first")
    parser.add_argument("--coverage", action="store_true", help="Include coverage XML output")
    parser.add_argument("--docker-smoke", action="store_true", help="Run Docker smoke checks")
    parser.add_argument("--mypy-only", action="store_true", help="Run just mypy (raw output)")
    args = parser.parse_args()

    if args.mypy_only:
        run_mypy_only()
        return

    t0 = time.monotonic()
    checks: dict[str, dict] = {}

    print("Running ruff lint...", file=sys.stderr)
    checks["ruff_lint"] = check_ruff_lint(fix=args.fix)

    print("Running ruff format...", file=sys.stderr)
    checks["ruff_format"] = check_ruff_format()

    print("Running mypy...", file=sys.stderr)
    checks["mypy"] = check_mypy()

    print("Running docs validation...", file=sys.stderr)
    checks["docs"] = check_docs()

    if args.skip_tests:
        checks["pytest"] = {"status": "skip", "reason": "--skip-tests"}
    else:
        print("Running pytest...", file=sys.stderr)
        checks["pytest"] = check_pytest(coverage=args.coverage)

    if args.docker_smoke:
        print("Running Docker smoke checks...", file=sys.stderr)
        checks["docker_smoke"] = check_docker_smoke()

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
