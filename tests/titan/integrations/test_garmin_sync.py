import base64
import json
import logging
import threading
import time
from unittest.mock import MagicMock

import pytest
from cryptography.fernet import Fernet

from titan.integrations import garmin_sync
from titan.integrations.garmin_sync import (
    GarminSync,
    _decrypt_token,
    _encrypt_token,
    _get_token_encryption_key,
)


@pytest.mark.integration
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


@pytest.mark.integration
def test_bg_worker_returns_immediately_when_stop_event_already_set(monkeypatch):
    sync = GarminSync(email="e", password="p")
    sync._stop_event.set()

    sync_all_calls = {"count": 0}

    def _sync_all():
        sync_all_calls["count"] += 1

    monkeypatch.setattr(sync, "sync_all", _sync_all)

    sync._bg_worker(interval_hours=2)

    assert sync_all_calls["count"] == 0


@pytest.mark.integration
def test_stop_background_sync_sets_event_and_joins_thread():
    sync = GarminSync(email="e", password="p")
    sync._sync_thread = MagicMock()
    sync._sync_thread.is_alive.side_effect = [True, False]

    sync.stop_background_sync()

    assert sync._stop_event.is_set()
    sync._sync_thread.join.assert_called_once_with(timeout=5)


@pytest.mark.integration
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


@pytest.mark.integration
def test_sync_all_payload_supports_dict_access_and_json_serialization():
    sync = GarminSync(email="e", password="p")
    sync.sync_activities = lambda days_back=7, **kw: [{"date": "2026-03-04"}]
    sync.sync_weight = lambda days_back=14: [{"date": "2026-03-04", "weight": 70.2}]
    sync.sync_sleep = lambda days_back=7: [{"date": "2026-03-04", "sleep_score": 80}]
    sync.sync_hrv = lambda days_back=7: [{"date": "2026-03-04", "rmssd": 41.5}]
    sync.last_hrv_sync_metrics = {"days_back": 7, "synced_days": 1, "skipped_days": 0}

    payload = sync.sync_all(days_back=7)

    assert set(payload) == {"activities", "weight", "sleep", "hrv", "hrv_sync_metrics", "data_trust", "data_age_hours"}
    assert payload["activities"][0]["date"] == "2026-03-04"
    assert payload["hrv_sync_metrics"]["synced_days"] == 1

    serialized = json.loads(json.dumps(payload))
    assert serialized["weight"][0]["weight"] == 70.2


@pytest.mark.integration
def test_sync_all_payload_coerces_hrv_metrics_to_ints():
    sync = GarminSync(email="e", password="p")
    sync.sync_activities = lambda days_back=7, **kw: []
    sync.sync_weight = lambda days_back=14: []
    sync.sync_sleep = lambda days_back=7: []
    sync.sync_hrv = lambda days_back=7: []
    sync.last_hrv_sync_metrics = {"days_back": "7", "synced_days": 2.0, "skipped_days": False}

    payload = sync.sync_all(days_back=7)

    assert payload["hrv_sync_metrics"] == {"days_back": 7, "synced_days": 2, "skipped_days": 0}


@pytest.mark.integration
def test_last_hrv_sync_metrics_initializes_with_expected_contract_fields():
    sync = GarminSync(email="e", password="p")

    assert sync.last_hrv_sync_metrics == {"days_back": 0, "synced_days": 0, "skipped_days": 0}


@pytest.mark.integration
def test_sync_hrv_disconnected_returns_empty_and_contract_metrics():
    sync = GarminSync(email="e", password="p")
    sync._ensure_connected = lambda: False

    payload = sync.sync_hrv(days_back=5)

    assert payload == []
    assert sync.last_hrv_sync_metrics == {"days_back": 5, "synced_days": 0, "skipped_days": 0}


@pytest.mark.integration
def test_sync_all_timeout_returns_timeout_cancelled_status(monkeypatch):
    sync = GarminSync(email="e", password="p")

    def _slow_sync_operation(_days_back):
        time.sleep(0.02)
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


@pytest.mark.integration
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


@pytest.mark.integration
def test_sync_all_payload_includes_data_trust_contract():
    sync = GarminSync(email="e", password="p")
    sync.sync_activities = lambda days_back=7, **kw: []
    sync.sync_weight = lambda days_back=14: []
    sync.sync_sleep = lambda days_back=7: []
    sync.sync_hrv = lambda days_back=7: []
    sync.last_hrv_sync_metrics = {"days_back": 7, "synced_days": 0, "skipped_days": 0}

    payload = sync.sync_all(days_back=7)

    assert payload["data_trust"]["source"] == "garmin"
    assert payload["data_trust"]["trust_level"] == "TRUSTED"


