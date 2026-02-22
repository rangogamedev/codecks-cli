"""File-based planning tools for AI agent sessions.

Provides init, status, update, and measure operations for lean planning
files (task_plan.md, findings.md, progress.md). Used by MCP server tools
and standalone CLI scripts.

All public functions accept a target_dir Path and return dicts compatible
with _finalize_tool_result in the MCP server.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path

PLANNING_FILES = ["task_plan.md", "findings.md", "progress.md"]
METRICS_FILE = ".plan_metrics.jsonl"

# Old template sizes (bytes) — the commented versions with HTML instructions
OLD_TEMPLATE_BYTES = {
    "task_plan.md": 4745,
    "findings.md": 3656,
    "progress.md": 4115,
}
OLD_TOTAL = sum(OLD_TEMPLATE_BYTES.values())  # 12,516 bytes

# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

TASK_PLAN_TEMPLATE = """\
# Task Plan

## Goal
[describe end state]

## Current Phase
Phase 1

## Phases

### Phase 1: Discovery
- [ ] Understand requirements
- [ ] Identify constraints
- [ ] Document in findings.md
- **Status:** in_progress

### Phase 2: Planning
- [ ] Define approach
- [ ] Create structure
- **Status:** pending

### Phase 3: Implementation
- [ ] Execute plan
- [ ] Test incrementally
- **Status:** pending

### Phase 4: Verification
- [ ] Verify requirements met
- [ ] Document results
- **Status:** pending

### Phase 5: Delivery
- [ ] Review outputs
- [ ] Deliver to user
- **Status:** pending

## Decisions
| Decision | Rationale |
|----------|-----------|

## Errors
| Error | Attempt | Resolution |
|-------|---------|------------|
"""

FINDINGS_TEMPLATE = """\
# Findings

## Requirements
-

## Research
-

## Technical Decisions
| Decision | Rationale |
|----------|-----------|

## Issues
| Issue | Resolution |
|-------|------------|

## Resources
-
"""

# {date} placeholder filled at creation time
PROGRESS_TEMPLATE = """\
# Progress Log

## Session: {date}

### Phase 1
- **Status:** in_progress
- Actions:
  -
- Files changed:
  -

## Test Results
| Test | Expected | Actual | Pass? |
|------|----------|--------|-------|

## Files Changed
-
"""

_FILE_TEMPLATES = [
    ("task_plan.md", TASK_PLAN_TEMPLATE),
    ("findings.md", FINDINGS_TEMPLATE),
    ("progress.md", None),  # uses PROGRESS_TEMPLATE with date
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English/markdown."""
    return len(text) // 4


def append_table_row(content: str, header_pattern: str, row: str) -> str:
    """Append a row to a markdown table identified by a header cell pattern.

    Finds the table whose header line contains header_pattern, then inserts
    the new row after the last existing data row (or after the separator
    if the table is empty).
    """
    lines = content.splitlines(keepends=True)
    header_idx = None
    for i, line in enumerate(lines):
        if header_pattern in line and line.strip().startswith("|"):
            header_idx = i
            break
    if header_idx is None:
        return content

    # Separator is the line right after header
    sep_idx = header_idx + 1

    # Walk past existing data rows
    insert_idx = sep_idx + 1
    while insert_idx < len(lines) and lines[insert_idx].strip().startswith("|"):
        insert_idx += 1

    lines.insert(insert_idx, row + "\n")
    return "".join(lines)


def append_to_section(content: str, section_header: str, bullet: str) -> str:
    """Append a bullet to a markdown section, replacing placeholder if needed.

    Looks for '## <section_header>' and adds '- <bullet>' either by replacing
    a lone '-' placeholder or by inserting after the last existing bullet.
    """
    lines = content.splitlines(keepends=True)
    section_idx = None
    for i, line in enumerate(lines):
        if line.strip() == f"## {section_header}":
            section_idx = i
            break
    if section_idx is None:
        return content

    # Find section end (next ## heading or EOF)
    end_idx = len(lines)
    for i in range(section_idx + 1, len(lines)):
        if lines[i].startswith("## "):
            end_idx = i
            break

    # Scan for bullets and placeholder within section
    last_bullet_idx = None
    placeholder_idx = None
    for i in range(section_idx + 1, end_idx):
        stripped = lines[i].strip()
        if stripped == "-":
            placeholder_idx = i
        elif stripped.startswith("- "):
            last_bullet_idx = i

    if placeholder_idx is not None and last_bullet_idx is None:
        # Replace lone placeholder with real content
        lines[placeholder_idx] = f"- {bullet}\n"
    elif last_bullet_idx is not None:
        lines.insert(last_bullet_idx + 1, f"- {bullet}\n")
    else:
        lines.insert(section_idx + 1, f"- {bullet}\n")

    return "".join(lines)


