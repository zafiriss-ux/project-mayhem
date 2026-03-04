import sqlite3
import threading
import time
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from titan.core.database import DatabaseManager
from titan.integrations.garmin_sync import GarminSync
from titan.integrations.telegram_bot import TitanTelegramBot
from titan.integrations.weather_api import WeatherAPI
from titan.orchestration.daily_coach import DailyCoach


@pytest.mark.timeout(30)
def test_full_lifecycle_stress_all_workers_start_run_stop_cleanly(monkeypatch, tmp_path):
    """T4-13: Start all workers together, run a few scheduler ticks, then stop cleanly."""
    db = DatabaseManager(db_name="stress_test.db", db_dir=tmp_path)

    # Explicitly mocked external integrations (no real network calls)
    garmin = GarminSync(email="user@example.com", password="pw")
    garmin.sync_all = MagicMock(return_value={"activities": [], "sleep": [], "hrv": [], "weight": []})

    weather = WeatherAPI(api_key="dummy", location="Athens,GR")
    weather.get_current_conditions = MagicMock(return_value={"temp_c": 18.0})
    weather.get_hourly_forecast = MagicMock(return_value=[])

    telegram = TitanTelegramBot(bot_token="", chat_id="123")

    # Minimal DailyCoach with fully mocked dependencies except DB
    hrv = MagicMock()
    hrv.hrv_log = []
    hrv.add_hrv_measurement = MagicMock()
    tsb = MagicMock()
    tsb.daily_loads = {}
    tsb.add_daily_load = MagicMock()
    readiness = MagicMock()
    optimal_time = MagicMock()
    nutrition = MagicMock()
    nutrition.analyze_weight_trend.return_value = {"current_weight": 70.0}
    weekly_planner = MagicMock()
    weekly_planner.get_today_session.return_value = {"session_type": "EASY", "duration_min": 30}
    autonomic = MagicMock()
    cs_tracker = MagicMock()
    cs_tracker.confidence = 1.0
    cs_tracker.archetype = "AEROBIC"
    cs_tracker.cs_smoothed = None
    glycogen = MagicMock()
    glycogen.daily_debt = 0.0
    glycogen.status = "OK"
    governance = MagicMock()
    fatigue_engine = MagicMock()
    apl = MagicMock()
    volume_load_gauge = MagicMock()
    outcome_tracker = MagicMock()

    coach = DailyCoach(
        garmin_sync=garmin,
        weather_api=weather,
        telegram_bot=telegram,
        hrv_engine=hrv,
        tsb_engine=tsb,
        readiness_engine=readiness,
        optimal_time_calc=optimal_time,
        nutrition_optimizer=nutrition,
        weekly_planner=weekly_planner,
        db=db,
        autonomic_engine=autonomic,
        cs_tracker=cs_tracker,
        glycogen_accum=glycogen,
        governance=governance,
        fatigue_engine=fatigue_engine,
        apl=apl,
        volume_load_gauge=volume_load_gauge,
        outcome_tracker=outcome_tracker,
    )

    tick_target = 3
    tick_done = threading.Event()
    scheduler_ticks: list[datetime] = []
    routine_starts: list[float] = []
    routine_finishes: list[float] = []
    duplicate_runs: list[int] = []
    programming_errors: list[Exception] = []
    active_runs = 0
    run_lock = threading.Lock()

    def fake_routine():
        nonlocal active_runs
        with run_lock:
            active_runs += 1
            if active_runs > 1:
                duplicate_runs.append(active_runs)
            routine_starts.append(time.monotonic())
        try:
            for _ in range(5):
                now = datetime.now().strftime("%Y-%m-%d")
                db.save_daily_metric(date=now, hrv=45.0, rhr=52, sleep_hours=7.0)
                db.get_training_load_history(days=7)
                time.sleep(0.01)
        except sqlite3.ProgrammingError as exc:
            programming_errors.append(exc)
            raise
        finally:
            with run_lock:
                active_runs -= 1
                routine_finishes.append(time.monotonic())

    coach.run_morning_routine = fake_routine

    def fast_scheduler_worker(self):
        for _ in range(tick_target):
            if self._stop_event.is_set():
                return
            with self._tasks_lock:
                tasks = list(self.scheduled_tasks)
            scheduler_ticks.append(datetime.now())
            for task in tasks:
                task["callback"]()
            if len(scheduler_ticks) >= tick_target:
                tick_done.set()
            self._stop_event.wait(timeout=0.02)
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=0.02)

    monkeypatch.setattr(TitanTelegramBot, "_scheduler_worker", fast_scheduler_worker)

    telegram.schedule_task(
        name="Morning Coaching",
        time_str="07:00",
        callback=coach.run_morning_routine_async,
    )

    try:
        garmin.start_background_sync(interval_hours=1)
        weather.start_background_updates(interval_hours=1)
        telegram.start_bot()

        assert tick_done.wait(timeout=5), "Scheduler did not reach 3 ticks in time"

    finally:
        garmin.stop_background_sync()
        weather.stop_background_updates()
        telegram.stop_bot()

        if coach._routine_thread is not None:
            coach._routine_thread.join(timeout=10)

        db.close()

    if garmin._sync_thread is not None:
        garmin._sync_thread.join(timeout=10)
    if weather._update_thread is not None:
        weather._update_thread.join(timeout=10)
    if telegram._sched_thread is not None:
        telegram._sched_thread.join(timeout=10)

    assert garmin._sync_thread is None or not garmin._sync_thread.is_alive()
    assert weather._update_thread is None or not weather._update_thread.is_alive()
    assert telegram._sched_thread is None or not telegram._sched_thread.is_alive()
    assert coach._routine_thread is None or not coach._routine_thread.is_alive()

    assert len(scheduler_ticks) == tick_target
    assert len(routine_starts) == 1, "T1-07 guard should allow only one routine run while active"
    assert not duplicate_runs, f"Duplicate routine executions detected: {duplicate_runs}"
    assert not programming_errors, f"sqlite3.ProgrammingError observed: {programming_errors}"