@pytest.mark.integration
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


@pytest.mark.integration
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

    assert observed_timeout["value"] == 90


@pytest.mark.integration
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

    assert observed_timeout["value"] == 90


@pytest.mark.integration
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

    assert payload == [{"date": "2026-03-10", "weight_kg": 70.2}]


@pytest.mark.integration
def test_sync_activities_produces_estimated_training_load_for_valid_hr_data():
    """sync_activities() must populate estimated_training_load > 0 when avg_hr
    and athlete_max_hr are valid."""
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

    activities = sync.sync_activities(days_back=1, athlete_max_hr=190)

    assert len(activities) == 1
    act = activities[0]
    assert "estimated_training_load" in act
    assert act["estimated_training_load"] > 0


@pytest.mark.integration
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


@pytest.mark.integration
def test_connect_retries_on_429_and_succeeds(monkeypatch, tmp_path):
    """connect() retries on 429, emits retry events, and succeeds on a later attempt."""
    monkeypatch.setenv("TITAN_ENV", "dev")
    import sys

    token_file = tmp_path / ".garth_token"
    call_count = {"n": 0}
    sleep_calls = []

    class _FakeGarth:
        def dumps(self):
            return "new_token"

    class _Garmin:
        def __init__(self, email=None, password=None):
            self.client = _FakeGarth()

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


@pytest.mark.integration
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
            self.client = _FakeGarth()

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


@pytest.mark.integration
def test_connect_token_ping_rate_limited_assumes_valid_and_returns_true(monkeypatch, tmp_path):
    """429 on ping + secondary call succeeds → token assumed valid: is_connected=True, no re-login."""
    monkeypatch.setenv("TITAN_ENV", "dev")
    import sys

    token_file = tmp_path / ".garth_token"
    token_file.write_text("saved_token_data", encoding="utf-8")

    login_called = {"n": 0}

    class _FakeGarth:
        def loads(self, _data):
            pass

    class _Garmin:
        def __init__(self, email=None, password=None):
            self.client = _FakeGarth()

        def connectapi(self, _path):
            raise RuntimeError("429 too many requests")

        def get_user_summary(self, _date):
            return {"displayName": "test_user"}  # Secondary call succeeds → token valid

        def login(self):
            login_called["n"] += 1

    monkeypatch.setitem(sys.modules, "garminconnect", type("_mod", (), {"Garmin": _Garmin})())

    events = []
    monkeypatch.setattr(garmin_sync, "_garmin_event", lambda action, **fields: events.append((action, fields)))

    sync = GarminSync(email="u", password="p")
    monkeypatch.setattr(sync, "_get_token_path", lambda: token_file)

    result = sync.connect()

    assert result is True
    assert sync.is_connected is True
    assert login_called["n"] == 0, "Must NOT fall through to fresh login on 429 ping"
    assert token_file.exists(), "Token file must NOT be deleted on 429 ping"
    assumed_events = [a for a, _ in events if a == "connect_token_assumed_valid"]
    assert assumed_events, "connect_token_assumed_valid event must be emitted"



@pytest.mark.integration
def test_connect_token_ping_auth_fail_falls_through_to_login(monkeypatch, tmp_path):
    """When connectapi() raises an auth error, token is deleted and fresh login is attempted."""
    monkeypatch.setenv("TITAN_ENV", "dev")
    import sys

    token_file = tmp_path / ".garth_token"
    token_file.write_text("saved_token_data", encoding="utf-8")

    login_called = {"n": 0}

    class _FakeGarth:
        def loads(self, _data):
            pass

        def dumps(self):
            return "fresh_token"

    class _Garmin:
        def __init__(self, email=None, password=None):
            self.client = _FakeGarth()

        def connectapi(self, _path):
            raise RuntimeError("401 unauthorized")

        def login(self):
            login_called["n"] += 1

    monkeypatch.setitem(sys.modules, "garminconnect", type("_mod", (), {"Garmin": _Garmin})())

    events = []
    monkeypatch.setattr(garmin_sync, "_garmin_event", lambda action, **fields: events.append((action, fields)))

    sync = GarminSync(email="u", password="p")
    monkeypatch.setattr(sync, "_get_token_path", lambda: token_file)

    result = sync.connect()

    assert result is True
    assert sync.is_connected is True
    assert login_called["n"] == 1, "Must fall through to fresh login on auth fail"
    load_failed_events = [a for a, _ in events if a == "connect_token_load_failed"]
    assert load_failed_events, "connect_token_load_failed event must be emitted"


