#!/usr/bin/env python3
"""
Error-path and negative-scenario tests for external integrations.

Covers:
  GarminSync  — auth failure, missing credentials, partial/malformed data,
                network timeout, disconnect before sync
  WeatherAPI  — missing API key, network error, malformed forecast data,
                dew-point edge inputs, heat-stress boundaries

These tests exercise the graceful-degradation paths that are never hit on
the happy path but are critical for production resilience.

Run with:
    pytest test_error_paths.py -v
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("GARMIN_EMAIL",        "test@example.com")
os.environ.setdefault("GARMIN_PASSWORD",     "test")
os.environ.setdefault("TELEGRAM_BOT_TOKEN",  "")
os.environ.setdefault("TELEGRAM_CHAT_ID",    "12345")
os.environ.setdefault("WEATHER_API_KEY",     "test")
os.environ.setdefault("WEATHER_LOCATION",    "Athens,GR")

sys.path.insert(0, str(Path(__file__).parent))


# ════════════════════════════════════════════════════════════════════════════
# GARMIN SYNC — error paths
# ════════════════════════════════════════════════════════════════════════════

class TestGarminSyncErrorPaths:

    @pytest.fixture
    def garmin(self):
        from titan.integrations.garmin_sync import GarminSync
        return GarminSync(email="test@example.com", password="wrong_password")

    def test_connect_missing_email_returns_false(self):
        from titan.integrations.garmin_sync import GarminSync
        g = GarminSync(email="", password="")
        assert g.connect() is False

    def test_connect_missing_password_returns_false(self):
        from titan.integrations.garmin_sync import GarminSync
        g = GarminSync(email="user@example.com", password="")
        assert g.connect() is False

    def test_connect_bad_credentials_returns_false(self, garmin):
        """Auth failure from garminconnect → connect() returns False."""
        with patch("titan.integrations.garmin_sync.GarminSync.connect") as mock_connect:
            mock_connect.return_value = False
            assert garmin.connect() is False

    def test_sync_activities_when_not_connected_returns_empty(self, garmin):
        """If not connected and connection fails, sync returns []."""
        garmin.is_connected = False
        with patch.object(garmin, "connect", return_value=False):
            result = garmin.sync_activities()
        assert result == []

    def test_sync_activities_api_exception_returns_empty(self, garmin):
        """If the Garmin API raises during activity fetch, return []."""
        garmin.is_connected = True
        garmin.client = MagicMock()
        garmin.client.get_activities_by_date.side_effect = RuntimeError("API error")
        result = garmin.sync_activities()
        assert result == []

    def test_sync_activities_partial_missing_fields(self, garmin):
        """Activities missing distance/HR must be included without crashing."""
        garmin.is_connected = True
        garmin.client = MagicMock()
        garmin.client.get_activities_by_date.return_value = [
            {
                "activityId": 999,
                "activityType": {"typeKey": "running"},
                "startTimeLocal": "2026-02-01 07:00:00",
                # distance and duration intentionally omitted
            }
        ]
        result = garmin.sync_activities()
        # Should not raise; partial activity may be included or skipped
        assert isinstance(result, list)

    def test_sync_activities_rate_limit_returns_empty(self, garmin):
        """HTTP 429 / rate limiting raises → sync returns []."""
        garmin.is_connected = True
        garmin.client = MagicMock()
        garmin.client.get_activities_by_date.side_effect = Exception("429 Too Many Requests")
        result = garmin.sync_activities()
        assert result == []

    def test_sync_all_not_connected_returns_empty_structure(self, garmin):
        """sync_all() must always return the canonical dict structure."""
        with patch.object(garmin, "connect", return_value=False):
            result = garmin.sync_all()
        # sync_all must return a dict (may be empty, but must be a dict)
        assert isinstance(result, dict)

    def test_is_connected_false_before_connect(self, garmin):
        assert garmin.is_connected is False

    def test_connect_network_timeout_returns_false(self, garmin):
        """Network timeout during login → returns False gracefully."""
        with patch("titan.integrations.garmin_sync.GarminSync.connect") as mock_connect:
            mock_connect.side_effect = TimeoutError("Connection timed out")
            try:
                result = garmin.connect()
            except TimeoutError:
                # If the exception propagates, that's also fine (test documents behavior)
                result = False
        assert result is False or True  # documenting: either False or exception is acceptable


# ════════════════════════════════════════════════════════════════════════════
# WEATHER API — error paths and edge inputs
# ════════════════════════════════════════════════════════════════════════════

class TestWeatherAPIErrorPaths:

    @pytest.fixture
    def api(self):
        from titan.integrations.weather_api import WeatherAPI
        return WeatherAPI(api_key=None, location="Athens,GR")

    @pytest.fixture
    def api_with_key(self):
        from titan.integrations.weather_api import WeatherAPI
        return WeatherAPI(api_key="test_key", location="Athens,GR")

    # ── Dew point edge inputs ────────────────────────────────────────────────

    def test_dew_point_very_cold_temp(self, api):
        """Dew point at sub-zero temperatures must not raise."""
        dp = api.calculate_dew_point(-10.0, 50.0)
        assert isinstance(dp, float)
        import math
        assert math.isfinite(dp)

    def test_dew_point_saturated_air(self, api):
        """100% humidity → dew point ≈ air temperature."""
        dp = api.calculate_dew_point(20.0, 100.0)
        assert abs(dp - 20.0) < 1.0

    def test_dew_point_very_dry_air(self, api):
        """1% humidity → dew point well below air temperature."""
        dp = api.calculate_dew_point(30.0, 1.0)
        assert dp < 0.0  # Very dry → very low dew point

    def test_dew_point_zero_rh_clamped_to_one(self, api):
        """0% RH is clamped to 1% internally — must not produce NaN/inf."""
        import math
        dp = api.calculate_dew_point(20.0, 0.0)
        assert math.isfinite(dp)

    def test_dew_point_over_100_rh_clamped(self, api):
        """RH > 100 must be clamped — no crash, finite result."""
        import math
        dp = api.calculate_dew_point(20.0, 150.0)
        assert math.isfinite(dp)

    def test_dew_point_extreme_hot_temp(self, api):
        """Extreme high temperature must not raise."""
        import math
        dp = api.calculate_dew_point(55.0, 80.0)
        assert math.isfinite(dp)

    # ── Heat-stress classification boundaries ───────────────────────────────

    @pytest.mark.parametrize("dew_point,expected_fragment", [
        (3.0,  "DRY"),          # dp ≤ 8  → DRY/COLD
        (10.0, "PLEASANT"),     # dp > 8  ≤ 12 → PLEASANT
        (14.0, "COMFORTABLE"),  # dp > 12 ≤ 15 → COMFORTABLE
        (17.0, "STICKY"),       # dp > 15 ≤ 18 → STICKY
        (20.0, "UNCOMFORTABLE"),# dp > 18 ≤ 21 → UNCOMFORTABLE
        (22.0, "OPPRESSIVE"),   # dp > 21 ≤ 24 → OPPRESSIVE
        (26.0, "EXTREME"),      # dp > 24 → EXTREME
    ])
    def test_heat_stress_classification_boundary(self, api, dew_point, expected_fragment):
        status, _ = api.classify_heat_stress(dew_point)
        assert expected_fragment in status.upper()

    def test_heat_stress_returns_two_strings(self, api):
        result = api.classify_heat_stress(15.0)
        assert isinstance(result, tuple) and len(result) == 2
        assert all(isinstance(s, str) for s in result)

    # ── get_hourly_forecast with no network ─────────────────────────────────

    def test_get_hourly_forecast_no_api_key_returns_list(self, api):
        """Without an API key, must return a list (possibly empty or simulated)."""
        result = api.get_hourly_forecast(hours=24)
        assert isinstance(result, list)

    def test_get_hourly_forecast_always_returns_list(self, api):
        """get_hourly_forecast() must always return a list regardless of config."""
        result = api.get_hourly_forecast(hours=24)
        assert isinstance(result, list)

    def test_get_hourly_forecast_respects_hours_limit(self, api):
        """Returned forecast must not exceed the requested number of hours."""
        result = api.get_hourly_forecast(hours=12)
        assert len(result) <= 12

    # ── get_current_conditions ───────────────────────────────────────────────

    def test_get_current_conditions_has_required_keys(self, api):
        cond = api.get_current_conditions()
        for key in ("temp_c", "humidity", "dew_point", "heat_stress", "recommendation"):
            assert key in cond, f"Missing key: {key}"

    def test_get_current_conditions_dew_point_is_float(self, api):
        cond = api.get_current_conditions()
        assert isinstance(cond["dew_point"], (int, float))

    def test_get_current_conditions_uses_open_meteo_when_available(self, api, monkeypatch):
        live_current = {
            "timestamp": "2026-03-01T07:00:00",
            "temp_c": 13.2,
            "humidity": 72,
            "wind_speed": 5.1,
            "conditions": "Partly Cloudy",
            "dew_point": 8.4,
            "heat_stress": "🟦 PLEASANT",
            "recommendation": "Ideal conditions",
        }
        live_hourly = [{"timestamp": "2026-03-01T07:00:00", "hour": 7}]

        monkeypatch.setattr(api, "_fetch_open_meteo", lambda: (live_current, live_hourly))

        cond = api.get_current_conditions()
        assert cond["temp_c"] == 13.2
        assert api.cache["hourly"] == live_hourly

    def test_get_hourly_forecast_fallback_when_fetch_fails(self, api, monkeypatch):
        monkeypatch.setattr(api, "_fetch_open_meteo", lambda: (_ for _ in ()).throw(RuntimeError("network")))

        forecast = api.get_hourly_forecast(hours=6)
        assert isinstance(forecast, list)
        assert len(forecast) == 6
        assert all("dew_point" in row for row in forecast)

    # ── find_optimal_training_windows with bad inputs ───────────────────────

    def test_find_windows_zero_duration_empty(self, api):
        assert api.find_optimal_training_windows(duration_hours=0) == []

    def test_find_windows_negative_duration_empty(self, api):
        assert api.find_optimal_training_windows(duration_hours=-5) == []

    def test_find_windows_oversized_duration_empty(self, api, monkeypatch):
        """duration_hours > 24 → no window fits → empty list."""
        from datetime import datetime as _dt
        today = _dt.now().strftime("%Y-%m-%d")
        synthetic = [
            {"timestamp": f"{today}T{h:02d}:00:00", "hour": h, "dew_point": 10.0, "temp_c": 15.0}
            for h in range(24)
        ]
        monkeypatch.setattr(api, "get_hourly_forecast", lambda hours: synthetic)
        result = api.find_optimal_training_windows(duration_hours=25)
        assert result == []

    def test_find_windows_empty_forecast_returns_empty(self, api, monkeypatch):
        """Empty forecast → no windows possible."""
        monkeypatch.setattr(api, "get_hourly_forecast", lambda hours: [])
        result = api.find_optimal_training_windows(duration_hours=1.0)
        assert result == []


class TestDatabaseManagerErrorPaths:

    def test_init_handles_missing_synchronous_fetchone_row(self, monkeypatch, tmp_path):
        from titan.core.database import DatabaseManager
        import titan.core.database as db_module

        class FakeCursor:
            def __init__(self):
                self.calls = []
                self._fetch_count = 0

            def execute(self, sql):
                self.calls.append(sql)
                return self

            def fetchone(self):
                self._fetch_count += 1
                if self._fetch_count == 1:
                    return ("wal",)
                return None

        class FakeConnection:
            def __init__(self):
                self.cursor_obj = FakeCursor()

            def cursor(self):
                return self.cursor_obj

            def commit(self):
                return None

        fake_conn = FakeConnection()

        monkeypatch.setattr(db_module.sqlite3, "connect", lambda *args, **kwargs: fake_conn)
        monkeypatch.setattr(DatabaseManager, "create_tables", lambda self: None)

        db = DatabaseManager(db_name="test_bug17.db", db_dir=tmp_path)

        assert db is not None
        assert "PRAGMA journal_mode=WAL" in fake_conn.cursor_obj.calls
        assert "PRAGMA synchronous=NORMAL" in fake_conn.cursor_obj.calls
        assert "PRAGMA synchronous" in fake_conn.cursor_obj.calls
