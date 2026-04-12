"""Tests for SQLite storage layer (CardStore).

All tests use :memory: SQLite — no disk I/O.
"""

import threading

import pytest

from codecks_cli.store import CardStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_C1 = "00000000-0000-0000-0000-000000000001"
_C2 = "00000000-0000-0000-0000-000000000002"
_C3 = "00000000-0000-0000-0000-000000000003"


def _make_card(
    card_id: str = _C1,
    title: str = "Test card",
    status: str = "started",
    priority: str = "a",
    effort: int | None = 3,
    deck: str = "Gameplay",
    owner: str = "Alice",
    content: str = "Some content",
    tags: list[str] | None = None,
    is_doc: bool = False,
) -> dict:
    return {
        "id": card_id,
        "title": title,
        "status": status,
        "priority": priority,
        "effort": effort,
        "deck": deck,
        "owner": owner,
        "content": content,
        "tags": tags or [],
        "is_doc": is_doc,
    }


@pytest.fixture
def store():
    """Create an in-memory CardStore for each test."""
    s = CardStore(":memory:")
    yield s
    s.close()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class TestSchema:
    def test_init_creates_tables(self, store: CardStore):
        """Verify all expected tables exist after init."""
        with store._lock:
            rows = store._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        names = {r["name"] for r in rows}
        assert "cards" in names
        assert "decks" in names
        assert "meta" in names
        assert "claims" in names
        assert "query_cache" in names


# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------


class TestCards:
    def test_upsert_and_get_card(self, store: CardStore):
        """Round-trip: upsert a single card and retrieve it."""
        card = _make_card()
        store.upsert_cards([card])
        result = store.get_card(_C1)
        assert result is not None
        assert result["id"] == _C1
        assert result["title"] == "Test card"
        assert result["status"] == "started"
        assert result["priority"] == "a"
        assert result["effort"] == 3
        assert result["deck_name"] == "Gameplay"
        assert result["owner_name"] == "Alice"

    def test_upsert_cards_bulk(self, store: CardStore):
        """Bulk insert 100 cards and verify count."""
        cards = [_make_card(card_id=f"00000000-0000-0000-0000-{i:012d}") for i in range(100)]
        store.upsert_cards(cards)
        assert store.card_count() == 100

    def test_get_card_not_found(self, store: CardStore):
        """get_card returns None for missing IDs."""
        assert store.get_card("nonexistent") is None

    def test_upsert_replaces_existing(self, store: CardStore):
        """Upserting the same ID replaces the old record."""
        store.upsert_cards([_make_card(title="v1")])
        store.upsert_cards([_make_card(title="v2")])
        result = store.get_card(_C1)
        assert result is not None
        assert result["title"] == "v2"
        assert store.card_count() == 1


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


class TestQuery:
    def test_query_cards_by_status(self, store: CardStore):
        """Filter cards by status."""
        store.upsert_cards(
            [
                _make_card(card_id=_C1, status="started"),
                _make_card(card_id=_C2, status="done"),
                _make_card(card_id=_C3, status="started"),
            ]
        )
        results = store.query_cards(status="started")
        assert len(results) == 2
        assert all(r["status"] == "started" for r in results)

    def test_query_cards_by_deck(self, store: CardStore):
        """Filter cards by deck (case insensitive)."""
        store.upsert_cards(
            [
                _make_card(card_id=_C1, deck="Gameplay"),
                _make_card(card_id=_C2, deck="Audio"),
                _make_card(card_id=_C3, deck="gameplay"),  # different case
            ]
        )
        results = store.query_cards(deck="gameplay")
        assert len(results) == 2

    def test_query_cards_by_owner(self, store: CardStore):
        """Filter cards by owner (case insensitive)."""
        store.upsert_cards(
            [
                _make_card(card_id=_C1, owner="Alice"),
                _make_card(card_id=_C2, owner="Bob"),
                _make_card(card_id=_C3, owner="alice"),
            ]
        )
        results = store.query_cards(owner="alice")
        assert len(results) == 2

    def test_query_cards_pagination(self, store: CardStore):
        """Limit and offset work correctly."""
        cards = [_make_card(card_id=f"00000000-0000-0000-0000-{i:012d}") for i in range(10)]
        store.upsert_cards(cards)
        page1 = store.query_cards(limit=3, offset=0)
        page2 = store.query_cards(limit=3, offset=3)
        assert len(page1) == 3
        assert len(page2) == 3
        assert page1[0]["id"] != page2[0]["id"]

    def test_query_cards_search(self, store: CardStore):
        """Search via LIKE in query_cards."""
        store.upsert_cards(
            [
                _make_card(card_id=_C1, title="Inventory system"),
                _make_card(card_id=_C2, title="Audio mixer"),
            ]
        )
        results = store.query_cards(search="inventory")
        assert len(results) == 1
        assert results[0]["title"] == "Inventory system"


# ---------------------------------------------------------------------------
# FTS
# ---------------------------------------------------------------------------


