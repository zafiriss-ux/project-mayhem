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

    assert set(payload) == {"activities", "weight", "sleep", "hrv", "hrv_sync_metrics", "data_trust"}
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


def test_sync_all_payload_includes_data_trust_contract():
    sync = GarminSync(email="e", password="p")
    sync.sync_activities = lambda days_back=7: []
    sync.sync_weight = lambda days_back=14: []
    sync.sync_sleep = lambda days_back=7: []
    sync.sync_hrv = lambda days_back=7: []
    sync.last_hrv_sync_metrics = {"days_back": 7, "synced_days": 0, "skipped_days": 0}

    payload = sync.sync_all(days_back=7)

    assert payload["data_trust"]["source"] == "garmin"
    assert payload["data_trust"]["trust_level"] == "TRUSTED"


def test_sync_all_timeout_payload_marks_data_trust_invalid(monkeypatch):
    sync = GarminSync(email="e", password="p")

    class _TimeoutFuture:
        def result(self, timeout):
            raise garmin_sync.FuturesTimeoutError()

        def cancel(self):
            return True

    class _FakeExecutor:
        def __init__(self, max_workers):
            self.max_workers = max_workers

        def submit(self, fn, *args):
            return _TimeoutFuture()

        def shutdown(self, wait, cancel_futures):
            return None

    monkeypatch.setenv("GARMIN_SYNC_TIMEOUT_S", "1")
    monkeypatch.setattr(garmin_sync, "ThreadPoolExecutor", _FakeExecutor)

    payload = sync.sync_all(days_back=3)

    assert payload["data_trust"]["trust_level"] == "INVALID"
    assert "sync_timeout_cancelled" in payload["data_trust"]["reasons"]


def test_sync_all_invalid_timeout_env_falls_back_to_default(monkeypatch):
    sync = GarminSync(email="e", password="p")
    observed_timeout: dict[str, int] = {}

    class _SuccessfulFuture:
        def result(self, timeout):
            observed_timeout["value"] = timeout
            return {
                "activities": [],
                "weight": [],
                "sleep": [],
                "hrv": [],
                "hrv_sync_metrics": {"days_back": 0, "synced_days": 0, "skipped_days": 0},
                "data_trust": {"source": "garmin", "trust_level": "TRUSTED", "reasons": []},
            }

    class _FakeExecutor:
        def __init__(self, max_workers):
            self.max_workers = max_workers

        def submit(self, fn, *args):
            return _SuccessfulFuture()

        def shutdown(self, wait, cancel_futures):
            return None

    monkeypatch.setenv("GARMIN_SYNC_TIMEOUT_S", "abc")
    monkeypatch.setattr(garmin_sync, "ThreadPoolExecutor", _FakeExecutor)

    sync.sync_all(days_back=7)

    assert observed_timeout["value"] == 20


def test_sync_all_negative_timeout_env_falls_back_to_default(monkeypatch):
    sync = GarminSync(email="e", password="p")
    observed_timeout: dict[str, int] = {}

    class _SuccessfulFuture:
        def result(self, timeout):
            observed_timeout["value"] = timeout
            return {
                "activities": [],
                "weight": [],
                "sleep": [],
                "hrv": [],
                "hrv_sync_metrics": {"days_back": 0, "synced_days": 0, "skipped_days": 0},
                "data_trust": {"source": "garmin", "trust_level": "TRUSTED", "reasons": []},
            }

    class _FakeExecutor:
        def __init__(self, max_workers):
            self.max_workers = max_workers

        def submit(self, fn, *args):
            return _SuccessfulFuture()

        def shutdown(self, wait, cancel_futures):
            return None

    monkeypatch.setenv("GARMIN_SYNC_TIMEOUT_S", "-5")
    monkeypatch.setattr(garmin_sync, "ThreadPoolExecutor", _FakeExecutor)

    sync.sync_all(days_back=7)

    assert observed_timeout["value"] == 20


def test_sync_weight_empty_all_day_summaries_are_skipped_without_index_error():
    sync = GarminSync(email="e", password="p")
    sync._ensure_connected = lambda: True
    sync.client = MagicMock()
    sync.client.get_weigh_ins.return_value = {
        "dailyWeightSummaries": [
            {"calendarDate": "2026-03-09", "allDayWeightSummaries": []},
            {
                "calendarDate": "2026-03-10",
                "allDayWeightSummaries": [{"latestWeight": 70200, "bmi": 22.0}],
            },
        ]
    }

    payload = sync.sync_weight(days_back=2)

    assert payload == [{"date": "2026-03-10", "weight_kg": 70.2, "bmi": 22.0, "source": "garmin"}]


