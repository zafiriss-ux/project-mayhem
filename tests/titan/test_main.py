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
        self.stop_calls = 0

    def register_command(self, name, callback):
        self.commands[name] = callback

    def start_bot(self):
        return None

    def stop_bot(self):
        self.stop_calls += 1

    def schedule_task(self, **kwargs):
        return None

    def send_weekly_plan(self, plan):
        return None


class _DummyWeeklyPlanner:
    def __init__(self, *args, **kwargs):
        return None

    def generate_weekly_plan(self, athlete_profile, phase):
        return {"status": "ok"}


class _DummyDailyCoach:
    def __init__(self, *args, **kwargs):
        return None

    def run_morning_routine_async(self):
        return None


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

    dummy_garmin = _DummyGarmin()
    dummy_weather = _DummyWeather()
    dummy_telegram = _DummyTelegram()
    dummy_db = _DummyDatabase()

    monkeypatch.setattr(titan_main, "GarminSync", lambda: dummy_garmin)
    monkeypatch.setattr(titan_main, "TitanTelegramBot", lambda: dummy_telegram)
    monkeypatch.setattr(titan_main, "DatabaseManager", lambda: dummy_db)
    monkeypatch.setattr(titan_main, "DailyCoach", _DummyDailyCoach)
    monkeypatch.setattr(titan_main, "WeeklyPlanGenerator", _DummyWeeklyPlanner)
    monkeypatch.setattr(titan_main, "OptimalTimeCalculator", lambda weather: object())
    monkeypatch.setattr(titan_main, "NutritionOptimizer", lambda glycogen_model: object())
    monkeypatch.setattr(titan_main, "TitanContextContract", _DummyTitanContextContract)

    monkeypatch.setattr(titan_main, "HRVGuidedEngine", lambda: object())
    monkeypatch.setattr(titan_main, "TSBEngine", lambda: object())
    monkeypatch.setattr(titan_main, "ACWREngine", lambda: object())
    monkeypatch.setattr(titan_main, "ReadinessEngine", lambda: object())
    monkeypatch.setattr(titan_main, "GlycogenModel", lambda: object())
    monkeypatch.setattr(titan_main, "DriftEngine", lambda: object())
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


def test_main_smoke_invalid_env_value_exits_before_menu(monkeypatch):
    _patch_main_dependencies(monkeypatch)
    called = {"menu": 0}
    monkeypatch.setattr(titan_main, "main_menu", lambda _ctx: called.__setitem__("menu", called["menu"] + 1))
    monkeypatch.setenv("ATHLETE_AGE", "not-an-int")

    with pytest.raises(SystemExit):
        titan_main.main()

    assert called["menu"] == 0
