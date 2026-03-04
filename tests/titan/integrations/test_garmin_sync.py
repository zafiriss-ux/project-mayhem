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


def test_sync_all_payload_supports_dict_access_and_json_serialization():
    sync = GarminSync(email="e", password="p")
    sync.sync_activities = lambda days_back=7: [{"date": "2026-03-04"}]
    sync.sync_weight = lambda days_back=14: [{"date": "2026-03-04", "weight": 70.2}]
    sync.sync_sleep = lambda days_back=7: [{"date": "2026-03-04", "sleep_score": 80}]
    sync.sync_hrv = lambda days_back=7: [{"date": "2026-03-04", "rmssd": 41.5}]
    sync.last_hrv_sync_metrics = {"days_back": 7, "synced_days": 1, "skipped_days": 0}

    payload = sync.sync_all(days_back=7)

    assert set(payload) == {"activities", "weight", "sleep", "hrv", "hrv_sync_metrics"}
    assert payload["activities"][0]["date"] == "2026-03-04"
    assert payload["hrv_sync_metrics"]["synced_days"] == 1

    import json

    serialized = json.loads(json.dumps(payload))
    assert serialized["weight"][0]["weight"] == 70.2


def test_sync_all_payload_coerces_hrv_metrics_to_ints():
    sync = GarminSync(email="e", password="p")
    sync.sync_activities = lambda days_back=7: []
    sync.sync_weight = lambda days_back=14: []
    sync.sync_sleep = lambda days_back=7: []
    sync.sync_hrv = lambda days_back=7: []
    sync.last_hrv_sync_metrics = {"days_back": "7", "synced_days": 2.0, "skipped_days": False}

    payload = sync.sync_all(days_back=7)

    assert payload["hrv_sync_metrics"] == {"days_back": 7, "synced_days": 2, "skipped_days": 0}
