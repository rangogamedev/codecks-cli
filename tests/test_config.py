"""Tests for config.py — env loading, saving, and constants."""

from unittest.mock import patch

import pytest

from codecks_cli import config

# Keys that load_env() checks in os.environ as fallback (Docker support).
_KNOWN_ENV_KEYS = [
    "CODECKS_TOKEN",
    "CODECKS_ACCESS_KEY",
    "CODECKS_REPORT_TOKEN",
    "CODECKS_ACCOUNT",
    "CODECKS_USER_ID",
    "CODECKS_HTTP_TIMEOUT_SECONDS",
    "CODECKS_HTTP_MAX_RETRIES",
    "CODECKS_HTTP_RETRY_BASE_SECONDS",
    "CODECKS_HTTP_MAX_RESPONSE_BYTES",
    "CODECKS_HTTP_LOG",
    "CODECKS_HTTP_LOG_SAMPLE_RATE",
    "CODECKS_MCP_RESPONSE_MODE",
    "GDD_GOOGLE_DOC_URL",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
]


class TestLoadEnv:
    @pytest.fixture(autouse=True)
    def _clean_environ(self, monkeypatch):
        """Remove known keys from os.environ so file-parsing tests are isolated."""
        for key in _KNOWN_ENV_KEYS:
            monkeypatch.delenv(key, raising=False)

    def test_basic_key_value(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("FOO=bar\nBAZ=qux\n")
        monkeypatch.setattr(config, "ENV_PATH", str(env_file))
        result = config.load_env()
        assert result == {"FOO": "bar", "BAZ": "qux"}

    def test_strips_whitespace(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("  KEY  =  value  \n")
        monkeypatch.setattr(config, "ENV_PATH", str(env_file))
        result = config.load_env()
        assert result == {"KEY": "value"}

    def test_skips_comments(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("# comment\nKEY=val\n# another comment\n")
        monkeypatch.setattr(config, "ENV_PATH", str(env_file))
        result = config.load_env()
        assert result == {"KEY": "val"}

    def test_skips_blank_lines(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("A=1\n\n\nB=2\n")
        monkeypatch.setattr(config, "ENV_PATH", str(env_file))
        result = config.load_env()
        assert result == {"A": "1", "B": "2"}

    def test_value_with_equals_sign(self, tmp_path, monkeypatch):
        """Values can contain = signs (split on first only)."""
        env_file = tmp_path / ".env"
        env_file.write_text("TOKEN=abc=def=ghi\n")
        monkeypatch.setattr(config, "ENV_PATH", str(env_file))
        result = config.load_env()
        assert result == {"TOKEN": "abc=def=ghi"}

    def test_missing_file_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "ENV_PATH", str(tmp_path / "nonexistent"))
        result = config.load_env()
        assert result == {}

    def test_empty_file(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("")
        monkeypatch.setattr(config, "ENV_PATH", str(env_file))
        result = config.load_env()
        assert result == {}


class TestLoadEnvOsEnvironFallback:
    """load_env() falls back to os.environ for known CODECKS_* keys (Docker support)."""

    def test_os_environ_fallback_when_no_env_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "ENV_PATH", str(tmp_path / "nonexistent"))
        monkeypatch.setenv("CODECKS_TOKEN", "from-environ")
        result = config.load_env()
        assert result["CODECKS_TOKEN"] == "from-environ"

    def test_env_file_takes_precedence_over_os_environ(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("CODECKS_TOKEN=from-file\n")
        monkeypatch.setattr(config, "ENV_PATH", str(env_file))
        monkeypatch.setenv("CODECKS_TOKEN", "from-environ")
        result = config.load_env()
        assert result["CODECKS_TOKEN"] == "from-file"

    def test_unknown_keys_not_pulled_from_environ(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "ENV_PATH", str(tmp_path / "nonexistent"))
        monkeypatch.setenv("RANDOM_KEY", "should-not-appear")
        result = config.load_env()
        assert "RANDOM_KEY" not in result

    def test_multiple_known_keys_from_environ(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "ENV_PATH", str(tmp_path / "nonexistent"))
        monkeypatch.setenv("CODECKS_TOKEN", "tok")
        monkeypatch.setenv("CODECKS_ACCOUNT", "acct")
        monkeypatch.setenv("CODECKS_MCP_RESPONSE_MODE", "envelope")
        result = config.load_env()
        assert result["CODECKS_TOKEN"] == "tok"
        assert result["CODECKS_ACCOUNT"] == "acct"
        assert result["CODECKS_MCP_RESPONSE_MODE"] == "envelope"


class TestSaveEnvValue:
    def test_creates_new_key(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("A=1\n")
        monkeypatch.setattr(config, "ENV_PATH", str(env_file))
        config.save_env_value("B", "2")
        assert env_file.read_text() == "A=1\nB=2\n"

    def test_updates_existing_key(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("A=1\nB=old\nC=3\n")
        monkeypatch.setattr(config, "ENV_PATH", str(env_file))
        config.save_env_value("B", "new")
        assert env_file.read_text() == "A=1\nB=new\nC=3\n"

    def test_creates_file_if_missing(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        monkeypatch.setattr(config, "ENV_PATH", str(env_file))
        config.save_env_value("KEY", "val")
        assert env_file.read_text() == "KEY=val\n"


class TestEnvParsers:
    """_env_int and _env_float should gracefully handle bad .env values."""

    def test_env_int_valid(self, monkeypatch):
        monkeypatch.setattr(config, "env", {"K": "42"})
        assert config._env_int("K", 10) == 42

    def test_env_int_missing_returns_default(self, monkeypatch):
        monkeypatch.setattr(config, "env", {})
        assert config._env_int("MISSING", 99) == 99

    def test_env_int_empty_returns_default(self, monkeypatch):
        monkeypatch.setattr(config, "env", {"K": ""})
        assert config._env_int("K", 99) == 99

    def test_env_int_bad_value_returns_default(self, monkeypatch):
        """Critical fix #1: non-numeric .env values no longer crash at import."""
        monkeypatch.setattr(config, "env", {"K": "not_a_number"})
        assert config._env_int("K", 30) == 30

    def test_env_float_valid(self, monkeypatch):
        monkeypatch.setattr(config, "env", {"K": "1.5"})
        assert config._env_float("K", 1.0) == 1.5

    def test_env_float_missing_returns_default(self, monkeypatch):
        monkeypatch.setattr(config, "env", {})
        assert config._env_float("MISSING", 2.0) == 2.0

    def test_env_float_bad_value_returns_default(self, monkeypatch):
        """Critical fix #1: non-numeric .env values no longer crash at import."""
        monkeypatch.setattr(config, "env", {"K": "abc"})
        assert config._env_float("K", 1.0) == 1.0

    def test_env_bool_truthy(self, monkeypatch):
        for val in ("1", "true", "yes", "on", "True", "YES"):
            monkeypatch.setattr(config, "env", {"K": val})
            assert config._env_bool("K") is True

    def test_env_bool_falsy(self, monkeypatch):
        for val in ("0", "false", "no", "off", "anything"):
            monkeypatch.setattr(config, "env", {"K": val})
            assert config._env_bool("K") is False


class TestConstants:
    def test_valid_statuses(self):
        assert "not_started" in config.VALID_STATUSES
        assert "started" in config.VALID_STATUSES
        assert "done" in config.VALID_STATUSES
        assert "blocked" in config.VALID_STATUSES
        assert "in_review" in config.VALID_STATUSES
        assert "invalid" not in config.VALID_STATUSES

    def test_valid_priorities(self):
        assert config.VALID_PRIORITIES == {"a", "b", "c", "null"}

    def test_pri_labels(self):
        assert config.PRI_LABELS == {"a": "high", "b": "med", "c": "low"}

    def test_valid_sort_fields(self):
        expected = {"status", "priority", "effort", "deck", "title", "owner", "updated", "created"}
        assert config.VALID_SORT_FIELDS == expected


class TestSaveEnvPermissions:
    """save_env_value() should chmod .env to 0o600 after writing."""

    @patch("codecks_cli.config.os.chmod")
    def test_chmod_called_after_write(self, mock_chmod, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        monkeypatch.setattr(config, "ENV_PATH", str(env_file))
        config.save_env_value("KEY", "val")
        mock_chmod.assert_called_once_with(str(env_file), 0o600)

    def test_chmod_error_does_not_crash(self, tmp_path, monkeypatch):
        """On Windows or restricted systems, chmod failure is silently ignored."""
        env_file = tmp_path / ".env"
        monkeypatch.setattr(config, "ENV_PATH", str(env_file))
        with patch("codecks_cli.config.os.chmod", side_effect=OSError("not supported")):
            config.save_env_value("KEY", "val")
        assert env_file.read_text() == "KEY=val\n"
