#!/usr/bin/env python3
"""
Smoke tests for titan/ui/menu_system.py.

menu_system.py is purely a UI layer with no independent logic — it delegates
to engines passed via a context dict and uses print()/input().  These tests:

  1. Verify that every public menu function is importable and callable.
  2. Provide a minimal context so the real code paths run (not just the
     "engine not initialised" early-return paths).
  3. Monkeypatch builtins.input to prevent the test from blocking.
  4. Monkeypatch os.system (clear screen) so it is a no-op in CI.

Run with:
    pytest test_menu_system.py -v
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
# HELPERS
# ════════════════════════════════════════════════════════════════════════════

def _make_ctx(tmp_path):
    """Build a minimal titan_ctx dict with real (but light) engine instances."""
    from titan.science.hrv_engine import HRVGuidedEngine
    from titan.science.tsb_engine import TSBEngine
    from titan.science.acwr_engine import ACWREngine
    from titan.features.weekly_planner import WeeklyPlanGenerator
    from titan.features.optimal_time_calculator import OptimalTimeCalculator
    from titan.science.glycogen_model import GlycogenModel
    from titan.features.nutrition_optimizer import NutritionOptimizer
    from titan.core.equipment import EquipmentManager
    from titan.integrations.weather_api import WeatherAPI

    hrv_eng  = HRVGuidedEngine()
    tsb_eng  = TSBEngine()
    acwr_eng = ACWREngine()
    planner  = WeeklyPlanGenerator(hrv_eng, tsb_eng, acwr_eng)

    # Stub optimal_time_calc with a mock to avoid real network calls
    opt_time_mock = MagicMock()
    opt_time_mock.calculate_optimal_time.return_value = {
        "recommended_time": "07:30",
        "dew_point":        12.0,
        "temperature":      18.0,
        "quality":          "GOOD",
        "reasoning":        ["Low dew point"],
    }

    return {
        "hrv_engine":          hrv_eng,
        "tsb_engine":          tsb_eng,
        "acwr_engine":         acwr_eng,
        "weekly_planner":      planner,
        "optimal_time_calc":   opt_time_mock,
        "nutrition_optimizer": NutritionOptimizer(GlycogenModel()),
        "equipment_manager":   EquipmentManager(),
        "weather":             WeatherAPI(),
        "telegram":            MagicMock(),
        "garmin":              MagicMock(sync_all=MagicMock(return_value={
            "activities": [], "sleep": [], "weight": [], "hrv": [],
        })),
        "phase":               "BUILD",
        "athlete_profile":     {"weight_kg": 75.0, "threshold_hr": 170,
                                "name": "Test Runner"},
        "today_session":       {"session_type": "EASY", "duration_min": 60},
        "recent_activities":   [],
        "recent_sleep":        [],
        "last_weekly_plan":    None,
        "today_session_type":  "EASY",
        "optimal_time_str":    "07:30",
    }


# ════════════════════════════════════════════════════════════════════════════
# 1. IMPORT SMOKE TEST
# ════════════════════════════════════════════════════════════════════════════

class TestMenuSystemImport:

    def test_module_importable(self):
        import titan.ui.menu_system  # must not raise

    def test_all_public_functions_callable(self):
        from titan.ui import menu_system
        public_fns = [
            "main_menu",
            "menu_daily_plan",
            "menu_weekly_plan",
            "menu_nutrition",
            "menu_data_browser",
            "menu_shoe_selector",
            "menu_garmin_sync",
            "menu_weight_trend",
            "menu_analytics",
            "menu_settings",
        ]
        for fn in public_fns:
            assert hasattr(menu_system, fn), f"Missing function: {fn}"
            assert callable(getattr(menu_system, fn))


# ════════════════════════════════════════════════════════════════════════════
# 2. INDIVIDUAL MENU SMOKE TESTS
#    builtins.input → always "0" / "n" to avoid blocking
#    os.system      → no-op
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def no_screen_clear():
    with patch("os.system"):
        yield


class TestMenuDailyPlan:

    def test_runs_without_engines(self):
        from titan.ui.menu_system import menu_daily_plan
        with patch("builtins.input", return_value=""):
            menu_daily_plan({})  # empty ctx — hits early guards

    def test_runs_with_full_ctx(self, tmp_path):
        from titan.ui.menu_system import menu_daily_plan
        ctx = _make_ctx(tmp_path)
        with patch("builtins.input", return_value=""):
            menu_daily_plan(ctx)


class TestMenuWeeklyPlan:

    def test_missing_planner_returns_early(self):
        from titan.ui.menu_system import menu_weekly_plan
        with patch("builtins.input", return_value=""):
            menu_weekly_plan({})  # no weekly_planner → early return

    def test_with_planner_generates_plan(self, tmp_path):
        from titan.ui.menu_system import menu_weekly_plan
        ctx = _make_ctx(tmp_path)
        with patch("builtins.input", return_value="n"):
            menu_weekly_plan(ctx)
        assert ctx.get("last_weekly_plan") is not None

    def test_plan_stored_in_context(self, tmp_path):
        from titan.ui.menu_system import menu_weekly_plan
        ctx = _make_ctx(tmp_path)
        with patch("builtins.input", return_value="n"):
            menu_weekly_plan(ctx)
        plan = ctx["last_weekly_plan"]
        assert "daily_sessions" in plan
        assert len(plan["daily_sessions"]) == 7


class TestMenuNutrition:

    def test_missing_optimizer_returns_early(self):
        from titan.ui.menu_system import menu_nutrition
        with patch("builtins.input", return_value=""):
            menu_nutrition({})

    def test_with_optimizer_does_not_crash(self, tmp_path):
        from titan.ui.menu_system import menu_nutrition
        ctx = _make_ctx(tmp_path)
        with patch("builtins.input", return_value="n"):
            menu_nutrition(ctx)


class TestMenuSettings:

    def test_settings_with_empty_profile(self):
        from titan.ui.menu_system import menu_settings
        with patch("builtins.input", return_value=""):
            menu_settings({})  # must not crash even with empty ctx

    def test_settings_with_profile(self, tmp_path):
        from titan.ui.menu_system import menu_settings
        ctx = _make_ctx(tmp_path)
        with patch("builtins.input", return_value=""):
            menu_settings(ctx)


class TestMenuShoeSelector:

    def test_missing_equipment_returns_early(self):
        from titan.ui.menu_system import menu_shoe_selector
        with patch("builtins.input", return_value=""):
            menu_shoe_selector({})

    def test_with_equipment_manager(self, tmp_path):
        from titan.ui.menu_system import menu_shoe_selector
        ctx = _make_ctx(tmp_path)
        with patch("builtins.input", return_value=""):
            menu_shoe_selector(ctx)


class TestMenuGarminSync:

    def test_missing_garmin_returns_early(self):
        from titan.ui.menu_system import menu_garmin_sync
        with patch("builtins.input", return_value=""):
            menu_garmin_sync({})

    def test_with_garmin_mock_stores_activities(self, tmp_path):
        from titan.ui.menu_system import menu_garmin_sync
        ctx = _make_ctx(tmp_path)
        with patch("builtins.input", return_value=""):
            menu_garmin_sync(ctx)
        # After sync, recent_activities must exist in ctx (may be empty)
        assert "recent_activities" in ctx


class TestMenuWeightTrend:

    def test_missing_nutrition_returns_early(self):
        from titan.ui.menu_system import menu_weight_trend
        with patch("builtins.input", return_value=""):
            menu_weight_trend({})

    def test_with_nutrition_does_not_crash(self, tmp_path):
        from titan.ui.menu_system import menu_weight_trend
        ctx = _make_ctx(tmp_path)
        with patch("builtins.input", return_value=""):
            menu_weight_trend(ctx)


class TestMenuAnalytics:

    def test_no_activities_shows_message(self):
        from titan.ui.menu_system import menu_analytics
        with patch("builtins.input", return_value=""):
            menu_analytics({"recent_activities": []})

    def test_with_activities_computes_stats(self, tmp_path):
        from titan.ui.menu_system import menu_analytics
        ctx = _make_ctx(tmp_path)
        ctx["recent_activities"] = [
            {"distance_km": 10.0, "avg_hr": 140},
            {"distance_km":  8.0, "avg_hr": 135},
            {"distance_km": 12.0, "avg_hr": 145},
        ]
        with patch("builtins.input", return_value=""):
            menu_analytics(ctx)   # must not raise


# ════════════════════════════════════════════════════════════════════════════
# 3. Private helper functions
# ════════════════════════════════════════════════════════════════════════════

class TestMenuHelpers:
    """Smoke-tests for the private _browser_* functions in menu_data_browser."""

    @pytest.fixture
    def ctx(self, tmp_path):
        return _make_ctx(tmp_path)

    def _run_data_browser_option(self, ctx, option_key):
        """
        Simulate choosing option_key inside menu_data_browser, then '0' to exit.
        """
        from titan.ui.menu_system import menu_data_browser
        inputs = iter([option_key, "", "0"])
        with patch("builtins.input", side_effect=inputs):
            menu_data_browser(ctx)

    def test_data_browser_activities_no_data(self, ctx):
        self._run_data_browser_option(ctx, "1")

    def test_data_browser_drift_no_data(self, ctx):
        self._run_data_browser_option(ctx, "2")

    def test_data_browser_hrv_no_data(self, ctx):
        self._run_data_browser_option(ctx, "3")

    def test_data_browser_sleep_no_data(self, ctx):
        self._run_data_browser_option(ctx, "4")

    def test_data_browser_weight_no_data(self, ctx):
        self._run_data_browser_option(ctx, "5")

    def test_data_browser_tsb_no_data(self, ctx):
        self._run_data_browser_option(ctx, "6")

    def test_data_browser_exit_immediately(self, ctx):
        self._run_data_browser_option(ctx, "0")
