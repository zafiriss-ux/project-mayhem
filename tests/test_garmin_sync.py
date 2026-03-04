import logging
import threading
import time

from titan.integrations import garmin_sync
from titan.integrations.garmin_sync import (
    GARMIN_API_UNAVAILABLE,
    GARMIN_AUTH_FAIL,
    GARMIN_PAYLOAD_MALFORMED,
    GARMIN_RATE_LIMIT,
    GARMIN_TIMEOUT,
    GarminSync,
)


class _FakeClient:
    def __init__(self, *, activities=None, weigh_ins=None, sleep=None, hrv=None):
        self.activities = activities
        self.weigh_ins = weigh_ins
        self.sleep = sleep or []
        self.hrv = hrv or []
        self.requested_sleep_dates = []
        self.requested_hrv_dates = []

    def get_activities_by_date(self, _start, _end, _activity_type):
        if isinstance(self.activities, Exception):
            raise self.activities
        return self.activities or []

    def get_weigh_ins(self, _start, _end):
        if isinstance(self.weigh_ins, Exception):
            raise self.weigh_ins
        return self.weigh_ins or {"dailyWeightSummaries": []}

    def get_sleep_data(self, day):
        self.requested_sleep_dates.append(day)
        item = self.sleep.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def get_hrv_data(self, day):
        self.requested_hrv_dates.append(day)
        item = self.hrv.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _connected_sync(client):
    sync = GarminSync(email="u", password="p")
    sync.is_connected = True
    sync.client = client
    return sync


def test_sync_activities_happy_path(monkeypatch):
    events = []
    monkeypatch.setattr(garmin_sync, "_garmin_event", lambda action, **fields: events.append((action, fields)))

    sync = _connected_sync(
        _FakeClient(
            activities=[
                {
                    "startTimeLocal": "2026-03-01T08:00:00",
                    "activityType": {"typeKey": "running"},
                    "distance": 5000,
                    "duration": 1500,
                    "averageHeartRate": 150,
                    "maxHeartRate": 170,
                    "calories": 400,
                    "elevationGain": 50,
                    "activityId": 111,
                }
            ]
        )
    )

    result = sync.sync_activities(days_back=1)

    assert len(result) == 1
    assert result[0]["distance_km"] == 5.0
    assert result[0]["avg_pace_sec_per_km"] == 300
    assert all(action != GARMIN_PAYLOAD_MALFORMED for action, _ in events)


def test_sync_activities_error_emits_failure_class_event(monkeypatch):
    events = []
    monkeypatch.setattr(garmin_sync, "_garmin_event", lambda action, **fields: events.append((action, fields)))

    sync = _connected_sync(_FakeClient(activities=Exception("429 too many requests")))

    result = sync.sync_activities(days_back=1)

    assert result == []
    action, fields = events[-1]
    assert action == GARMIN_RATE_LIMIT
    assert fields["subsystem"] == "sync_activities"
    assert fields["failure_class"] == GARMIN_RATE_LIMIT


def test_sync_weight_happy_path(monkeypatch):
    events = []
    monkeypatch.setattr(garmin_sync, "_garmin_event", lambda action, **fields: events.append((action, fields)))

    sync = _connected_sync(
        _FakeClient(
            weigh_ins={
                "dailyWeightSummaries": [
                    {
                        "calendarDate": "2026-03-02",
                        "allDayWeightSummaries": [{"latestWeight": 72400, "bmi": 22.8}],
                    }
                ]
            }
        )
    )

    result = sync.sync_weight(days_back=7)

    assert result == [{"date": "2026-03-02", "weight_kg": 72.4, "bmi": 22.8, "source": "garmin"}]
    assert events == []


def test_sync_weight_error_emits_failure_class_event(monkeypatch):
    events = []
    monkeypatch.setattr(garmin_sync, "_garmin_event", lambda action, **fields: events.append((action, fields)))

    sync = _connected_sync(_FakeClient(weigh_ins=Exception("Unauthorized credentials")))

    result = sync.sync_weight(days_back=7)

    assert result == []
    action, fields = events[-1]
    assert action == GARMIN_AUTH_FAIL
    assert fields["subsystem"] == "sync_weight"


def test_sync_sleep_happy_path(monkeypatch):
    events = []
    monkeypatch.setattr(garmin_sync, "_garmin_event", lambda action, **fields: events.append((action, fields)))

    sync = _connected_sync(
        _FakeClient(
            sleep=[
                {
                    "dailySleepDTO": {
                        "sleepTimeSeconds": 28800,
                        "deepSleepSeconds": 7200,
                        "remSleepSeconds": 5400,
                        "sleepScores": {"overall": {"value": 84}},
                    }
                }
            ]
        )
    )

    result = sync.sync_sleep(days_back=1)

    assert result == [
        {
            "date": sync.client.requested_sleep_dates[0],
            "total_sleep_hours": 8.0,
            "deep_sleep_hours": 2.0,
            "rem_sleep_hours": 1.5,
            "sleep_score": 84,
        }
    ]
    assert events == []


def test_sync_sleep_error_emits_failure_class_event(monkeypatch):
    events = []
    monkeypatch.setattr(garmin_sync, "_garmin_event", lambda action, **fields: events.append((action, fields)))

    sync = _connected_sync(_FakeClient(sleep=[TimeoutError("timeout while fetching sleep")]))

    result = sync.sync_sleep(days_back=1)

    assert result == []
    action, fields = events[-1]
    assert action == GARMIN_TIMEOUT
    assert fields["subsystem"] == "sync_sleep"


