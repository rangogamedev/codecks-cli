"""Tests for MCP server snapshot cache (warm_cache, cache_status, cached reads, invalidation)."""

import json
import time
from unittest.mock import MagicMock, patch

import pytest

from codecks_cli.mcp_server import _core

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_ACCOUNT = {"name": "Test", "id": "acc-1", "email": "t@t.com"}
SAMPLE_CARDS = [
    {
        "id": "aaaabbbb-cccc-dddd-eeee-ffffffffffff",
        "title": "Card A",
        "status": "started",
        "priority": "a",
        "deck": "Code",
        "owner": "Alice",
        "content": "body A",
        "effort": 3,
        "updated_at": "2026-03-01T10:00:00Z",
    },
    {
        "id": "aaaabbbb-cccc-dddd-eeee-gggggggggggg",
        "title": "Card B",
        "status": "blocked",
        "priority": "b",
        "deck": "Art",
        "owner": "Bob",
        "content": "body B",
        "effort": 5,
        "updated_at": "2026-01-01T10:00:00Z",
    },
    {
        "id": "aaaabbbb-cccc-dddd-eeee-hhhhhhhhhhhh",
        "title": "Card C",
        "status": "not_started",
        "priority": "c",
        "deck": "Code",
        "owner": None,
        "content": "body C",
        "effort": 1,
        "updated_at": "2026-03-04T10:00:00Z",
    },
]
SAMPLE_HAND = [
    {"id": "aaaabbbb-cccc-dddd-eeee-ffffffffffff", "title": "Card A", "status": "started"}
]
SAMPLE_DECKS = [{"id": "d-1", "name": "Code", "projectId": "p-1"}, {"id": "d-2", "name": "Art"}]
SAMPLE_PM_FOCUS = {
    "counts": {"total": 3, "blocked": 1, "stale": 1},
    "blocked": [SAMPLE_CARDS[1]],
    "stale": [SAMPLE_CARDS[1]],
    "in_review": [],
    "hand": SAMPLE_HAND,
    "suggested": [SAMPLE_CARDS[2]],
}
SAMPLE_STANDUP = {
    "recently_done": [],
    "in_progress": [SAMPLE_CARDS[0]],
    "blocked": [SAMPLE_CARDS[1]],
    "hand": SAMPLE_HAND,
}


def _make_snapshot():
    """Build a valid in-memory snapshot dict."""
    return {
        "fetched_at": "2026-03-05T10:00:00Z",
        "fetched_ts": time.monotonic(),
        "account": SAMPLE_ACCOUNT,
        "cards_result": {"cards": SAMPLE_CARDS, "stats": None},
        "hand": SAMPLE_HAND,
        "decks": SAMPLE_DECKS,
        "pm_focus": SAMPLE_PM_FOCUS,
        "standup": SAMPLE_STANDUP,
    }


@pytest.fixture(autouse=True)
def _reset_cache():
    """Ensure cache is clean before and after each test."""
    _core._invalidate_cache()
    # Use an in-memory SQLite store to avoid reading stale data from .pm_store.db
    from codecks_cli.store import CardStore

    _core._reset_store()
    _core._store = CardStore(":memory:")
    yield
    _core._invalidate_cache()
    _core._reset_store()


def _inject_cache(snapshot=None):
    """Directly inject a snapshot into the cache for testing."""
    snap = snapshot or _make_snapshot()
    _core._snapshot_cache = snap
    _core._cache_loaded_at = snap["fetched_ts"]
    # Rebuild card repository indexes from injected data
    cards_data = snap.get("cards_result")
    if isinstance(cards_data, dict):
        _core._repo.load(cards_data.get("cards", []))


# ---------------------------------------------------------------------------
# Cache Core Tests
# ---------------------------------------------------------------------------


