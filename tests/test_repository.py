"""Tests for CardRepository — indexed card data access layer."""

from __future__ import annotations

from codecks_cli.mcp_server._repository import CardRepository

SAMPLE_CARDS = [
    {
        "id": "aaaabbbb-cccc-dddd-eeee-ffffffffffff",
        "title": "Card A",
        "status": "started",
        "priority": "a",
        "deck": "Code",
        "owner": "Alice",
        "content": "body A about steeping",
        "effort": 3,
    },
    {
        "id": "aaaabbbb-cccc-dddd-eeee-gggggggggggg",
        "title": "Card B",
        "status": "blocked",
        "priority": "b",
        "deck": "Art",
        "owner": "Bob",
        "content": "body B about textures",
        "effort": 5,
    },
    {
        "id": "aaaabbbb-cccc-dddd-eeee-hhhhhhhhhhhh",
        "title": "Card C",
        "status": "not_started",
        "priority": "c",
        "deck": "Code",
        "owner": None,
        "content": "body C about brewing",
        "effort": 1,
    },
    {
        "id": "aaaabbbb-cccc-dddd-eeee-iiiiiiiiiiii",
        "title": "Card D",
        "status": "started",
        "priority": "a",
        "deck": "Design",
        "owner": "Alice",
        "content": "",
        "effort": 2,
    },
]


class TestLoad:
    def test_load_builds_indexes(self):
        repo = CardRepository()
        repo.load(SAMPLE_CARDS)

        assert repo.count == 4
        assert len(repo.all_cards) == 4

    def test_get_by_id(self):
        repo = CardRepository()
        repo.load(SAMPLE_CARDS)

        card = repo.get("aaaabbbb-cccc-dddd-eeee-ffffffffffff")
        assert card is not None
        assert card["title"] == "Card A"

    def test_get_nonexistent_returns_none(self):
        repo = CardRepository()
        repo.load(SAMPLE_CARDS)

        assert repo.get("nonexistent-uuid") is None

    def test_by_status(self):
        repo = CardRepository()
        repo.load(SAMPLE_CARDS)

        started = repo.by_status("started")
        assert len(started) == 2
        titles = {c["title"] for c in started}
        assert titles == {"Card A", "Card D"}

        blocked = repo.by_status("blocked")
        assert len(blocked) == 1
        assert blocked[0]["title"] == "Card B"

    def test_by_status_empty(self):
        repo = CardRepository()
        repo.load(SAMPLE_CARDS)

        assert repo.by_status("done") == []

    def test_by_deck(self):
        repo = CardRepository()
        repo.load(SAMPLE_CARDS)

        code_cards = repo.by_deck("Code")
        assert len(code_cards) == 2
        titles = {c["title"] for c in code_cards}
        assert titles == {"Card A", "Card C"}

    def test_case_insensitive_deck_lookup(self):
        repo = CardRepository()
        repo.load(SAMPLE_CARDS)

        assert len(repo.by_deck("code")) == 2
        assert len(repo.by_deck("CODE")) == 2
        assert len(repo.by_deck("Code")) == 2

    def test_by_owner(self):
        repo = CardRepository()
        repo.load(SAMPLE_CARDS)

        alice_cards = repo.by_owner("Alice")
        assert len(alice_cards) == 2

        bob_cards = repo.by_owner("bob")  # case-insensitive
        assert len(bob_cards) == 1

    def test_none_owner_indexed_as_unassigned(self):
        repo = CardRepository()
        repo.load(SAMPLE_CARDS)

        unassigned = repo.by_owner("unassigned")
        assert len(unassigned) == 1
        assert unassigned[0]["title"] == "Card C"


