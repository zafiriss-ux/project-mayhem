import threading
import time

import pytest

from titan.integrations.garmin_sync import GarminSync


@pytest.mark.integration
def test_background_worker_lifecycle_start_stop_join_and_idempotent_start(monkeypatch):
    sync = GarminSync(email="dummy@example.com", password="dummy-password")
    iteration_event = threading.Event()
    iteration_count = {"value": 0}
    worker_exceptions: list[BaseException] = []

    original_bg_worker = GarminSync._bg_worker

    def _wrapped_bg_worker(self, interval_hours):
        try:
            original_bg_worker(self, interval_hours)
        except BaseException as exc:  # defensive capture for thread failures
            worker_exceptions.append(exc)
            raise

    def _fake_sync_all():
        iteration_count["value"] += 1
        iteration_event.set()
        return {
            "activities": [],
            "weight": [],
            "sleep": [],
            "hrv": [],
            "hrv_sync_metrics": {"days_back": 0, "synced_days": 0, "skipped_days": 0},
            "status": "ok",
        }

    monkeypatch.setattr(GarminSync, "_bg_worker", _wrapped_bg_worker)
    monkeypatch.setattr(sync, "sync_all", _fake_sync_all)

    sync.start_background_sync(interval_hours=1)
    first_thread = sync._sync_thread

    assert first_thread is not None
    assert first_thread.is_alive()
    assert iteration_event.wait(timeout=2)
    assert iteration_count["value"] >= 1

    sync.start_background_sync(interval_hours=1)
    assert sync._sync_thread is first_thread

    sync.stop_background_sync()
    first_thread.join(timeout=5)

    assert not first_thread.is_alive()
    assert worker_exceptions == []


@pytest.mark.integration
def test_start_background_sync_creates_thread_with_dummy_credentials(monkeypatch):
    sync = GarminSync(email="dummy@example.com", password="dummy-password")
    iteration_event = threading.Event()

    def _fake_sync_all():
        iteration_event.set()
        return {
            "activities": [],
            "weight": [],
            "sleep": [],
            "hrv": [],
            "hrv_sync_metrics": {"days_back": 0, "synced_days": 0, "skipped_days": 0},
            "status": "ok",
        }

    monkeypatch.setattr(sync, "sync_all", _fake_sync_all)

    sync.start_background_sync(interval_hours=1)

    assert sync._sync_thread is not None
    assert sync._sync_thread.name == "GarminSync"
    assert iteration_event.wait(timeout=2)

    sync.stop_background_sync()
    sync._sync_thread.join(timeout=5)
    assert not sync._sync_thread.is_alive()
