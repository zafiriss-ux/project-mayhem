import json
from datetime import datetime
from unittest.mock import MagicMock

import pytest

import titan.integrations.weather_api as weather_api
from titan.integrations.weather_api import WeatherAPI


@pytest.mark.integration
def test_urllib_response_status_and_json_paths():
    response = weather_api._UrllibResponse(body=b'{"ok": true}', status_code=200)
    response.raise_for_status()

    assert response.json() == {"ok": True}
    assert weather_api._UrllibResponse(body=b"", status_code=200).json() == {}

    error_response = weather_api._UrllibResponse(body=b"{}", status_code=404)
    try:
        error_response.raise_for_status()
    except RuntimeError as exc:
        assert str(exc) == "HTTP error status: 404"
    else:
        raise AssertionError("Expected RuntimeError for 4xx status")


@pytest.mark.integration
def test_http_get_uses_requests_when_available(monkeypatch):
    sentinel = object()
    get_mock = MagicMock(return_value=sentinel)

    monkeypatch.setattr(weather_api, "_HAS_REQUESTS", True)
    monkeypatch.setattr(weather_api, "requests", MagicMock(get=get_mock))

    result = weather_api._http_get(
        "https://example.test", params={"a": 1}, timeout=3, verify=False
    )

    assert result is sentinel
    get_mock.assert_called_once_with(
        "https://example.test", params={"a": 1}, timeout=3, verify=False
    )


@pytest.mark.integration
def test_http_get_uses_urllib_fallback_and_verify_toggle(monkeypatch):
    class _FakeUrlopenResponse:
        status = 206

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"path": "urllib"}'

    def _urlopen(url, timeout, context):
        calls.append((url, timeout, context))
        return _FakeUrlopenResponse()

    calls = []
    monkeypatch.setattr(weather_api, "_HAS_REQUESTS", False)
    monkeypatch.setattr(weather_api.ssl, "create_default_context", lambda: "verified")
    monkeypatch.setattr(weather_api.ssl, "_create_unverified_context", lambda: "unverified")
    monkeypatch.setattr(weather_api.urllib.request, "urlopen", _urlopen)

    verified_response = weather_api._http_get(
        "https://example.test/geocode", params={"name": "Athens"}, timeout=8, verify=True
    )
    unverified_response = weather_api._http_get(
        "https://example.test/geocode", params={}, timeout=4, verify=False
    )

    assert calls[0] == ("https://example.test/geocode?name=Athens", 8, "verified")
    assert calls[1] == ("https://example.test/geocode", 4, "unverified")
    assert verified_response.status_code == 206
    assert unverified_response.json() == {"path": "urllib"}


@pytest.mark.integration
def test_parse_location_without_country_returns_empty_country():
    api = WeatherAPI(location="Athens")

    assert api._parse_location() == ("Athens", "")


@pytest.mark.integration
def test_resolve_coordinates_raises_when_no_results(monkeypatch):
    api = WeatherAPI(location="Unknown")

    class _Response:
        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {"results": []}

    monkeypatch.setattr(weather_api, "_http_get", lambda *args, **kwargs: _Response())

    try:
        api._resolve_coordinates()
    except ValueError as exc:
        assert str(exc) == "Location not found: Unknown"
    else:
        raise AssertionError("Expected ValueError when geocoding has no results")


@pytest.mark.integration
def test_start_background_updates_returns_early_if_thread_alive(monkeypatch):
    api = WeatherAPI(location="Athens,GR")
    events = []
    monkeypatch.setattr(weather_api, "_weather_event", lambda action, **fields: events.append((action, fields)))

    existing_thread = MagicMock()
    existing_thread.is_alive.return_value = True
    api._update_thread = existing_thread

    api.start_background_updates(interval_hours=2)

    existing_thread.is_alive.assert_called_once()
    assert events == []