class TestClear:
    def test_clear_empties_all(self):
        repo = CardRepository()
        repo.load(SAMPLE_CARDS)
        assert repo.count == 4

        repo.clear()
        assert repo.count == 0
        assert repo.all_cards == []
        assert repo.get("aaaabbbb-cccc-dddd-eeee-ffffffffffff") is None
        assert repo.by_status("started") == []
        assert repo.by_deck("Code") == []
        assert repo.by_owner("Alice") == []

    def test_reload_replaces_data(self):
        repo = CardRepository()
        repo.load(SAMPLE_CARDS)
        assert repo.count == 4

        new_cards = [
            {"id": "new-id-000", "title": "New", "status": "done", "deck": "X", "owner": "Z"}
        ]
        repo.load(new_cards)
        assert repo.count == 1
        assert repo.get("aaaabbbb-cccc-dddd-eeee-ffffffffffff") is None
        assert repo.get("new-id-000") is not None
        assert repo.by_status("started") == []
        assert repo.by_status("done")[0]["title"] == "New"


class TestSearch:
    def test_search_matches_title(self):
        repo = CardRepository()
        repo.load(SAMPLE_CARDS)

        results = repo.search("Card A")
        assert len(results) == 1
        assert results[0]["title"] == "Card A"

    def test_search_matches_content(self):
        repo = CardRepository()
        repo.load(SAMPLE_CARDS)

        results = repo.search("steeping")
        assert len(results) == 1
        assert results[0]["title"] == "Card A"

    def test_search_case_insensitive(self):
        repo = CardRepository()
        repo.load(SAMPLE_CARDS)

        results = repo.search("BREWING")
        assert len(results) == 1
        assert results[0]["title"] == "Card C"

    def test_search_no_match(self):
        repo = CardRepository()
        repo.load(SAMPLE_CARDS)

        assert repo.search("nonexistent term") == []

    def test_search_partial_match(self):
        repo = CardRepository()
        repo.load(SAMPLE_CARDS)

        # "body" appears in content of cards A, B, C
        results = repo.search("body")
        assert len(results) == 3


class TestDeckMappings:
    def test_load_decks_builds_mappings(self):
        repo = CardRepository()
        decks = [
            {"id": "d1", "title": "Code"},
            {"id": "d2", "title": "Art"},
        ]
        repo.load_decks(decks)
        assert repo.deck_id_for("Code") == "d1"
        assert repo.deck_id_for("code") == "d1"  # case-insensitive
        assert repo.deck_name_for("d1") == "Code"
        assert repo.deck_id_for("Nonexistent") is None

    def test_load_decks_with_name_key(self):
        repo = CardRepository()
        decks = [{"id": "d1", "name": "Features"}]
        repo.load_decks(decks)
        assert repo.deck_id_for("features") == "d1"

    def test_clear_clears_deck_mappings(self):
        repo = CardRepository()
        repo.load_decks([{"id": "d1", "title": "Code"}])
        repo.clear()
        assert repo.deck_id_for("code") is None


class TestEdgeCases:
    def test_load_empty_list(self):
        repo = CardRepository()
        repo.load([])
        assert repo.count == 0

    def test_load_skips_non_dict_items(self):
        repo = CardRepository()
        repo.load([{"id": "a", "status": "done", "deck": "X"}, "not a dict", 42])
        assert repo.count == 1

    def test_load_handles_missing_fields(self):
        repo = CardRepository()
        repo.load([{"id": "a"}])
        assert repo.get("a") is not None
        assert repo.by_status("") == [{"id": "a"}]

    def test_deck_name_key_fallback(self):
        """Cards may have 'deck_name' instead of 'deck'."""
        repo = CardRepository()
        repo.load([{"id": "a", "deck_name": "Features", "status": "started"}])
        assert len(repo.by_deck("features")) == 1

    def test_owner_name_key_fallback(self):
        """Cards may have 'owner_name' instead of 'owner'."""
        repo = CardRepository()
        repo.load([{"id": "a", "owner_name": "Thomas", "status": "started", "deck": "X"}])
        assert len(repo.by_owner("thomas")) == 1
