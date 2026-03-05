import json
from datetime import datetime
from unittest.mock import MagicMock

import titan.integrations.weather_api as weather_api
from titan.integrations.weather_api import WeatherAPI


def test_background_worker_continues_until_stop_event_set(monkeypatch):
    api = WeatherAPI(location="Athens,GR")
    calls = {"count": 0}

    def _current():
        calls["count"] += 1
        return {}

    monkeypatch.setattr(api, "get_current_conditions", _current)
    monkeypatch.setattr(api, "get_hourly_forecast", lambda: [])

    wait_calls = {"count": 0, "timeouts": []}

    def _wait(timeout):
        wait_calls["count"] += 1
        wait_calls["timeouts"].append(timeout)
        if wait_calls["count"] == 2:
            api._stop_event.set()
        return api._stop_event.is_set()

    monkeypatch.setattr(api._stop_event, "wait", _wait)

    api._background_update_worker(interval_hours=1)

    assert calls["count"] == 2
    assert wait_calls["count"] == 2
    assert wait_calls["timeouts"] == [3600, 3600]


def test_background_worker_exits_immediately_when_stop_event_set(monkeypatch):
    api = WeatherAPI(location="Athens,GR")
    api._stop_event.set()

    get_current = MagicMock()
    get_hourly = MagicMock()
    monkeypatch.setattr(api, "get_current_conditions", get_current)
    monkeypatch.setattr(api, "get_hourly_forecast", get_hourly)

    api._background_update_worker(interval_hours=1)

    get_current.assert_not_called()
    get_hourly.assert_not_called()


def test_stop_background_updates_sets_event_and_joins_thread():
    api = WeatherAPI(location="Athens,GR")
    api._update_thread = MagicMock()

    api.stop_background_updates()

    assert api._stop_event.is_set()
    api._update_thread.join.assert_called_once_with(timeout=5)


def test_stop_background_updates_emits_shutdown_timeout_when_thread_stays_alive(monkeypatch):
    events = []
    monkeypatch.setattr(weather_api, "_weather_event", lambda action, **fields: events.append((action, fields)))

    api = WeatherAPI(location="Athens,GR")
    api._update_thread = MagicMock()
    api._update_thread.is_alive.return_value = True

    api.stop_background_updates()

    assert any(
        action == "worker_shutdown_timeout"
        and fields.get("level") == weather_api.logging.ERROR
        and fields.get("worker_name") == "WeatherUpdater"
        and fields.get("timeout_seconds") == 5
        and fields.get("still_alive") is True
        for action, fields in events
    )

def test_get_current_conditions_live_marks_data_quality(monkeypatch):
    api = WeatherAPI(location="Athens,GR")
    monkeypatch.setattr(api, "_fetch_open_meteo", lambda: ({"temp_c": 19}, [{"hour": 6}]))

    payload = api.get_current_conditions()

    assert payload["data_quality"] == "live"


def test_get_current_conditions_cache_marks_data_quality(monkeypatch):
    api = WeatherAPI(location="Athens,GR")
    monkeypatch.setattr(api, "_fetch_open_meteo", lambda: ({"temp_c": 19}, [{"hour": 6}]))

    first_payload = api.get_current_conditions()
    cached_payload = api.get_current_conditions()

    assert first_payload["data_quality"] == "live"
    assert cached_payload["data_quality"] == "cached"


def test_get_current_conditions_fallback_emits_degraded_event(monkeypatch, caplog):
    api = WeatherAPI(location="Athens,GR")

    def _raise():
        raise RuntimeError("api_down")

    monkeypatch.setattr(api, "_fetch_open_meteo", _raise)

    with caplog.at_level("WARNING"):
        payload = api.get_current_conditions()

    assert payload["data_quality"] == "synthetic"
    degraded_events = [
        json.loads(record.message)
        for record in caplog.records
        if "weather_degraded_mode_active" in record.message
    ]
    assert degraded_events
    assert degraded_events[0]["error_class"] == "RuntimeError"
    assert degraded_events[0]["detail"] == "api_down"

def test_calculate_dew_point_clamps_humidity_boundaries():
    assert WeatherAPI.calculate_dew_point(temp_c=20, humidity=0) == -37.8
    assert WeatherAPI.calculate_dew_point(temp_c=20, humidity=150) == 20.0


def test_find_optimal_training_windows_respects_fractional_duration(monkeypatch):
    api = WeatherAPI(location="Athens,GR")
    base = datetime(2026, 1, 1, 5, 0, 0)
    forecast = [
        {"timestamp": base.replace(hour=hour).isoformat(), "hour": hour, "dew_point": 10, "temp_c": 15}
        for hour in range(5, 9)
    ]

    class _FixedDateTime:
        @staticmethod
        def now():
            return base

        @staticmethod
        def fromisoformat(value):
            return datetime.fromisoformat(value)

    monkeypatch.setattr("titan.integrations.weather_api.datetime", _FixedDateTime)
    monkeypatch.setattr(api, "get_hourly_forecast", lambda hours=48: forecast)

    windows = api.find_optimal_training_windows(duration_hours=1.5)

    assert len(windows) == 3
    assert all(window["quality"] == "🟩 EXCELLENT" for window in windows)


def test_find_optimal_training_windows_non_positive_duration_returns_empty(monkeypatch):
    api = WeatherAPI(location="Athens,GR")
    called = {"value": False}

    def _forecast(_hours=48):
        called["value"] = True
        return []

    monkeypatch.setattr(api, "get_hourly_forecast", _forecast)

    assert api.find_optimal_training_windows(duration_hours=0) == []
    assert called["value"] is False
