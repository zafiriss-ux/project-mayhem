import logging

import pytest

from titan import main as titan_main


class _DummyGarmin:
    def __init__(self):
        self.stop_calls = 0

    def start_background_sync(self, interval_hours):
        return None

    def stop_background_sync(self):
        self.stop_calls += 1


class _DummyWeather:
    def __init__(self):
        self.stop_calls = 0

    def start_background_updates(self, interval_hours):
        return None

    def stop_background_updates(self):
        self.stop_calls += 1


class _DummyTelegram:
    def __init__(self):
        self.commands = {}
        self.scheduled_tasks = []
        self.stop_calls = 0
        self.weekly_plans_sent = []

    def register_command(self, name, callback):
        self.commands[name] = callback

    def start_bot(self):
        return None

    def stop_bot(self):
        self.stop_calls += 1

    def schedule_task(self, **kwargs):
        self.scheduled_tasks.append(kwargs)

    def send_weekly_plan(self, plan):
        self.weekly_plans_sent.append(plan)


class _DummyHRVEngine:
    def get_hrv_summary(self):
        return {"latest_hrv": 70, "baseline": 65, "trend": "up"}


class _DummyTSBEngine:
    ctl = 52.0
    atl = 47.0

    def calculate_tsb(self):
        return (5, "FRESH")


class _DummyReadinessEngine:
    def analyze_readiness(self, **kwargs):
        return {"score": 85, "status": "READY", "recommendation": "Go"}


class _DummyDriftEngine:
    def analyze_cardiac_drift(self, hr_data, duration_min):
        return {"drift_percent": 2.0, "assessment": "GOOD", "lt_zone": "AEROBIC"}


class _DummyNutritionOptimizer:
    def __init__(self, _glycogen_model):
        return None

    def analyze_weight_trend(self):
        return {"current_weight": 70.0}

    def calculate_daily_nutrition(self, weight_kg, today_session):
        return {"carbs_g": 300, "protein_g": 120, "fat_g": 70, "total_calories": 2500}


class _DummyOptimalTimeCalculator:
    def __init__(self, _weather):
        return None

    def calculate_optimal_time(self, session_type, duration_hours=1.0, day_offset=0, tsb_value=None):
        return {"recommended_time": "07:00"}


class _DummyWeeklyPlanner:
    def __init__(self, *args, **kwargs):
        return None

    def generate_weekly_plan(self, athlete_profile, phase):
        return {"status": "ok"}


class _DummyDailyCoach:
    def __init__(self, *args, **kwargs):
        self.outcome_tracker = type(
            "OutcomeTracker",
            (),
            {
                "get_calibration_summary": staticmethod(
                    lambda: {
                        "status": "CALIBRATED",
                        "n_decisions": 10,
                        "n_with_outcome": 8,
                        "completion_rate": 0.8,
                        "governance_lock_rate": 0.1,
                        "athlete_override_rate": 0.2,
                        "avg_rpe_when_completed": 6.5,
                    }
                )
            },
        )()
        return None

    def run_morning_routine_async(self):
        return None

    def run_morning_routine(self):
        return None


class _DummyGarminSync(_DummyGarmin):
    def sync_all(self):
        return {
            "activities": [{"date": "2026-01-01", "distance_km": 10, "avg_hr": 150, "duration_sec": 3600}],
            "weight": [{"date": "2026-01-01", "weight_kg": 70.0}],
            "hrv": [{"date": "2026-01-01", "rmssd": 70}],
            "sleep": [{"date": "2026-01-01"}],
        }

    def sync_activities(self, days_back):
        return [{"date": "2026-01-01", "distance_km": 10, "avg_hr": 150, "duration_sec": 3600}]


class _DummyEquipment:
    def recommend_shoe(self, session_type):
        return "Daily Trainer"


class _DummyDatabase:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class _DummyTitanContextContract:
    def __init__(self, **payload):
        self.payload = payload

    def to_payload(self):
        return self.payload


def _patch_main_dependencies(monkeypatch):
    monkeypatch.setattr(titan_main, "_print_banner", lambda: None)
    monkeypatch.setattr(titan_main, "ensure_credentials", lambda: True)

    dummy_garmin = _DummyGarminSync()
    dummy_weather = _DummyWeather()
    dummy_telegram = _DummyTelegram()
    dummy_db = _DummyDatabase()

    monkeypatch.setattr(titan_main, "GarminSync", lambda: dummy_garmin)
    monkeypatch.setattr(titan_main, "TitanTelegramBot", lambda: dummy_telegram)
    monkeypatch.setattr(titan_main, "DatabaseManager", lambda: dummy_db)
    monkeypatch.setattr(titan_main, "DailyCoach", _DummyDailyCoach)
    monkeypatch.setattr(titan_main, "WeeklyPlanGenerator", _DummyWeeklyPlanner)
    monkeypatch.setattr(titan_main, "OptimalTimeCalculator", _DummyOptimalTimeCalculator)
    monkeypatch.setattr(titan_main, "NutritionOptimizer", _DummyNutritionOptimizer)
    monkeypatch.setattr(titan_main, "TitanContextContract", _DummyTitanContextContract)

    monkeypatch.setattr(titan_main, "HRVGuidedEngine", _DummyHRVEngine)
    monkeypatch.setattr(titan_main, "TSBEngine", _DummyTSBEngine)
    monkeypatch.setattr(titan_main, "ACWREngine", lambda: object())
    monkeypatch.setattr(titan_main, "ReadinessEngine", _DummyReadinessEngine)
    monkeypatch.setattr(titan_main, "GlycogenModel", lambda: object())
    monkeypatch.setattr(titan_main, "DriftEngine", _DummyDriftEngine)
    monkeypatch.setattr(titan_main, "LactateLogic", lambda: object())
    monkeypatch.setattr(titan_main, "TRIMPEngine", lambda: object())
    monkeypatch.setattr(titan_main, "FatigueEngine", lambda: object())
    monkeypatch.setattr(titan_main, "AdaptiveMemory", lambda: object())
    monkeypatch.setattr(titan_main, "BiomechanicsAnalysis", lambda: object())
    monkeypatch.setattr(titan_main, "EfficiencyEngine", lambda: object())
    monkeypatch.setattr(titan_main, "DurabilityEngine", lambda: object())
    monkeypatch.setattr(titan_main, "CriticalSpeedEngine", lambda: object())
    monkeypatch.setattr(titan_main, "RCPEngine", lambda: object())

    weather_module = type("WeatherModule", (), {"WeatherAPI": lambda: dummy_weather})
    import sys

    monkeypatch.setitem(sys.modules, "titan.integrations.weather_api", weather_module)

    return dummy_garmin, dummy_weather, dummy_telegram, dummy_db


