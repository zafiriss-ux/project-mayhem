import json
import logging
import threading
import time
from unittest.mock import MagicMock

from titan.integrations import garmin_sync
from titan.integrations.garmin_sync import GarminSync


def test_bg_worker_exits_when_stop_event_is_set(monkeypatch):
    sync = GarminSync(email="e", password="p")
    sync_calls = {"count": 0}

    def _sync_all():
        sync_calls["count"] += 1

    monkeypatch.setattr(sync, "sync_all", _sync_all)

    wait_calls = {"count": 0}

    observed = {"timeout": None}

    def _wait(timeout):
        observed["timeout"] = timeout
        wait_calls["count"] += 1
        sync._stop_event.set()
        return True

    monkeypatch.setattr(sync._stop_event, "wait", _wait)

    sync._bg_worker(interval_hours=1)

    assert sync_calls["count"] == 1
    assert wait_calls["count"] == 1
    assert observed["timeout"] == 3600.0


def test_bg_worker_returns_immediately_when_stop_event_already_set(monkeypatch):
    sync = GarminSync(email="e", password="p")
    sync._stop_event.set()

    sync_all_calls = {"count": 0}

    def _sync_all():
        sync_all_calls["count"] += 1

    monkeypatch.setattr(sync, "sync_all", _sync_all)

    sync._bg_worker(interval_hours=2)

    assert sync_all_calls["count"] == 0


def test_stop_background_sync_sets_event_and_joins_thread():
    sync = GarminSync(email="e", password="p")
    sync._sync_thread = MagicMock()
    sync._sync_thread.is_alive.side_effect = [True, False]

    sync.stop_background_sync()

    assert sync._stop_event.is_set()
    sync._sync_thread.join.assert_called_once_with(timeout=5)


def test_stop_background_sync_hung_thread_emits_error_timeout_event(caplog):
    sync = GarminSync(email="e", password="p")
    never_set = threading.Event()

    hung_thread = threading.Thread(target=never_set.wait, name="HungGarminWorker", daemon=True)
    hung_thread.start()
    assert hung_thread.is_alive()

    observed = {"timeout": None}
    original_join = hung_thread.join

    def _join(timeout=None):
        observed["timeout"] = timeout
        return original_join(timeout=0)

    hung_thread.join = _join
    sync._sync_thread = hung_thread

    with caplog.at_level(logging.ERROR):
        sync.stop_background_sync()

    assert observed["timeout"] == 5
    event = json.loads(caplog.records[-1].message)
    assert event["action"] == "worker_shutdown_timeout"
    assert event["worker_name"] == "HungGarminWorker"
    assert event["timeout_seconds"] == 5
    assert event["still_alive"] is True
    assert caplog.records[-1].levelno == logging.ERROR


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


def test_last_hrv_sync_metrics_initializes_with_expected_contract_fields():
    sync = GarminSync(email="e", password="p")

    assert sync.last_hrv_sync_metrics == {"days_back": 0, "synced_days": 0, "skipped_days": 0}


def test_sync_hrv_disconnected_returns_empty_and_contract_metrics():
    sync = GarminSync(email="e", password="p")
    sync._ensure_connected = lambda: False

    payload = sync.sync_hrv(days_back=5)

    assert payload == []
    assert sync.last_hrv_sync_metrics == {"days_back": 5, "synced_days": 0, "skipped_days": 0}


def test_sync_all_timeout_returns_timeout_cancelled_status(monkeypatch):
    sync = GarminSync(email="e", password="p")

    def _slow_sync_operation(_days_back):
        time.sleep(0.2)
        return {
            "activities": [{"date": "never"}],
            "weight": [],
            "sleep": [],
            "hrv": [],
            "hrv_sync_metrics": {"days_back": 0, "synced_days": 0, "skipped_days": 0},
        }

    monkeypatch.setattr(sync, "_sync_operation", _slow_sync_operation)
    monkeypatch.setenv("GARMIN_SYNC_TIMEOUT_S", "0")

    payload = sync.sync_all(days_back=7)

    assert payload["status"] == "timeout_cancelled"
    assert payload["activities"] == []


def test_sync_all_timeout_emits_cancel_event_and_attempts_future_cancel(monkeypatch):
    sync = GarminSync(email="e", password="p")
    events = []
    monkeypatch.setattr(garmin_sync, "_garmin_event", lambda action, **fields: events.append((action, fields)))
    monkeypatch.setenv("GARMIN_SYNC_TIMEOUT_S", "1")

    observed = {"cancel_called": False}

    class _TimeoutFuture:
        def result(self, timeout):
            raise garmin_sync.FuturesTimeoutError()

        def cancel(self):
            observed["cancel_called"] = True
            return True

    class _FakeExecutor:
        def __init__(self, max_workers):
            self.max_workers = max_workers

        def submit(self, fn, *args):
            return _TimeoutFuture()

        def shutdown(self, wait, cancel_futures):
            return None

    monkeypatch.setattr(garmin_sync, "ThreadPoolExecutor", _FakeExecutor)

    payload = sync.sync_all(days_back=3)

    assert observed["cancel_called"] is True
    assert payload["status"] == "timeout_cancelled"
    cancel_event = [event for event in events if event[0] == "garmin_sync_cancelled"]
    assert cancel_event
    _, fields = cancel_event[0]
    assert fields["reason"] == "timeout"
    assert fields["timeout_seconds"] == 1
    assert fields["operation_name"] == "sync_all"
