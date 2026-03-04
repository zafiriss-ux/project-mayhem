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
