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


def test_rate_limiter_never_over_admits_under_concurrency(monkeypatch):
    """50 threads racing the limiter must never put more than the cap in a window.

    The window check and the slot reservation share one critical section, so
    threads that all see room cannot all be admitted. A fake clock (advanced
    only by the limiter's own sleep) keeps this deterministic and fast.
    """
    max_calls = 5
    window = 1.0
    monkeypatch.setattr(_core, "_api_call_timestamps", [])
    monkeypatch.setattr(_core, "_RATE_LIMIT_MAX", max_calls)
    monkeypatch.setattr(_core, "_RATE_LIMIT_WINDOW", window)

    clock = {"now": 0.0}
    clock_lock = threading.Lock()

    def fake_monotonic():
        with clock_lock:
            return clock["now"]

    def fake_sleep(seconds):
        with clock_lock:
            clock["now"] += max(seconds, 0.001)

    monkeypatch.setattr(_core.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(_core.time, "sleep", fake_sleep)

    observed: list[int] = []

    class FakeClient:
        def get_account(self):
            # Sample the reservation list; pruning only happens at admission, so
            # its length is the number of admissions in the current window.
            with _core._state_lock:
                observed.append(len(_core._api_call_timestamps))
            return {"ok": True}

    monkeypatch.setattr(_core, "_client", FakeClient())

    errors = _run_threads(lambda _i: _core._call("get_account"), 50)

    assert errors == []
    assert len(observed) == 50
    assert max(observed) <= max_calls, f"over-admitted: {max(observed)} > {max_calls}"
    assert len(_core._api_call_timestamps) <= max_calls


def test_overlapping_batches_suppress_disk_writes_until_the_last_exit(tmp_path, monkeypatch):
    """The batch flag is a depth counter, so nested batches don't clear each other."""
    cache_file = tmp_path / "cache.json"
    monkeypatch.setattr(_core, "CACHE_PATH", str(cache_file))
    monkeypatch.setattr(_core, "_batch_depth", 0)
    monkeypatch.setattr(_core, "_snapshot_cache", {"cards": []})

    _core._set_batch_in_progress(True)  # outer batch
    _core._set_batch_in_progress(True)  # overlapping inner batch
    _core._persist_cache_to_disk()
    assert not cache_file.exists()

    _core._set_batch_in_progress(False)  # inner exits, outer still running
    assert _core._batch_depth == 1
    _core._persist_cache_to_disk()
    assert not cache_file.exists()

    _core._set_batch_in_progress(False)  # last exit re-enables disk writes
    assert _core._batch_depth == 0
    _core._persist_cache_to_disk()
    assert cache_file.exists()

    _core._set_batch_in_progress(False)  # unbalanced exit must not go negative
    assert _core._batch_depth == 0
