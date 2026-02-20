"""
codecks-cli shared configuration, constants, and module-level state.
Standalone module — no imports from other project files.
"""

import os
import tempfile

# ---------------------------------------------------------------------------
# .env path and helpers
# ---------------------------------------------------------------------------

_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_PACKAGE_DIR)

ENV_PATH = os.path.join(_PROJECT_ROOT, ".env")


def load_env():
    env = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    env[key.strip()] = val.strip()
    return env


def save_env_value(key, value):
    """Update or add a key in the .env file (atomic write-then-rename)."""
    lines = []
    found = False
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as f:
            lines = f.readlines()
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}\n"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}\n")
    # Write to temp file then rename for crash-safety.
    env_dir = os.path.dirname(ENV_PATH) or "."
    fd, tmp_path = tempfile.mkstemp(dir=env_dir, prefix=".env_tmp_")
    try:
        with os.fdopen(fd, "w") as f:
            f.writelines(lines)
        # Atomic rename (overwrites on POSIX; Windows needs remove first).
        try:
            os.replace(tmp_path, ENV_PATH)
        except OSError:
            # Fallback for very old Windows versions without os.replace().
            if os.path.exists(ENV_PATH):
                os.remove(ENV_PATH)
            os.rename(tmp_path, ENV_PATH)
    except Exception:
        # Clean up temp file on any failure.
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
    # Restrict to owner-only on Unix/Mac. No-op on Windows.
    try:
        os.chmod(ENV_PATH, 0o600)
    except (OSError, NotImplementedError):
        pass


def _env_bool(key, default=False):
    """Parse common boolean env formats."""
    raw = env.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(key, default):
    """Parse integer env values with fallback."""
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(key, default):
    """Parse float env values with fallback."""
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VERSION = "0.4.0"

VALID_STATUSES = {"not_started", "started", "done", "blocked", "in_review"}
VALID_PRIORITIES = {"a", "b", "c", "null"}
PRI_LABELS = {"a": "high", "b": "med", "c": "low"}
VALID_SORT_FIELDS = {"status", "priority", "effort", "deck", "title", "owner", "updated", "created"}
VALID_CARD_TYPES = {"hero", "doc"}
VALID_SEVERITIES = {"critical", "high", "low", "null"}

BASE_URL = "https://api.codecks.io"

# ---------------------------------------------------------------------------
# Module-level state (loaded from .env)
# ---------------------------------------------------------------------------

env = load_env()

SESSION_TOKEN = env.get("CODECKS_TOKEN", "")
ACCESS_KEY = env.get("CODECKS_ACCESS_KEY", "")
REPORT_TOKEN = env.get("CODECKS_REPORT_TOKEN", "")
ACCOUNT = env.get("CODECKS_ACCOUNT", "")
USER_ID = env.get("CODECKS_USER_ID", "")
HTTP_TIMEOUT_SECONDS = _env_int("CODECKS_HTTP_TIMEOUT_SECONDS", 30)
HTTP_MAX_RETRIES = _env_int("CODECKS_HTTP_MAX_RETRIES", 2)
HTTP_RETRY_BASE_SECONDS = _env_float("CODECKS_HTTP_RETRY_BASE_SECONDS", 1.0)
HTTP_MAX_RESPONSE_BYTES = _env_int("CODECKS_HTTP_MAX_RESPONSE_BYTES", 5_000_000)
HTTP_LOG_ENABLED = _env_bool("CODECKS_HTTP_LOG", False)
HTTP_LOG_SAMPLE_RATE = min(1.0, max(0.0, _env_float("CODECKS_HTTP_LOG_SAMPLE_RATE", 1.0)))

# ---------------------------------------------------------------------------
# GDD-related paths and Google OAuth constants
# ---------------------------------------------------------------------------

GDD_DOC_URL = env.get("GDD_GOOGLE_DOC_URL", "")
GDD_CACHE_PATH = os.path.join(_PROJECT_ROOT, ".gdd_cache.md")

GOOGLE_CLIENT_ID = env.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = env.get("GOOGLE_CLIENT_SECRET", "")
GDD_TOKENS_PATH = os.path.join(_PROJECT_ROOT, ".gdd_tokens.json")
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GOOGLE_SCOPE = "https://www.googleapis.com/auth/drive.readonly"

# ---------------------------------------------------------------------------
# Runtime cache (populated lazily by query helpers)
# ---------------------------------------------------------------------------

_cache = {}
RUNTIME_STRICT = False

# ---------------------------------------------------------------------------
# Custom exceptions (defined here to avoid circular imports)
# ---------------------------------------------------------------------------


class CliError(Exception):
    """Exit code 1 — validation, not-found, network, parse errors."""

    exit_code = 1


class SetupError(CliError):
    """Exit code 2 — token expired, no config."""

    exit_code = 2
