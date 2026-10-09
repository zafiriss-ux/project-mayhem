"""ADR-0060 D1 / INV-15: the worker's "has today's routine run?" survives a restart.

A restart is a fresh ``run_forever`` (or a fresh scheduler) on the same database
file, with nothing carried over in memory. The claim row in
``worker_routine_executions`` is the only thing that can stop a second morning
routine, and with it a second ``governance_outcomes`` write, on the same day.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest

from titan import worker
from titan.core.database import DatabaseManager

pytestmark = pytest.mark.integration

_MORNING = datetime(2026, 10, 9, 8, 0, tzinfo=UTC)
_NIGHT = datetime(2026, 10, 9, 3, 0, tzinfo=UTC)
_TODAY = "2026-10-09"


class _GovernanceWritingCoach:
    """Stands in for DailyCoach: one routine = one governance_outcomes row."""

    calls: list[str] = []
    after_routine: threading.Event | None = None

    def __init__(self, db: DatabaseManager, athlete_id: str = "owner") -> None:
        self.db = db
        self.athlete_id = athlete_id

    def run_morning_routine(self) -> bool:
        type(self).calls.append(self.athlete_id)
        self.db.save_governance_decision({
            "athlete_profile_id": self.athlete_id,
            "date": _TODAY,
            "session_planned": "EASY",
            "session_post_governance": "EASY",
        })
        if type(self).after_routine is not None:
            type(self).after_routine.set()
        return True


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("TITAN_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TITAN_MULTI_ATHLETE", "")
    monkeypatch.setattr(worker, "_run_backup", lambda db: None)
    monkeypatch.setattr(worker, "_seconds_until_next_run", lambda *a, **k: 0.01)
    monkeypatch.setattr(worker, "_build_daily_coach", _GovernanceWritingCoach)
    _GovernanceWritingCoach.calls = []
    _GovernanceWritingCoach.after_routine = None
    return tmp_path


def _rows(db_file: Path, sql: str) -> list[tuple]:
    conn = sqlite3.connect(db_file)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def _start_worker(data_dir: Path, *, stop_after_routine: bool) -> None:
    """One worker process lifetime: a fresh run_forever on the same file."""
    stop = threading.Event()
    if stop_after_routine:
        _GovernanceWritingCoach.after_routine = stop
    else:
        stop.set()  # nothing should run; leave at the first sleep
    worker.run_forever(str(data_dir / "titan_core.db"), shutdown_event=stop)


def test_restart_does_not_rerun_the_routine_or_double_write_governance(data_dir, monkeypatch):
    monkeypatch.setattr(worker, "_utc_now", lambda: _MORNING)
    db_file = data_dir / "titan_core.db"

    _start_worker(data_dir, stop_after_routine=True)
    _start_worker(data_dir, stop_after_routine=False)  # restart, same day

    assert _GovernanceWritingCoach.calls == ["owner"]
    assert _rows(db_file, "SELECT COUNT(*) FROM governance_outcomes") == [(1,)]
    claims = _rows(db_file, "SELECT athlete_id, execution_date, routine_type, completed_at "
                            "FROM worker_routine_executions")
    assert len(claims) == 1
    assert claims[0][:3] == ("owner", _TODAY, "morning")
    assert claims[0][3] is not None  # the routine returned, so the claim is complete


def test_next_day_runs_again(data_dir, monkeypatch):
    clock = [_MORNING]
    monkeypatch.setattr(worker, "_utc_now", lambda: clock[0])

    _start_worker(data_dir, stop_after_routine=True)
    clock[0] = _MORNING.replace(day=10)
    _start_worker(data_dir, stop_after_routine=True)

    assert _GovernanceWritingCoach.calls == ["owner", "owner"]
    dates = _rows(data_dir / "titan_core.db",
                  "SELECT execution_date FROM worker_routine_executions ORDER BY execution_date")
    assert dates == [("2026-10-09",), ("2026-10-10",)]


def test_before_0700_utc_nothing_is_claimed_or_run(data_dir, monkeypatch):
    monkeypatch.setattr(worker, "_utc_now", lambda: _NIGHT)

    _start_worker(data_dir, stop_after_routine=False)

    assert _GovernanceWritingCoach.calls == []
    assert _rows(data_dir / "titan_core.db", "SELECT COUNT(*) FROM worker_routine_executions") == [(0,)]


def test_a_routine_that_crashed_midway_is_not_retried_and_is_reported(data_dir, monkeypatch, caplog):
    monkeypatch.setattr(worker, "_utc_now", lambda: _MORNING)
    db = DatabaseManager(db_dir=data_dir)
    assert db.claim_routine_execution(
        athlete_id="owner", execution_date=_TODAY, routine_type="morning", started_at=_MORNING
    )
    db.close()

    with caplog.at_level(logging.WARNING, logger="titan.worker.runner"):
        _start_worker(data_dir, stop_after_routine=False)

    assert _GovernanceWritingCoach.calls == []
    incomplete = [r for r in caplog.records if r.getMessage() == "worker_routine_incomplete"]
    assert len(incomplete) == 1
    assert incomplete[0].execution_date == _TODAY


def test_failed_claim_fails_closed_then_retries(tmp_path, monkeypatch, caplog):
    """D1 step 5: a claim error (not a key conflict) skips the cycle with CRITICAL."""

    class _FlakyDb:
        def __init__(self) -> None:
            self.attempts = 0

        def claim_routine_execution(self, **_kwargs) -> bool:
            self.attempts += 1
            if self.attempts == 1:
                raise sqlite3.OperationalError("database is locked")
            return True

    db = _FlakyDb()
    ran: list[str] = []
    monkeypatch.setattr(worker, "_utc_now", lambda: _MORNING)
    monkeypatch.setattr(
        worker, "_run_routine_supervised",
        lambda *a, **k: ran.append(k["execution_date"]),
    )

    with caplog.at_level(logging.CRITICAL, logger="titan.worker.runner"):
        stopped = worker._run_due_routine(db, threading.Event(), tmp_path / "hb", 0.01, 10)

    assert stopped is False
    assert db.attempts == 2
    assert ran == [_TODAY]  # only after the claim succeeded
    assert [r.getMessage() for r in caplog.records] == ["worker_routine_claim_failed"]


def test_failed_claim_never_runs_the_routine_before_stop(tmp_path, monkeypatch):
    class _BrokenDb:
        def claim_routine_execution(self, **_kwargs) -> bool:
            raise sqlite3.OperationalError("disk I/O error")

    stop = threading.Event()
    stop.set()
    monkeypatch.setattr(worker, "_utc_now", lambda: _MORNING)
    monkeypatch.setattr(
        worker, "_run_routine_supervised",
        lambda *a, **k: pytest.fail("routine ran without a claim"),
    )

    assert worker._run_due_routine(_BrokenDb(), stop, tmp_path / "hb", 0.01, 10) is True


def _scheduler_callbacks(db: DatabaseManager, monkeypatch) -> dict:
    """Run _run_with_scheduler once (one process lifetime) and return its callbacks."""
    import titan.orchestration.coaching_scheduler as cs

    registered: dict = {}

    class _FakeScheduler:
        def __init__(self, interval_seconds: float) -> None:
            self._athlete_callbacks = registered

        def register_athlete(self, athlete_id, callback) -> None:  # noqa: ANN001
            registered[athlete_id] = callback

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

    monkeypatch.setattr(cs, "CoachingScheduler", _FakeScheduler)
    monkeypatch.setattr(worker, "_supervise_scheduler", lambda *a, **k: None)
    worker._run_with_scheduler(db, threading.Event())
    return registered


def test_multi_athlete_scheduler_uses_the_durable_claim(data_dir, monkeypatch):
    """D1 step 4: the scheduler's per-day gate survives a restart too."""
    monkeypatch.setattr(worker, "_utc_now", lambda: _MORNING)
    db = DatabaseManager(db_dir=data_dir)

    first = _scheduler_callbacks(db, monkeypatch)
    first["owner"]()
    first["owner"]()  # next 60 s poll, same process
    restarted = _scheduler_callbacks(db, monkeypatch)
    restarted["owner"]()  # same day, new process

    assert _GovernanceWritingCoach.calls == ["owner"]
    assert _rows(data_dir / "titan_core.db", "SELECT COUNT(*) FROM governance_outcomes") == [(1,)]
    db.close()


def test_multi_athlete_scheduler_waits_for_0700_utc(data_dir, monkeypatch):
    monkeypatch.setattr(worker, "_utc_now", lambda: _NIGHT)
    db = DatabaseManager(db_dir=data_dir)

    _scheduler_callbacks(db, monkeypatch)["owner"]()

    assert _GovernanceWritingCoach.calls == []
    assert db.get_incomplete_routine_executions(_TODAY) == []
    db.close()


def test_claim_is_the_insert_itself(tmp_path):
    db = DatabaseManager(db_dir=tmp_path)
    kwargs = {"athlete_id": "owner", "execution_date": _TODAY, "routine_type": "morning"}

    assert db.claim_routine_execution(started_at=_MORNING, **kwargs) is True
    assert db.claim_routine_execution(started_at=_MORNING, **kwargs) is False
    assert db.claim_routine_execution(
        started_at=_MORNING, **{**kwargs, "athlete_id": "athlete-2"}
    ) is True
    assert db.get_incomplete_routine_executions(_TODAY) == [("athlete-2", "morning"), ("owner", "morning")]

    db.complete_routine_execution(completed_at=_MORNING, **kwargs)
    assert db.get_incomplete_routine_executions(_TODAY) == [("athlete-2", "morning")]
    db.close()