class TestCacheCore:
    def test_cache_starts_empty(self):
        assert _core._snapshot_cache is None
        assert _core._cache_loaded_at == 0.0

    def test_load_cache_from_disk_missing_file(self, tmp_path):
        with patch.object(_core, "CACHE_PATH", str(tmp_path / "missing.json")):
            assert _core._load_cache_from_disk() is False
            assert _core._snapshot_cache is None

    def test_load_cache_from_disk_valid(self, tmp_path):
        cache_file = tmp_path / "cache.json"
        cache_file.write_text(json.dumps({"fetched_at": "2026-03-05T10:00:00Z", "account": {}}))
        with patch.object(_core, "CACHE_PATH", str(cache_file)):
            assert _core._load_cache_from_disk() is True
            assert _core._snapshot_cache is not None
            assert _core._snapshot_cache["fetched_at"] == "2026-03-05T10:00:00Z"

    def test_load_cache_from_disk_invalid_json(self, tmp_path):
        cache_file = tmp_path / "cache.json"
        cache_file.write_text("not json")
        with patch.object(_core, "CACHE_PATH", str(cache_file)):
            assert _core._load_cache_from_disk() is False

    def test_load_cache_from_disk_missing_fetched_at(self, tmp_path):
        cache_file = tmp_path / "cache.json"
        cache_file.write_text(json.dumps({"account": {}}))
        with patch.object(_core, "CACHE_PATH", str(cache_file)):
            assert _core._load_cache_from_disk() is False

    def test_load_cache_idempotent(self, tmp_path):
        """Second call returns True without re-reading disk (same mtime)."""
        cache_file = tmp_path / "cache.json"
        cache_file.write_text(json.dumps({"fetched_at": "2026-03-05T10:00:00Z"}))
        with patch.object(_core, "CACHE_PATH", str(cache_file)):
            _core._load_cache_from_disk()
            # Second call with same file (unchanged mtime) returns True via early-return
            assert _core._load_cache_from_disk() is True

    def test_is_cache_valid_when_empty(self):
        assert _core._is_cache_valid() is False

    def test_is_cache_valid_within_ttl(self):
        _inject_cache()
        assert _core._is_cache_valid() is True

    def test_is_cache_valid_expired(self):
        snap = _make_snapshot()
        snap["fetched_ts"] = time.monotonic() - 600  # 10 min ago
        _inject_cache(snap)
        _core._cache_loaded_at = snap["fetched_ts"]
        assert _core._is_cache_valid() is False

    def test_is_cache_valid_ttl_zero_disables(self):
        _inject_cache()
        with patch.object(_core, "CACHE_TTL_SECONDS", 0):
            assert _core._is_cache_valid() is False

    def test_invalidate_cache_clears_state(self):
        _inject_cache()
        assert _core._snapshot_cache is not None
        _core._invalidate_cache()
        assert _core._snapshot_cache is None
        assert _core._cache_loaded_at == 0.0

    def test_get_cache_metadata_no_cache(self):
        meta = _core._get_cache_metadata()
        assert meta == {"cached": False}

    def test_get_cache_metadata_with_cache(self):
        _inject_cache()
        meta = _core._get_cache_metadata()
        assert meta["cached"] is True
        assert "cache_age_seconds" in meta
        assert meta["cache_fetched_at"] == "2026-03-05T10:00:00Z"

    def test_get_snapshot_returns_cache(self):
        _inject_cache()
        assert _core._get_snapshot() is not None
        assert _core._get_snapshot()["fetched_at"] == "2026-03-05T10:00:00Z"

    def test_get_snapshot_returns_none_when_empty(self):
        assert _core._get_snapshot() is None


class TestSlimHelpers:
    def test_slim_card_list_drops_extra_fields(self):
        card = {
            "id": "1",
            "title": "T",
            "accountId": "a",
            "cardId": "c",
            "createdAt": "d",
            "deck": "X",
        }
        slimmed = _core._slim_card_list(card)
        assert "id" in slimmed
        assert "title" in slimmed
        assert "deck" in slimmed
        assert "accountId" not in slimmed
        assert "cardId" not in slimmed
        assert "createdAt" not in slimmed

    def test_slim_deck_drops_project_id(self):
        deck = {"id": "d-1", "name": "Code", "projectId": "p-1"}
        slimmed = _core._slim_deck(deck)
        assert "name" in slimmed
        assert "projectId" not in slimmed