# ---------------------------------------------------------------------------
# Fix 1: 429 on ping + auth fail on secondary call → session invalidated,
#         token deleted, re-login attempted
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_connect_token_ping_429_secondary_auth_fail_invalidates_session(monkeypatch, tmp_path):
    """429 on verification ping + auth error on secondary data call → _invalidate_session called,
    token deleted, connect() returns False (no re-login in a rate-limited window)."""
    monkeypatch.setenv("TITAN_ENV", "dev")
    import sys

    token_file = tmp_path / ".garth_token"
    token_file.write_text("saved_token_data", encoding="utf-8")

    login_called = {"n": 0}

    class _FakeGarth:
        def loads(self, _data):
            pass

        def dumps(self):
            return "fresh_token"

    class _Garmin:
        def __init__(self, email=None, password=None):
            self.client = _FakeGarth()

        def connectapi(self, _path):
            raise RuntimeError("429 too many requests")

        def get_user_summary(self, _date):
            raise RuntimeError("401 unauthorized")

        def login(self):
            login_called["n"] += 1

    monkeypatch.setitem(sys.modules, "garminconnect", type("_mod", (), {"Garmin": _Garmin})())

    events = []
    monkeypatch.setattr(garmin_sync, "_garmin_event", lambda action, **fields: events.append((action, fields)))

    invalidated = []
    sync = GarminSync(email="u", password="p")
    monkeypatch.setattr(sync, "_get_token_path", lambda: token_file)
    original_invalidate = sync._invalidate_session
    def _track_invalidate():
        invalidated.append(True)
        original_invalidate()
    monkeypatch.setattr(sync, "_invalidate_session", _track_invalidate)

    result = sync.connect()

    # Must NOT attempt a re-login — we are in a rate-limited window
    assert login_called["n"] == 0, "Must NOT fall through to fresh login in a rate-limited window"
    # _invalidate_session must have been called to clean up auth state
    assert invalidated == [True], "_invalidate_session must be called on secondary auth failure"
    # connect_token_stale_after_429 event must be emitted to signal the stale-token detection
    stale_events = [a for a, _ in events if a == "connect_token_stale_after_429"]
    assert stale_events, "connect_token_stale_after_429 event must be emitted"
    # connect() must return False — the caller will retry on the next scheduled cycle
    assert result is False, "connect() must return False when secondary call fails during rate-limited window"
    assert sync.is_connected is False
    # Token file must be deleted so the next cycle attempts a fresh credential login
    assert not token_file.exists(), "Token file must be deleted after secondary auth failure"


@pytest.mark.integration
def test_connect_token_ping_429_secondary_also_429_assumes_valid(monkeypatch, tmp_path):
    """429 on ping + 429 on secondary call → keep current assume-valid behavior."""
    monkeypatch.setenv("TITAN_ENV", "dev")
    import sys

    token_file = tmp_path / ".garth_token"
    token_file.write_text("saved_token_data", encoding="utf-8")

    login_called = {"n": 0}

    class _FakeGarth:
        def loads(self, _data):
            pass

    class _Garmin:
        def __init__(self, email=None, password=None):
            self.client = _FakeGarth()

        def connectapi(self, _path):
            raise RuntimeError("429 too many requests")

        def get_user_summary(self, _date):
            raise RuntimeError("429 rate limit again")

        def login(self):
            login_called["n"] += 1

    monkeypatch.setitem(sys.modules, "garminconnect", type("_mod", (), {"Garmin": _Garmin})())

    events = []
    monkeypatch.setattr(garmin_sync, "_garmin_event", lambda action, **fields: events.append((action, fields)))

    sync = GarminSync(email="u", password="p")
    monkeypatch.setattr(sync, "_get_token_path", lambda: token_file)

    result = sync.connect()

    assert result is True
    assert sync.is_connected is True
    assert login_called["n"] == 0, "Must NOT fall through to fresh login when both calls are 429"
    assert token_file.exists(), "Token file must NOT be deleted when both calls are rate-limited"
    assumed_events = [a for a, _ in events if a == "connect_token_assumed_valid"]
    assert assumed_events, "connect_token_assumed_valid event must be emitted"


