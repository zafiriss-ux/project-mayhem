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
    action, fields = events[0]
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
    assert ("weight_synced", {"subsystem": "sync_weight", "count": 1, "days_back": 7, "detail": "Synced 1 weight entries"}) in events


def test_sync_weight_error_emits_failure_class_event(monkeypatch):
    events = []
    monkeypatch.setattr(garmin_sync, "_garmin_event", lambda action, **fields: events.append((action, fields)))

    sync = _connected_sync(_FakeClient(weigh_ins=Exception("Unauthorized credentials")))

    result = sync.sync_weight(days_back=7)

    assert result == []
    auth_fail_events = [(a, f) for a, f in events if a == GARMIN_AUTH_FAIL]
    assert auth_fail_events, f"Expected GARMIN_AUTH_FAIL event; got: {[a for a, _ in events]}"
    action, fields = auth_fail_events[0]
    assert action == GARMIN_AUTH_FAIL
    assert fields["subsystem"] == "sync_weight"


def test_sync_weight_empty_all_day_summaries_does_not_raise(monkeypatch):
    events = []
    monkeypatch.setattr(garmin_sync, "_garmin_event", lambda action, **fields: events.append((action, fields)))

    sync = _connected_sync(
        _FakeClient(
            weigh_ins={
                "dailyWeightSummaries": [
                    {
                        "calendarDate": "2026-03-03",
                        "allDayWeightSummaries": [],
                    }
                ]
            }
        )
    )

    result = sync.sync_weight(days_back=7)

    assert result == []
    assert ("weight_synced", {"subsystem": "sync_weight", "count": 0, "days_back": 7, "detail": "Synced 0 weight entries"}) in events


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
    assert ("sleep_synced", {"subsystem": "sync_sleep", "count": 1, "days_back": 1, "detail": "Synced 1 sleep sessions"}) in events


def test_sync_sleep_error_emits_failure_class_event(monkeypatch):
    events = []
    monkeypatch.setattr(garmin_sync, "_garmin_event", lambda action, **fields: events.append((action, fields)))

    sync = _connected_sync(_FakeClient(sleep=[TimeoutError("timeout while fetching sleep")]))

    result = sync.sync_sleep(days_back=1)

    assert result == []
    failure_events = [event for event in events if event[0] == GARMIN_TIMEOUT]
    assert failure_events
    action, fields = failure_events[0]
    assert action == GARMIN_TIMEOUT
    assert fields["subsystem"] == "sync_sleep"


def test_sync_sleep_skipped_day_logs_and_emits_structured_event(monkeypatch, caplog):
    events = []
    monkeypatch.setattr(garmin_sync, "_garmin_event", lambda action, **fields: events.append((action, fields)))

    sync = _connected_sync(
        _FakeClient(
            sleep=[
                ValueError("bad sleep payload"),
                {
                    "dailySleepDTO": {
                        "sleepTimeSeconds": 25200,
                        "deepSleepSeconds": 3600,
                        "remSleepSeconds": 5400,
                        "sleepScores": {"overall": {"value": 77}},
                    }
                },
            ]
        )
    )

    with caplog.at_level(logging.WARNING):
        result = sync.sync_sleep(days_back=2)

    assert len(result) == 1
    skipped_action, skipped_event = events[0]
    assert skipped_action == GARMIN_PAYLOAD_MALFORMED
    assert skipped_event["failure_class"] == GARMIN_PAYLOAD_MALFORMED
    assert skipped_event["error_class"] == "ValueError"
    assert skipped_event["error_message"] == "bad sleep payload"
    assert skipped_event["date"] in sync.client.requested_sleep_dates
    assert "Skipping sleep day" in caplog.text
    assert "ValueError" in caplog.text
    assert "bad sleep payload" in caplog.text


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


