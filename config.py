"""
codecks-cli shared configuration, constants, and module-level state.
Standalone module — no imports from other project files.
"""

import os

# ---------------------------------------------------------------------------
# .env path and helpers
# ---------------------------------------------------------------------------

ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def load_env():
    env = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    env[key.strip()] = val.strip()
    return env


def save_env_value(key, value):
    """Update or add a key in the .env file."""
    lines = []
    found = False
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r") as f:
            lines = f.readlines()
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}\n"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}\n")
    with open(ENV_PATH, "w") as f:
        f.writelines(lines)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VERSION = "0.4.0"

VALID_STATUSES = {"not_started", "started", "done", "blocked", "in_review"}
VALID_PRIORITIES = {"a", "b", "c", "null"}
PRI_LABELS = {"a": "high", "b": "med", "c": "low"}
VALID_SORT_FIELDS = {"status", "priority", "effort", "deck", "title",
                     "owner", "updated", "created"}
VALID_CARD_TYPES = {"hero", "doc"}

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

# ---------------------------------------------------------------------------
# GDD-related paths and Google OAuth constants
# ---------------------------------------------------------------------------

GDD_DOC_URL = env.get("GDD_GOOGLE_DOC_URL", "")
GDD_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               ".gdd_cache.md")

GOOGLE_CLIENT_ID = env.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = env.get("GOOGLE_CLIENT_SECRET", "")
GDD_TOKENS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                ".gdd_tokens.json")
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GOOGLE_SCOPE = "https://www.googleapis.com/auth/drive.readonly"

# ---------------------------------------------------------------------------
# Runtime cache (populated lazily by query helpers)
# ---------------------------------------------------------------------------

_cache = {}

# ---------------------------------------------------------------------------
# Custom exceptions (defined here to avoid circular imports)
# ---------------------------------------------------------------------------

class CliError(Exception):
    """Exit code 1 — validation, not-found, network, parse errors."""
    exit_code = 1

class SetupError(CliError):
    """Exit code 2 — token expired, no config."""
    exit_code = 2
