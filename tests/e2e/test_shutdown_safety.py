from __future__ import annotations

import pytest

from tests.e2e.conftest import (
    StubAPL,
    StubAutonomic,
    StubCS,
    StubFatigue,
    StubGarminSync,
    StubGlycogen,
    StubGovernance,
    StubNutrition,
    StubOptimalTime,
    StubOutcomeTracker,
    StubReadiness,
    StubSimpleEngine,
    StubTelegram,
    StubTSB,
    StubVLG,
    StubWeather,
    StubWeeklyPlanner,
)
from titan.core.database import DatabaseManager
from titan.integrations import telegram_bot, weather_api
from titan.integrations.garmin_sync import GarminSync
from titan.integrations.telegram_bot import TitanTelegramBot
from titan.integrations.weather_api import WeatherAPI
from titan.orchestration.daily_coach import DailyCoach


class StubThread:
    def __init__(self, name: str, alive_before_join: bool, alive_after_join: bool):
        self.name = name
        self._alive_before_join = alive_before_join
        self._alive_after_join = alive_after_join
        self.join_calls: list[int] = []

    def join(self, timeout: int = 0):
        self.join_calls.append(timeout)

    def is_alive(self) -> bool:
        if self.join_calls:
            return self._alive_after_join
        return self._alive_before_join


def _build_production_daily_coach(db: DatabaseManager, fixed_today: str) -> DailyCoach:
    return DailyCoach(
        garmin_sync=StubGarminSync(today=fixed_today),
        weather_api=StubWeather(),
        telegram_bot=StubTelegram(),
        hrv_engine=StubSimpleEngine(),
        tsb_engine=StubTSB(),
        readiness_engine=StubReadiness(),
        optimal_time_calc=StubOptimalTime(),
        nutrition_optimizer=StubNutrition(),
        weekly_planner=StubWeeklyPlanner(),
        db=db,
        autonomic_engine=StubAutonomic(),
        cs_tracker=StubCS(),
        glycogen_accum=StubGlycogen(),
        governance=StubGovernance(),
        fatigue_engine=StubFatigue(),
        apl=StubAPL(),
        volume_load_gauge=StubVLG(),
        outcome_tracker=StubOutcomeTracker(),
    )


@pytest.mark.integration
def test_shutdown_safety_invariants_hung_worker_timeout_and_db_close_order(tmp_path, monkeypatch):
    db = DatabaseManager(db_name="e2e_shutdown_safety.db", db_dir=tmp_path)
    coach = _build_production_daily_coach(db=db, fixed_today="2026-03-04")

    garmin = GarminSync()
    weather = WeatherAPI()
    telegram = TitanTelegramBot()

    order: list[str] = []
    telegram_events: list[dict] = []

    garmin._sync_thread = StubThread(name="GarminSync", alive_before_join=True, alive_after_join=False)
    weather._update_thread = StubThread(name="WeatherUpdater", alive_before_join=True, alive_after_join=False)

    # Simulate one deterministic hung worker in Telegram shutdown.
    telegram._sched_thread = StubThread(name="Scheduler", alive_before_join=True, alive_after_join=False)
    telegram._poll_thread = StubThread(name="Polling", alive_before_join=True, alive_after_join=True)

    original_telegram_event = telegram_bot._telegram_event
    monkeypatch.setattr(
        telegram_bot,
        "_telegram_event",
        lambda action, **fields: telegram_events.append({"action": action, **fields}),
    )

    original_garmin_stop = garmin.stop_background_sync
    original_weather_stop = weather.stop_background_updates
    original_telegram_stop = telegram.stop_bot
    original_db_close = db.close

    def _recording_garmin_stop():
        order.append("garmin.stop_background_sync")
        return original_garmin_stop()

    def _recording_weather_stop():
        order.append("weather.stop_background_updates")
        return original_weather_stop()

    def _recording_telegram_stop():
        order.append("telegram.stop_bot")
        return original_telegram_stop()

    def _recording_db_close():
        order.append("db.close")
        return original_db_close()

    monkeypatch.setattr(garmin, "stop_background_sync", _recording_garmin_stop)
    monkeypatch.setattr(weather, "stop_background_updates", _recording_weather_stop)
    monkeypatch.setattr(telegram, "stop_bot", _recording_telegram_stop)
    monkeypatch.setattr(db, "close", _recording_db_close)

    try:
        # Production shutdown path sequence from titan.main.finally
        garmin.stop_background_sync()
        weather.stop_background_updates()
        telegram.stop_bot()
        routine_thread = getattr(coach, "_routine_thread", None)
        if routine_thread is not None and routine_thread.is_alive():
            timeout_seconds = 30
            routine_thread.join(timeout=timeout_seconds)
        db.close()
    finally:
        monkeypatch.setattr(telegram_bot, "_telegram_event", original_telegram_event)

    timeout_events = [event for event in telegram_events if event["action"] == "worker_shutdown_timeout"]

    assert any(
        event["worker_name"] == "Polling"
        and event["timeout_seconds"] == 5
        and event["still_alive"] is True
        for event in timeout_events
    )

    assert order.count("db.close") == 1
    assert order[-1] == "db.close"
    assert order.index("garmin.stop_background_sync") < order.index("db.close")
    assert order.index("weather.stop_background_updates") < order.index("db.close")
    assert order.index("telegram.stop_bot") < order.index("db.close")

    assert garmin._sync_thread.join_calls == [5]
    assert weather._update_thread.join_calls == [5]
    assert telegram._sched_thread.join_calls == [5]
    assert telegram._poll_thread.join_calls == [5]


@pytest.mark.integration
def test_shutdown_safety_no_hung_worker_no_timeout_event(tmp_path, monkeypatch):
    db = DatabaseManager(db_name="e2e_shutdown_safety_no_hang.db", db_dir=tmp_path)
    _build_production_daily_coach(db=db, fixed_today="2026-03-04")

    telegram = TitanTelegramBot()
    telegram._sched_thread = StubThread(name="Scheduler", alive_before_join=True, alive_after_join=False)
    telegram._poll_thread = StubThread(name="Polling", alive_before_join=True, alive_after_join=False)

    telegram_events: list[dict] = []
    monkeypatch.setattr(
        telegram_bot,
        "_telegram_event",
        lambda action, **fields: telegram_events.append({"action": action, **fields}),
    )

    telegram.stop_bot()
    db.close()

    timeout_events = [event for event in telegram_events if event["action"] == "worker_shutdown_timeout"]
    assert timeout_events == []
