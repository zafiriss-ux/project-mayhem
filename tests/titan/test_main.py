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