def test_parse_env_number_happy_path(monkeypatch):
    monkeypatch.setenv("ATHLETE_AGE", "36")

    value = titan_main._parse_env_number("ATHLETE_AGE", "35", int)

    assert value == 36


def test_main_credentials_failure_logs_structured_startup_event(monkeypatch, caplog):
    monkeypatch.setattr(titan_main, "_print_banner", lambda: None)
    monkeypatch.setattr(titan_main, "ensure_credentials", lambda: False)

    with caplog.at_level(logging.ERROR), pytest.raises(SystemExit):
        titan_main.main()

    record = next(r for r in caplog.records if r.msg == "startup_failure")
    assert record.component == "launcher"
    assert record.error_class == "CredentialsUnavailable"
    assert record.detail == "ensure_credentials() returned False"


def test_main_keyboard_interrupt_logs_shutdown_and_cleans_up(monkeypatch, caplog):
    garmin, weather, telegram, db = _patch_main_dependencies(monkeypatch)
    monkeypatch.setattr(titan_main, "main_menu", lambda _: (_ for _ in ()).throw(KeyboardInterrupt))

    with caplog.at_level(logging.INFO):
        titan_main.main()

    record = next(r for r in caplog.records if r.msg == "shutdown_requested")
    assert record.reason == "keyboard_interrupt"
    assert record.timestamp
    assert garmin.stop_calls == 1
    assert weather.stop_calls == 1
    assert telegram.stop_calls == 1
    assert db.closed is True


def test_main_normal_exit_runs_clean_shutdown_without_shutdown_log(monkeypatch, caplog):
    garmin, weather, telegram, db = _patch_main_dependencies(monkeypatch)
    monkeypatch.setattr(titan_main, "main_menu", lambda _: None)

    with caplog.at_level(logging.INFO):
        titan_main.main()

    assert not any(r.msg == "shutdown_requested" for r in caplog.records)
    assert garmin.stop_calls == 1
    assert weather.stop_calls == 1
    assert telegram.stop_calls == 1
    assert db.closed is True


def test_main_smoke_uses_env_overrides_and_passes_profile_to_context(monkeypatch):
    _garmin, _weather, telegram, _db = _patch_main_dependencies(monkeypatch)

    captured_ctx = {}

    def _capture_main_menu(ctx):
        captured_ctx.update(ctx)

    monkeypatch.setattr(titan_main, "main_menu", _capture_main_menu)
    monkeypatch.setenv("ATHLETE_NAME", "Ada")
    monkeypatch.setenv("ATHLETE_AGE", "41")
    monkeypatch.setenv("ATHLETE_WEIGHT", "62.5")
    monkeypatch.setenv("ATHLETE_HEIGHT", "168")
    monkeypatch.setenv("ATHLETE_MAX_HR", "186")
    monkeypatch.setenv("ATHLETE_THRESHOLD_HR", "164")
    monkeypatch.setenv("TRAINING_PHASE", "PEAK")
    monkeypatch.setenv("TRAINING_GOAL", "MARATHON")

    titan_main.main()

    profile = captured_ctx["athlete_profile"]
    assert profile == {
        "name": "Ada",
        "age": 41,
        "weight_kg": 62.5,
        "height_cm": 168.0,
        "max_hr": 186,
        "threshold_hr": 164,
        "phase": "PEAK",
        "goal": "MARATHON",
    }
    assert {"today", "week", "stats", "recovery", "nutrition", "sync", "activities", "drift", "shoes", "calibration"}.issubset(telegram.commands)
    assert len(telegram.scheduled_tasks) == 2
    captured_ctx["equipment"] = _DummyEquipment()

    results = [command() for command in telegram.commands.values()]
    assert all("❌" not in result for result in results)

    weekly_task = next(task for task in telegram.scheduled_tasks if task["name"] == "Weekly Plan")
    weekly_task["callback"]()

    assert telegram.weekly_plans_sent


def test_main_smoke_invalid_env_value_exits_before_menu(monkeypatch):
    _patch_main_dependencies(monkeypatch)
    called = {"menu": 0}
    monkeypatch.setattr(titan_main, "main_menu", lambda _ctx: called.__setitem__("menu", called["menu"] + 1))
    monkeypatch.setenv("ATHLETE_AGE", "not-an-int")

    with pytest.raises(SystemExit):
        titan_main.main()

    assert called["menu"] == 0
