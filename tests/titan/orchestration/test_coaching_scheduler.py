import threading

import pytest

from titan.orchestration.coaching_scheduler import CoachingScheduler


@pytest.mark.unit
def test_register_athlete_happy_path_stores_callback_and_lock():
    scheduler = CoachingScheduler(interval_seconds=0.01)

    scheduler.register_athlete("athlete-1", lambda: None)

    assert "athlete-1" in scheduler._athlete_callbacks
    assert "athlete-1" in scheduler._athlete_locks


@pytest.mark.unit
def test_register_athlete_duplicate_raises_value_error():
    scheduler = CoachingScheduler(interval_seconds=0.01)
    scheduler.register_athlete("athlete-1", lambda: None)

    try:
        scheduler.register_athlete("athlete-1", lambda: None)
        raised = False
    except ValueError as exc:
        raised = True
        assert "already registered" in str(exc)

    assert raised is True


@pytest.mark.unit
def test_start_and_stop_lifecycle_runs_callbacks():
    scheduler = CoachingScheduler(interval_seconds=0.01)
    called = threading.Event()

    def _callback():
        called.set()

    scheduler.register_athlete("athlete-1", _callback)
    scheduler.start()
    assert called.wait(timeout=0.2) is True
    scheduler.stop()


@pytest.mark.unit
def test_stop_without_start_is_noop():
    scheduler = CoachingScheduler(interval_seconds=0.01)

    scheduler.stop()

    assert scheduler._thread is None


@pytest.mark.unit
def test_per_athlete_overlap_lock_skips_overlapping_cycle():
    scheduler = CoachingScheduler(interval_seconds=0.01)
    calls = {"count": 0}

    def _callback():
        calls["count"] += 1

    scheduler.register_athlete("athlete-1", _callback)
    lock = scheduler._athlete_locks["athlete-1"]
    assert lock.acquire(blocking=False) is True
    try:
        scheduler._run_athlete_cycle("athlete-1", scheduler._athlete_callbacks["athlete-1"])
    finally:
        lock.release()

    assert calls["count"] == 0


@pytest.mark.unit
def test_start_when_already_running_does_not_spawn_new_thread():
    scheduler = CoachingScheduler(interval_seconds=0.05)
    scheduler.register_athlete("athlete-1", lambda: None)

    scheduler.start()
    first_thread = scheduler._thread
    scheduler.start()
    second_thread = scheduler._thread
    scheduler.stop()

    assert first_thread is second_thread
