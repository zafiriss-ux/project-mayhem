from unittest.mock import MagicMock

from titan.integrations.garmin_sync import GarminSync


def test_bg_worker_exits_when_stop_event_is_set(monkeypatch):
    sync = GarminSync(email="e", password="p")
    sync_calls = {"count": 0}

    def _sync_all():
        sync_calls["count"] += 1

    monkeypatch.setattr(sync, "sync_all", _sync_all)

    wait_calls = {"count": 0}

    def _wait(timeout):
        wait_calls["count"] += 1
        sync._stop_event.set()
        return True

    monkeypatch.setattr(sync._stop_event, "wait", _wait)

    sync._bg_worker(interval_hours=1)

    assert sync_calls["count"] == 1
    assert wait_calls["count"] == 1


def test_stop_background_sync_sets_event_and_joins_thread():
    sync = GarminSync(email="e", password="p")
    sync._sync_thread = MagicMock()
    sync._sync_thread.is_alive.return_value = True

    sync.stop_background_sync()

    assert sync._stop_event.is_set()
    sync._sync_thread.join.assert_called_once_with(timeout=5)
