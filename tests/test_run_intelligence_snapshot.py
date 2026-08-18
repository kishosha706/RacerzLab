from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock

from racelab_engine.services import run_intelligence_service as service


def test_shared_intelligence_snapshot_is_single_flight_and_semantic(monkeypatch) -> None:
    service.clear_run_intelligence_snapshot_cache()
    release = Event()
    started = Event()
    counter_lock = Lock()
    calls = 0
    immutable_bundle = object()

    monkeypatch.setattr(service, "_snapshot_key", lambda *_args: "semantic-revision")

    def build(*_args, **_kwargs):
        nonlocal calls
        with counter_lock:
            calls += 1
        started.set()
        assert release.wait(timeout=2)
        return immutable_bundle

    monkeypatch.setattr(service, "_build_run_intelligence_uncached", build)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(service.build_run_intelligence, "run-a")
        assert started.wait(timeout=2)
        second = pool.submit(service.build_run_intelligence, "run-a")
        release.set()
        assert first.result(timeout=2) is immutable_bundle
        assert second.result(timeout=2) is immutable_bundle
    assert calls == 1
    assert service.build_run_intelligence("run-a") is immutable_bundle
    assert service.run_intelligence_snapshot_stats() == {
        "build_count": 1,
        "cache_entries": 1,
        "inflight": 0,
    }
    service.clear_run_intelligence_snapshot_cache()


def test_persisted_exact_snapshot_skips_cold_builder(monkeypatch) -> None:
    service.clear_run_intelligence_snapshot_cache()
    persisted_bundle = object()
    monkeypatch.setattr(service, "_snapshot_key", lambda *_args: "semantic-revision")
    monkeypatch.setattr(
        service,
        "_load_persisted_snapshot",
        lambda _database, key: persisted_bundle if key == "semantic-revision" else None,
    )

    def unexpected_build(*_args, **_kwargs):
        raise AssertionError("persistent exact-identity reuse must not cold-build")

    monkeypatch.setattr(service, "_build_run_intelligence_uncached", unexpected_build)
    assert service.build_run_intelligence("run-a") is persisted_bundle
    assert service.run_intelligence_snapshot_stats() == {
        "build_count": 0,
        "cache_entries": 1,
        "inflight": 0,
    }
    service.clear_run_intelligence_snapshot_cache()