# ---------------------------------------------------------------------------
# Fix 3: auth exception in sync_activities → _invalidate_session() called
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_sync_activities_auth_exception_invalidates_session(monkeypatch):
    """Auth exception in sync_activities outer except block → _invalidate_session() called."""
    sync = GarminSync(email="u", password="p")
    sync.is_connected = True

    class _FakeClient:
        def get_activities_by_date(self, *_args, **_kwargs):
            raise RuntimeError("401 unauthorized")

    sync.client = _FakeClient()

    invalidated = {"called": False}

    def _fake_invalidate(*_error):
        invalidated["called"] = True

    monkeypatch.setattr(sync, "_invalidate_session", _fake_invalidate)

    events = []
    monkeypatch.setattr(garmin_sync, "_garmin_event", lambda action, **fields: events.append((action, fields)))
    monkeypatch.setattr(garmin_sync, "_emit_failure", lambda *_a, **_k: None)

    result = sync.sync_activities(days_back=1)

    assert result == [], "sync_activities must return empty list on exception"
    assert invalidated["called"], "_invalidate_session must be called on auth exception"


@pytest.mark.integration
def test_sync_sleep_outer_auth_exception_invalidates_session(monkeypatch):
    """Auth exception escaping sync_sleep outer try → _invalidate_session() called."""
    sync = GarminSync(email="u", password="p")
    sync.is_connected = True

    class _FakeClient:
        def get_sleep_data(self, _date):
            raise RuntimeError("401 unauthorized")

    sync.client = _FakeClient()

    invalidated = {"called": False}

    def _fake_invalidate(*_error):
        invalidated["called"] = True

    monkeypatch.setattr(sync, "_invalidate_session", _fake_invalidate)

    events = []
    monkeypatch.setattr(garmin_sync, "_garmin_event", lambda action, **fields: events.append((action, fields)))
    monkeypatch.setattr(garmin_sync, "_emit_failure", lambda *_a, **_k: None)

    # The inner per-day except catches auth errors and calls _invalidate_session + break,
    # so the outer except won't fire here. Verify via the inner path.
    result = sync.sync_sleep(days_back=1)

    assert result == []
    assert invalidated["called"], "_invalidate_session must be called on auth exception in sync_sleep"


@pytest.mark.integration
def test_instance_counter_increments(monkeypatch):
    """Each GarminSync() increments the class-level instance counter."""
    monkeypatch.setattr(garmin_sync, "_garmin_event", lambda *a, **kw: None)
    monkeypatch.setattr(garmin_sync, "_emit_failure", lambda *a, **kw: None)

    before = GarminSync._instance_count
    GarminSync(email="a", password="b")
    after_one = GarminSync._instance_count
    GarminSync(email="c", password="d")
    after_two = GarminSync._instance_count

    assert after_one == before + 1
    assert after_two == before + 2


@pytest.mark.integration
def test_instance_counter_logs_warning_on_duplicate(monkeypatch, caplog):
    """Second+ GarminSync instance logs a warning about duplicate."""
    monkeypatch.setattr(garmin_sync, "_garmin_event", lambda *a, **kw: None)
    monkeypatch.setattr(garmin_sync, "_emit_failure", lambda *a, **kw: None)

    # Ensure counter is > 0 from previous tests; create one more to trigger warning
    with caplog.at_level(logging.WARNING):
        GarminSync(email="x", password="y")

    assert any("garmin_sync_duplicate_instance" in r.message for r in caplog.records)


# ─── ADR-0050 / T5-12 Pass 2 — garmin_api_degraded CRITICAL event tests ──────

def _find_degraded_event(records):
    """Return the garmin_api_degraded event record, or None."""
    for r in records:
        try:
            payload = json.loads(r.message)
            if payload.get("action") == "garmin_api_degraded":
                return payload
        except (json.JSONDecodeError, AttributeError):
            pass
    return None