class TestFTS:
    def test_search_cards_fts(self, store: CardStore):
        """FTS5 search finds matching cards by title or content."""
        store.upsert_cards(
            [
                _make_card(card_id=_C1, title="Inventory system", content="Tracks items"),
                _make_card(card_id=_C2, title="Audio mixer", content="Handles sound"),
                _make_card(card_id=_C3, title="Shop UI", content="Inventory display panel"),
            ]
        )
        results = store.search_cards("inventory")
        ids = {r["id"] for r in results}
        # Should find C1 (title) and C3 (content)
        assert _C1 in ids
        assert _C3 in ids
        assert _C2 not in ids


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------


class TestMeta:
    def test_meta_set_get(self, store: CardStore):
        """Round-trip meta key-value."""
        store.set_meta("fetched_at", "2026-01-01T00:00:00Z")
        assert store.get_meta("fetched_at") == "2026-01-01T00:00:00Z"

    def test_meta_get_missing(self, store: CardStore):
        """get_meta returns None for missing keys."""
        assert store.get_meta("nonexistent") is None

    def test_meta_overwrite(self, store: CardStore):
        """set_meta overwrites existing values."""
        store.set_meta("key", "v1")
        store.set_meta("key", "v2")
        assert store.get_meta("key") == "v2"


# ---------------------------------------------------------------------------
# Claims
# ---------------------------------------------------------------------------


class TestClaims:
    def test_claims_crud(self, store: CardStore):
        """Full CRUD cycle for claims."""
        # Upsert
        store.upsert_claim(_C1, "agent-1", reason="working on it")
        claim = store.get_claim(_C1)
        assert claim is not None
        assert claim["agent_name"] == "agent-1"
        assert claim["reason"] == "working on it"

        # All claims
        store.upsert_claim(_C2, "agent-2")
        all_claims = store.all_claims()
        assert len(all_claims) == 2
        assert _C1 in all_claims
        assert _C2 in all_claims

        # Remove
        assert store.remove_claim(_C1) is True
        assert store.get_claim(_C1) is None
        assert store.remove_claim(_C1) is False  # already removed

    def test_claim_get_missing(self, store: CardStore):
        """get_claim returns None for unclaimed cards."""
        assert store.get_claim("no-such-card") is None


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


class TestCleanup:
    def test_clear_cards(self, store: CardStore):
        """clear_cards removes only cards, not meta or claims."""
        store.upsert_cards([_make_card()])
        store.set_meta("key", "val")
        store.upsert_claim(_C1, "agent-1")
        store.clear_cards()
        assert store.card_count() == 0
        assert store.get_meta("key") == "val"
        assert store.get_claim(_C1) is not None

    def test_clear_all(self, store: CardStore):
        """clear_all removes everything."""
        store.upsert_cards([_make_card()])
        store.set_meta("key", "val")
        store.upsert_claim(_C1, "agent-1")
        store.clear_all()
        assert store.card_count() == 0
        assert store.get_meta("key") is None
        assert store.get_claim(_C1) is None


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_thread_safety(self, store: CardStore):
        """Concurrent upserts from multiple threads don't crash."""
        errors: list[Exception] = []

        def worker(thread_id: int) -> None:
            try:
                cards = [
                    _make_card(card_id=f"00000000-0000-0000-{thread_id:04d}-{i:012d}")
                    for i in range(20)
                ]
                store.upsert_cards(cards)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread errors: {errors}"
        assert store.card_count() == 100  # 5 threads x 20 cards


# ---------------------------------------------------------------------------
# Tags JSON roundtrip
# ---------------------------------------------------------------------------


class TestTagsRoundtrip:
    def test_card_tags_json_roundtrip(self, store: CardStore):
        """Tags are stored as JSON and returned as a list."""
        tags = ["bug", "high-priority", "gameplay"]
        store.upsert_cards([_make_card(tags=tags)])
        result = store.get_card(_C1)
        assert result is not None
        assert isinstance(result["tags"], list)
        assert result["tags"] == tags

    def test_card_tags_empty(self, store: CardStore):
        """Cards with no tags return an empty list."""
        store.upsert_cards([_make_card(tags=[])])
        result = store.get_card(_C1)
        assert result is not None
        assert result["tags"] == []

    def test_card_tags_none(self, store: CardStore):
        """Cards with None tags return an empty list."""
        card = _make_card()
        card["tags"] = None
        store.upsert_cards([card])
        result = store.get_card(_C1)
        assert result is not None
        assert result["tags"] == []


# ---------------------------------------------------------------------------
# Decks
# ---------------------------------------------------------------------------


class TestDecks:
    def test_upsert_decks(self, store: CardStore):
        """Round-trip deck upsert."""
        decks = [
            {"id": "d1", "title": "Gameplay", "projectId": "p1", "project_name": "Main"},
            {"id": "d2", "title": "Audio", "projectId": "p1", "project_name": "Main"},
        ]
        store.upsert_decks(decks)
        with store._lock:
            rows = store._conn.execute("SELECT * FROM decks ORDER BY id").fetchall()
        assert len(rows) == 2
        assert rows[0]["title"] == "Gameplay"

    def test_all_cards_empty(self, store: CardStore):
        """all_cards returns empty list on empty store."""
        assert store.all_cards() == []