# ---------------------------------------------------------------------------
# Warm Cache Tests
# ---------------------------------------------------------------------------


class TestWarmCache:
    def test_warm_cache_impl_populates_memory(self):
        mock_client = MagicMock()
        mock_client.get_account.return_value = SAMPLE_ACCOUNT
        mock_client.list_cards.return_value = {"cards": SAMPLE_CARDS, "stats": None}
        mock_client.list_hand.return_value = SAMPLE_HAND
        mock_client.list_decks.return_value = SAMPLE_DECKS

        with (
            patch.object(_core, "_get_client", return_value=mock_client),
            patch.object(_core, "CACHE_PATH", "/dev/null"),
        ):
            result = _core._warm_cache_impl()

        assert result["ok"] is True
        assert result["card_count"] == 3
        assert result["hand_size"] == 1
        assert result["deck_count"] == 2
        assert _core._snapshot_cache is not None
        assert _core._is_cache_valid() is True
        # pm_focus and standup are computed, not fetched
        mock_client.pm_focus.assert_not_called()
        mock_client.standup.assert_not_called()
        assert "pm_focus" in _core._snapshot_cache
        assert "standup" in _core._snapshot_cache

    def test_warm_cache_impl_computes_pm_focus(self):
        """Verify computed pm_focus has the expected structure."""
        mock_client = MagicMock()
        mock_client.get_account.return_value = SAMPLE_ACCOUNT
        mock_client.list_cards.return_value = {"cards": SAMPLE_CARDS, "stats": None}
        mock_client.list_hand.return_value = SAMPLE_HAND
        mock_client.list_decks.return_value = SAMPLE_DECKS

        with (
            patch.object(_core, "_get_client", return_value=mock_client),
            patch.object(_core, "CACHE_PATH", "/dev/null"),
        ):
            _core._warm_cache_impl()

        pm = _core._snapshot_cache["pm_focus"]
        assert "counts" in pm
        assert "blocked" in pm
        assert "in_review" in pm
        assert "hand" in pm
        assert "stale" in pm
        assert "suggested" in pm
        assert "deck_health" in pm
        assert "filters" in pm
        # Card B is blocked
        assert pm["counts"]["blocked"] == 1

    def test_warm_cache_impl_computes_standup(self):
        """Verify computed standup has the expected structure."""
        mock_client = MagicMock()
        mock_client.get_account.return_value = SAMPLE_ACCOUNT
        mock_client.list_cards.return_value = {"cards": SAMPLE_CARDS, "stats": None}
        mock_client.list_hand.return_value = SAMPLE_HAND
        mock_client.list_decks.return_value = SAMPLE_DECKS

        with (
            patch.object(_core, "_get_client", return_value=mock_client),
            patch.object(_core, "CACHE_PATH", "/dev/null"),
        ):
            _core._warm_cache_impl()

        standup = _core._snapshot_cache["standup"]
        assert "recently_done" in standup
        assert "in_progress" in standup
        assert "blocked" in standup
        assert "hand" in standup
        assert "filters" in standup

    def test_warm_cache_populates_repository(self):
        """Verify warm_cache builds repository indexes."""
        mock_client = MagicMock()
        mock_client.get_account.return_value = SAMPLE_ACCOUNT
        mock_client.list_cards.return_value = {"cards": SAMPLE_CARDS, "stats": None}
        mock_client.list_hand.return_value = SAMPLE_HAND
        mock_client.list_decks.return_value = SAMPLE_DECKS

        with (
            patch.object(_core, "_get_client", return_value=mock_client),
            patch.object(_core, "CACHE_PATH", "/dev/null"),
        ):
            _core._warm_cache_impl()

        repo = _core.get_repository()
        assert repo.count == 3
        assert repo.get(SAMPLE_CARDS[0]["id"]) is not None

    def test_warm_cache_impl_writes_disk(self, tmp_path):
        mock_client = MagicMock()
        mock_client.get_account.return_value = SAMPLE_ACCOUNT
        mock_client.list_cards.return_value = {"cards": [], "stats": None}
        mock_client.list_hand.return_value = []
        mock_client.list_decks.return_value = []

        cache_file = tmp_path / ".pm_cache.json"
        with (
            patch.object(_core, "_get_client", return_value=mock_client),
            patch.object(_core, "CACHE_PATH", str(cache_file)),
        ):
            _core._warm_cache_impl()

        assert cache_file.exists()
        data = json.loads(cache_file.read_text())
        assert "fetched_at" in data
        assert "fetched_ts" not in data  # Should not persist monotonic timestamp

    def test_warm_cache_mcp_tool(self):
        """Test the warm_cache() MCP tool wrapper."""
        from codecks_cli.mcp_server._tools_local import warm_cache

        mock_client = MagicMock()
        mock_client.get_account.return_value = SAMPLE_ACCOUNT
        mock_client.list_cards.return_value = {"cards": SAMPLE_CARDS, "stats": None}
        mock_client.list_hand.return_value = SAMPLE_HAND
        mock_client.list_decks.return_value = SAMPLE_DECKS

        with (
            patch("codecks_cli.mcp_server._core._get_client", return_value=mock_client),
            patch("codecks_cli.mcp_server._core.CACHE_PATH", "/dev/null"),
        ):
            result = warm_cache()

        assert result["ok"] is True
        assert result["card_count"] == 3

    def test_warm_cache_error_handling(self):
        from codecks_cli.mcp_server._tools_local import warm_cache

        with patch("codecks_cli.mcp_server._core._get_client", side_effect=Exception("no auth")):
            result = warm_cache()
        assert result["ok"] is False
        assert "no auth" in result["error"]