# C1 — authentication failure in _connect_impl()
@pytest.mark.integration
def test_garmin_api_degraded_emitted_on_auth_fail_in_connect(monkeypatch, caplog):
    """C1: garmin_api_degraded CRITICAL is emitted when _connect_impl() fails with auth error.

    Patches garminconnect at the sys.modules level so the exception is caught
    by the try/except inside _connect_impl, which is where emission logic lives.
    """
    import sys
    from unittest.mock import MagicMock

    import titan.integrations.garmin_sync as _gs
    monkeypatch.setattr(_gs, "_garmin_event", lambda *a, **kw: None)

    # Fake garminconnect so login raises a recognisable auth error.
    fake_gc = MagicMock()
    fake_gc.Garmin.return_value.login.side_effect = Exception("Unauthorized")
    monkeypatch.setitem(sys.modules, "garminconnect", fake_gc)

    sync = GarminSync(email="e@x.com", password="pw")
    # Ensure no stale token file will be found.
    monkeypatch.setattr(sync, "_get_token_path", lambda: _gs.Path("/nonexistent_token_file"))

    with caplog.at_level(logging.ERROR):
        result = sync._connect_impl()

    assert result is False
    event = _find_degraded_event(caplog.records)
    assert event is not None, "garmin_api_degraded event not found in logs"
    assert event["action"] == "garmin_api_degraded"
    assert event["severity"] == "critical"
    assert event["failure_class"] == "GARMIN_AUTH_FAIL"
    assert event["sync_status"] == "connect_failed"
    assert event["trust_level"] == "INVALID"
    assert "GARMIN_AUTH_FAIL" in event["reasons"]
    assert event["degraded_mode_expected"] is True


# C1 — full connect() path emits garmin_api_degraded on auth failure
@pytest.mark.integration
def test_connect_emits_garmin_api_degraded_on_auth_failure(monkeypatch, caplog):
    """C1: connect() propagates garmin_api_degraded when login raises an auth error."""
    import sys
    from unittest.mock import MagicMock

    import titan.integrations.garmin_sync as _gs
    monkeypatch.setattr(_gs, "_garmin_event", lambda *a, **kw: None)

    fake_gc = MagicMock()
    fake_gc.Garmin.return_value.login.side_effect = Exception("401 Unauthorized")
    monkeypatch.setitem(sys.modules, "garminconnect", fake_gc)

    sync = GarminSync(email="e@x.com", password="pw")
    monkeypatch.setattr(sync, "_get_token_path", lambda: _gs.Path("/nonexistent_token_file"))

    with caplog.at_level(logging.ERROR):
        result = sync.connect()

    assert result is False
    event = _find_degraded_event(caplog.records)
    assert event is not None, "garmin_api_degraded not emitted on auth failure"
    assert event["severity"] == "critical"
    assert event["failure_class"] == "GARMIN_AUTH_FAIL"


# C2 — timeout in sync_all()
@pytest.mark.integration
def test_garmin_api_degraded_emitted_on_timeout(monkeypatch, caplog):
    """C2: garmin_api_degraded CRITICAL is emitted when sync_all() times out."""
    import titan.integrations.garmin_sync as _gs

    monkeypatch.setattr(_gs, "_garmin_event", lambda *a, **kw: None)
    monkeypatch.setattr(_gs, "_resolve_sync_timeout_seconds", lambda: 0)

    sync = GarminSync(email="e", password="p")

    _block = threading.Event()

    def _slow_operation(days_back):
        _block.wait()

    monkeypatch.setattr(sync, "_sync_operation", _slow_operation)

    with caplog.at_level(logging.ERROR):
        result = sync.sync_all(days_back=1)

    assert result.get("status") == "timeout_cancelled"
    event = _find_degraded_event(caplog.records)
    assert event is not None, "garmin_api_degraded not emitted on timeout"
    assert event["severity"] == "critical"
    assert event["failure_class"] == "GARMIN_TIMEOUT"
    assert event["sync_status"] == "timeout_cancelled"
    assert "SYNC_TIMEOUT" in event["reasons"]
    assert sync._consecutive_failures == 1
    _block.set()  # release background thread so executor shuts down cleanly