def _read_planning_file(target_dir: Path, name: str) -> str:
    """Read a planning file, raising FileNotFoundError if missing."""
    path = target_dir / name
    if not path.exists():
        raise FileNotFoundError(f"{name} not found in {target_dir}")
    return path.read_text(encoding="utf-8")


def _parse_plan(content: str) -> dict:
    """Extract structured data from task_plan.md content."""
    result: dict = {
        "goal": "",
        "current_phase": "",
        "phases": [],
        "decisions": 0,
        "errors": 0,
    }

    m = re.search(r"## Goal\n(.+)", content)
    if m:
        goal = m.group(1).strip()
        if goal != "[describe end state]":
            result["goal"] = goal

    m = re.search(r"## Current Phase\n(.+)", content)
    if m:
        result["current_phase"] = m.group(1).strip()

    for m in re.finditer(r"### Phase (\d+): (.+?)\n(.*?)\*\*Status:\*\* (\w+)", content, re.DOTALL):
        result["phases"].append(
            {"num": int(m.group(1)), "name": m.group(2).strip(), "status": m.group(4)}
        )

    decisions_section = re.search(r"## Decisions\n(.*?)(?=\n## |\Z)", content, re.DOTALL)
    if decisions_section:
        rows = re.findall(r"^\|[^-|].*\|$", decisions_section.group(1), re.MULTILINE)
        result["decisions"] = max(0, len(rows) - 1)

    errors_section = re.search(r"## Errors\n(.*?)(?=\n## |\Z)", content, re.DOTALL)
    if errors_section:
        rows = re.findall(r"^\|[^-|].*\|$", errors_section.group(1), re.MULTILINE)
        result["errors"] = max(0, len(rows) - 1)

    return result


def _measure_files(target_dir: Path) -> dict:
    """Measure current planning file sizes and token estimates."""
    files: dict[str, dict[str, int] | None] = {}
    total_bytes = 0
    total_tokens = 0
    for name in PLANNING_FILES:
        path = target_dir / name
        if path.exists():
            content = path.read_text(encoding="utf-8")
            size = len(content.encode("utf-8"))
            tokens = estimate_tokens(content)
            files[name] = {"bytes": size, "tokens": tokens}
            total_bytes += size
            total_tokens += tokens
        else:
            files[name] = None
    return {"files": files, "total_bytes": total_bytes, "total_tokens": total_tokens}


# ---------------------------------------------------------------------------
# Public API: init
# ---------------------------------------------------------------------------


def init_planning(target_dir: Path, force: bool = False) -> dict:
    """Create lean planning files in target_dir.

    Returns: {files: [{name, bytes}], total_bytes}
    """
    if not target_dir.is_dir():
        return {"ok": False, "error": f"{target_dir} is not a directory"}

    created: list[dict[str, str | int]] = []
    total_bytes = 0
    for name, template in _FILE_TEMPLATES:
        path = target_dir / name
        if path.exists() and not force:
            continue
        content = (
            template
            if template is not None
            else PROGRESS_TEMPLATE.format(date=date.today().isoformat())
        )
        path.write_text(content, encoding="utf-8")
        size = len(content.encode("utf-8"))
        total_bytes += size
        created.append({"name": name, "bytes": size})

    return {"ok": True, "files": created, "total_bytes": total_bytes}


# ---------------------------------------------------------------------------
# Public API: status
# ---------------------------------------------------------------------------


def get_planning_status(target_dir: Path) -> dict:
    """Get compact planning status summary.

    Returns: {goal, current_phase, phases, decisions, errors, files, total_tokens}
    """
    file_exists: dict[str, bool] = {}
    total_tokens = 0
    plan_content: str | None = None

    for name in PLANNING_FILES:
        path = target_dir / name
        if path.exists():
            content = path.read_text(encoding="utf-8")
            file_exists[name] = True
            total_tokens += estimate_tokens(content)
            if name == "task_plan.md":
                plan_content = content
        else:
            file_exists[name] = False

    if not any(file_exists.values()):
        return {"ok": False, "error": "No planning files found. Use planning_init first."}

    if plan_content:
        plan = _parse_plan(plan_content)
    else:
        plan = {
            "goal": "",
            "current_phase": "",
            "phases": [],
            "decisions": 0,
            "errors": 0,
        }

    return {
        "ok": True,
        "goal": plan["goal"],
        "current_phase": plan["current_phase"],
        "phases": plan["phases"],
        "decisions": plan["decisions"],
        "errors": plan["errors"],
        "files": file_exists,
        "total_tokens": total_tokens,
    }