# ---------------------------------------------------------------------------
# Cache Status Tests
# ---------------------------------------------------------------------------


class TestCacheStatus:
    def test_cache_status_empty(self):
        from codecks_cli.mcp_server._tools_local import cache_status

        with patch.object(_core, "CACHE_PATH", "/nonexistent/path"):
            result = cache_status()
        assert result["cached"] is False

    def test_cache_status_after_warm(self):
        from codecks_cli.mcp_server._tools_local import cache_status

        _inject_cache()
        result = cache_status()
        assert result["cached"] is True
        assert result["card_count"] == 3
        assert result["hand_size"] == 1
        assert "ttl_seconds" in result
        assert "ttl_remaining_seconds" in result
        assert result["expired"] is False


# ---------------------------------------------------------------------------
# Cached Read Tool Tests
# ---------------------------------------------------------------------------


class TestCachedReads:
    def test_list_cards_serves_from_cache(self):
        from codecks_cli.mcp_server._tools_read import list_cards

        _inject_cache()
        result = list_cards()
        assert result["cached"] is True
        assert result["total_count"] == 3

    def test_list_cards_with_status_filter_from_cache(self):
        from codecks_cli.mcp_server._tools_read import list_cards

        _inject_cache()
        result = list_cards(status="blocked")
        assert result["cached"] is True
        assert result["total_count"] == 1
        assert "Card B" in result["cards"][0]["title"]

    def test_list_cards_with_deck_filter_from_cache(self):
        from codecks_cli.mcp_server._tools_read import list_cards

        _inject_cache()
        result = list_cards(deck="Code")
        assert result["cached"] is True
        assert result["total_count"] == 2

    def test_list_cards_with_owner_filter_from_cache(self):
        from codecks_cli.mcp_server._tools_read import list_cards

        _inject_cache()
        result = list_cards(owner="none")
        assert result["cached"] is True
        assert result["total_count"] == 1
        assert "Card C" in result["cards"][0]["title"]

    def test_list_cards_with_search_from_cache(self):
        from codecks_cli.mcp_server._tools_read import list_cards

        _inject_cache()
        result = list_cards(search="Card A")
        assert result["cached"] is True
        assert result["total_count"] == 1

    def test_list_cards_pagination_from_cache(self):
        from codecks_cli.mcp_server._tools_read import list_cards

        _inject_cache()
        result = list_cards(limit=2, offset=0)
        assert result["total_count"] == 3
        assert len(result["cards"]) == 2
        assert result["has_more"] is True

    def test_list_cards_sort_from_cache(self):
        from codecks_cli.mcp_server._tools_read import list_cards

        _inject_cache()
        result = list_cards(sort="title")
        assert "Card A" in result["cards"][0]["title"]
        assert "Card C" in result["cards"][2]["title"]

    def test_list_cards_archived_bypasses_cache(self):
        from codecks_cli.mcp_server._tools_read import list_cards

        _inject_cache()
        with patch("codecks_cli.mcp_server._tools_read._call") as mock_call:
            mock_call.return_value = {"cards": [], "stats": None}
            list_cards(archived=True)
            mock_call.assert_called_once()

    def test_list_cards_falls_through_on_miss(self):
        from codecks_cli.mcp_server._tools_read import list_cards

        with patch("codecks_cli.mcp_server._tools_read._call") as mock_call:
            mock_call.return_value = {"cards": SAMPLE_CARDS, "stats": None}
            result = list_cards()
            mock_call.assert_called_once()
            assert "cached" not in result or result.get("cached") is not True

    def test_get_account_from_cache(self):
        from codecks_cli.mcp_server._tools_read import get_account

        _inject_cache()
        result = get_account()
        assert result["cached"] is True
        assert result["name"] == "Test"

    def test_get_account_falls_through(self, tmp_path):
        from codecks_cli.mcp_server._tools_read import get_account

        # No cache injected + no disk cache — should fall through to API
        with (
            patch.object(_core, "CACHE_PATH", str(tmp_path / "missing.json")),
            patch("codecks_cli.mcp_server._tools_read._call") as mock_call,
        ):
            mock_call.return_value = SAMPLE_ACCOUNT
            get_account()
            mock_call.assert_called_once()

    def test_list_decks_from_cache(self):
        from codecks_cli.mcp_server._tools_read import list_decks

        _inject_cache()
        result = list_decks()
        assert result["cached"] is True
        decks = result["decks"]
        assert len(decks) == 2
        # projectId should be stripped by _slim_deck
        assert "projectId" not in decks[0]

    def test_get_card_from_cache_no_conversations(self):
        from codecks_cli.mcp_server._tools_read import get_card

        _inject_cache()
        result = get_card("aaaabbbb-cccc-dddd-eeee-ffffffffffff", include_conversations=False)
        assert result["cached"] is True
        assert "Card A" in result["title"]

    def test_get_card_with_conversations_bypasses_cache(self):
        from codecks_cli.mcp_server._tools_read import get_card

        _inject_cache()
        with patch("codecks_cli.mcp_server._tools_read._call") as mock_call:
            mock_call.return_value = {**SAMPLE_CARDS[0], "conversations": []}
            get_card("aaaabbbb-cccc-dddd-eeee-ffffffffffff", include_conversations=True)
            mock_call.assert_called_once()

    def test_get_card_cache_miss_falls_through(self):
        from codecks_cli.mcp_server._tools_read import get_card

        _inject_cache()
        with patch("codecks_cli.mcp_server._tools_read._call") as mock_call:
            mock_call.return_value = {"id": "unknown", "title": "New"}
            # This ID is not in the cache
            get_card("zzzzzzzz-zzzz-zzzz-zzzz-zzzzzzzzzzzz", include_conversations=False)
            mock_call.assert_called_once()

    def test_pm_focus_from_cache(self):
        from codecks_cli.mcp_server._tools_read import pm_focus

        _inject_cache()
        result = pm_focus()
        assert result["cached"] is True
        assert "counts" in result

    def test_pm_focus_with_filter_bypasses_cache(self):
        from codecks_cli.mcp_server._tools_read import pm_focus

        _inject_cache()
        with patch("codecks_cli.mcp_server._tools_read._call") as mock_call:
            mock_call.return_value = SAMPLE_PM_FOCUS
            pm_focus(project="Code")
            mock_call.assert_called_once()

    def test_standup_from_cache(self):
        from codecks_cli.mcp_server._tools_read import standup

        _inject_cache()
        result = standup()
        assert result["cached"] is True
        assert "in_progress" in result

    def test_standup_with_filter_bypasses_cache(self):
        from codecks_cli.mcp_server._tools_read import standup

        _inject_cache()
        with patch("codecks_cli.mcp_server._tools_read._call") as mock_call:
            mock_call.return_value = SAMPLE_STANDUP
            standup(owner="Alice")
            mock_call.assert_called_once()

    def test_list_hand_from_cache(self):
        from codecks_cli.mcp_server._tools_write import list_hand

        _inject_cache()
        result = list_hand()
        assert isinstance(result, list)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Write-Through Invalidation Tests
