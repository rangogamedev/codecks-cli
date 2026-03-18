"""Dispatch endpoint cache — persists discovered API endpoints for admin operations.

Stores discovered endpoints in ~/.codecks/dispatch_cache.json so that
subsequent calls can skip Playwright and use direct HTTP dispatch.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone


def cache_path() -> str:
    """Return the path to the dispatch endpoint cache file."""
    cache_dir = os.path.join(os.path.expanduser("~"), ".codecks")
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, "dispatch_cache.json")


def _load_cache() -> dict:
    """Load the cache from disk. Returns empty dict on any error."""
    path = cache_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
        return {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(data: dict) -> None:
    """Write cache to disk atomically."""
    path = cache_path()
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, path)
    except OSError:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def get_cached_endpoint(operation: str) -> dict | None:
    """Return cached endpoint info for an operation, or None if not cached.

    Returns dict with keys: endpoint, method, payload_template, headers_extra,
    discovered_at, last_verified, verify_count.
    """
    cache = _load_cache()
    entry = cache.get(operation)
    if not isinstance(entry, dict):
        return None
    if "endpoint" not in entry:
        return None
    return entry


def save_endpoint(
    operation: str,
    endpoint: str,
    method: str = "POST",
    payload_template: dict | None = None,
    headers_extra: dict | None = None,
) -> None:
    """Save or update a discovered endpoint in the cache."""
    cache = _load_cache()
    now = datetime.now(timezone.utc).isoformat()
    existing = cache.get(operation, {})
    verify_count = existing.get("verify_count", 0) if isinstance(existing, dict) else 0
    cache[operation] = {
        "endpoint": endpoint,
        "method": method,
        "payload_template": payload_template or {},
        "headers_extra": headers_extra or {},
        "discovered_at": existing.get("discovered_at", now) if isinstance(existing, dict) else now,
        "last_verified": now,
        "verify_count": verify_count + 1,
    }
    _save_cache(cache)


def touch(operation: str) -> None:
    """Update last_verified timestamp and increment verify_count."""
    cache = _load_cache()
    entry = cache.get(operation)
    if not isinstance(entry, dict):
        return
    entry["last_verified"] = datetime.now(timezone.utc).isoformat()
    entry["verify_count"] = entry.get("verify_count", 0) + 1
    _save_cache(cache)


def invalidate(operation: str) -> None:
    """Remove a cached endpoint (forces Playwright fallback on next call)."""
    cache = _load_cache()
    if operation in cache:
        del cache[operation]
        _save_cache(cache)


def invalidate_all() -> None:
    """Clear the entire cache."""
    _save_cache({})


def list_cached() -> dict:
    """Return the full cache (for diagnostics)."""
    return _load_cache()
