"""The Docker worker must build a real DailyCoach and reach run_morning_routine.

Before this test the worker was covered only by source-grep tests, and every
morning cycle raised TypeError while constructing collaborators (wrong
constructor keywords), which the cycle's generic except swallowed.
"""

import threading
from datetime import UTC, datetime

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
    # After 07:00 UTC, so today's routine is due whenever the suite runs.
    monkeypatch.setattr(worker, "_utc_now", lambda: datetime(2026, 10, 9, 8, 0, tzinfo=UTC))
    monkeypatch.setattr(worker.logging.getLogger("titan.worker.runner"), "exception", _no_cycle_error)

    worker.run_forever(str(tmp_path / "titan_core.db"), shutdown_event=stop)

    assert calls == ["owner"]


@pytest.mark.integration
@pytest.mark.parametrize("env_max_hr", [None, "177"])
def test_worker_uses_the_console_profile_max_hr(worker_db, monkeypatch, env_max_hr):
    """T5-117: worker and console read max HR from one profile, with one default."""
    from titan.core.athlete import UniversalAthleteProfile
    from titan.worker import _build_daily_coach

    if env_max_hr is None:
        monkeypatch.delenv("ATHLETE_MAX_HR", raising=False)
    else:
        monkeypatch.setenv("ATHLETE_MAX_HR", env_max_hr)

    coach = _build_daily_coach(worker_db)

    expected = UniversalAthleteProfile.from_env().max_hr
    assert coach.athlete_max_hr == expected
    assert expected == (191 if env_max_hr is None else 177)


@pytest.mark.integration
def test_worker_refuses_to_start_on_malformed_max_hr(worker_db, tmp_path, monkeypatch):
    from titan import worker

    monkeypatch.setenv("ATHLETE_MAX_HR", "not-a-number")
    monkeypatch.setattr(worker, "_run_backup", lambda db: pytest.fail("worker ran past start-up"))

    with pytest.raises(SystemExit):
        worker.run_forever(str(tmp_path / "titan_core.db"), shutdown_event=threading.Event())
