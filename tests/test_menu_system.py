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
    pytest tests/test_menu_system.py -v
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

sys.path.insert(0, str(Path(__file__).parent.parent))


# ════════════════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════════════════

def _make_ctx(tmp_path):
    """Build a minimal titan_ctx dict with real (but light) engine instances."""
    from titan.core.equipment import EquipmentManager
    from titan.features.nutrition_optimizer import NutritionOptimizer
    from titan.features.optimal_time_calculator import OptimalTimeCalculator
    from titan.features.weekly_planner import WeeklyPlanGenerator
    from titan.integrations.weather_api import WeatherAPI
    from titan.science.acwr_engine import ACWREngine
    from titan.science.glycogen_model import GlycogenModel
    from titan.science.hrv_engine import HRVGuidedEngine
    from titan.science.tsb_engine import TSBEngine

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

    def test_failed_connection_shows_error_message(self, tmp_path, capsys):
        """When Garmin is not connected, menu must show ❌ and error text."""
        from titan.ui.menu_system import menu_garmin_sync
        ctx = _make_ctx(tmp_path)
        ctx["garmin"].is_connected = False
        ctx["garmin"].last_connect_error = "InvalidCredentialsException: Invalid credentials"
        ctx["garmin"].sync_all.return_value = {
            "activities": [], "sleep": [], "weight": [], "hrv": [],
        }
        with patch("builtins.input", return_value=""):
            menu_garmin_sync(ctx)
        out = capsys.readouterr().out
        assert "❌" in out
        assert "Αποτυχία σύνδεσης" in out
        assert "InvalidCredentialsException" in out

    def test_timeout_shows_timeout_message(self, tmp_path, capsys):
        """Timeout status must surface timeout message instead of silent zeros."""
        from titan.ui.menu_system import menu_garmin_sync
        ctx = _make_ctx(tmp_path)
        ctx["garmin"].is_connected = False
        ctx["garmin"].last_connect_error = None
        ctx["garmin"].sync_all.return_value = {
            "activities": [], "sleep": [], "weight": [], "hrv": [],
            "status": "timeout_cancelled",
        }
        with patch("builtins.input", return_value=""):
            menu_garmin_sync(ctx)
        out = capsys.readouterr().out
        assert "Timeout" in out
        assert "❌" in out

    def test_connected_with_data_shows_checkmarks(self, tmp_path, capsys):
        """Successful sync with data must show ✅ for each non-zero count."""
        from titan.ui.menu_system import menu_garmin_sync
        ctx = _make_ctx(tmp_path)
        ctx["garmin"].is_connected = True
        ctx["garmin"].last_connect_error = None
        ctx["garmin"].sync_all.return_value = {
            "activities": [{"date": "2026-03-23", "distance_km": 10}],
            "sleep": [{"date": "2026-03-23", "total_sleep_hours": 7}],
            "weight": [],
            "hrv": [],
        }
        with patch("builtins.input", return_value=""):
            menu_garmin_sync(ctx)
        out = capsys.readouterr().out
        assert out.count("✅") >= 2  # at least activities + sleep


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


# ════════════════════════════════════════════════════════════════════════════
# #1246 (E2E-01): the today screen shows the stored decision of the day
# ════════════════════════════════════════════════════════════════════════════
# The decisions and the plan are synthetic. Reproduced in #1517.


def _today_screen(capsys, tmp_path, stored_session, plan_session="LONG_RUN"):
    """Render "Σημερινό Πλάνο" for today with a plan and, if given, a stored decision."""
    from datetime import UTC, datetime

    from titan.core.database import DatabaseManager
    from titan.ui.menu_system import menu_daily_plan

    now = datetime.now(UTC)
    db = DatabaseManager(db_dir=tmp_path)
    try:
        if stored_session is not None:
            db.save_governance_decision({
                "athlete_profile_id": "owner", "date": now.date().isoformat(),
                "session_planned": plan_session, "session_post_governance": stored_session,
                "locks_applied": [],
            })
        plan = {"daily_sessions": [{
            "day": now.strftime("%A"), "session_type": plan_session,
            "distance_km": 5.1, "details": "template",
        }]}
        with patch("builtins.input", return_value=""):
            menu_daily_plan({"db": db, "last_weekly_plan": plan})
        stored = db.get_governance_decision_on("owner", now.date().isoformat())
    finally:
        db.close()
    return capsys.readouterr().out, stored


def _instruction(out):
    return [line.strip() for line in out.splitlines() if "ΠΡΟΠΟΝΗΣΗ:" in line]


def test_1246_control_the_stored_decision_of_today_is_rest(capsys, tmp_path):
    _, stored = _today_screen(capsys, tmp_path, "REST")
    assert stored["session_post_governance"] == "REST"