# ---------------------------------------------------------------------------
# Public API: update operations
# ---------------------------------------------------------------------------


def _op_goal(target_dir: Path, text: str | None = None, **_kwargs: object) -> dict:
    """Set the goal line in task_plan.md."""
    if not text:
        return {"ok": False, "error": "text is required for goal operation"}
    content = _read_planning_file(target_dir, "task_plan.md")
    lines = content.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.strip() == "## Goal":
            for j in range(i + 1, len(lines)):
                if lines[j].strip() and not lines[j].startswith("#"):
                    lines[j] = text + "\n"
                    break
            else:
                lines.insert(i + 1, text + "\n")
            break
    (target_dir / "task_plan.md").write_text("".join(lines), encoding="utf-8")
    return {"ok": True, "message": f"Goal set: {text}"}


def _op_advance(target_dir: Path, phase: int | None = None, **_kwargs: object) -> dict:
    """Mark current phase complete, advance to next (or to specific phase)."""
    content = _read_planning_file(target_dir, "task_plan.md")

    phases = []
    for m in re.finditer(r"(### Phase (\d+): .+?\n.*?\*\*Status:\*\* )(\w+)", content, re.DOTALL):
        phases.append((m.start(3), m.end(3), int(m.group(2)), m.group(3)))

    if not phases:
        return {"ok": False, "error": "No phases found in task_plan.md"}

    if phase is not None:
        target = phase
    else:
        current = next((p for p in phases if p[3] == "in_progress"), None)
        if current is None:
            return {"ok": False, "error": "No phase is currently in_progress"}
        target = current[2] + 1

    new_content = content
    for start, end, num, _status in reversed(phases):
        if num < target:
            new_content = new_content[:start] + "complete" + new_content[end:]
        elif num == target:
            new_content = new_content[:start] + "in_progress" + new_content[end:]

    new_content = re.sub(r"(## Current Phase\n).*", rf"\g<1>Phase {target}", new_content)
    (target_dir / "task_plan.md").write_text(new_content, encoding="utf-8")

    target_name = ""
    name_match = re.search(rf"### Phase {target}: (.+)", content)
    if name_match:
        target_name = name_match.group(1).strip()
    msg = f"Advanced to Phase {target}"
    if target_name:
        msg += f": {target_name}"
    return {"ok": True, "message": msg}


def _op_phase_status(
    target_dir: Path,
    phase: int | None = None,
    status: str | None = None,
    **_kwargs: object,
) -> dict:
    """Set a specific phase's status."""
    if phase is None or status is None:
        return {"ok": False, "error": "phase and status are required for phase_status"}
    content = _read_planning_file(target_dir, "task_plan.md")

    pattern = rf"(### Phase {phase}\b.*?\*\*Status:\*\* )\w+"
    new_content, count = re.subn(pattern, rf"\g<1>{status}", content, count=1, flags=re.DOTALL)
    if count == 0:
        return {"ok": False, "error": f"Phase {phase} not found"}

    (target_dir / "task_plan.md").write_text(new_content, encoding="utf-8")
    return {"ok": True, "message": f"Phase {phase} -> {status}"}


def _op_error(target_dir: Path, text: str | None = None, **_kwargs: object) -> dict:
    """Append an error row to task_plan.md's errors table."""
    if not text:
        return {"ok": False, "error": "text is required for error operation"}
    content = _read_planning_file(target_dir, "task_plan.md")
    row = f"| {text} | 1 | |"
    new_content = append_table_row(content, "| Error |", row)
    (target_dir / "task_plan.md").write_text(new_content, encoding="utf-8")
    return {"ok": True, "message": f"Error logged: {text}"}


def _op_decision(
    target_dir: Path,
    text: str | None = None,
    rationale: str | None = None,
    **_kwargs: object,
) -> dict:
    """Append a decision row to task_plan.md's decisions table."""
    if not text or not rationale:
        return {"ok": False, "error": "text and rationale are required for decision"}
    content = _read_planning_file(target_dir, "task_plan.md")
    row = f"| {text} | {rationale} |"
    new_content = append_table_row(content, "| Decision |", row)
    (target_dir / "task_plan.md").write_text(new_content, encoding="utf-8")
    return {"ok": True, "message": f"Decision: {text}"}


