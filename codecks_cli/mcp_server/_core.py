"""Core helpers: client caching, _call dispatcher, response contract, UUID validation, snapshot cache."""

from __future__ import annotations

import json
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from codecks_cli import CliError, CodecksClient, SetupError
from codecks_cli.config import (
    CACHE_PATH,
    CACHE_TTL_SECONDS,
    CONTRACT_SCHEMA_VERSION,
    MCP_RESPONSE_MODE,
)
from codecks_cli.mcp_server._repository import CardRepository
from codecks_cli.store import CardStore

_client: CodecksClient | None = None


def _get_client() -> CodecksClient:
    """Return a cached CodecksClient, creating one on first use."""
    global _client
    if _client is None:
        _client = CodecksClient()
    return _client


# ---------------------------------------------------------------------------
# SQLite store (lazy-initialized)
# ---------------------------------------------------------------------------

_store: CardStore | None = None


def _get_store() -> CardStore:
    """Return the lazy-initialized CardStore singleton."""
    global _store
    if _store is None:
        _store = CardStore()
    return _store


def _reset_store() -> None:
    """Close and discard the SQLite store. For test isolation."""
    global _store
    if _store is not None:
        try:
            _store.close()
        except Exception:
            pass
        _store = None


# ---------------------------------------------------------------------------
# Snapshot cache (in-memory, lazy-loaded from .pm_cache.json)
# ---------------------------------------------------------------------------

_snapshot_cache: dict | None = None
_cache_loaded_at: float = 0.0  # time.monotonic() when loaded/warmed
_disk_cache_mtime: float = 0.0  # st_mtime of .pm_cache.json when last loaded
_batch_in_progress: bool = False  # Suppress disk writes during batch ops
_repo = CardRepository()

# Rate-limit tracking (Codecks API: 40 req/5s)
_api_call_timestamps: list[float] = []
_RATE_LIMIT_WINDOW = 5.0  # seconds
_RATE_LIMIT_MAX = 35  # leave headroom below 40


def get_repository() -> CardRepository:
    """Return the card repository (populated after cache warm or disk load)."""
    return _repo