@pytest.mark.integration
def test_background_worker_emits_error_event_when_fetch_fails(monkeypatch):
    api = WeatherAPI(location="Athens,GR")
    events = []
    monkeypatch.setattr(weather_api, "_weather_event", lambda action, **fields: events.append((action, fields)))

    def _current():
        raise RuntimeError("broken-current")

    monkeypatch.setattr(api, "get_current_conditions", _current)
    monkeypatch.setattr(api, "get_hourly_forecast", lambda: [])

    def _wait(timeout):
        api._stop_event.set()
        return True

    monkeypatch.setattr(api._stop_event, "wait", _wait)

    api._background_update_worker(interval_hours=1)

    assert any(
        action == "weather_background_update_error"
        and fields.get("error_class") == "RuntimeError"
        and fields.get("detail") == "broken-current"
        for action, fields in events
    )


@pytest.mark.integration
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


@pytest.mark.integration
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


@pytest.mark.integration
def test_stop_background_updates_sets_event_and_joins_thread():
    api = WeatherAPI(location="Athens,GR")
    api._update_thread = MagicMock()

    api.stop_background_updates()

    assert api._stop_event.is_set()
    api._update_thread.join.assert_called_once_with(timeout=5)


@pytest.mark.integration
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

@pytest.mark.integration
def test_get_current_conditions_live_marks_data_quality(monkeypatch):
    api = WeatherAPI(location="Athens,GR")
    monkeypatch.setattr(api, "_fetch_open_meteo", lambda: ({"temp_c": 19}, [{"hour": 6}]))

    payload = api.get_current_conditions()

    assert payload["data_quality"] == "live"
    assert payload["weather_confidence"] == "LIVE"


@pytest.mark.integration
def test_get_current_conditions_cache_marks_data_quality(monkeypatch):
    api = WeatherAPI(location="Athens,GR")
    monkeypatch.setattr(api, "_fetch_open_meteo", lambda: ({"temp_c": 19}, [{"hour": 6}]))

    first_payload = api.get_current_conditions()
    cached_payload = api.get_current_conditions()

    assert first_payload["data_quality"] == "live"
    assert cached_payload["data_quality"] == "cached"


@pytest.mark.integration
def test_get_current_conditions_fallback_emits_degraded_event(monkeypatch, caplog):
    api = WeatherAPI(location="Athens,GR")

    def _raise():
        raise RuntimeError("api_down")

    monkeypatch.setattr(api, "_fetch_open_meteo", _raise)

    with caplog.at_level("WARNING"):
        payload = api.get_current_conditions()

    assert payload["data_quality"] == "synthetic"
    assert payload["weather_confidence"] == "SYNTHETIC"
    degraded_events = [
        json.loads(record.message)
        for record in caplog.records
        if "weather_degraded_mode_active" in record.message
    ]
    fallback_events = [
        json.loads(record.message)
        for record in caplog.records
        if "weather_synthetic_fallback_activated" in record.message
    ]
    assert degraded_events
    assert fallback_events
    assert degraded_events[0]["error_class"] == "RuntimeError"
    assert degraded_events[0]["detail"] == "api_down"
    assert fallback_events[0]["location"] == "Athens,GR"

@pytest.mark.integration
def test_calculate_dew_point_clamps_humidity_boundaries():
    assert WeatherAPI.calculate_dew_point(temp_c=20, humidity=0) == -37.8
    assert WeatherAPI.calculate_dew_point(temp_c=20, humidity=150) == 20.0


@pytest.mark.integration
def test_find_optimal_training_windows_respects_fractional_duration(monkeypatch):
    api = WeatherAPI(location="Athens,GR")
    base = datetime(2026, 1, 1, 5, 0, 0)
    forecast = [
        {"timestamp": base.replace(hour=hour).isoformat(), "hour": hour, "dew_point": 10, "temp_c": 15}
        for hour in range(5, 9)
    ]

    class _FixedDateTime:
        @staticmethod
        def now(tz=None):
            return base

        @staticmethod
        def fromisoformat(value):
            return datetime.fromisoformat(value)

    monkeypatch.setattr("titan.integrations.weather_api.datetime", _FixedDateTime)
    monkeypatch.setattr(api, "get_hourly_forecast", lambda hours=48: forecast)

    windows = api.find_optimal_training_windows(duration_hours=1.5)

    assert len(windows) == 3
    assert all(window["quality"] == "🟩 EXCELLENT" for window in windows)