def test_resolve_sync_timeout_seconds_invalid_env_falls_back_to_default(monkeypatch):
    events = []
    monkeypatch.setattr(garmin_sync, "_garmin_event", lambda action, **fields: events.append((action, fields)))
    monkeypatch.setenv("GARMIN_SYNC_TIMEOUT_S", "not-an-int")

    timeout_s = garmin_sync._resolve_sync_timeout_seconds()

    assert timeout_s == garmin_sync._DEFAULT_SYNC_TIMEOUT_S
    assert events == [
        (
            "invalid_sync_timeout",
            {
                "subsystem": "sync_all",
                "configured_timeout": "not-an-int",
                "fallback_timeout_s": garmin_sync._DEFAULT_SYNC_TIMEOUT_S,
                "detail": "GARMIN_SYNC_TIMEOUT_S is not an integer; using default timeout.",
            },
        )
    ]


def test_resolve_sync_timeout_seconds_negative_env_falls_back_to_default(monkeypatch):
    events = []
    monkeypatch.setattr(garmin_sync, "_garmin_event", lambda action, **fields: events.append((action, fields)))
    monkeypatch.setenv("GARMIN_SYNC_TIMEOUT_S", "-5")

    timeout_s = garmin_sync._resolve_sync_timeout_seconds()

    assert timeout_s == garmin_sync._DEFAULT_SYNC_TIMEOUT_S
    assert events == [
        (
            "negative_sync_timeout",
            {
                "subsystem": "sync_all",
                "configured_timeout": -5,
                "fallback_timeout_s": garmin_sync._DEFAULT_SYNC_TIMEOUT_S,
                "detail": "GARMIN_SYNC_TIMEOUT_S is negative; using default timeout.",
            },
        )
    ]


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


def test_connect_saves_token_after_login(monkeypatch, tmp_path):
    """Successful login persists garth token to disk."""
    token_file = tmp_path / ".garth_token"

    class _FakeGarth:
        def dumps(self):
            return "garth_token_data"

    class _Garmin:
        def __init__(self, email=None, password=None):
            self.client = _FakeGarth()

        def login(self):
            pass

    import sys
    monkeypatch.setitem(sys.modules, "garminconnect", type("_mod", (), {"Garmin": _Garmin})())

    sync = GarminSync(email="u", password="p")
    monkeypatch.setattr(sync, "_get_token_path", lambda: token_file)

    assert sync.connect() is True
    assert sync.is_connected is True
    assert token_file.read_text(encoding="utf-8") == "garth_token_data"


def test_connect_loads_saved_token_skips_login(monkeypatch, tmp_path):
    """Existing valid token is loaded from disk; login() is not called."""
    token_file = tmp_path / ".garth_token"
    token_file.write_text("stored_token", encoding="utf-8")

    login_called = []

    class _FakeGarth:
        def loads(self, data):
            pass

    class _Garmin:
        def __init__(self, email=None, password=None):
            self.client = _FakeGarth()

        def login(self):
            login_called.append(True)

        def connectapi(self, path):
            # Simulate successful token verification ping.
            return {}

    import sys
    monkeypatch.setitem(sys.modules, "garminconnect", type("_mod", (), {"Garmin": _Garmin})())

    sync = GarminSync(email="u", password="p")
    monkeypatch.setattr(sync, "_get_token_path", lambda: token_file)

    assert sync.connect() is True
    assert sync.is_connected is True
    assert login_called == []


def test_connect_expired_token_garth_loads_fails_falls_back_to_login(monkeypatch, tmp_path):
    """Expired/invalid token causes garth.loads() to fail; falls back to full login and saves new token."""
    token_file = tmp_path / ".garth_token"
    token_file.write_text("expired_token", encoding="utf-8")

    login_called = []

    class _FakeGarth:
        def loads(self, data):
            raise RuntimeError("GarthHTTPError: token expired")

        def dumps(self):
            return "new_token"

    class _Garmin:
        def __init__(self, email=None, password=None):
            self.client = _FakeGarth()

        def login(self):
            login_called.append(True)

    import sys
    monkeypatch.setitem(sys.modules, "garminconnect", type("_mod", (), {"Garmin": _Garmin})())

    sync = GarminSync(email="u", password="p")
    monkeypatch.setattr(sync, "_get_token_path", lambda: token_file)

    assert sync.connect() is True
    assert sync.is_connected is True
    assert login_called == [True]
    assert token_file.read_text(encoding="utf-8") == "new_token"