def _load_cache_from_disk() -> bool:
    """Load .pm_cache.json into memory, reloading if disk file is newer.

    Uses mtime comparison for cross-process cache coherence: if another
    process wrote a newer cache file (e.g., after mutations), this process
    automatically picks up the fresh data on next read.
    """
    global _snapshot_cache, _cache_loaded_at, _disk_cache_mtime

    # Check disk file mtime
    try:
        current_mtime = os.path.getmtime(CACHE_PATH)
    except (FileNotFoundError, OSError):
        current_mtime = 0.0

    # Skip reload if we already have data from this version of the file
    if _snapshot_cache is not None and current_mtime > 0 and current_mtime <= _disk_cache_mtime:
        return True

    # Load from disk (first load or newer version available)
    if current_mtime > 0:
        try:
            with open(CACHE_PATH, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "fetched_at" in data:
                data["fetched_ts"] = time.monotonic()
                _snapshot_cache = data
                _cache_loaded_at = data["fetched_ts"]
                _disk_cache_mtime = current_mtime
                # Rebuild card indexes from loaded data
                cards_data = data.get("cards_result")
                if isinstance(cards_data, dict):
                    _repo.load(cards_data.get("cards", []))
                decks_data = data.get("decks")
                if isinstance(decks_data, list):
                    _repo.load_decks(decks_data)
                return True
        except (json.JSONDecodeError, OSError):
            pass  # JSON load failed — try SQLite fallback below

    # Fallback: try SQLite store
    if _snapshot_cache is None:
        try:
            store = _get_store()
            fetched = store.get_meta("fetched_at")
            if fetched:
                if _repo.load_from_store(store):
                    _snapshot_cache = {"fetched_at": fetched, "fetched_ts": time.monotonic()}
                    _cache_loaded_at = _snapshot_cache["fetched_ts"]
                    return True
        except Exception:
            pass

    return False


def _is_cache_valid() -> bool:
    """Return True if in-memory cache exists and hasn't expired."""
    if _snapshot_cache is None:
        return False
    if CACHE_TTL_SECONDS <= 0:
        return False
    age = time.monotonic() - _cache_loaded_at
    return age < CACHE_TTL_SECONDS


def _get_snapshot() -> dict | None:
    """Return current snapshot cache (may be None)."""
    return _snapshot_cache


def _get_cache_metadata() -> dict:
    """Return cache staleness info for inclusion in tool responses.

    Includes ``stale_warning: True`` when cache age exceeds 80% of TTL.
    """
    if _snapshot_cache is None:
        return {"cached": False}
    age = time.monotonic() - _cache_loaded_at
    meta: dict = {
        "cached": True,
        "cache_age_seconds": round(age, 1),
        "cache_fetched_at": _snapshot_cache.get("fetched_at", ""),
    }
    if CACHE_TTL_SECONDS > 0 and age > CACHE_TTL_SECONDS * 0.8:
        meta["stale_warning"] = True
        meta["cache_ttl_seconds"] = CACHE_TTL_SECONDS
    return meta


def _invalidate_cache() -> None:
    """Clear in-memory snapshot cache. Next read will hit the API."""
    global _snapshot_cache, _cache_loaded_at
    _snapshot_cache = None
    _cache_loaded_at = 0.0
    _repo.clear()
    # Also clear the cards.py process-level cache so list_decks/list_cards
    # re-query the API instead of returning stale data.
    from codecks_cli import config

    config._cache.clear()


def _extract_hand_ids(hand: list) -> set[str]:
    """Extract card IDs from hand list."""
    return {c.get("id") for c in hand if isinstance(c, dict) and c.get("id")}


def _compute_pm_focus(
    cards: list[dict], hand_ids: set[str], *, stale_days: int = 14, limit: int = 5
) -> dict:
    """Compute PM focus dashboard from pre-fetched cards and hand.

    Mirrors CodecksClient.pm_focus() at client.py:543-646.
    Operates on the enriched card format already in cache.
    """
    from datetime import timedelta

    from codecks_cli._utils import _parse_iso_timestamp

    cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)

    started = []
    blocked = []
    in_review = []
    hand_cards = []
    stale = []
    candidates = []
    deck_agg: dict[str, dict[str, int]] = {}
    owner_agg: dict[str, dict[str, int]] = {}

    for card in cards:
        status = card.get("status")
        is_stale = False

        if status == "started":
            started.append(card)
        if status == "blocked":
            blocked.append(card)
        if status == "in_review":
            in_review.append(card)

        cid = card.get("id")
        if cid and cid in hand_ids:
            hand_cards.append(card)
        if status == "not_started" and cid and cid not in hand_ids:
            candidates.append(card)

        # Stale: started or in_review cards not updated in stale_days
        if status in ("started", "in_review"):
            updated = _parse_iso_timestamp(
                card.get("updated_at") or card.get("lastUpdatedAt") or card.get("last_updated_at")
            )
            if updated and updated < cutoff:
                stale.append(card)
                is_stale = True

        # Aggregate by deck and owner
        deck = card.get("deck") or card.get("deck_name") or "unknown"
        owner = card.get("owner") or card.get("owner_name") or "unassigned"
        for key, agg in ((deck, deck_agg), (owner, owner_agg)):
            if key not in agg:
                agg[key] = {"total": 0, "blocked": 0, "stale": 0, "in_progress": 0}
            agg[key]["total"] += 1
            if status == "blocked":
                agg[key]["blocked"] += 1
            if is_stale:
                agg[key]["stale"] += 1
            if status in ("started", "in_review"):
                agg[key]["in_progress"] += 1

    # Sort candidates by priority (a > b > c > none)
    pri_rank = {"a": 0, "b": 1, "c": 2, None: 3, "": 3}
    candidates.sort(
        key=lambda c: (
            pri_rank.get(c.get("priority"), 3),
            0 if c.get("effort") is not None else 1,
            -(c.get("effort") or 0),
            str(c.get("title", "")).lower(),
        )
    )
    suggested = candidates[:limit]

    return {
        "counts": {
            "started": len(started),
            "blocked": len(blocked),
            "in_review": len(in_review),
            "hand": len(hand_cards),
            "stale": len(stale),
        },
        "blocked": blocked,
        "in_review": in_review,
        "hand": hand_cards,
        "stale": stale,
        "suggested": suggested,
        "deck_health": {
            "by_deck": deck_agg,
            "by_owner": owner_agg,
        },
        "filters": {
            "project": None,
            "owner": None,
            "limit": limit,
            "stale_days": stale_days,
        },
    }