# ---------------------------------------------------------------------------


class TestCacheInvalidation:
    def _setup_mock_call(self):
        """Inject cache and return a mock client."""
        _inject_cache()
        assert _core._is_cache_valid() is True
        mock_client = MagicMock()
        return mock_client

    def test_create_card_invalidates_cache(self):
        mock = self._setup_mock_call()
        mock.create_card.return_value = {"id": "new"}
        with patch.object(_core, "_get_client", return_value=mock):
            _core._call("create_card", title="test")
        # Selective invalidation: cards_result, pm_focus, standup removed
        assert _core._snapshot_cache is not None
        assert "cards_result" not in _core._snapshot_cache
        assert "pm_focus" not in _core._snapshot_cache
        assert "standup" not in _core._snapshot_cache
        # account and decks should survive
        assert "account" in _core._snapshot_cache

    def test_update_cards_invalidates_cache(self):
        mock = self._setup_mock_call()
        mock.update_cards.return_value = {"updated": 1}
        with patch.object(_core, "_get_client", return_value=mock):
            _core._call("update_cards", card_ids=[], updates={})
        # Selective invalidation: cards_result, pm_focus, standup removed
        assert _core._snapshot_cache is not None
        assert "cards_result" not in _core._snapshot_cache
        assert "account" in _core._snapshot_cache

    def test_mark_done_invalidates_cache(self):
        mock = self._setup_mock_call()
        mock.mark_done.return_value = {"ok": True}
        with patch.object(_core, "_get_client", return_value=mock):
            _core._call("mark_done", card_ids=["aaaabbbb-cccc-dddd-eeee-ffffffffffff"])
        # Write-through: cache updated in place, keys still present
        assert _core._snapshot_cache is not None
        assert "cards_result" in _core._snapshot_cache
        assert "account" in _core._snapshot_cache

    def test_add_to_hand_invalidates_cache(self):
        mock = self._setup_mock_call()
        mock.add_to_hand.return_value = {"ok": True}
        with patch.object(_core, "_get_client", return_value=mock):
            _core._call("add_to_hand", card_ids=["aaaabbbb-cccc-dddd-eeee-ffffffffffff"])
        # Write-through: cache updated in place, keys still present
        assert _core._snapshot_cache is not None
        assert "hand" in _core._snapshot_cache
        assert "pm_focus" in _core._snapshot_cache
        assert "cards_result" in _core._snapshot_cache

    def test_read_does_not_invalidate_cache(self):
        mock = self._setup_mock_call()
        mock.list_cards.return_value = {"cards": []}
        with patch.object(_core, "_get_client", return_value=mock):
            _core._call("list_cards")
        assert _core._snapshot_cache is not None

    def test_failed_mutation_does_not_invalidate(self):
        _inject_cache()
        mock = MagicMock()
        mock.create_card.side_effect = Exception("API down")
        with patch.object(_core, "_get_client", return_value=mock):
            result = _core._call("create_card", title="test")
        assert result["ok"] is False
        # Cache should still be valid because mutation failed
        assert _core._snapshot_cache is not None