def _op_finding(
    target_dir: Path,
    section: str | None = None,
    text: str | None = None,
    **_kwargs: object,
) -> dict:
    """Append a bullet to a section in findings.md."""
    if not section or not text:
        return {"ok": False, "error": "section and text are required for finding"}
    content = _read_planning_file(target_dir, "findings.md")
    new_content = append_to_section(content, section, text)
    if new_content == content:
        return {"ok": False, "error": f"Section '{section}' not found in findings.md"}
    (target_dir / "findings.md").write_text(new_content, encoding="utf-8")
    return {"ok": True, "message": f"Finding [{section}]: {text}"}


def _op_issue(
    target_dir: Path,
    text: str | None = None,
    resolution: str | None = None,
    **_kwargs: object,
) -> dict:
    """Append an issue row to findings.md's issues table."""
    if not text or not resolution:
        return {"ok": False, "error": "text and resolution are required for issue"}
    content = _read_planning_file(target_dir, "findings.md")
    row = f"| {text} | {resolution} |"
    new_content = append_table_row(content, "| Issue |", row)
    (target_dir / "findings.md").write_text(new_content, encoding="utf-8")
    return {"ok": True, "message": f"Issue: {text}"}


def _op_log(target_dir: Path, text: str | None = None, **_kwargs: object) -> dict:
    """Append an action to the current phase's Actions list in progress.md."""
    if not text:
        return {"ok": False, "error": "text is required for log operation"}
    content = _read_planning_file(target_dir, "progress.md")
    lines = content.splitlines(keepends=True)

    found_in_progress = False
    insert_idx = None
    replace_placeholder = False

    for i, line in enumerate(lines):
        if "**Status:** in_progress" in line:
            found_in_progress = True
            continue
        if found_in_progress and line.strip().startswith("- Actions"):
            j = i + 1
            while j < len(lines) and lines[j].startswith("  "):
                j += 1
            if j == i + 1:
                insert_idx = i + 1
            elif j == i + 2 and lines[i + 1].strip() == "-":
                insert_idx = i + 1
                replace_placeholder = True
            else:
                insert_idx = j
            break
        if found_in_progress and (line.startswith("## ") or line.startswith("### ")):
            break

    if insert_idx is not None:
        if replace_placeholder:
            lines[insert_idx] = f"  - {text}\n"
        else:
            lines.insert(insert_idx, f"  - {text}\n")
        (target_dir / "progress.md").write_text("".join(lines), encoding="utf-8")
    else:
        with open(target_dir / "progress.md", "a", encoding="utf-8") as f:
            f.write(f"\n- {text}\n")

    return {"ok": True, "message": f"Logged: {text}"}


def _op_file_changed(target_dir: Path, text: str | None = None, **_kwargs: object) -> dict:
    """Append a file path to the Files Changed section in progress.md."""
    if not text:
        return {"ok": False, "error": "text is required for file_changed operation"}
    content = _read_planning_file(target_dir, "progress.md")
    new_content = append_to_section(content, "Files Changed", text)
    (target_dir / "progress.md").write_text(new_content, encoding="utf-8")
    return {"ok": True, "message": f"File: {text}"}


def _op_test(
    target_dir: Path,
    test_name: str | None = None,
    expected: str | None = None,
    actual: str | None = None,
    result: str | None = None,
    **_kwargs: object,
) -> dict:
    """Append a test result row to progress.md's test results table."""
    if not test_name or not expected or not actual or not result:
        return {
            "ok": False,
            "error": "test_name, expected, actual, and result are required for test",
        }
    content = _read_planning_file(target_dir, "progress.md")
    row = f"| {test_name} | {expected} | {actual} | {result} |"
    new_content = append_table_row(content, "| Test |", row)
    (target_dir / "progress.md").write_text(new_content, encoding="utf-8")
    return {"ok": True, "message": f"Test: {test_name} -> {result}"}


_UPDATE_DISPATCH: dict[str, object] = {
    "goal": _op_goal,
    "advance": _op_advance,
    "phase_status": _op_phase_status,
    "error": _op_error,
    "decision": _op_decision,
    "finding": _op_finding,
    "issue": _op_issue,
    "log": _op_log,
    "file_changed": _op_file_changed,
    "test": _op_test,
}


