"""P27-B5: CoachingScheduler athlete callback must gate to once-per-day at 07:00 UTC.

Without the gate, CoachingScheduler's 60s poll loop would invoke
DailyCoach.run_morning_routine() on every tick — risking a Garmin ban and
corpus poisoning. These tests exercise the registered callback directly,
mirroring the single-athlete while-True loop's daily cadence semantics.
"""

import datetime as _real_dt
import threading

import pytest

import titan.worker as worker_module


class _FakeDateTime:
    current: _real_dt.datetime

    @classmethod
    def now(cls, tz=None):  # noqa: ANN001
        return cls.current


class _FakeDtModule:
    datetime = _FakeDateTime
    UTC = _real_dt.UTC


class _Inert:
    def __init__(self, *args, **kwargs):
        pass


class _FakeEngineRegistry:
    @classmethod
    def from_db(cls, db=None, athlete_id=None):  # noqa: ANN001
        return cls()


class _FakeDailyCoach:
    run_count = 0

    def __init__(self, **kwargs):
        pass

    def run_morning_routine(self):
        _FakeDailyCoach.run_count += 1


class _CapturingScheduler:
    last_instance = None

    def __init__(self, interval_seconds: float = 60.0) -> None:
        self._athlete_callbacks: dict = {}
        _CapturingScheduler.last_instance = self

    def register_athlete(self, athlete_id, callback):  # noqa: ANN001
        self._athlete_callbacks[athlete_id] = callback

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


@pytest.fixture(autouse=True)
def _patch_dependencies(monkeypatch):
    monkeypatch.setattr(worker_module, "_dt", _FakeDtModule)
    monkeypatch.setattr("titan.integrations.garmin_sync.GarminSync", _Inert)
    monkeypatch.setattr("titan.integrations.weather_api.WeatherAPI", _Inert)
    monkeypatch.setattr("titan.integrations.telegram_bot.TitanTelegramBot", _Inert)
    monkeypatch.setattr("titan.orchestration.engine_registry.EngineRegistry", _FakeEngineRegistry)
    monkeypatch.setattr("titan.features.optimal_time_calculator.OptimalTimeCalculator", _Inert)
    monkeypatch.setattr("titan.features.nutrition_optimizer.NutritionOptimizer", _Inert)
    monkeypatch.setattr("titan.features.weekly_planner.WeeklyPlanGenerator", _Inert)
    monkeypatch.setattr("titan.orchestration.daily_coach.DailyCoach", _FakeDailyCoach)
    monkeypatch.setattr("titan.orchestration.coaching_scheduler.CoachingScheduler", _CapturingScheduler)
    _FakeDailyCoach.run_count = 0
    _CapturingScheduler.last_instance = None


def _registered_owner_callback():
    stop_event = threading.Event()
    stop_event.set()  # _run_with_scheduler returns as soon as it observes stop
    worker_module._run_with_scheduler(db=object(), stop_event=stop_event)
    return _CapturingScheduler.last_instance._athlete_callbacks["owner"]


@pytest.mark.unit
def test_callback_skips_before_0700_utc():
    callback = _registered_owner_callback()
    _FakeDateTime.current = _real_dt.datetime(2026, 6, 8, 6, 59, tzinfo=_real_dt.UTC)

    callback()

    assert _FakeDailyCoach.run_count == 0


@pytest.mark.unit
def test_callback_runs_once_at_0700_then_skips_rest_of_day():
    callback = _registered_owner_callback()
    _FakeDateTime.current = _real_dt.datetime(2026, 6, 8, 7, 0, tzinfo=_real_dt.UTC)

    callback()  # fires
    callback()  # same minute — already ran today
    _FakeDateTime.current = _real_dt.datetime(2026, 6, 8, 23, 59, tzinfo=_real_dt.UTC)
    callback()  # later same calendar day — still gated

    assert _FakeDailyCoach.run_count == 1


@pytest.mark.unit
def test_callback_fires_again_on_next_calendar_day():
    callback = _registered_owner_callback()

    _FakeDateTime.current = _real_dt.datetime(2026, 6, 8, 7, 5, tzinfo=_real_dt.UTC)
    callback()
    _FakeDateTime.current = _real_dt.datetime(2026, 6, 9, 7, 5, tzinfo=_real_dt.UTC)
    callback()

    assert _FakeDailyCoach.run_count == 2
