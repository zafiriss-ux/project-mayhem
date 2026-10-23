"""P4-03 (ADR-0069 §4β): a second morning attempt waits while the first is still running.

The 15-minute gap of D-113 counts from the start of the first attempt; an attempt that runs
longer could be overlapped by the next one, and both would send. Since v34 the attempt in
progress is marked in ``worker_routine_executions``. The mark of a process that is gone (a
worker that crashed and restarted) or older than the attempt's time limit does not hold.
Synthetic data only.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

import titan.worker as worker
from titan.core.database import DatabaseManager

T0 = dt.datetime(2026, 3, 2, 7, 0, tzinfo=dt.UTC)
GAP = dt.timedelta(minutes=15)
BUDGET = dt.timedelta(minutes=30)


def _db(tmp_path: Path) -> DatabaseManager:
    return DatabaseManager(db_name="titan_core.db", db_dir=tmp_path)


def _begin(db: DatabaseManager, at: dt.datetime, runner: str) -> tuple[str, int]:
    return db.begin_routine_attempt(
        athlete_id="owner", execution_date="2026-03-02", routine_type="morning",
        started_at=at, max_attempts=3, retry_gap=GAP, runner=runner, stale_after=BUDGET,
    )


@pytest.mark.unit
def test_a_second_attempt_waits_while_the_first_runs(tmp_path: Path) -> None:
    db = _db(tmp_path)
    try:
        assert _begin(db, T0, "console:aaa") == ("run", 1)
        assert _begin(db, T0 + dt.timedelta(minutes=16), "worker:bbb") == ("wait", 1)
        db.end_routine_attempt(athlete_id="owner", execution_date="2026-03-02", routine_type="morning")
        assert _begin(db, T0 + dt.timedelta(minutes=16), "worker:bbb") == ("run", 2)
    finally:
        db.close()


@pytest.mark.unit
def test_the_mark_of_a_crashed_process_of_the_same_runner_does_not_hold(tmp_path: Path) -> None:
    """A restarted worker continues 15 minutes after the first attempt, as before (D-113)."""
    db = _db(tmp_path)
    try:
        assert _begin(db, T0, "worker:old") == ("run", 1)
        assert _begin(db, T0 + dt.timedelta(minutes=16), "worker:new") == ("run", 2)
    finally:
        db.close()


@pytest.mark.unit
def test_a_mark_older_than_the_time_limit_does_not_hold(tmp_path: Path) -> None:
    db = _db(tmp_path)
    try:
        assert _begin(db, T0, "console:aaa") == ("run", 1)
        assert _begin(db, T0 + dt.timedelta(minutes=29), "worker:bbb") == ("wait", 1)
        assert _begin(db, T0 + dt.timedelta(minutes=31), "worker:bbb") == ("run", 2)
    finally:
        db.close()


@pytest.mark.unit
def test_the_worker_claim_waits_for_the_consoles_running_attempt(tmp_path: Path, monkeypatch) -> None:
    db = _db(tmp_path)
    try:
        monkeypatch.setattr(worker, "_routine_budget_s", lambda: BUDGET.total_seconds())
        assert worker._claim_routine(db, "owner", T0, spaced=True, last_start=False, runner="console") == 1
        later = T0 + dt.timedelta(minutes=16)
        assert worker._claim_routine(db, "owner", later, spaced=True, last_start=False) is False
        worker._end_attempt(db, "owner", "2026-03-02")
        assert worker._claim_routine(db, "owner", later, spaced=True, last_start=False) == 2
    finally:
        db.close()


@pytest.mark.unit
def test_an_attempt_clears_its_mark_when_it_ends(tmp_path: Path, monkeypatch) -> None:
    db = _db(tmp_path)
    try:
        monkeypatch.setattr(worker, "_routine_budget_s", lambda: BUDGET.total_seconds())
        monkeypatch.setattr(worker, "_run_morning", lambda *_a, **_k: False)
        assert worker._claim_routine(db, "owner", T0, spaced=True, last_start=False, runner="console") == 1
        worker._attempt_morning(db, "owner", "2026-03-02", 1)
        row = db.conn.execute(
            "SELECT running_since, running_by FROM worker_routine_executions WHERE athlete_id = 'owner'"
        ).fetchone()
        assert tuple(row) == (None, None)
    finally:
        db.close()