def test_connect_stale_token_api_ping_fails_falls_back_to_login(monkeypatch, tmp_path):
    """Token loads from disk successfully but server rejects it (api ping fails).

    This covers the root-cause of the 0/0/0 silent-failure bug: garth.loads()
    succeeds (token deserialises) but the Garmin server returns 401 on the
    first API call.  The verification ping in connect() catches this before any
    sync attempt and falls through to a full login.
    """
    token_file = tmp_path / ".garth_token"
    token_file.write_text("stale_but_parseable_token", encoding="utf-8")

    login_called = []

    class _FakeGarth:
        def loads(self, data):
            pass  # Deserialises without error – token *looks* fine

        def dumps(self):
            return "fresh_token"

    class _Garmin:
        def __init__(self, email=None, password=None):
            self.client = _FakeGarth()

        def login(self):
            login_called.append(True)

        def connectapi(self, path):
            raise RuntimeError("GarthHTTPError: 401 Unauthorized")

    import sys
    monkeypatch.setitem(sys.modules, "garminconnect", type("_mod", (), {"Garmin": _Garmin})())

    sync = GarminSync(email="u", password="p")
    monkeypatch.setattr(sync, "_get_token_path", lambda: token_file)

    assert sync.connect() is True
    assert sync.is_connected is True
    # login() must have been called to obtain a fresh session
    assert login_called == [True]
    # Stale token file must have been replaced with the fresh one
    assert token_file.read_text(encoding="utf-8") == "fresh_token"


def test_invalidate_session_resets_state_and_deletes_token(monkeypatch, tmp_path):
    """_invalidate_session() sets is_connected=False, clears client, deletes token."""
    token_file = tmp_path / ".garth_token"
    token_file.write_text("active_token", encoding="utf-8")

    events = []
    monkeypatch.setattr(garmin_sync, "_garmin_event", lambda action, **fields: events.append((action, fields)))

    sync = GarminSync(email="u", password="p")
    sync.is_connected = True
    sync.client = object()
    monkeypatch.setattr(sync, "_get_token_path", lambda: token_file)

    sync._invalidate_session()

    assert sync.is_connected is False
    assert sync.client is None
    assert not token_file.exists()
    assert any(action == "session_invalidated" for action, _ in events)


def test_sync_activities_auth_fail_invalidates_session(monkeypatch):
    """GARMIN_AUTH_FAIL during activities sync resets is_connected for re-auth."""
    events = []
    monkeypatch.setattr(garmin_sync, "_garmin_event", lambda action, **fields: events.append((action, fields)))

    sync = _connected_sync(_FakeClient(activities=Exception("401 Unauthorized")))
    invalidated = []
    monkeypatch.setattr(sync, "_invalidate_session", lambda: invalidated.append(True))

    result = sync.sync_activities(days_back=1)

    assert result == []
    assert invalidated == [True]


def test_sync_weight_auth_fail_invalidates_session(monkeypatch):
    """GARMIN_AUTH_FAIL during weight sync resets is_connected for re-auth."""
    events = []
    monkeypatch.setattr(garmin_sync, "_garmin_event", lambda action, **fields: events.append((action, fields)))

    sync = _connected_sync(_FakeClient(weigh_ins=Exception("401 forbidden")))
    invalidated = []
    monkeypatch.setattr(sync, "_invalidate_session", lambda: invalidated.append(True))

    result = sync.sync_weight(days_back=7)

    assert result == []
    assert invalidated == [True]


def test_sync_sleep_auth_fail_invalidates_session_and_breaks_loop(monkeypatch):
    """GARMIN_AUTH_FAIL on a sleep day invalidates session and stops iterating further days."""
    events = []
    monkeypatch.setattr(garmin_sync, "_garmin_event", lambda action, **fields: events.append((action, fields)))

    # 3 days requested; first day returns auth fail, remaining days should NOT be fetched
    sync = _connected_sync(_FakeClient(sleep=[Exception("401 Unauthorized"), {}, {}]))
    invalidated = []
    monkeypatch.setattr(sync, "_invalidate_session", lambda: invalidated.append(True))

    result = sync.sync_sleep(days_back=3)

    assert result == []
    assert invalidated == [True]
    # Only one date should have been requested (loop broke after auth fail)
    assert len(sync.client.requested_sleep_dates) == 1