def test_sync_hrv_happy_path_updates_metrics_and_returns_data(monkeypatch):
    events = []
    monkeypatch.setattr(garmin_sync, "_garmin_event", lambda action, **fields: events.append((action, fields)))

    sync = _connected_sync(
        _FakeClient(
            hrv=[
                {"hrvSummary": {"lastNight5MinHigh": 48.26, "status": "BALANCED"}},
                {"hrvSummary": {"weeklyAvg": 51.0, "status": "LOW"}},
            ]
        )
    )

    result = sync.sync_hrv(days_back=2)

    assert len(result) == 2
    assert result[0]["rmssd"] == 48.3
    assert result[1]["rmssd"] == 51.0
    assert sync.last_hrv_sync_metrics == {"days_back": 2, "synced_days": 2, "skipped_days": 0}
    assert ("hrv_sync_metrics", {"days_back": 2, "synced_days": 2, "skipped_days": 0}) in events


def test_sync_hrv_skipped_day_logs_and_emits_structured_event(monkeypatch, caplog):
    events = []
    monkeypatch.setattr(garmin_sync, "_garmin_event", lambda action, **fields: events.append((action, fields)))

    sync = _connected_sync(
        _FakeClient(
            hrv=[
                ValueError("bad hrv payload"),
                {"hrvSummary": {"lastNight5MinHigh": 42, "status": "BALANCED"}},
            ]
        )
    )

    with caplog.at_level(logging.WARNING):
        result = sync.sync_hrv(days_back=2)

    assert len(result) == 1
    assert sync.last_hrv_sync_metrics == {"days_back": 2, "synced_days": 1, "skipped_days": 1}

    skipped_action, skipped_event = events[0]
    assert skipped_action == GARMIN_PAYLOAD_MALFORMED
    assert skipped_event["failure_class"] == GARMIN_PAYLOAD_MALFORMED
    assert skipped_event["error_class"] == "ValueError"
    assert skipped_event["error_message"] == "bad hrv payload"
    assert skipped_event["date"] in sync.client.requested_hrv_dates

    assert "Skipping HRV day" in caplog.text
    assert "ValueError" in caplog.text
    assert "bad hrv payload" in caplog.text


def test_sync_hrv_top_level_exception_emits_api_unavailable(monkeypatch):
    events = []
    monkeypatch.setattr(garmin_sync, "_garmin_event", lambda action, **fields: events.append((action, fields)))

    sync = _connected_sync(_FakeClient(hrv=[]))

    def _boom(*_args, **_kwargs):
        raise RuntimeError("upstream unavailable")

    monkeypatch.setattr(garmin_sync, "timedelta", _boom)

    result = sync.sync_hrv(days_back=1)

    assert result == []
    action, fields = events[0]
    assert action == GARMIN_API_UNAVAILABLE
    assert fields["subsystem"] == "sync_hrv"


def test_connect_happy_path_sets_connected(monkeypatch):
    class _Garmin:
        def __init__(self, _email, _password):
            self.logged_in = False

        def login(self):
            self.logged_in = True

    class _mod:
        Garmin = _Garmin

    import sys

    monkeypatch.setitem(sys.modules, "garminconnect", _mod)

    sync = GarminSync(email="u", password="p")

    assert sync.connect() is True
    assert sync.is_connected is True


def test_connect_auth_failure_logs_startup_failure(caplog, monkeypatch):
    class _Garmin:
        def __init__(self, _email, _password):
            pass

        def login(self):
            raise RuntimeError("auth denied")

    class _mod:
        Garmin = _Garmin

    import sys

    monkeypatch.setitem(sys.modules, "garminconnect", _mod)

    sync = GarminSync(email="u", password="p")

    with caplog.at_level(logging.ERROR):
        assert sync.connect() is False

    record = next(r for r in caplog.records if r.msg == "startup_failure")
    assert record.component == "garmin_sync_connect"
    assert record.error_class == "RuntimeError"
    assert record.detail == "auth denied"


def test_connect_uses_redacted_secret_container_without_duplicate_aliases():
    sync = GarminSync(email="runner@example.com", password="s3cr3t")

    assert sync.email.reveal() == "runner@example.com"
    assert sync.password.reveal() == "s3cr3t"
    assert str(sync.email) == "***"
    assert repr(sync.password) == "'***'"
    assert not hasattr(sync, "_email_secret")
    assert not hasattr(sync, "_password_secret")


def test_connect_missing_credentials_fails_safely():
    sync = GarminSync(email="", password="")

    assert sync.connect() is False
    assert sync.is_connected is False


def test_bg_worker_continues_until_stop_event_is_set(monkeypatch):
    sync = GarminSync(email="u", password="p")
    ticks = []

    def _sync_all():
        ticks.append(time.monotonic())
        if len(ticks) == 2:
            sync._stop_event.set()

    monkeypatch.setattr(sync, "sync_all", _sync_all)

    sync._bg_worker(interval_hours=0)

    assert len(ticks) == 2


def test_stop_background_sync_sets_event_and_joins_thread():
    sync = GarminSync(email="u", password="p")
    started = threading.Event()

    def _waiter():
        started.set()
        sync._stop_event.wait(timeout=10)

    sync._sync_thread = threading.Thread(target=_waiter)
    sync._sync_thread.start()
    assert started.wait(timeout=1)

    sync.stop_background_sync()

    assert sync._stop_event.is_set()
    assert not sync._sync_thread.is_alive()