# C3 — consecutive failure threshold crossed
@pytest.mark.integration
def test_garmin_api_degraded_emitted_on_consecutive_failure_threshold(monkeypatch, caplog):
    """C3: garmin_api_degraded is emitted when consecutive empty syncs reach threshold."""
    import titan.integrations.garmin_sync as _gs

    monkeypatch.setattr(_gs, "_garmin_event", lambda *a, **kw: None)

    sync = GarminSync(email="e", password="p")

    def _empty_operation(days_back):
        from titan.orchestration.contracts import GarminSyncResultContract, HRVSyncMetricsContract
        from titan.science.data_trust import evaluate_garmin_trust
        hrv_metrics = HRVSyncMetricsContract(days_back=days_back, synced_days=0, skipped_days=0).to_payload()
        return GarminSyncResultContract(
            activities=[],
            weight=[],
            sleep=[],
            hrv=[],
            hrv_sync_metrics=hrv_metrics,
            data_trust=evaluate_garmin_trust(data_age_hours=0.0).to_payload(),
        ).to_payload()

    monkeypatch.setattr(sync, "_sync_operation", _empty_operation)

    from titan.config.thresholds import GARMIN_DEGRADATION_FAILURE_THRESHOLD_COUNT

    # Run threshold - 1 syncs: no event yet
    for _ in range(GARMIN_DEGRADATION_FAILURE_THRESHOLD_COUNT - 1):
        sync.sync_all(days_back=1)

    caplog.clear()
    with caplog.at_level(logging.ERROR):
        sync.sync_all(days_back=1)

    event = _find_degraded_event(caplog.records)
    assert event is not None, "garmin_api_degraded not emitted at threshold crossing"
    assert event["severity"] == "critical"
    assert "CONSECUTIVE_FAILURE_THRESHOLD_CROSSED" in event["reasons"]
    assert sync._consecutive_failures >= GARMIN_DEGRADATION_FAILURE_THRESHOLD_COUNT
    assert sync.is_api_degraded is True


# C4 — trust resolves to INVALID before threshold
@pytest.mark.integration
def test_garmin_api_degraded_emitted_on_trust_invalid(monkeypatch, caplog):
    """C4: garmin_api_degraded is emitted when trust resolves INVALID before threshold crossed."""
    import titan.integrations.garmin_sync as _gs
    from titan.science.data_trust import DataTrustLevel, DataTrustReport, evaluate_garmin_trust

    monkeypatch.setattr(_gs, "_garmin_event", lambda *a, **kw: None)

    sync = GarminSync(email="e", password="p")
    # Inject a high data age so trust evaluates to INVALID
    sync._last_successful_sync_at = None  # never synced → age = inf

    def _empty_operation(days_back):
        from titan.orchestration.contracts import GarminSyncResultContract, HRVSyncMetricsContract
        hrv_metrics = HRVSyncMetricsContract(days_back=days_back, synced_days=0, skipped_days=0).to_payload()
        return GarminSyncResultContract(
            activities=[],
            weight=[],
            sleep=[],
            hrv=[],
            hrv_sync_metrics=hrv_metrics,
            data_trust=evaluate_garmin_trust(data_age_hours=0.0).to_payload(),
        ).to_payload()

    monkeypatch.setattr(sync, "_sync_operation", _empty_operation)

    # Keep consecutive_failures below threshold so C3 doesn't fire instead
    sync._consecutive_failures = 0

    with caplog.at_level(logging.ERROR):
        sync.sync_all(days_back=1)

    event = _find_degraded_event(caplog.records)
    assert event is not None, "garmin_api_degraded not emitted on trust INVALID"
    assert event["severity"] == "critical"
    assert event["trust_level"] == "INVALID"
    assert "TRUST_LEVEL_INVALID" in event["reasons"]


# is_api_degraded property
@pytest.mark.integration
def test_is_api_degraded_property():
    """is_api_degraded returns True only when threshold is reached."""
    from titan.config.thresholds import GARMIN_DEGRADATION_FAILURE_THRESHOLD_COUNT

    sync = GarminSync(email="e", password="p")
    assert sync.is_api_degraded is False

    sync._consecutive_failures = GARMIN_DEGRADATION_FAILURE_THRESHOLD_COUNT - 1
    assert sync.is_api_degraded is False

    sync._consecutive_failures = GARMIN_DEGRADATION_FAILURE_THRESHOLD_COUNT
    assert sync.is_api_degraded is True


# Reset on success
@pytest.mark.integration
def test_consecutive_failures_reset_on_successful_sync(monkeypatch):
    """_consecutive_failures resets to 0 on a sync that returns records."""
    import titan.integrations.garmin_sync as _gs

    monkeypatch.setattr(_gs, "_garmin_event", lambda *a, **kw: None)

    sync = GarminSync(email="e", password="p")
    sync._consecutive_failures = 5  # simulate prior failures

    def _good_operation(days_back):
        from titan.orchestration.contracts import GarminSyncResultContract, HRVSyncMetricsContract
        from titan.science.data_trust import evaluate_garmin_trust
        hrv_metrics = HRVSyncMetricsContract(days_back=days_back, synced_days=1, skipped_days=0).to_payload()
        return GarminSyncResultContract(
            activities=[{"date": "2026-03-23"}],
            weight=[],
            sleep=[],
            hrv=[],
            hrv_sync_metrics=hrv_metrics,
            data_trust=evaluate_garmin_trust(data_age_hours=0.0).to_payload(),
        ).to_payload()

    monkeypatch.setattr(sync, "_sync_operation", _good_operation)
    sync.sync_all(days_back=1)

    assert sync._consecutive_failures == 0
    assert sync._last_successful_sync_at is not None
    assert sync.is_api_degraded is False


