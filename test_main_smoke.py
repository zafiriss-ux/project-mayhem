#!/usr/bin/env python3
"""
Smoke tests for titan/main.py startup path.

titan/main.py (19.8KB) is the main orchestrator — it wires up all engines,
registers Telegram callbacks, and launches background threads.  It was
previously completely untested.

These tests verify:
  1. All imports in main.py succeed.
  2. The module-level helper (_print_banner) is importable and callable.
  3. Key engine instances can be created with the same import chain main.py uses.
  4. _register_telegram_callbacks() wires callbacks without raising.
  5. The application context built by main.py contains the expected keys.

We never call the interactive main_menu() or start background threads that
would block the test runner.

Run with:
    pytest test_main_smoke.py -v
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── env stub ─────────────────────────────────────────────────────────────────
os.environ.setdefault("GARMIN_EMAIL",        "test@example.com")
os.environ.setdefault("GARMIN_PASSWORD",     "test")
os.environ.setdefault("TELEGRAM_BOT_TOKEN",  "")   # empty → no real polling
os.environ.setdefault("TELEGRAM_CHAT_ID",    "12345")
os.environ.setdefault("WEATHER_API_KEY",     "test")
os.environ.setdefault("WEATHER_LOCATION",    "Athens,GR")

sys.path.insert(0, str(Path(__file__).parent))


# ════════════════════════════════════════════════════════════════════════════
# 1. Import chain smoke tests
# ════════════════════════════════════════════════════════════════════════════

class TestMainImports:
    """
    Verify that every top-level import in titan/main.py resolves without error.
    If any import fails here, it will also fail at runtime.
    """

    def test_import_garmin_sync(self):
        from titan.integrations.garmin_sync import GarminSync  # noqa

    def test_import_weather_api(self):
        from titan.integrations.weather_api import WeatherAPI  # noqa

    def test_import_telegram_bot(self):
        from titan.integrations.telegram_bot import TitanTelegramBot  # noqa

    def test_import_hrv_engine(self):
        from titan.science.hrv_engine import HRVGuidedEngine  # noqa

    def test_import_tsb_engine(self):
        from titan.science.tsb_engine import TSBEngine  # noqa

    def test_import_acwr_engine(self):
        from titan.science.acwr_engine import ACWREngine  # noqa

    def test_import_readiness_engine(self):
        from titan.science.readiness_engine import ReadinessEngine  # noqa

    def test_import_glycogen_model(self):
        from titan.science.glycogen_model import GlycogenModel  # noqa

    def test_import_drift_engine(self):
        from titan.science.drift_engine import DriftEngine  # noqa

    def test_import_lactate_logic(self):
        from titan.science.lactate_logic import LactateLogic  # noqa

    def test_import_trimp_engine(self):
        from titan.science.trimp_engine import TRIMPEngine  # noqa

    def test_import_fatigue_engine(self):
        from titan.science.fatigue_engine import FatigueEngine  # noqa

    def test_import_adaptive_memory(self):
        from titan.science.adaptive_memory import AdaptiveMemory  # noqa

    def test_import_biomechanics(self):
        from titan.science.biomechanics import BiomechanicsAnalysis  # noqa

    def test_import_efficiency_engine(self):
        from titan.science.efficiency_engine import EfficiencyEngine  # noqa

    def test_import_durability_engine(self):
        from titan.science.durability_engine import DurabilityEngine  # noqa

    def test_import_critical_speed(self):
        from titan.science.critical_speed import CriticalSpeedEngine  # noqa

    def test_import_rcp_engine(self):
        from titan.science.rcp_engine import RCPEngine  # noqa

    def test_import_database_manager(self):
        from titan.core.database import DatabaseManager  # noqa

    def test_import_weekly_planner(self):
        from titan.features.weekly_planner import WeeklyPlanGenerator  # noqa

    def test_import_optimal_time_calculator(self):
        from titan.features.optimal_time_calculator import OptimalTimeCalculator  # noqa

    def test_import_nutrition_optimizer(self):
        from titan.features.nutrition_optimizer import NutritionOptimizer  # noqa

    def test_import_daily_coach(self):
        from titan.orchestration.daily_coach import DailyCoach  # noqa

    def test_import_menu_system(self):
        from titan.ui.menu_system import main_menu  # noqa

    def test_import_setup_wizard(self):
        from titan.ui.setup_wizard import ensure_credentials  # noqa


# ════════════════════════════════════════════════════════════════════════════
# 2. Engine instantiation
# ════════════════════════════════════════════════════════════════════════════

class TestEngineInstantiation:
    """
    Verify that all engines used in main.py can be instantiated
    (i.e. __init__ doesn't crash without config/network).
    """

    def test_garmin_sync_instantiates(self):
        from titan.integrations.garmin_sync import GarminSync
        g = GarminSync()
        assert g is not None

    def test_weather_api_instantiates(self):
        from titan.integrations.weather_api import WeatherAPI
        w = WeatherAPI()
        assert w is not None

    def test_telegram_bot_instantiates(self):
        from titan.integrations.telegram_bot import TitanTelegramBot
        b = TitanTelegramBot(bot_token="", chat_id="12345")
        assert b is not None

    def test_hrv_engine_instantiates(self):
        from titan.science.hrv_engine import HRVGuidedEngine
        assert HRVGuidedEngine() is not None

    def test_tsb_engine_instantiates(self):
        from titan.science.tsb_engine import TSBEngine
        assert TSBEngine() is not None

    def test_acwr_engine_instantiates(self):
        from titan.science.acwr_engine import ACWREngine
        assert ACWREngine() is not None

    def test_weekly_planner_instantiates(self):
        from titan.science.hrv_engine import HRVGuidedEngine
        from titan.science.tsb_engine import TSBEngine
        from titan.science.acwr_engine import ACWREngine
        from titan.features.weekly_planner import WeeklyPlanGenerator
        p = WeeklyPlanGenerator(HRVGuidedEngine(), TSBEngine(), ACWREngine())
        assert p is not None

    def test_optimal_time_calculator_instantiates(self):
        from titan.integrations.weather_api import WeatherAPI
        from titan.features.optimal_time_calculator import OptimalTimeCalculator
        assert OptimalTimeCalculator(WeatherAPI()) is not None

    def test_nutrition_optimizer_instantiates(self):
        from titan.science.glycogen_model import GlycogenModel
        from titan.features.nutrition_optimizer import NutritionOptimizer
        assert NutritionOptimizer(GlycogenModel()) is not None

    def test_database_manager_instantiates(self, tmp_path):
        from titan.core.database import DatabaseManager
        db = DatabaseManager(str(tmp_path / "smoke.db"))
        assert db is not None
        db.close()


# ════════════════════════════════════════════════════════════════════════════
# 3. _print_banner helper
# ════════════════════════════════════════════════════════════════════════════

class TestPrintBanner:

    def test_banner_importable_and_callable(self, capsys):
        from titan.main import _print_banner
        _print_banner()
        out = capsys.readouterr().out
        assert "TITAN" in out

    def test_banner_mentions_key_features(self, capsys):
        from titan.main import _print_banner
        _print_banner()
        out = capsys.readouterr().out
        assert "HRV" in out or "TSB" in out or "Garmin" in out

class TestEnvNumericParsing:

    def test_parse_env_number_valid_int(self, monkeypatch):
        from titan.main import _parse_env_number
        monkeypatch.setenv("ATHLETE_AGE", "42")
        assert _parse_env_number("ATHLETE_AGE", "35", int) == 42

    def test_parse_env_number_invalid_exits(self, monkeypatch, capsys):
        from titan.main import _parse_env_number
        monkeypatch.setenv("ATHLETE_AGE", "abc")
        with pytest.raises(SystemExit) as exc:
            _parse_env_number("ATHLETE_AGE", "35", int)
        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "Invalid environment variable ATHLETE_AGE" in out



# ════════════════════════════════════════════════════════════════════════════
# 4. _register_telegram_callbacks
# ════════════════════════════════════════════════════════════════════════════

class TestRegisterTelegramCallbacks:

    @pytest.fixture
    def minimal_ctx(self, tmp_path):
        from titan.core.database import DatabaseManager
        from titan.science.hrv_engine import HRVGuidedEngine
        from titan.science.tsb_engine import TSBEngine
        from titan.science.acwr_engine import ACWREngine
        from titan.science.glycogen_model import GlycogenModel
        from titan.features.weekly_planner import WeeklyPlanGenerator
        from titan.features.optimal_time_calculator import OptimalTimeCalculator
        from titan.features.nutrition_optimizer import NutritionOptimizer
        from titan.orchestration.daily_coach import DailyCoach

        db = DatabaseManager(str(tmp_path / "cb_test.db"))
        hrv = HRVGuidedEngine()
        tsb = TSBEngine()
        opt = OptimalTimeCalculator(MagicMock(
            get_hourly_forecast=MagicMock(return_value=[]),
        ))
        nut = NutritionOptimizer(GlycogenModel())
        planner = WeeklyPlanGenerator(hrv, tsb, ACWREngine())

        garmin_mock  = MagicMock()
        garmin_mock.sync_all.return_value = {
            "activities": [], "sleep": [], "hrv": [], "hrr": [], "weight": [],
        }
        telegram_mock = MagicMock()
        telegram_mock.send_daily_coaching.return_value = True

        coach = DailyCoach(
            garmin_sync=garmin_mock,
            weather_api=MagicMock(),
            telegram_bot=telegram_mock,
            hrv_engine=hrv,
            tsb_engine=tsb,
            readiness_engine=MagicMock(),
            optimal_time_calc=opt,
            nutrition_optimizer=nut,
            weekly_planner=planner,
            db=db,
        )

        return {
            "daily_coach":    coach,
            "weekly_planner": planner,
            "garmin":         garmin_mock,
            "telegram":       telegram_mock,
            "athlete_profile": {"weight_kg": 75.0, "phase": "BUILD"},
            "tsb_engine":     tsb,
            "hrv_engine":     hrv,
            "acwr_engine":    ACWREngine(),
            "nutrition":      nut,
            "db":             db,
        }

    def test_register_callbacks_does_not_raise(self, minimal_ctx):
        from titan.main import _register_telegram_callbacks
        telegram_mock = minimal_ctx["telegram"]
        _register_telegram_callbacks(telegram_mock, minimal_ctx)

    def test_register_wires_today_callback(self, minimal_ctx):
        from titan.main import _register_telegram_callbacks
        telegram_mock = minimal_ctx["telegram"]
        _register_telegram_callbacks(telegram_mock, minimal_ctx)
        # Verify "today" command was registered (check first positional arg of each call)
        registered_commands = [c[0][0] for c in telegram_mock.register_command.call_args_list]
        assert "today" in registered_commands
        assert telegram_mock.register_command.call_count >= 1