def update_planning(
    target_dir: Path,
    operation: str,
    *,
    text: str | None = None,
    phase: int | None = None,
    status: str | None = None,
    rationale: str | None = None,
    section: str | None = None,
    resolution: str | None = None,
    test_name: str | None = None,
    expected: str | None = None,
    actual: str | None = None,
    result: str | None = None,
) -> dict:
    """Dispatch a planning update operation.

    Operations and their required kwargs:
        goal:         text
        advance:      phase (optional, auto-advances if omitted)
        phase_status: phase, status (pending/in_progress/complete)
        error:        text
        decision:     text (decision), rationale
        finding:      section, text
        issue:        text (issue description), resolution
        log:          text
        file_changed: text (file path)
        test:         test_name, expected, actual, result (pass/fail)
    """
    handler = _UPDATE_DISPATCH.get(operation)
    if handler is None:
        valid = ", ".join(sorted(_UPDATE_DISPATCH))
        return {"ok": False, "error": f"Unknown operation: {operation}. Valid: {valid}"}

    try:
        result_dict: dict = handler(  # type: ignore[operator]
            target_dir,
            text=text,
            phase=phase,
            status=status,
            rationale=rationale,
            section=section,
            resolution=resolution,
            test_name=test_name,
            expected=expected,
            actual=actual,
            result=result,
        )
        return result_dict
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Public API: measure
# ---------------------------------------------------------------------------


def measure_planning(target_dir: Path, operation: str) -> dict:
    """Token tracking for planning files.

    Operations:
        snapshot:           Measure current files, append to .plan_metrics.jsonl.
        report:             Current state + historical peak/growth + savings.
        compare_templates:  Side-by-side old vs new template comparison.
    """
    if operation == "snapshot":
        return _measure_snapshot(target_dir)
    if operation == "report":
        return _measure_report(target_dir)
    if operation == "compare_templates":
        return _measure_compare(target_dir)
    return {
        "ok": False,
        "error": f"Unknown measure operation: {operation}. "
        "Valid: snapshot, report, compare_templates",
    }


def _measure_snapshot(target_dir: Path) -> dict:
    """Measure current files and append a snapshot to .plan_metrics.jsonl."""
    data = _measure_files(target_dir)
    data["timestamp"] = datetime.now().isoformat()

    metrics_path = target_dir / METRICS_FILE
    with open(metrics_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(data) + "\n")

    return {
        "ok": True,
        "total_bytes": data["total_bytes"],
        "total_tokens": data["total_tokens"],
        "message": f"Snapshot saved: {data['total_bytes']} bytes, ~{data['total_tokens']} tokens",
    }


def _measure_report(target_dir: Path) -> dict:
    """Return token usage report with current, peak, growth, and savings."""
    current = _measure_files(target_dir)
    metrics_path = target_dir / METRICS_FILE

    report: dict = {
        "ok": True,
        "files": current["files"],
        "total_bytes": current["total_bytes"],
        "total_tokens": current["total_tokens"],
    }

    if metrics_path.exists():
        snapshots = []
        with open(metrics_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    snapshots.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        if snapshots:
            report["snapshot_count"] = len(snapshots)
            report["initial_tokens"] = snapshots[0]["total_tokens"]
            report["peak_tokens"] = max(s["total_tokens"] for s in snapshots)
            report["growth"] = current["total_tokens"] - snapshots[0]["total_tokens"]

    old_tokens = OLD_TOTAL // 4
    savings = old_tokens - current["total_tokens"]
    if savings > 0:
        pct = (savings * 100) // old_tokens
        report["savings_vs_old"] = {"tokens_saved": savings, "percent": pct}

    return report


def _measure_compare(target_dir: Path) -> dict:
    """Compare old commented vs new lean template sizes."""
    current = _measure_files(target_dir)

    comparison: list[dict] = []
    total_old = 0
    total_new = 0
    for name in PLANNING_FILES:
        old_bytes = OLD_TEMPLATE_BYTES.get(name, 0)
        info = current["files"].get(name)
        new_bytes = info["bytes"] if info else 0
        saved_pct = (old_bytes - new_bytes) * 100 // old_bytes if old_bytes else 0
        comparison.append(
            {
                "file": name,
                "old_bytes": old_bytes,
                "new_bytes": new_bytes,
                "saved_percent": saved_pct,
            }
        )
        total_old += old_bytes
        total_new += new_bytes

    total_saved_pct = (total_old - total_new) * 100 // total_old if total_old else 0

    return {
        "ok": True,
        "files": comparison,
        "total_old_bytes": total_old,
        "total_new_bytes": total_new,
        "total_saved_percent": total_saved_pct,
        "old_tokens": total_old // 4,
        "new_tokens": total_new // 4,
        "tokens_saved_per_read": total_old // 4 - total_new // 4,
    }