# ────────────────────────────────────────────────────────────────────────────
# athlete_max_hr source correctness (T5-44)
# ────────────────────────────────────────────────────────────────────────────


def _make_activity_payload(avg_hr: int = 145, max_hr: int = 175) -> dict:
    return {
        "startTimeLocal": "2026-03-21 07:00:00",
        "activityType": {"typeKey": "running"},
        "duration": 3600,
        "distance": 10000.0,
        "averageHR": avg_hr,
        "maxHR": max_hr,
        "calories": 600,
        "elevationGain": 50,
        "activityId": "act-trimp-001",
    }


@pytest.mark.integration
def test_sync_activities_uses_athlete_max_hr_not_session_peak_for_trimp():
    """sync_activities() must pass athlete_max_hr to TRIMPEngine, not session peak HR.

    avg_hr=130, session_max_hr=145, athlete_max_hr=190.
      With session_peak as ceiling: 130/145 ≈ 89.7% → zone 4 → TRIMP = 60×4 = 240
      With athlete_max_hr:          130/190 ≈ 68.4% → zone 2 → TRIMP = 60×2 = 120

    Correct answer is 120.  The test confirms zone 2 by checking estimated_training_load.
    """
    sync = GarminSync(email="e", password="p")
    sync._ensure_connected = lambda: True
    sync.client = MagicMock()
    sync.client.get_activities_by_date.return_value = [
        _make_activity_payload(avg_hr=130, max_hr=145)
    ]

    activities = sync.sync_activities(days_back=1, athlete_max_hr=190)

    assert len(activities) == 1
    act = activities[0]
    # 60 min × zone-2 multiplier (2) = 120
    assert act["estimated_training_load"] == 120.0


@pytest.mark.integration
def test_sync_activities_athlete_max_hr_zero_yields_zero_load():
    """When athlete_max_hr is not supplied (defaults to 0), TRIMP cannot be
    calculated and estimated_training_load must be 0.0."""
    sync = GarminSync(email="e", password="p")
    sync._ensure_connected = lambda: True
    sync.client = MagicMock()
    sync.client.get_activities_by_date.return_value = [
        _make_activity_payload(avg_hr=145, max_hr=175)
    ]

    activities = sync.sync_activities(days_back=1)  # athlete_max_hr defaults to 0

    assert len(activities) == 1
    assert activities[0]["estimated_training_load"] == 0.0


@pytest.mark.integration
def test_sync_activities_session_max_hr_preserved_in_activity_record():
    """session_max_hr from Garmin payload must remain in the activity dict
    under the 'max_hr' key for diagnostic purposes, regardless of athlete_max_hr."""
    sync = GarminSync(email="e", password="p")
    sync._ensure_connected = lambda: True
    sync.client = MagicMock()
    sync.client.get_activities_by_date.return_value = [
        _make_activity_payload(avg_hr=145, max_hr=172)
    ]

    activities = sync.sync_activities(days_back=1, athlete_max_hr=190)

    assert len(activities) == 1
    # Session peak must be retained verbatim
    assert activities[0]["max_hr"] == 172


@pytest.mark.integration
def test_sync_activities_session_peak_above_athlete_max_hr_does_not_crash():
    """Noisy HR data can produce session_max_hr > athlete_max_hr.
    sync_activities() must not crash and must clamp to zone 5."""
    sync = GarminSync(email="e", password="p")
    sync._ensure_connected = lambda: True
    sync.client = MagicMock()
    # avg_hr exceeds athlete_max_hr — extreme outlier
    sync.client.get_activities_by_date.return_value = [
        _make_activity_payload(avg_hr=200, max_hr=210)
    ]

    activities = sync.sync_activities(days_back=1, athlete_max_hr=190)

    assert len(activities) == 1
    act = activities[0]
    # Should not raise; TRIMP should be zone 5 × 60 min = 300
    assert act["estimated_training_load"] == 300.0