def test_sync_hrv_auth_fail_invalidates_session_and_breaks_loop(monkeypatch):
    """GARMIN_AUTH_FAIL on an HRV day invalidates session and stops iterating further days."""
    events = []
    monkeypatch.setattr(garmin_sync, "_garmin_event", lambda action, **fields: events.append((action, fields)))

    sync = _connected_sync(_FakeClient(hrv=[Exception("401 Unauthorized"), {}, {}]))
    invalidated = []
    monkeypatch.setattr(sync, "_invalidate_session", lambda: invalidated.append(True))

    result = sync.sync_hrv(days_back=3)

    assert result == []
    assert invalidated == [True]
    assert len(sync.client.requested_hrv_dates) == 1


def test_connect_token_save_failure_does_not_break_connect(monkeypatch, tmp_path):
    """If saving the token fails, connect() still returns True."""
    token_file = tmp_path / "readonly_dir" / ".garth_token"  # parent dir does not exist yet

    class _FakeGarth:
        def dumps(self):
            raise OSError("disk full")

    class _Garmin:
        def __init__(self, email=None, password=None):
            self.client = _FakeGarth()

        def login(self):
            pass

    import sys
    monkeypatch.setitem(sys.modules, "garminconnect", type("_mod", (), {"Garmin": _Garmin})())

    sync = GarminSync(email="u", password="p")
    monkeypatch.setattr(sync, "_get_token_path", lambda: token_file)

    # garth.dumps() raises before mkdir, so token file should not exist
    assert sync.connect() is True
    assert sync.is_connected is True


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


# ── last_connect_error ────────────────────────────────────────────────────────

def test_last_connect_error_set_on_missing_credentials(monkeypatch):
    """connect() must set last_connect_error when credentials are absent."""
    monkeypatch.delenv("GARMIN_EMAIL", raising=False)
    monkeypatch.delenv("GARMIN_PASSWORD", raising=False)
    sync = GarminSync(email="", password="")
    sync.connect()
    assert sync.last_connect_error is not None
    assert "missing" in sync.last_connect_error.lower()


def test_last_connect_error_cleared_on_successful_token_load(monkeypatch, tmp_path):
    """connect() must clear last_connect_error when token loads successfully."""
    import sys
    from unittest.mock import MagicMock

    token_file = tmp_path / ".garth_token"
    token_file.write_text('{"token": "ok"}', encoding="utf-8")

    class _FakeGarminInstance:
        class client:
            @staticmethod
            def loads(_data):
                pass

            @staticmethod
            def dumps():
                return '{"token": "ok"}'

        @staticmethod
        def connectapi(_path):
            pass  # token valid — no exception

        @staticmethod
        def login():
            pass

    fake_gc_module = MagicMock()
    fake_gc_module.Garmin.return_value = _FakeGarminInstance()
    monkeypatch.setitem(sys.modules, "garminconnect", fake_gc_module)
    monkeypatch.setattr(
        "titan.integrations.garmin_sync.GarminSync._get_token_path",
        lambda _self: token_file,
    )

    sync = GarminSync(email="a@b.com", password="secret")
    sync.last_connect_error = "previous error"
    result = sync.connect()

    assert result is True
    assert sync.last_connect_error is None


def test_last_connect_error_set_on_login_failure(monkeypatch, tmp_path):
    """connect() must store the exception message when login raises."""
    import sys
    from unittest.mock import MagicMock

    token_file = tmp_path / ".garth_token"  # does not exist

    fake_gc_module = MagicMock()
    fake_gc_module.Garmin.side_effect = RuntimeError("401 Unauthorized: bad password")
    monkeypatch.setitem(sys.modules, "garminconnect", fake_gc_module)
    monkeypatch.setattr(
        "titan.integrations.garmin_sync.GarminSync._get_token_path",
        lambda _self: token_file,
    )

    sync = GarminSync(email="a@b.com", password="wrongpass")
    result = sync.connect()

    assert result is False
    assert sync.last_connect_error is not None
    assert "RuntimeError" in sync.last_connect_error
