import json
from unittest.mock import MagicMock

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