def _compute_standup(cards: list[dict], hand_ids: set[str], *, days: int = 2) -> dict:
    """Compute daily standup from pre-fetched cards and hand.

    Mirrors CodecksClient.standup() at client.py:648-696.
    Operates on the enriched card format already in cache.
    """
    from datetime import timedelta

    from codecks_cli._utils import _parse_iso_timestamp

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    recently_done = []
    in_progress = []
    blocked = []
    hand_cards = []

    for card in cards:
        status = card.get("status")
        cid = card.get("id")

        if status == "done":
            updated = _parse_iso_timestamp(
                card.get("updated_at") or card.get("lastUpdatedAt") or card.get("last_updated_at")
            )
            if updated and updated >= cutoff:
                recently_done.append(card)
        elif status in ("started", "in_review"):
            in_progress.append(card)

        if status == "blocked":
            blocked.append(card)

        if cid and cid in hand_ids and status != "done":
            hand_cards.append(card)

    return {
        "recently_done": recently_done,
        "in_progress": in_progress,
        "blocked": blocked,
        "hand": hand_cards,
        "filters": {"project": None, "owner": None, "days": days},
    }


def _warm_cache_impl() -> dict:
    """Fetch all cacheable data, store in memory and on disk.

    Makes 4 API round-trips (down from ~10 before deduplication).
    pm_focus and standup are computed from the fetched cards+hand data.

    Returns:
        Summary dict with card_count, hand_size, deck_count, fetched_at.
    """
    global _snapshot_cache, _cache_loaded_at

    client = _get_client()
    now_ts = time.monotonic()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 4 API round-trips in parallel (account, cards, hand, decks)
    # Cache warming uses include_content=False — content only fetched on-demand
    # by get_card/search. Saves ~40-60% of API payload size.
    with ThreadPoolExecutor(max_workers=4) as pool:
        f_account = pool.submit(client.get_account)
        f_cards = pool.submit(client.list_cards, include_content=False)
        f_hand = pool.submit(client.list_hand)
        f_decks = pool.submit(client.list_decks, include_card_counts=False)

        _api_timeout = CACHE_TTL_SECONDS  # 60s — generous for parallel init
        account = f_account.result(timeout=_api_timeout)
        cards_result = f_cards.result(timeout=_api_timeout)
        hand = f_hand.result(timeout=_api_timeout)
        decks = f_decks.result(timeout=_api_timeout)

    # Compute derived views from pre-fetched data (0 API calls)
    all_cards = cards_result.get("cards", []) if isinstance(cards_result, dict) else []
    hand_ids = _extract_hand_ids(hand)
    pm_focus_data = _compute_pm_focus(all_cards, hand_ids)
    standup_data = _compute_standup(all_cards, hand_ids)

    snapshot = {
        "fetched_at": now_iso,
        "fetched_ts": now_ts,
        "account": account,
        "cards_result": cards_result,
        "hand": hand,
        "decks": decks,
        "pm_focus": pm_focus_data,
        "standup": standup_data,
    }

    _snapshot_cache = snapshot
    _cache_loaded_at = now_ts

    # Build card indexes and name mappings
    _repo.load(all_cards)
    if isinstance(decks, list):
        _repo.load_decks(decks)

    # Persist to disk (atomic write)
    disk_data = dict(snapshot)
    disk_data.pop("fetched_ts", None)
    try:
        cache_dir = os.path.dirname(CACHE_PATH) or "."
        fd, tmp = tempfile.mkstemp(dir=cache_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(disk_data, f, ensure_ascii=False)
            os.replace(tmp, CACHE_PATH)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except OSError:
        pass  # Disk write failure is non-fatal

    # Persist to SQLite store (best-effort)
    try:
        store = _get_store()
        _repo.persist_to_store(store)
        if isinstance(decks, list):
            store.upsert_decks(decks)
        store.set_meta("fetched_at", now_iso)
        store.set_meta("card_count", str(len(all_cards)))
    except Exception:
        pass  # SQLite persistence is best-effort

    return {
        "ok": True,
        "card_count": len(cards_result.get("cards", []) if isinstance(cards_result, dict) else []),
        "hand_size": len(hand) if isinstance(hand, list) else 0,
        "deck_count": len(decks) if isinstance(decks, list) else 0,
        "fetched_at": now_iso,
    }


# ---------------------------------------------------------------------------
# Agent session registry (persisted to disk)
# ---------------------------------------------------------------------------

_CLAIMS_FILE = ".pm_claims.json"
_CLAIMS_PATH = os.path.join(os.path.dirname(CACHE_PATH), _CLAIMS_FILE)

_agent_sessions: dict[str, dict] = {}


def _save_claims() -> None:
    """Persist agent claims to disk (atomic write via tempfile + os.replace)."""
    try:
        claims_dir = os.path.dirname(_CLAIMS_PATH) or "."
        fd, tmp = tempfile.mkstemp(dir=claims_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(_agent_sessions, f, ensure_ascii=False)
            os.replace(tmp, _CLAIMS_PATH)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except OSError:
        pass  # Disk write failure is non-fatal

    # Also persist to SQLite store (best-effort)
    try:
        store = _get_store()
        for agent_name, session in _agent_sessions.items():
            for card_id in session.get("active_cards", []):
                store.upsert_claim(card_id, agent_name)
    except Exception:
        pass


def _load_claims() -> None:
    """Load persisted agent claims from disk. Missing/corrupt file is OK."""
    global _agent_sessions
    try:
        with open(_CLAIMS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            _agent_sessions.update(data)
            return
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass  # JSON load failed — try SQLite fallback below

    # Fallback: try SQLite store
    try:
        store = _get_store()
        claims = store.all_claims()
        if claims:
            # Rebuild _agent_sessions from flat claim records
            for card_id, claim in claims.items():
                agent = claim.get("agent_name", "")
                if not agent:
                    continue
                if agent not in _agent_sessions:
                    _agent_sessions[agent] = {
                        "active_cards": [],
                        "claimed_at": {},
                        "last_seen": claim.get("claimed_at", ""),
                    }
                if card_id not in _agent_sessions[agent]["active_cards"]:
                    _agent_sessions[agent]["active_cards"].append(card_id)
                    _agent_sessions[agent]["claimed_at"][card_id] = claim.get("claimed_at", "")
    except Exception:
        pass


def _register_agent(agent_name: str, card_id: str | None = None) -> None:
    """Track an agent and optionally the card it is working on."""
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if agent_name not in _agent_sessions:
        _agent_sessions[agent_name] = {
            "active_cards": [],
            "claimed_at": {},
            "last_seen": now_iso,
        }
    _agent_sessions[agent_name]["last_seen"] = now_iso
    if card_id and card_id not in _agent_sessions[agent_name]["active_cards"]:
        _agent_sessions[agent_name]["active_cards"].append(card_id)
        _agent_sessions[agent_name]["claimed_at"][card_id] = now_iso
    _save_claims()


def _unregister_agent_card(agent_name: str, card_id: str) -> bool:
    """Remove a card from an agent's active list. Returns True if removed."""
    session = _agent_sessions.get(agent_name)
    if not session:
        return False
    if card_id in session["active_cards"]:
        session["active_cards"].remove(card_id)
        session["claimed_at"].pop(card_id, None)
        session["last_seen"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        _save_claims()
        return True
    return False


def _get_agent_for_card(card_id: str) -> str | None:
    """Return the agent name that has claimed a card, or None."""
    for name, session in _agent_sessions.items():
        if card_id in session.get("active_cards", []):
            return name
    return None


def _get_all_sessions() -> dict[str, dict]:
    """Return a copy of all agent sessions."""
    return {name: dict(session) for name, session in _agent_sessions.items()}


def _reset_sessions() -> None:
    """Clear all agent sessions (for test isolation)."""
    _agent_sessions.clear()


# Load persisted claims on module init
_load_claims()


# ---------------------------------------------------------------------------
# Selective cache invalidation
# ---------------------------------------------------------------------------

_CACHE_INVALIDATION_MAP: dict[str, list[str]] = {
    "add_to_hand": ["hand", "pm_focus", "standup"],
    "remove_from_hand": ["hand", "pm_focus", "standup"],
    "create_card": ["cards_result", "pm_focus", "standup"],
    "update_cards": ["cards_result", "pm_focus", "standup"],
    "mark_done": ["cards_result", "pm_focus", "standup"],
    "mark_started": ["cards_result", "pm_focus", "standup"],
    "archive_card": ["cards_result", "pm_focus", "standup"],
    "unarchive_card": ["cards_result", "pm_focus", "standup"],
    "delete_card": ["cards_result", "pm_focus", "standup"],
    "scaffold_feature": ["cards_result", "pm_focus", "standup"],
    "split_features": ["cards_result", "pm_focus", "standup"],
    # Comment mutations don't affect card lists
    "create_comment": [],
    "reply_comment": [],
    "close_comment": [],
    "reopen_comment": [],
}


def _invalidate_cache_for(method_name: str) -> None:
    """Selectively invalidate cache keys affected by a mutation.

    Falls back to full invalidation for unknown methods.
    """
    if method_name not in _CACHE_INVALIDATION_MAP:
        _invalidate_cache()
        return
    keys = _CACHE_INVALIDATION_MAP[method_name]
    if not keys or _snapshot_cache is None:
        return
    for key in keys:
        _snapshot_cache.pop(key, None)
    if "cards_result" in keys:
        _repo.clear()


# ---------------------------------------------------------------------------
# Write-through cache + disk sync (cross-process coherence)
# ---------------------------------------------------------------------------


def _persist_cache_to_disk() -> None:
    """Write current in-memory cache to disk for cross-process sharing.

    Other MCP server processes will detect the updated file via mtime
    comparison in ``_load_cache_from_disk()`` and reload automatically.
    Skipped during batch operations (``_batch_in_progress``) to avoid
    excessive disk writes — caller persists once after the batch.
    """
    global _disk_cache_mtime
    if _snapshot_cache is None or _batch_in_progress:
        return
    try:
        disk_data = {k: v for k, v in _snapshot_cache.items() if k != "fetched_ts"}
        disk_data["fetched_at"] = datetime.now(timezone.utc).isoformat()
        cache_dir = os.path.dirname(CACHE_PATH) or "."
        fd, tmp = tempfile.mkstemp(dir=cache_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(
                    disk_data, f, default=str
                )  # default=str prevents TypeError on non-serializable
            os.replace(tmp, CACHE_PATH)
            # Update our mtime so we don't reload our own write
            _disk_cache_mtime = os.path.getmtime(CACHE_PATH)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except (OSError, TypeError, ValueError):
        pass  # Non-fatal — cache is best-effort


def _recompute_derived() -> None:
    """Recompute pm_focus and standup from current cache state."""
    if _snapshot_cache is None:
        return
    cards = _snapshot_cache.get("cards_result", {}).get("cards", [])
    hand_ids = _extract_hand_ids(_snapshot_cache.get("hand", []))
    _snapshot_cache["pm_focus"] = _compute_pm_focus(cards, hand_ids)
    _snapshot_cache["standup"] = _compute_standup(cards, hand_ids)


def _write_through_cache(method_name: str, result, **kwargs) -> None:
    """Update in-memory cache after a successful mutation.

    Instead of invalidating (deleting cache keys and forcing an API call),
    we inject the mutation result directly into the cache. This gives
    same-process reads instant consistency.
    """
    if _snapshot_cache is None:
        return
    if not isinstance(result, dict) or not result.get("ok"):
        # Mutation failed or result is not a dict — fall back to invalidation
        _invalidate_cache_for(method_name)
        return

    cards_result = _snapshot_cache.get("cards_result")
    if not isinstance(cards_result, dict):
        _invalidate_cache_for(method_name)
        return
    cards: list = cards_result.get("cards", [])

    try:
        if method_name == "create_card":
            card_id = result.get("card_id", "")
            if card_id:
                new_card = {
                    "id": card_id,
                    "title": result.get("title", kwargs.get("title", "")),
                    "status": "not_started",
                    "priority": kwargs.get("priority"),
                    "effort": kwargs.get("effort"),
                    "deck_name": result.get("deck", kwargs.get("deck", "")),
                    "owner_name": result.get("owner", kwargs.get("owner", "")),
                }
                cards.append(new_card)
                _repo.add(new_card)
                _recompute_derived()

        elif method_name == "delete_card":
            card_id = kwargs.get("card_id", "")
            cards_result["cards"] = [c for c in cards if c.get("id") != card_id]
            _repo.remove(card_id)
            # Also remove from hand if present
            hand = _snapshot_cache.get("hand", [])
            _snapshot_cache["hand"] = [c for c in hand if c.get("id") != card_id]
            _recompute_derived()

        elif method_name in ("mark_done", "mark_started"):
            # mark_done/mark_started take card_ids (plural list), not card_id
            card_ids = kwargs.get("card_ids", [])
            new_status = "done" if method_name == "mark_done" else "started"
            for cid in card_ids:
                for card in cards:
                    if card.get("id") == cid:
                        card["status"] = new_status
                        break
                _repo.update(cid, {"status": new_status})
            _recompute_derived()

        elif method_name == "add_to_hand":
            added_ids = set(kwargs.get("card_ids", []))
            hand = _snapshot_cache.get("hand", [])
            existing_ids = {c.get("id") for c in hand}
            for card in cards:
                if card.get("id") in added_ids and card.get("id") not in existing_ids:
                    hand.append(card)
            _recompute_derived()

        elif method_name == "remove_from_hand":
            removed_ids = set(kwargs.get("card_ids", []))
            _snapshot_cache["hand"] = [
                c for c in _snapshot_cache.get("hand", []) if c.get("id") not in removed_ids
            ]
            _recompute_derived()

        elif method_name == "archive_card":
            card_id = kwargs.get("card_id", "")
            cards_result["cards"] = [c for c in cards if c.get("id") != card_id]
            _repo.remove(card_id)
            hand = _snapshot_cache.get("hand", [])
            _snapshot_cache["hand"] = [c for c in hand if c.get("id") != card_id]
            _recompute_derived()

        else:
            # For update_cards, scaffold_feature, split_features, etc.
            # — fall back to selective invalidation (too complex to write-through)
            _invalidate_cache_for(method_name)
            return

    except Exception:
        # Any error in write-through: fall back to safe invalidation
        _invalidate_cache_for(method_name)
        return

    # Persist to disk for cross-process coherence
    _persist_cache_to_disk()


# ---------------------------------------------------------------------------
# Response contract helpers
# ---------------------------------------------------------------------------


def _contract_error(
    message: str,
    error_type: str = "error",
    *,
    retryable: bool = False,
    error_code: str = "UNKNOWN",
) -> dict:
    """Return a stable MCP error envelope with legacy compatibility fields."""
    return {
        "ok": False,
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "type": error_type,  # legacy
        "error": message,  # legacy
        "retryable": retryable,
        "error_code": error_code,
        "error_detail": {
            "type": error_type,
            "message": message,
        },
    }


def _ensure_contract_dict(payload: dict) -> dict:
    """Add stable contract metadata to dict responses."""
    out = dict(payload)
    out.setdefault("schema_version", CONTRACT_SCHEMA_VERSION)
    if out.get("ok") is False:
        error_type = str(out.get("type", "error"))
        error_message = out.get("error", "Unknown error")
        if not isinstance(error_message, str):
            error_message = str(error_message)
            out["error"] = error_message
        out.setdefault(
            "error_detail",
            {
                "type": error_type,
                "message": error_message,
            },
        )
        return out
    out.setdefault("ok", True)
    return out


def _finalize_tool_result(result):
    """Finalize tool response based on configured MCP response mode.

    Modes:
        - legacy (default): preserve existing top-level shapes; dicts gain
          contract metadata (ok/schema_version).
        - envelope: always return {"ok", "schema_version", "data"} for success.
    """
    if isinstance(result, dict):
        normalized = _ensure_contract_dict(result)
        if normalized.get("ok") is False:
            return normalized
        if MCP_RESPONSE_MODE == "envelope":
            data = dict(normalized)
            data.pop("ok", None)
            data.pop("schema_version", None)
            return {
                "ok": True,
                "schema_version": CONTRACT_SCHEMA_VERSION,
                "data": data,
            }
        return normalized
    if MCP_RESPONSE_MODE == "envelope":
        return {
            "ok": True,
            "schema_version": CONTRACT_SCHEMA_VERSION,
            "data": result,
        }
    return result


# ---------------------------------------------------------------------------
# Client method dispatch
# ---------------------------------------------------------------------------

_ALLOWED_METHODS = {
    "get_account",
    "list_cards",
    "get_card",
    "list_decks",
    "list_projects",
    "list_milestones",
    "list_tags",
    "list_activity",
    "pm_focus",
    "standup",
    "list_hand",
    "add_to_hand",
    "remove_from_hand",
    "create_card",
    "update_cards",
    "mark_done",
    "mark_started",
    "archive_card",
    "unarchive_card",
    "delete_card",
    "scaffold_feature",
    "split_features",
    "create_comment",
    "reply_comment",
    "close_comment",
    "list_conversations",
    "reopen_comment",
}

_MUTATION_METHODS = {
    "create_card",
    "update_cards",
    "mark_done",
    "mark_started",
    "archive_card",
    "unarchive_card",
    "delete_card",
    "scaffold_feature",
    "split_features",
    "add_to_hand",
    "remove_from_hand",
    "create_comment",
    "reply_comment",
    "close_comment",
    "reopen_comment",
}

# Methods that save undo snapshots before executing
_UNDOABLE_METHODS = {"update_cards", "mark_done", "mark_started"}


def _find_uuid_hint(short_id: str) -> str:
    """Search cache for a card whose ID starts with the given prefix."""
    if _snapshot_cache is None:
        return ""
    cards_result = _snapshot_cache.get("cards_result")
    if not isinstance(cards_result, dict):
        return ""
    for card in cards_result.get("cards", []):
        if isinstance(card, dict):
            full_id = card.get("id", "")
            if full_id.startswith(short_id) or full_id.replace("-", "").startswith(short_id):
                title = card.get("title", "")[:50]
                return f" Did you mean '{full_id}' ({title})?"
    return ""


def _validate_uuid(value: str, field: str = "card_id") -> str:
    """Validate that a string is a 36-char UUID. Raises CliError if not."""
    if not isinstance(value, str) or len(value) != 36 or value.count("-") != 4:
        hint = ""
        if isinstance(value, str) and 4 <= len(value) <= 12:
            hint = _find_uuid_hint(value)
        raise CliError(
            f"[ERROR] {field} must be a full 36-char UUID, got: {value!r}. "
            f"Short IDs like 8-char codes do not work with the API.{hint}"
        )
    return value


def _validate_uuid_list(values: list[str], field: str = "card_ids") -> list[str]:
    """Validate a list of UUID strings."""
    return [_validate_uuid(v, field) for v in values]


def _call(method_name: str, **kwargs):
    """Call a CodecksClient method, converting exceptions to error dicts.

    Mutations automatically update the snapshot cache via write-through.
    Undoable mutations (update_cards, mark_done, mark_started) save an undo
    snapshot before executing.

    All API calls are bounded by ``HTTP_TIMEOUT_SECONDS * 2`` to prevent
    agent hangs on unresponsive API endpoints.
    """
    if method_name not in _ALLOWED_METHODS:
        return _contract_error(f"Unknown method: {method_name}", "error")

    # Rate-limit awareness: pause if approaching API limit
    now = time.monotonic()
    _api_call_timestamps[:] = [t for t in _api_call_timestamps if now - t < _RATE_LIMIT_WINDOW]
    if len(_api_call_timestamps) >= _RATE_LIMIT_MAX:
        wait = _RATE_LIMIT_WINDOW - (now - _api_call_timestamps[0])
        if wait > 0:
            time.sleep(min(wait, _RATE_LIMIT_WINDOW))
    _api_call_timestamps.append(time.monotonic())

    try:
        client = _get_client()
        # Save undo snapshot before undoable mutations
        if method_name in _UNDOABLE_METHODS:
            card_ids = kwargs.get("card_ids", [])
            if card_ids:
                try:
                    from codecks_cli._operations import snapshot_before_mutation

                    snapshot_before_mutation(client, card_ids)
                except Exception:
                    pass  # Best-effort snapshot
        result = getattr(client, method_name)(**kwargs)
        if method_name in _MUTATION_METHODS:
            _write_through_cache(method_name, result, **kwargs)
        return result
    except SetupError as e:
        return _contract_error(str(e), "setup", retryable=False, error_code="SETUP_ERROR")
    except CliError as e:
        error_msg = str(e)
        # Enhance deck/milestone resolution errors with available values
        context = _suggest_valid_values(error_msg)
        if context:
            error_msg = f"{error_msg}\n{context}"
        return _contract_error(error_msg, "error", retryable=False, error_code="CLI_ERROR")
    except (ConnectionError, TimeoutError, OSError) as e:
        return _contract_error(
            f"Network error calling {method_name}: {e}. "
            f"The operation may have partially completed — check state before retrying.",
            "error",
            retryable=True,
            error_code="NETWORK_ERROR",
        )
    except Exception as e:
        return _contract_error(
            f"Unexpected error in {method_name}: {e}",
            "error",
            retryable=True,
            error_code="UNEXPECTED_ERROR",
        )


def _suggest_valid_values(error_msg: str) -> str:
    """Enhance error messages with available values from cache.

    When an agent misspells a deck name or uses a wrong milestone,
    this provides the valid options so the LLM can self-correct.
    """
    msg_lower = error_msg.lower()
    suggestions = []
    if "deck" in msg_lower and ("not found" in msg_lower or "unknown" in msg_lower):
        deck_names = [name for name in _repo._deck_name_to_id.keys()] if _repo else []
        if deck_names:
            suggestions.append(f"Available decks: {', '.join(sorted(deck_names, key=str.lower))}")
    if "milestone" in msg_lower and ("not found" in msg_lower or "unknown" in msg_lower):
        if _snapshot_cache and "milestones" in _snapshot_cache:
            ms = _snapshot_cache["milestones"]
            if isinstance(ms, list):
                names = [m.get("name", "") for m in ms if isinstance(m, dict)]
                if names:
                    suggestions.append(f"Available milestones: {', '.join(names)}")
    if "owner" in msg_lower and ("not found" in msg_lower or "unknown" in msg_lower):
        owners = set(_repo._by_owner.keys()) if _repo else set()
        if owners:
            suggestions.append(f"Available owners: {', '.join(sorted(owners))}")
    return "\n".join(suggestions)


# ---------------------------------------------------------------------------
# Card/deck slimming for token efficiency
# ---------------------------------------------------------------------------

_SLIM_DROP = {
    "deckId",
    "deck_id",
    "milestoneId",
    "milestone_id",
    "assignee",
    "projectId",
    "project_id",
    "childCardInfo",
    "child_card_info",
    "masterTags",
}

_SLIM_LIST_DROP = _SLIM_DROP | {
    "accountId",
    "cardId",
    "createdAt",
    "content",
    "isDoc",
    "is_doc",
    "lastUpdatedAt",
    "last_updated_at",
    "checkboxStats",
    "checkbox_stats",
    "resolvables",
}

# Minimal fields for _card_summary — 7-field ultra-compact representation (~200 bytes)
_SUMMARY_FIELDS = {
    "id",
    "title",
    "status",
    "priority",
    "effort",
    "deck",
    "deck_name",
    "owner",
    "owner_name",
}


def _slim_card(card: dict) -> dict:
    """Strip redundant raw IDs from a card dict for token efficiency."""
    return {k: v for k, v in card.items() if k not in _SLIM_DROP}


def _slim_card_list(card: dict) -> dict:
    """Extra-slim card for list views (drops timestamps, content, and extra IDs)."""
    return {k: v for k, v in card.items() if k not in _SLIM_LIST_DROP}


def _card_summary(card: dict) -> dict:
    """Ultra-compact card representation (~200 bytes vs ~2KB full).

    Returns only: id, title, status, priority, effort, deck, owner.
    Use for dashboard card arrays where full card data isn't needed.
    """
    return {
        "id": card.get("id", ""),
        "title": card.get("title", ""),
        "status": card.get("status"),
        "priority": card.get("priority"),
        "effort": card.get("effort"),
        "deck": card.get("deck") or card.get("deck_name") or "",
        "owner": card.get("owner") or card.get("owner_name") or "",
    }


def _slim_deck(deck: dict) -> dict:
    """Strip redundant fields from deck dicts."""
    drop = {"projectId", "project_id"}
    return {k: v for k, v in deck.items() if k not in drop}
