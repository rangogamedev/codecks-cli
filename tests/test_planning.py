"""Tests for codecks_cli/planning.py — file-based planning tools.

Tests planning logic directly (init, status, update, measure) without
going through the MCP server layer. Extracted from test_mcp_server.py.
"""

from codecks_cli.planning import (
    get_planning_status,
    init_planning,
    measure_planning,
    update_planning,
)


class TestInitPlanning:
    def test_creates_all_files(self, tmp_path):
        result = init_planning(tmp_path)
        assert result["ok"] is True
        assert len(result["files"]) == 3
        assert result["total_bytes"] > 0
        assert (tmp_path / "task_plan.md").exists()
        assert (tmp_path / "findings.md").exists()
        assert (tmp_path / "progress.md").exists()

    def test_skips_existing_without_force(self, tmp_path):
        (tmp_path / "task_plan.md").write_text("existing")
        result = init_planning(tmp_path)
        assert result["ok"] is True
        assert len(result["files"]) == 2  # only findings + progress
        assert (tmp_path / "task_plan.md").read_text() == "existing"

    def test_force_overwrites(self, tmp_path):
        (tmp_path / "task_plan.md").write_text("old")
        result = init_planning(tmp_path, force=True)
        assert result["ok"] is True
        assert len(result["files"]) == 3
        assert "## Goal" in (tmp_path / "task_plan.md").read_text()


class TestGetPlanningStatus:
    def test_no_files_returns_error(self, tmp_path):
        result = get_planning_status(tmp_path)
        assert result["ok"] is False
        assert "No planning files" in result["error"]

    def test_returns_structured_status(self, tmp_path):
        init_planning(tmp_path)
        result = get_planning_status(tmp_path)
        assert result["ok"] is True
        assert result["current_phase"] == "Phase 1"
        assert len(result["phases"]) == 5
        assert result["phases"][0]["status"] == "in_progress"
        assert result["decisions"] == 0
        assert result["errors"] == 0
        assert result["total_tokens"] > 0
        assert result["files"]["task_plan.md"] is True

    def test_shows_goal_after_set(self, tmp_path):
        init_planning(tmp_path)
        update_planning(tmp_path, "goal", text="Build auth system")
        result = get_planning_status(tmp_path)
        assert result["goal"] == "Build auth system"


class TestUpdatePlanning:
    def test_goal(self, tmp_path):
        init_planning(tmp_path)
        result = update_planning(tmp_path, "goal", text="Ship v2.0")
        assert result["ok"] is True
        assert "Ship v2.0" in result["message"]
        content = (tmp_path / "task_plan.md").read_text()
        assert "Ship v2.0" in content

    def test_advance(self, tmp_path):
        init_planning(tmp_path)
        result = update_planning(tmp_path, "advance")
        assert result["ok"] is True
        assert "Phase 2" in result["message"]
        content = (tmp_path / "task_plan.md").read_text()
        assert "Phase 2" in content

    def test_advance_to_specific_phase(self, tmp_path):
        init_planning(tmp_path)
        result = update_planning(tmp_path, "advance", phase=3)
        assert result["ok"] is True
        assert "Phase 3" in result["message"]

    def test_phase_status(self, tmp_path):
        init_planning(tmp_path)
        result = update_planning(tmp_path, "phase_status", phase=2, status="in_progress")
        assert result["ok"] is True
        assert "Phase 2" in result["message"]

    def test_error(self, tmp_path):
        init_planning(tmp_path)
        result = update_planning(tmp_path, "error", text="API timeout")
        assert result["ok"] is True
        content = (tmp_path / "task_plan.md").read_text()
        assert "API timeout" in content

    def test_decision(self, tmp_path):
        init_planning(tmp_path)
        result = update_planning(tmp_path, "decision", text="Use JWT", rationale="Stateless auth")
        assert result["ok"] is True
        content = (tmp_path / "task_plan.md").read_text()
        assert "Use JWT" in content
        assert "Stateless auth" in content

    def test_finding(self, tmp_path):
        init_planning(tmp_path)
        result = update_planning(
            tmp_path, "finding", section="Requirements", text="Must support OAuth2"
        )
        assert result["ok"] is True
        content = (tmp_path / "findings.md").read_text()
        assert "Must support OAuth2" in content

    def test_issue(self, tmp_path):
        init_planning(tmp_path)
        result = update_planning(
            tmp_path, "issue", text="Rate limit hit", resolution="Add retry logic"
        )
        assert result["ok"] is True
        content = (tmp_path / "findings.md").read_text()
        assert "Rate limit hit" in content

    def test_log(self, tmp_path):
        init_planning(tmp_path)
        result = update_planning(tmp_path, "log", text="Implemented login flow")
        assert result["ok"] is True
        content = (tmp_path / "progress.md").read_text()
        assert "Implemented login flow" in content

    def test_file_changed(self, tmp_path):
        init_planning(tmp_path)
        result = update_planning(tmp_path, "file_changed", text="src/auth.py")
        assert result["ok"] is True
        content = (tmp_path / "progress.md").read_text()
        assert "src/auth.py" in content

    def test_test_result(self, tmp_path):
        init_planning(tmp_path)
        result = update_planning(
            tmp_path,
            "test",
            test_name="test_login",
            expected="200 OK",
            actual="200 OK",
            result="pass",
        )
        assert result["ok"] is True
        content = (tmp_path / "progress.md").read_text()
        assert "test_login" in content

    def test_invalid_operation(self, tmp_path):
        result = update_planning(tmp_path, "invalid_op")
        assert result["ok"] is False
        assert "Unknown operation" in result["error"]

    def test_missing_file_returns_error(self, tmp_path):
        result = update_planning(tmp_path, "goal", text="test")
        assert result["ok"] is False
        assert "not found" in result["error"]


class TestMeasurePlanning:
    def test_snapshot(self, tmp_path):
        init_planning(tmp_path)
        result = measure_planning(tmp_path, "snapshot")
        assert result["ok"] is True
        assert result["total_bytes"] > 0
        assert (tmp_path / ".plan_metrics.jsonl").exists()

    def test_report(self, tmp_path):
        init_planning(tmp_path)
        result = measure_planning(tmp_path, "report")
        assert result["ok"] is True
        assert result["total_bytes"] > 0
        assert "savings_vs_old" in result

    def test_report_with_snapshots(self, tmp_path):
        init_planning(tmp_path)
        measure_planning(tmp_path, "snapshot")
        result = measure_planning(tmp_path, "report")
        assert result["ok"] is True
        assert result["snapshot_count"] == 1
        assert "initial_tokens" in result
        assert "peak_tokens" in result

    def test_compare_templates(self, tmp_path):
        init_planning(tmp_path)
        result = measure_planning(tmp_path, "compare_templates")
        assert result["ok"] is True
        assert len(result["files"]) == 3
        assert result["total_old_bytes"] == 12516
        assert result["tokens_saved_per_read"] > 0

    def test_invalid_operation(self, tmp_path):
        result = measure_planning(tmp_path, "invalid")
        assert result["ok"] is False
        assert "Unknown measure operation" in result["error"]
