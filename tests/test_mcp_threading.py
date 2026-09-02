"""Thread-safety tests for MCP server shared state.

MCP SDK v2 dispatches synchronous tool functions on a worker-thread pool
(``anyio.to_thread.run_sync``), so the module-level caches in ``_core`` and the
``CardRepository`` indexes really are touched concurrently.
"""

import threading
import time

from codecks_cli.mcp_server import _core
from codecks_cli.mcp_server._repository import CardRepository


def _run_threads(target, count):
    """Run *target* in *count* threads released simultaneously; re-raise errors."""
    barrier = threading.Barrier(count)
    errors: list[BaseException] = []
    lock = threading.Lock()

    def runner(index):
        try:
            barrier.wait(timeout=10)
            target(index)
        except BaseException as e:  # noqa: BLE001 - surfaced by the assertion below
            with lock:
                errors.append(e)

    threads = [threading.Thread(target=runner, args=(i,)) for i in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not any(t.is_alive() for t in threads), "thread did not finish"
    return errors


def test_get_store_returns_one_instance_under_concurrency(monkeypatch):
    """Two threads racing the lazy init must share a single CardStore."""
    constructed = []
    construct_lock = threading.Lock()

    class SlowStore:
        def __init__(self):
            with construct_lock:
                constructed.append(self)
            # Widen the race window that an unlocked lazy init would lose.
            time.sleep(0.05)

        def close(self):
            pass

    monkeypatch.setattr(_core, "CardStore", SlowStore)
    monkeypatch.setattr(_core, "_store", None)

    seen: list[object] = []
    seen_lock = threading.Lock()

    def get_store(_index):
        store = _core._get_store()
        with seen_lock:
            seen.append(store)

    errors = _run_threads(get_store, 2)

    assert errors == []
    assert len(constructed) == 1
    assert len(seen) == 2
    assert seen[0] is seen[1]


def test_repository_load_and_read_concurrently(monkeypatch):
    """Index rebuilds must not make concurrent reads raise."""
    repo = CardRepository()
    cards = [
        {
            "id": f"{i:08d}-0000-0000-0000-000000000000",
            "title": f"Card {i}",
            "status": "started" if i % 2 else "done",
            "deck": "engineering",
            "owner": "alice",
        }
        for i in range(200)
    ]
    repo.load(cards)

    stop = threading.Event()

    def writer(_index):
        for _ in range(60):
            repo.load(cards)
            repo.load_decks([{"id": "d1", "title": "Engineering"}])
            repo.add(
                {
                    "id": "aaaaaaaa-0000-0000-0000-000000000000",
                    "title": "extra",
                    "status": "blocked",
                }
            )
            repo.update("aaaaaaaa-0000-0000-0000-000000000000", {"status": "done"})
            repo.remove("aaaaaaaa-0000-0000-0000-000000000000")
        stop.set()

    def reader(_index):
        while not stop.is_set():
            assert isinstance(repo.all_cards, list)
            for card in repo.all_cards:
                assert "id" in card
            repo.by_status("started")
            repo.by_deck("engineering")
            repo.by_owner("alice")
            repo.get(cards[0]["id"])
            repo.search("Card 1")
            repo.deck_id_for("engineering")
            assert repo.count >= 0

    errors = _run_threads(lambda i: writer(i) if i == 0 else reader(i), 4)

    assert errors == []
    assert repo.count == len(cards)


def test_rate_limit_timestamps_survive_concurrent_calls(monkeypatch):
    """The shared rate-limit list must not be corrupted by parallel _call()s."""
    monkeypatch.setattr(_core, "_api_call_timestamps", [])

    class FakeClient:
        def get_account(self):
            return {"ok": True}

    monkeypatch.setattr(_core, "_client", FakeClient())

    results: list[dict] = []
    results_lock = threading.Lock()

    # Stay under _RATE_LIMIT_MAX so the limiter never sleeps mid-test.
    per_thread = 5
    threads = 4

    def call(_index):
        for _ in range(per_thread):
            out = _core._call("get_account")
            with results_lock:
                results.append(out)

    errors = _run_threads(call, threads)

    assert errors == []
    assert len(results) == per_thread * threads
    assert all(r.get("ok") for r in results)
    # Every call recorded exactly one timestamp — no lost or duplicated writes.
    assert len(_core._api_call_timestamps) == per_thread * threads
    assert all(isinstance(t, float) for t in _core._api_call_timestamps)