@pytest.mark.integration
def test_find_optimal_training_windows_non_positive_duration_returns_empty(monkeypatch):
    api = WeatherAPI(location="Athens,GR")
    called = {"value": False}

    def _forecast(_hours=48):
        called["value"] = True
        return []

    monkeypatch.setattr(api, "get_hourly_forecast", _forecast)

    assert api.find_optimal_training_windows(duration_hours=0) == []
    assert called["value"] is False


@pytest.mark.integration
def test_get_current_conditions_live_includes_trusted_data_trust(monkeypatch):
    api = WeatherAPI(location="Athens,GR")
    monkeypatch.setattr(api, "_fetch_open_meteo", lambda: ({"temp_c": 19}, [{"hour": 6}]))

    payload = api.get_current_conditions()

    assert payload["data_trust"]["source"] == "weather"
    assert payload["data_trust"]["trust_level"] == "TRUSTED"


@pytest.mark.integration
def test_get_current_conditions_fallback_includes_suspect_data_trust(monkeypatch):
    api = WeatherAPI(location="Athens,GR")
    monkeypatch.setattr(api, "_fetch_open_meteo", lambda: (_ for _ in ()).throw(RuntimeError("offline")))

    payload = api.get_current_conditions()

    assert payload["data_trust"]["trust_level"] == "SUSPECT"
    assert "weather_synthetic_fallback" in payload["data_trust"]["reasons"]


@pytest.mark.integration
def test_create_synthetic_fallback_uses_location_profile(monkeypatch):
    api = WeatherAPI(location="Helsinki,FI")

    class _FixedDateTime:
        @staticmethod
        def now(tz=None):
            return datetime(2026, 1, 10, 6, 0, 0)

    monkeypatch.setattr(weather_api, "datetime", _FixedDateTime)

    payload = api._create_synthetic_fallback()

    assert payload["temp_c"] == 5.0
    assert payload["humidity"] == 74
    assert payload["weather_confidence"] == "SYNTHETIC"


@pytest.mark.integration
def test_get_hourly_forecast_synthetic_sets_weather_confidence(monkeypatch):
    api = WeatherAPI(location="Sydney,AU")
    monkeypatch.setattr(api, "_fetch_open_meteo", lambda: (_ for _ in ()).throw(RuntimeError("offline")))

    forecast = api.get_hourly_forecast(hours=2)

    assert len(forecast) == 2
    assert all(item["data_quality"] == "synthetic" for item in forecast)
    assert all(item["weather_confidence"] == "SYNTHETIC" for item in forecast)


@pytest.mark.integration
def test_classify_heat_stress_uses_threshold_source_of_truth(monkeypatch):
    monkeypatch.setattr(weather_api, "WEATHER_DEW_POINT_EXTREME_MIN_C", 25.0)
    monkeypatch.setattr(weather_api, "WEATHER_DEW_POINT_OPPRESSIVE_MIN_C", 22.0)
    monkeypatch.setattr(weather_api, "WEATHER_DEW_POINT_UNCOMFORTABLE_MIN_C", 19.0)
    monkeypatch.setattr(weather_api, "WEATHER_DEW_POINT_STICKY_MIN_C", 16.0)
    monkeypatch.setattr(weather_api, "WEATHER_DEW_POINT_COMFORTABLE_MIN_C", 13.0)
    monkeypatch.setattr(weather_api, "WEATHER_DEW_POINT_PLEASANT_MIN_C", 9.0)

    status, _ = WeatherAPI.classify_heat_stress(25.5)
    assert status == "🔥 EXTREME"

    boundary_status, _ = WeatherAPI.classify_heat_stress(25.0)
    assert boundary_status == "🟥 OPPRESSIVE"


@pytest.mark.integration
def test_classify_heat_stress_boundary_below_pleasant_is_dry_cold():
    status, recommendation = WeatherAPI.classify_heat_stress(8.0)

    assert status == "🟪 DRY/COLD"
    assert recommendation == "Good for fast running"
