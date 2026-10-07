"""The Docker worker must build a real DailyCoach and reach run_morning_routine.

Before this test the worker was covered only by source-grep tests, and every
morning cycle raised TypeError while constructing collaborators (wrong
constructor keywords), which the cycle's generic except swallowed.
"""

import threading

import pytest

from titan.core.database import DatabaseManager
from titan.orchestration.daily_coach import DailyCoach


@pytest.fixture
def worker_db(tmp_path, monkeypatch):
    monkeypatch.setenv("TITAN_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    return DatabaseManager(db_dir=tmp_path)


@pytest.mark.integration
def test_build_daily_coach_returns_wired_coach(worker_db):
    from titan.worker import _build_daily_coach

    coach = _build_daily_coach(worker_db)

    assert isinstance(coach, DailyCoach)
    assert coach.db is worker_db
    assert coach.athlete_id == "owner"
    assert coach.hrv_engine is coach.engines.hrv
    assert coach.weekly_planner.hrv_engine is coach.engines.hrv


@pytest.mark.integration
def test_build_daily_coach_scopes_engines_to_athlete(worker_db):
    from titan.worker import _build_daily_coach

    coach = _build_daily_coach(worker_db, athlete_id="athlete-2")

    assert coach.athlete_id == "athlete-2"


@pytest.mark.integration
def test_run_forever_reaches_morning_routine(worker_db, tmp_path, monkeypatch):
    from titan import worker

    stop = threading.Event()
    calls: list[str] = []

    def _fake_routine(self):
        calls.append(self.athlete_id)
        stop.set()

    def _no_cycle_error(*_args, **_kwargs):
        raise AssertionError("worker_cycle_error: coach construction failed")

    monkeypatch.setattr(DailyCoach, "run_morning_routine", _fake_routine)
    monkeypatch.setattr(worker, "_run_backup", lambda db: None)
    monkeypatch.setattr(worker, "_seconds_until_next_run", lambda *a, **k: 0.01)
    monkeypatch.setattr(worker.logging.getLogger("titan.worker.runner"), "exception", _no_cycle_error)

    worker.run_forever(str(tmp_path / "titan_core.db"), shutdown_event=stop)

    assert calls == ["owner"]