def test_sync_activities_produces_estimated_training_load_for_valid_hr_data():
    """sync_activities() must populate estimated_training_load > 0 when avg_hr and max_hr are valid."""
    sync = GarminSync(email="e", password="p")
    sync._ensure_connected = lambda: True
    sync.client = MagicMock()
    sync.client.get_activities_by_date.return_value = [
        {
            "startTimeLocal": "2026-03-21 07:00:00",
            "activityType": {"typeKey": "running"},
            "duration": 3600,
            "distance": 10000.0,
            "averageHR": 145,
            "maxHR": 175,
            "calories": 600,
            "elevationGain": 50,
            "activityId": "act-001",
        }
    ]

    activities = sync.sync_activities(days_back=1)

    assert len(activities) == 1
    act = activities[0]
    assert "estimated_training_load" in act
    assert act["estimated_training_load"] > 0


def test_sync_activities_estimated_training_load_zero_when_no_hr_data():
    """sync_activities() sets estimated_training_load=0 when HR data is absent."""
    sync = GarminSync(email="e", password="p")
    sync._ensure_connected = lambda: True
    sync.client = MagicMock()
    sync.client.get_activities_by_date.return_value = [
        {
            "startTimeLocal": "2026-03-21 07:00:00",
            "activityType": {"typeKey": "running"},
            "duration": 3600,
            "distance": 10000.0,
            "averageHR": 0,
            "maxHR": 0,
            "calories": 600,
            "elevationGain": 50,
            "activityId": "act-002",
        }
    ]

    activities = sync.sync_activities(days_back=1)

    assert len(activities) == 1
    assert activities[0]["estimated_training_load"] == 0.0


def test_connect_retries_on_429_and_succeeds(monkeypatch, tmp_path):
    """connect() retries on 429, emits retry events, and succeeds on a later attempt."""
    import sys

    token_file = tmp_path / ".garth_token"
    call_count = {"n": 0}
    sleep_calls = []

    class _FakeGarth:
        def dumps(self):
            return "new_token"

    class _Garmin:
        def __init__(self, email=None, password=None):
            self.garth = _FakeGarth()

        def login(self):
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise RuntimeError("429 too many requests")

    monkeypatch.setitem(sys.modules, "garminconnect", type("_mod", (), {"Garmin": _Garmin})())

    events = []
    monkeypatch.setattr(garmin_sync, "_garmin_event", lambda action, **fields: events.append((action, fields)))
    monkeypatch.setattr(garmin_sync.time, "sleep", lambda s: sleep_calls.append(s))

    sync = GarminSync(email="u", password="p")
    monkeypatch.setattr(sync, "_get_token_path", lambda: token_file)

    result = sync.connect()

    assert result is True
    assert sync.is_connected is True
    assert call_count["n"] == 3
    # Two retries → two sleeps with the first two backoff values
    assert sleep_calls == [60, 120]
    retry_events = [(a, f) for a, f in events if a == "connect_retry_429"]
    assert len(retry_events) == 2
    assert retry_events[0][1]["attempt"] == 1
    assert retry_events[0][1]["wait_s"] == 60
    assert retry_events[1][1]["attempt"] == 2
    assert retry_events[1][1]["wait_s"] == 120


def test_connect_stops_after_max_retries_on_429(monkeypatch, tmp_path):
    """connect() fails after exhausting all 3 retries on persistent 429 errors."""
    import sys

    token_file = tmp_path / ".garth_token"
    call_count = {"n": 0}
    sleep_calls = []

    class _FakeGarth:
        def dumps(self):
            return "new_token"

    class _Garmin:
        def __init__(self, email=None, password=None):
            self.garth = _FakeGarth()

        def login(self):
            call_count["n"] += 1
            raise RuntimeError("429 too many requests")

    monkeypatch.setitem(sys.modules, "garminconnect", type("_mod", (), {"Garmin": _Garmin})())

    events = []
    monkeypatch.setattr(garmin_sync, "_garmin_event", lambda action, **fields: events.append((action, fields)))
    monkeypatch.setattr(garmin_sync.time, "sleep", lambda s: sleep_calls.append(s))

    sync = GarminSync(email="u", password="p")
    monkeypatch.setattr(sync, "_get_token_path", lambda: token_file)

    result = sync.connect()

    assert result is False
    assert sync.is_connected is False
    # 1 initial attempt + 3 retries = 4 total login() calls
    assert call_count["n"] == 4
    # 3 retries → 3 sleeps
    assert sleep_calls == [60, 120, 240]
    retry_events = [(a, f) for a, f in events if a == "connect_retry_429"]
    assert len(retry_events) == 3
    # Final failure emits connect_failed
    assert any(a == "connect_failed" for a, _ in events)
