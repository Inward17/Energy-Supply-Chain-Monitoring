from argparse import Namespace
from pathlib import Path

import pytest

import cron_worker
from src.database import neo4j_graph, postgres_db


def test_process_singleton_excludes_a_second_file_handle():
    lock_path = Path(__file__).with_name(".test-cron-worker.lock")
    lock_path.unlink(missing_ok=True)
    first = cron_worker._ProcessSingleton(lock_path)
    second = cron_worker._ProcessSingleton(lock_path)

    try:
        assert first.acquire() is True
        assert second.acquire() is False
        assert second.owner_pid == str(first.owner_pid)

        first.release()
        assert second.acquire() is True
    finally:
        first.release()
        second.release()
        lock_path.unlink(missing_ok=True)


def test_cycle_guard_is_released_when_cycle_raises(monkeypatch):
    def fail_cycle():
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(cron_worker, "_run_cycle_unlocked", fail_cycle)

    with pytest.raises(RuntimeError, match="synthetic failure"):
        cron_worker.run_cycle()

    assert cron_worker._cycle_lock.acquire(blocking=False) is True
    cron_worker._cycle_lock.release()


def test_sdi_snapshot_hook_persists_the_canonical_calculation(monkeypatch):
    snapshot = {"sdi_score": 42.5}
    persisted = []

    monkeypatch.setattr(
        "src.agents.modeler_agent.compute_current_sdi",
        lambda: snapshot,
    )
    monkeypatch.setattr(postgres_db, "upsert_sdi_snapshot", persisted.append)

    cron_worker.step_sdi_snapshot()

    assert persisted == [snapshot]


def test_scheduled_startup_refreshes_ais_then_sdi(monkeypatch):
    calls = []
    cron_worker.schedule.clear()

    monkeypatch.setattr(postgres_db, "init_schema", lambda: calls.append("schema"))
    monkeypatch.setattr(neo4j_graph, "seed_graph", lambda: calls.append("graph"))
    monkeypatch.setattr(cron_worker, "run_cycle", lambda: calls.append("cycle"))
    monkeypatch.setattr(cron_worker, "step_ais", lambda: calls.append("ais"))
    monkeypatch.setattr(
        cron_worker,
        "step_sdi_snapshot",
        lambda: calls.append("sdi"),
    )
    monkeypatch.setattr(
        cron_worker,
        "step_portwatch",
        lambda: calls.append("portwatch"),
    )

    def stop_loop():
        raise KeyboardInterrupt

    monkeypatch.setattr(cron_worker.schedule, "run_pending", stop_loop)

    try:
        cron_worker._run_worker(Namespace(backfill=False, once=False))
    finally:
        cron_worker.schedule.clear()

    assert calls[:6] == [
        "schema",
        "graph",
        "cycle",
        "ais",
        "sdi",
        "portwatch",
    ]