# ---------------------------------------------------------------------------
# Filter Tests
# ---------------------------------------------------------------------------


class TestCachedCardFiltering:
    def test_filter_by_priority(self):
        from codecks_cli.mcp_server._tools_read import list_cards

        _inject_cache()
        result = list_cards(priority="a")
        assert result["total_count"] == 1
        assert "Card A" in result["cards"][0]["title"]

    def test_filter_by_hand_only(self):
        from codecks_cli.mcp_server._tools_read import list_cards

        _inject_cache()
        result = list_cards(hand_only=True)
        assert result["total_count"] == 1
        assert "Card A" in result["cards"][0]["title"]

    def test_filter_combined(self):
        from codecks_cli.mcp_server._tools_read import list_cards

        _inject_cache()
        result = list_cards(deck="Code", status="not_started")
        assert result["total_count"] == 1
        assert "Card C" in result["cards"][0]["title"]


# ---------------------------------------------------------------------------
# Stale Warning Tests
# ---------------------------------------------------------------------------


class TestStaleWarning:
    def test_metadata_includes_stale_warning_when_old(self):
        """Cache age > 80% TTL should include stale_warning."""
        from codecks_cli import config

        _core._snapshot_cache = {"fetched_at": "2026-03-07T00:00:00Z"}
        # Simulate cache loaded 250s ago (>80% of 300s TTL)
        _core._cache_loaded_at = time.monotonic() - 250
        meta = _core._get_cache_metadata()
        assert meta["cached"] is True
        assert meta["stale_warning"] is True
        assert meta["cache_ttl_seconds"] == config.CACHE_TTL_SECONDS

    def test_metadata_no_stale_warning_when_fresh(self):
        """Cache age < 80% TTL should NOT include stale_warning."""
        _core._snapshot_cache = {"fetched_at": "2026-03-07T00:00:00Z"}
        # Simulate cache loaded 10s ago (<80% of 60s TTL = 48s)
        _core._cache_loaded_at = time.monotonic() - 10
        meta = _core._get_cache_metadata()
        assert meta["cached"] is True
        assert "stale_warning" not in meta

    def test_metadata_no_cache(self):
        """No cache should return cached=False."""
        _core._snapshot_cache = None
        meta = _core._get_cache_metadata()
        assert meta["cached"] is False
        assert "stale_warning" not in meta


# ---------------------------------------------------------------------------
# Cache invalidation map completeness audit
# ---------------------------------------------------------------------------


class TestCacheInvalidationMapCompleteness:
    def test_all_mutation_methods_in_invalidation_map(self):
        """Every method in _MUTATION_METHODS must have an entry in _CACHE_INVALIDATION_MAP."""
        missing = _core._MUTATION_METHODS - set(_core._CACHE_INVALIDATION_MAP.keys())
        assert missing == set(), (
            f"Mutation methods missing from _CACHE_INVALIDATION_MAP: {missing}. "
            f"Add entries (even empty lists) for each new mutation method."
        )

    def test_invalidation_map_has_no_stale_entries(self):
        """Every key in _CACHE_INVALIDATION_MAP must be in _MUTATION_METHODS or _ALLOWED_METHODS."""
        known = _core._MUTATION_METHODS | _core._ALLOWED_METHODS
        stale = set(_core._CACHE_INVALIDATION_MAP.keys()) - known
        assert stale == set(), (
            f"_CACHE_INVALIDATION_MAP has entries for unknown methods: {stale}. "
            f"Remove stale entries or add methods to _ALLOWED_METHODS/_MUTATION_METHODS."
        )