# ---------------------------------------------------------------------------
# T5-101: Garth token Fernet encryption helpers
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_token_encrypted_when_key_set(monkeypatch):
    key = Fernet.generate_key()
    monkeypatch.setenv("TITAN_GARTH_TOKEN_KEY", key.decode())
    encrypted = _encrypt_token("test_data")
    assert encrypted != b"test_data"
    assert _decrypt_token(encrypted) == "test_data"


@pytest.mark.integration
def test_token_plaintext_when_key_missing(monkeypatch):
    monkeypatch.delenv("TITAN_GARTH_TOKEN_KEY", raising=False)
    monkeypatch.setenv("TITAN_ENV", "dev")
    result = _encrypt_token("test_data")
    assert result == b"test_data"


@pytest.mark.integration
def test_token_decrypt_plaintext_when_key_missing(monkeypatch):
    monkeypatch.delenv("TITAN_GARTH_TOKEN_KEY", raising=False)
    monkeypatch.setenv("TITAN_ENV", "dev")
    result = _decrypt_token(b"test_data")
    assert result == "test_data"


@pytest.mark.integration
def test_token_decrypt_raises_on_corrupt(monkeypatch):
    key = Fernet.generate_key()
    monkeypatch.setenv("TITAN_GARTH_TOKEN_KEY", key.decode())
    events = []
    monkeypatch.setattr(garmin_sync, "_garmin_event", lambda action, **fields: events.append((action, fields)))
    import pytest
    with pytest.raises(ValueError, match="token invalid"):
        _decrypt_token(b"plaintext_fallback")
    assert any(
        e[0] == "token_decrypt_failed" and e[1].get("failure_class") == "TOKEN_DECRYPT_FAIL"
        for e in events
    )


@pytest.mark.integration
def test_get_token_encryption_key_returns_none_when_unset(monkeypatch):
    monkeypatch.delenv("TITAN_GARTH_TOKEN_KEY", raising=False)
    assert _get_token_encryption_key() is None


@pytest.mark.integration
def test_get_token_encryption_key_returns_none_on_invalid_base64(monkeypatch):
    monkeypatch.setenv("TITAN_GARTH_TOKEN_KEY", "not-valid-base64!!!")
    assert _get_token_encryption_key() is None


@pytest.mark.integration
def test_get_token_encryption_key_returns_bytes_on_valid_key(monkeypatch):
    key = Fernet.generate_key()
    monkeypatch.setenv("TITAN_GARTH_TOKEN_KEY", key.decode())
    result = _get_token_encryption_key()
    assert isinstance(result, bytes)


# ---------------------------------------------------------------------------
# RBP-04 / F-10: the token key is checked when GarminSync is built
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_garmin_sync_refuses_a_malformed_token_key(monkeypatch):
    monkeypatch.setenv("TITAN_GARTH_TOKEN_KEY", "not-valid-base64!!!")
    with pytest.raises(ValueError, match="not a valid Fernet key"):
        GarminSync(email="a@example.com", password="pw")


@pytest.mark.integration
def test_garmin_sync_refuses_a_token_key_of_the_wrong_length(monkeypatch):
    monkeypatch.setenv("TITAN_GARTH_TOKEN_KEY", base64.urlsafe_b64encode(b"short").decode())
    with pytest.raises(ValueError, match="not a valid Fernet key"):
        GarminSync(email="a@example.com", password="pw")


@pytest.mark.integration
def test_empty_token_key_counts_as_unset(monkeypatch, caplog):
    """.env.example ships an empty TITAN_GARTH_TOKEN_KEY=; that must not stop GarminSync."""
    monkeypatch.setenv("TITAN_GARTH_TOKEN_KEY", "")
    with caplog.at_level(logging.WARNING, logger="titan.integrations.garmin_sync"):
        GarminSync(email="a@example.com", password="pw")
    assert _get_token_encryption_key() is None
    assert not any("Invalid TITAN_GARTH_TOKEN_KEY" in r.getMessage() for r in caplog.records)


@pytest.mark.integration
def test_garmin_sync_accepts_a_valid_token_key(monkeypatch):
    monkeypatch.setenv("TITAN_GARTH_TOKEN_KEY", Fernet.generate_key().decode())
    assert GarminSync(email="a@example.com", password="pw").is_connected is False