def test_1246_the_today_screen_shows_the_stored_rest(capsys, tmp_path):
    out, _ = _today_screen(capsys, tmp_path, "REST")
    # The plan may still be named next to the decision; the instruction line may not be it.
    assert "ΠΡΟΠΟΝΗΣΗ: LONG_RUN" not in out
    assert "REST" in out
    assert _instruction(out) == ["🏃 ΠΡΟΠΟΝΗΣΗ: REST"]
    assert "πλάνο εβδομάδας: LONG_RUN – 5.1 km" in out


def test_1246_a_stored_easy_replaces_the_planned_long_run(capsys, tmp_path):
    out, _ = _today_screen(capsys, tmp_path, "EASY")
    assert _instruction(out) == ["🏃 ΠΡΟΠΟΝΗΣΗ: EASY"]


def test_1246_the_plans_distance_is_only_shown_as_the_plans(capsys, tmp_path):
    """Governance may cut the volume of the same session, so 5.1 km stays the plan's."""
    out, _ = _today_screen(capsys, tmp_path, "LONG_RUN")
    assert _instruction(out) == ["🏃 ΠΡΟΠΟΝΗΣΗ: LONG_RUN"]
    assert "(πλάνο εβδομάδας: LONG_RUN – 5.1 km)" in out


def test_1246_without_a_stored_decision_the_plan_is_not_the_instruction(capsys, tmp_path):
    out, stored = _today_screen(capsys, tmp_path, None)
    assert stored is None
    assert _instruction(out) == []
    assert "Χωρίς αποθηκευμένη απόφαση για σήμερα" in out
    assert "Πλάνο εβδομάδας: LONG_RUN – 5.1 km" in out


def test_1246_another_athletes_decision_is_not_the_owners(capsys, tmp_path):
    from datetime import UTC, datetime

    from titan.core.database import DatabaseManager
    from titan.ui.menu_system import menu_daily_plan

    now = datetime.now(UTC)
    db = DatabaseManager(db_dir=tmp_path)
    try:
        db.save_governance_decision({
            "athlete_profile_id": "a1", "date": now.date().isoformat(),
            "session_planned": "EASY", "session_post_governance": "TEMPO", "locks_applied": [],
        })
        with patch("builtins.input", return_value=""):
            menu_daily_plan({"db": db, "last_weekly_plan": None})
    finally:
        db.close()
    out = capsys.readouterr().out
    assert "TEMPO" not in out


def test_1246_a_decision_that_cannot_be_read_is_not_replaced_by_the_plan(capsys):
    from datetime import UTC, datetime

    from titan.ui.menu_system import menu_daily_plan

    db = MagicMock()
    db.get_governance_decision_on.side_effect = RuntimeError("database is locked")
    plan = {"daily_sessions": [{"day": datetime.now(UTC).strftime("%A"), "session_type": "LONG_RUN",
                                "distance_km": 5.1, "details": "template"}]}
    with patch("builtins.input", return_value=""):
        menu_daily_plan({"db": db, "last_weekly_plan": plan})
    out = capsys.readouterr().out
    assert "δεν διαβάστηκε (RuntimeError)" in out
    assert _instruction(out) == []
    assert "database is locked" not in out
    # The decision may exist: the screen must not say there is none.
    assert "Χωρίς αποθηκευμένη απόφαση" not in out


def test_1246_no_decision_and_no_plan_still_says_there_is_no_decision(capsys, tmp_path):
    from titan.core.database import DatabaseManager
    from titan.ui.menu_system import menu_daily_plan

    db = DatabaseManager(db_dir=tmp_path)
    try:
        with patch("builtins.input", return_value=""):
            menu_daily_plan({"db": db, "last_weekly_plan": None})
    finally:
        db.close()
    out = capsys.readouterr().out
    assert "Χωρίς αποθηκευμένη απόφαση για σήμερα" in out
    assert _instruction(out) == []


def test_1246_a_malformed_stored_decision_is_treated_as_unreadable(capsys):
    from datetime import UTC, datetime

    from titan.ui.menu_system import menu_daily_plan

    db = MagicMock()
    db.get_governance_decision_on.return_value = {"date": datetime.now(UTC).date().isoformat()}
    with patch("builtins.input", return_value=""):
        menu_daily_plan({"db": db, "last_weekly_plan": None})
    out = capsys.readouterr().out
    assert "δεν διαβάστηκε (KeyError)" in out
    assert _instruction(out) == []


@pytest.mark.parametrize("session", [None, "", "   "])
def test_1246_a_stored_decision_without_a_session_is_treated_as_unreadable(capsys, session):
    from datetime import UTC, datetime

    from titan.ui.menu_system import menu_daily_plan

    db = MagicMock()
    db.get_governance_decision_on.return_value = {
        "date": datetime.now(UTC).date().isoformat(), "session_post_governance": session,
    }
    with patch("builtins.input", return_value=""):
        menu_daily_plan({"db": db, "last_weekly_plan": None})
    out = capsys.readouterr().out
    assert "δεν διαβάστηκε (ValueError)" in out
    assert _instruction(out) == []
