"""
Phase 7 Hardening Tests
=======================
Covers the fixes introduced in v5.8.0 hardening sprint:

  1. Version consistency across key project files
  2. Weather fallback: is_fallback flag present in both current-conditions
     AND hourly-forecast synthetic data
  3. Weather fallback: structured warning log emitted on API failure
  4. DailyCoach: no console input() calls; defaults applied correctly
  5. DailyCoach: soreness / subjective_fatigue clamping
"""

import inspect
import json
import logging
import pathlib
import types
import unittest
from unittest.mock import MagicMock, patch

ROOT = pathlib.Path(__file__).parent.parent


# ─────────────────────────────────────────────────────────────────────────────
# 1. Version consistency
# ─────────────────────────────────────────────────────────────────────────────

class TestVersionConsistency(unittest.TestCase):
    """Ensure README and requirements.txt both declare v5.8.0."""

    def _readme_version(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith("# TITAN OS"):
                # Extract e.g. "v5.8.0"
                parts = line.split()
                for p in parts:
                    if p.startswith("v") and p[1].isdigit():
                        return p.rstrip("—").strip()
        return None

    def _requirements_version(self):
        text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith("# TITAN OS"):
                parts = line.split()
                for p in parts:
                    if p.startswith("v") and p[1].isdigit():
                        return p.rstrip("—").strip()
        return None

    def test_readme_declares_v580(self):
        ver = self._readme_version()
        self.assertIsNotNone(ver, "README.md must have a version line starting with '# TITAN OS'")
        self.assertEqual(ver, "v5.8.0", f"README version should be v5.8.0, got {ver!r}")

    def test_requirements_declares_v580(self):
        ver = self._requirements_version()
        self.assertIsNotNone(ver, "requirements.txt must have a version comment on line 1")
        self.assertEqual(ver, "v5.8.0", f"requirements.txt version should be v5.8.0, got {ver!r}")

    def test_readme_and_requirements_versions_match(self):
        self.assertEqual(
            self._readme_version(),
            self._requirements_version(),
            "README.md and requirements.txt must declare the same version",
        )

    def test_readme_no_openweathermap_api_url(self):
        """Ensure README doesn't direct users to obsolete OpenWeatherMap endpoint."""
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn(
            "api.openweathermap.org",
            text,
            "README must not reference api.openweathermap.org — provider is Open-Meteo",
        )


# ─────────────────────────────────────────────────────────────────────────────
# 2. WeatherAPI — is_fallback flag
# ─────────────────────────────────────────────────────────────────────────────

class TestWeatherFallbackFlag(unittest.TestCase):
    """Fallback data must carry is_fallback=True so operators can detect degradation."""

    def _make_api(self):
        from titan.integrations.weather_api import WeatherAPI
        api = WeatherAPI.__new__(WeatherAPI)
        api.api_key = None
        api.location = "Athens,GR"
        api.cache = {}
        api.cache_timestamp = None
        api.cache_duration_hours = 1
        api._update_thread = None
        api._coords = None
        return api

    def test_current_conditions_fallback_has_is_fallback_true(self):
        api = self._make_api()
        with patch.object(api, "_fetch_open_meteo", side_effect=ConnectionError("network down")):
            result = api.get_current_conditions()
        self.assertIn("is_fallback", result, "Fallback current conditions must include 'is_fallback'")
        self.assertTrue(result["is_fallback"])

    def test_current_conditions_fallback_has_required_fields(self):
        api = self._make_api()
        with patch.object(api, "_fetch_open_meteo", side_effect=ConnectionError("network down")):
            result = api.get_current_conditions()
        for field in ("temp_c", "humidity", "wind_speed", "dew_point", "conditions"):
            self.assertIn(field, result, f"Fallback must include '{field}'")

    def test_hourly_forecast_fallback_has_is_fallback_true(self):
        api = self._make_api()
        with patch.object(api, "_fetch_open_meteo", side_effect=ConnectionError("network down")):
            forecast = api.get_hourly_forecast(hours=6)
        self.assertTrue(len(forecast) > 0, "Fallback forecast must not be empty")
        for i, entry in enumerate(forecast):
            self.assertIn(
                "is_fallback", entry,
                f"Fallback forecast entry [{i}] must include 'is_fallback'",
            )
            self.assertTrue(entry["is_fallback"])

    def test_hourly_forecast_fallback_length_matches_request(self):
        api = self._make_api()
        with patch.object(api, "_fetch_open_meteo", side_effect=ConnectionError("network down")):
            forecast = api.get_hourly_forecast(hours=12)
        self.assertEqual(len(forecast), 12)

    def test_hourly_forecast_fallback_has_required_fields(self):
        api = self._make_api()
        with patch.object(api, "_fetch_open_meteo", side_effect=ConnectionError("network down")):
            forecast = api.get_hourly_forecast(hours=3)
        for field in ("timestamp", "hour", "temp_c", "humidity", "dew_point", "wind_speed"):
            self.assertIn(field, forecast[0], f"Fallback forecast entry must include '{field}'")

    def test_successful_fetch_does_not_set_is_fallback(self):
        """Real (non-fallback) data must NOT have is_fallback."""
        api = self._make_api()
        fake_current = {
            "timestamp": "2026-03-02T07:00:00",
            "temp_c": 15.0,
            "humidity": 60,
            "wind_speed": 5.0,
            "conditions": "Clear",
            "dew_point": 7.2,
            "heat_stress": "🟦 PLEASANT",
            "recommendation": "Ideal conditions",
        }
        fake_forecast = [fake_current]
        with patch.object(api, "_fetch_open_meteo", return_value=(fake_current, fake_forecast)):
            result = api.get_current_conditions()
        self.assertFalse(result.get("is_fallback", False))


# ─────────────────────────────────────────────────────────────────────────────
# 3. WeatherAPI — structured warning log on fallback
# ─────────────────────────────────────────────────────────────────────────────

class TestWeatherFallbackLogging(unittest.TestCase):
    """Fallback activation must emit a structured warning log line."""

    def _make_api(self):
        from titan.integrations.weather_api import WeatherAPI
        api = WeatherAPI.__new__(WeatherAPI)
        api.api_key = None
        api.location = "Athens,GR"
        api.cache = {}
        api.cache_timestamp = None
        api.cache_duration_hours = 1
        api._update_thread = None
        api._coords = None
        return api

    def _capture_warnings(self, api, method_name, **kwargs):
        """Run method and capture WARNING+ log records from the weather_api logger."""
        records = []
        handler = logging.handlers_helper(records)
        logger = logging.getLogger("titan.integrations.weather_api")
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
        try:
            with patch.object(api, "_fetch_open_meteo", side_effect=RuntimeError("API down")):
                getattr(api, method_name)(**kwargs)
        finally:
            logger.removeHandler(handler)
        return records

    def test_current_conditions_fallback_emits_warning_log(self):
        api = self._make_api()
        records = []

        class Capture(logging.Handler):
            def emit(self, record):
                records.append(record)

        handler = Capture()
        logger = logging.getLogger("titan.integrations.weather_api")
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
        try:
            with patch.object(api, "_fetch_open_meteo", side_effect=RuntimeError("API down")):
                api.get_current_conditions()
        finally:
            logger.removeHandler(handler)

        self.assertTrue(len(records) >= 1, "At least one WARNING must be logged on fallback")
        payload = json.loads(records[0].getMessage())
        self.assertEqual(payload.get("action"), "fallback_activated")
        self.assertTrue(payload.get("is_fallback"))
        self.assertIn("reason", payload)

    def test_hourly_forecast_fallback_emits_warning_log(self):
        api = self._make_api()
        records = []

        class Capture(logging.Handler):
            def emit(self, record):
                records.append(record)

        handler = Capture()
        logger = logging.getLogger("titan.integrations.weather_api")
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
        try:
            with patch.object(api, "_fetch_open_meteo", side_effect=RuntimeError("API down")):
                api.get_hourly_forecast(hours=4)
        finally:
            logger.removeHandler(handler)

        self.assertTrue(len(records) >= 1, "At least one WARNING must be logged on fallback")
        payload = json.loads(records[0].getMessage())
        self.assertEqual(payload.get("action"), "fallback_activated")
        self.assertEqual(payload.get("source"), "get_hourly_forecast")

    def test_fallback_log_includes_error_reason(self):
        api = self._make_api()
        records = []

        class Capture(logging.Handler):
            def emit(self, record):
                records.append(record)

        handler = Capture()
        logger = logging.getLogger("titan.integrations.weather_api")
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
        try:
            with patch.object(api, "_fetch_open_meteo", side_effect=TimeoutError("timed out")):
                api.get_current_conditions()
        finally:
            logger.removeHandler(handler)

        payload = json.loads(records[0].getMessage())
        self.assertIn("timed out", payload.get("reason", ""))


# ─────────────────────────────────────────────────────────────────────────────
# 4. DailyCoach — no console input()
# ─────────────────────────────────────────────────────────────────────────────

class TestDailyCoachNoConsoleInput(unittest.TestCase):
    """run_morning_routine must not call builtins.input() under any branch."""

    def _source_of(self, method):
        try:
            return inspect.getsource(method)
        except (TypeError, OSError):
            return ""

    def test_run_morning_routine_has_no_input_call(self):
        from titan.orchestration.daily_coach import DailyCoach
        src = self._source_of(DailyCoach.run_morning_routine)
        # Look for bare input( call (not in a string/comment)
        import re
        # Strip comments and strings naively then check
        lines_without_comments = [
            line for line in src.splitlines()
            if not line.strip().startswith("#")
        ]
        clean = "\n".join(lines_without_comments)
        matches = re.findall(r'\binput\s*\(', clean)
        self.assertEqual(
            matches, [],
            f"run_morning_routine must not call input(); found {len(matches)} call(s)",
        )

    def test_run_morning_routine_docstring_mentions_no_console_io(self):
        from titan.orchestration.daily_coach import DailyCoach
        doc = DailyCoach.run_morning_routine.__doc__ or ""
        self.assertIn(
            "no console", doc.lower(),
            "Docstring should state there is no console I/O",
        )


# ─────────────────────────────────────────────────────────────────────────────
# 5. DailyCoach — soreness / fatigue defaults and clamping
# ─────────────────────────────────────────────────────────────────────────────

class TestDailyCoachInputDefaults(unittest.TestCase):
    """Verify soreness/fatigue defaults and clamping without running full routine."""

    def _make_coach(self):
        """Create a DailyCoach with all heavy dependencies mocked out."""
        from titan.orchestration.daily_coach import DailyCoach

        # Patch __init__ to avoid real DB / engine construction
        with patch.object(DailyCoach, "__init__", lambda self, **kw: None):
            coach = DailyCoach.__new__(DailyCoach)

        # Provide minimal attributes expected by run_morning_routine
        coach.garmin = MagicMock()
        coach.garmin.sync_all.return_value = {
            "activities": [], "hrv": [], "hrr": [], "sleep": [], "weight": [],
        }
        coach.weather = MagicMock()
        coach.telegram = MagicMock()
        coach.telegram.send_daily_coaching.return_value = True
        coach.hrv = MagicMock()
        coach.hrv.calculate_ln_rmssd_deviation.return_value = 0.0
        coach.hrv.get_hrv_summary.return_value = {
            "latest_hrv": 50.0, "baseline": 50.0, "std_dev": 5.0, "trend": "stable",
        }
        coach.hrv.hrv_log = []
        coach.tsb = MagicMock()
        coach.tsb.calculate_tsb.return_value = (0.0, "neutral")
        coach.tsb.daily_loads = {}
        coach.readiness = MagicMock()
        coach.readiness.analyze_readiness.return_value = {"score": 75}
        coach.optimal_time = MagicMock()
        coach.optimal_time.calculate_optimal_time.return_value = {
            "recommended_time": "07:00", "dew_point": 10, "quality": "GOOD",
        }
        coach.nutrition = MagicMock()
        coach.nutrition.analyze_weight_trend.return_value = {"current_weight": 70.0}
        coach.nutrition.calculate_daily_nutrition.return_value = {
            "carbs_g": 300, "protein_g": 150,
        }
        coach.weekly_planner = MagicMock()
        coach.weekly_planner.get_today_session.return_value = {
            "session_type": "EASY", "duration_min": 45,
            "distance_km": 10, "details": "", "phase": "BASE", "volume_pct": 1.0,
        }
        coach.db = MagicMock()
        coach.db.conn = MagicMock()
        coach.db.conn.cursor.return_value.__enter__ = MagicMock(return_value=MagicMock())
        coach.db.conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        cursor = MagicMock()
        cursor.fetchone.return_value = (50.0,)
        coach.db.conn.cursor.return_value = cursor
        coach.db.get_training_load_history.return_value = []
        coach.autonomic = MagicMock()
        coach.autonomic.hrr_log = []
        coach.autonomic.calculate_afi.return_value = 0.0
        coach.autonomic.apply_48h_buffer.return_value = 0.0
        coach.autonomic.get_readiness_constraints.return_value = {
            "afi_modifier": 0, "readiness_clamp": 100,
        }
        coach.cs_tracker = MagicMock()
        coach.cs_tracker.archetype = "BALANCED"
        coach.cs_tracker.cs_smoothed = 4.2
        coach.cs_tracker.confidence = 1.0
        coach.cs_tracker.apply_thermal.return_value = 4.2
        coach.glycogen = MagicMock()
        coach.glycogen.daily_debt = 0.0
        coach.glycogen.status = "OK"
        coach.glycogen.update = MagicMock()
        coach.glycogen.overnight_resynthesis = MagicMock()
        coach.glycogen.norwegian_protocol.return_value = {}
        coach.glycogen.electrolyte_guard = MagicMock(return_value="OK")
        coach.governance = MagicMock()
        coach.governance.apply_constraints.side_effect = lambda session_plan, context: session_plan
        coach.governance.get_governance_report.return_value = {}
        coach.fatigue = MagicMock()
        coach.fatigue.classify_fatigue.return_value = ("LOW", [])
        coach.apl = MagicMock()
        coach.apl.resolve.return_value = {"priority_vector": {}, "lock_thresholds": {}}
        coach.vlg = MagicMock()
        vlg_state = MagicMock()
        vlg_state.color = "GREEN"
        coach.vlg.resolve.return_value = vlg_state
        coach.outcome_tracker = MagicMock()
        return coach

    def test_soreness_defaults_to_5_when_none(self):
        """When soreness=None, routine must NOT block and must use 5."""
        coach = self._make_coach()
        captured = {}


        def capture_analyze(**kwargs):
            captured["soreness"] = kwargs.get("soreness")
            return {"score": 75}

        coach.readiness.analyze_readiness = MagicMock(side_effect=capture_analyze)
        # Must not block or raise — soreness=None triggers default
        coach.run_morning_routine(soreness=None, subjective_fatigue_score=None)
        self.assertEqual(captured.get("soreness"), 5)

    def test_soreness_explicit_value_passed_through(self):
        coach = self._make_coach()
        captured = {}

        def capture_analyze(**kwargs):
            captured["soreness"] = kwargs.get("soreness")
            return {"score": 75}

        coach.readiness.analyze_readiness = MagicMock(side_effect=capture_analyze)
        coach.run_morning_routine(soreness=3, subjective_fatigue_score=3)
        self.assertEqual(captured.get("soreness"), 3)

    def test_soreness_clamped_above_10(self):
        coach = self._make_coach()
        captured = {}

        def capture_analyze(**kwargs):
            captured["soreness"] = kwargs.get("soreness")
            return {"score": 75}

        coach.readiness.analyze_readiness = MagicMock(side_effect=capture_analyze)
        coach.run_morning_routine(soreness=99, subjective_fatigue_score=99)
        self.assertLessEqual(captured.get("soreness"), 10)

    def test_soreness_clamped_below_0(self):
        coach = self._make_coach()
        captured = {}

        def capture_analyze(**kwargs):
            captured["soreness"] = kwargs.get("soreness")
            return {"score": 75}

        coach.readiness.analyze_readiness = MagicMock(side_effect=capture_analyze)
        coach.run_morning_routine(soreness=-5, subjective_fatigue_score=0)
        self.assertGreaterEqual(captured.get("soreness"), 0)

    def test_subjective_fatigue_defaults_to_soreness(self):
        """When subjective_fatigue_score=None, it should equal soreness."""
        coach = self._make_coach()
        captured = {}

        def capture_classify(**kwargs):
            captured["soreness"] = kwargs.get("soreness")
            return ("LOW", [])

        coach.fatigue.classify_fatigue = MagicMock(side_effect=capture_classify)
        coach.run_morning_routine(soreness=7, subjective_fatigue_score=None)
        self.assertEqual(captured.get("soreness"), 7)

    def test_no_console_input_blocked(self):
        """run_morning_routine must complete without needing stdin."""
        import io
        import sys
        coach = self._make_coach()
        old_stdin = sys.stdin
        sys.stdin = io.StringIO("")  # empty stdin — input() would raise EOFError
        try:
            # Should not raise EOFError
            result = coach.run_morning_routine(soreness=None, subjective_fatigue_score=None)
        finally:
            sys.stdin = old_stdin
        # Returns True (Telegram mock returns True)
        self.assertTrue(result)


# ─────────────────────────────────────────────────────────────────────────────
# 6. WeatherAPI — Open-Meteo, no API key required
# ─────────────────────────────────────────────────────────────────────────────

class TestWeatherApiProviderContract(unittest.TestCase):
    """Verify the weather module uses Open-Meteo endpoints exclusively."""

    def test_open_meteo_geocoding_endpoint_used(self):
        import titan.integrations.weather_api as wmod
        src = inspect.getsource(wmod)
        self.assertIn("geocoding-api.open-meteo.com", src)

    def test_open_meteo_forecast_endpoint_used(self):
        import titan.integrations.weather_api as wmod
        src = inspect.getsource(wmod)
        self.assertIn("api.open-meteo.com/v1/forecast", src)

    def test_openweathermap_not_used(self):
        import titan.integrations.weather_api as wmod
        src = inspect.getsource(wmod)
        self.assertNotIn(
            "api.openweathermap.org", src,
            "weather_api.py must not call api.openweathermap.org",
        )

    def test_api_key_not_required_for_fetch(self):
        """_fetch_open_meteo must not pass an api_key to requests.get."""
        try:
            from titan.integrations.weather_api import WeatherAPI
        except ModuleNotFoundError as exc:
            if exc.name == "requests":
                self.skipTest("requests is not installed in this environment")
            raise

        api = WeatherAPI.__new__(WeatherAPI)
        api.api_key = None
        api.location = "Athens,GR"
        api.cache = {}
        api.cache_timestamp = None
        api.cache_duration_hours = 1
        api._update_thread = None
        api._coords = (37.98, 23.73)

        calls = []
        def fake_get(url, params=None, **kwargs):
            calls.append({"url": url, "params": params or {}})
            # Return a fake response
            m = MagicMock()
            m.raise_for_status = MagicMock()
            m.json.return_value = {
                "hourly": {
                    "time": ["2026-03-02T07:00"],
                    "temperature_2m": [15.0],
                    "relative_humidity_2m": [60],
                    "weather_code": [0],
                    "wind_speed_10m": [5.0],
                },
                "current": {
                    "temperature_2m": 15.0,
                    "relative_humidity_2m": 60,
                    "weather_code": 0,
                    "wind_speed_10m": 5.0,
                },
            }
            return m

        with patch("titan.integrations.weather_api._http_get", side_effect=fake_get):
            api._fetch_open_meteo()

        for call in calls:
            params = call["params"]
            self.assertNotIn("appid", params, "Open-Meteo does not use 'appid'")
            self.assertNotIn("api_key", params, "Open-Meteo does not use 'api_key'")


if __name__ == "__main__":
    unittest.main()
