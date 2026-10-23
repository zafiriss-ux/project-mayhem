"""M0-01 / M0-18: an attempt that outlives its time limit cannot send or record over a later one.

The "attempt in progress" mark stops holding after ``WORKER_ROUTINE_BUDGET_S``, while the
owner's routine thread is never abandoned. A later attempt can then take the day over. The
attempt number is the fencing token: only the day's latest attempt, on an open day, records
a decision or sends a briefing, and an attempt clears only its own mark. A delivery is
recorded before the mark is cleared (M0-18). Synthetic data only.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from types import SimpleNamespace

import pytest

import titan.worker as worker
from titan.core.database import DatabaseManager
from titan.orchestration.daily_coach import DailyCoach
from titan.science.outcome_tracker import OutcomeTracker

DAY = "2026-03-02"
T0 = dt.datetime(2026, 3, 2, 7, 0, tzinfo=dt.UTC)
BUDGET = dt.timedelta(minutes=30)


def _db(tmp_path: Path) -> DatabaseManager:
    return DatabaseManager(db_name="titan_core.db", db_dir=tmp_path)


def _begin(db: DatabaseManager, at: dt.datetime, runner: str) -> tuple[str, int]:
    return db.begin_routine_attempt(
        athlete_id="owner", execution_date=DAY, routine_type="morning",
        started_at=at, max_attempts=3, runner=runner, stale_after=BUDGET,
    )


def _row(db: DatabaseManager) -> tuple:
    return tuple(db.conn.execute(
        "SELECT attempts, running_by, delivered_at IS NOT NULL, completed_at IS NOT NULL "
        "FROM worker_routine_executions WHERE athlete_id = 'owner' AND execution_date = ?", (DAY,),
    ).fetchone())


@pytest.mark.unit
def test_an_attempt_clears_only_its_own_mark(tmp_path: Path) -> None:
    db = _db(tmp_path)
    try:
        assert _begin(db, T0, "worker:aaa") == ("run", 1)
        assert _begin(db, T0 + BUDGET + dt.timedelta(minutes=1), "console:bbb") == ("run", 2)
        # Attempt 1 ends late: attempt 2's mark stays, so a third runner still waits.
        db.end_routine_attempt(athlete_id="owner", execution_date=DAY, routine_type="morning", attempt=1)
        assert _row(db)[1] == "console:bbb"
        assert _begin(db, T0 + BUDGET + dt.timedelta(minutes=2), "worker:ccc") == ("wait", 2)
    finally:
        db.close()


@pytest.mark.unit
def test_only_the_latest_attempt_of_an_open_day_is_current(tmp_path: Path) -> None:
    db = _db(tmp_path)
    try:
        def current(n: int) -> bool:
            return db.routine_attempt_is_current(
                athlete_id="owner", execution_date=DAY, routine_type="morning", attempt=n,
            )

        assert current(1) is False  # no row yet
        _begin(db, T0, "worker:aaa")
        assert current(1) is True
        _begin(db, T0 + BUDGET + dt.timedelta(minutes=1), "console:bbb")
        assert (current(1), current(2)) == (False, True)
        db.mark_routine_delivered(
            athlete_id="owner", execution_date=DAY, routine_type="morning", delivered_at=T0 + BUDGET,
        )
        assert current(2) is False  # a delivered day is closed
    finally:
        db.close()


class _Telegram:
    def __init__(self, sent: list[dict]) -> None:
        self.sent = sent

    def send_daily_coaching(self, payload: dict) -> bool:
        self.sent.append(payload)
        return True


class _Coach:
    """A stand-in coach that runs DailyCoach's own record and send handlers."""

    def __init__(self, db: DatabaseManager, session: str, sent: list[dict], meanwhile=None) -> None:  # noqa: ANN001
        self.athlete_id = "owner"
        self.garmin = None
        self.telegram = _Telegram(sent)
        self.outcome_tracker = OutcomeTracker(db=db, athlete_id="owner")
        self._session = session
        self._meanwhile = meanwhile

    def run_morning_routine(self) -> bool:
        if self._meanwhile is not None:
            self._meanwhile()  # another attempt takes the day over while this one computes
        result = SimpleNamespace(
            decision_trace={"session_planned_pre_governance": self._session,
                            "session_post_governance": self._session},
            session_plan={"session_type": self._session},
            coaching_payload={"session": self._session},
        )
        DailyCoach._make_record_outcome_handler(self)(None, result)
        return DailyCoach._make_send_telegram_handler(self)(None, result)


@pytest.mark.integration
def test_an_overrunning_attempt_neither_records_nor_sends_over_the_attempt_that_took_over(
    tmp_path: Path, monkeypatch,
) -> None:
    """The audit's scenario: A runs past the time limit, B takes the day over and delivers.

    One briefing goes out, B's, and the stored decision is the one B delivered.
    """
    db_a, db_b = _db(tmp_path), _db(tmp_path)
    sent: list[dict] = []
    coaches: dict[int, _Coach] = {}

    def b_takes_over() -> None:
        assert _begin(db_b, T0 + BUDGET + dt.timedelta(minutes=1), "console:bbb") == ("run", 2)
        assert worker._attempt_morning(db_b, "owner", DAY, 2) is True

    coaches[id(db_a)] = _Coach(db_a, "TEMPO", sent, meanwhile=b_takes_over)
    coaches[id(db_b)] = _Coach(db_b, "EASY", sent)
    monkeypatch.setattr(worker, "_build_daily_coach", lambda db, athlete_id: coaches[id(db)])
    monkeypatch.setattr(worker, "_prepare_weekly_plan", lambda *_a, **_k: None)
    monkeypatch.setattr(worker, "_plan_next_week_on_sunday", lambda *_a, **_k: None)
    monkeypatch.setattr(worker, "_record_garmin_token_state", lambda *_a, **_k: None)
    try:
        assert _begin(db_a, T0, "worker:aaa") == ("run", 1)

        assert worker._attempt_morning(db_a, "owner", DAY, 1) is False

        assert sent == [{"session": "EASY", "briefing_date": DAY}]
        assert db_a.get_governance_decision_on("owner", DAY)["session_post_governance"] == "EASY"
        assert _row(db_a)[:3] == (2, None, True)  # attempt 2 delivered it; its mark is cleared
    finally:
        db_a.close()
        db_b.close()


@pytest.mark.unit
def test_a_failing_check_sends_nothing() -> None:
    """Fail closed: when the worker cannot tell whether its attempt owns the day."""
    sent: list[dict] = []

    def broken() -> bool:
        raise RuntimeError("database is locked")

    coach = SimpleNamespace(telegram=_Telegram(sent), attempt_is_current=broken, routine_date=DAY)
    result = SimpleNamespace(coaching_payload={"session": "EASY"})
    assert DailyCoach._make_send_telegram_handler(coach)(None, result) is False
    assert sent == []


@pytest.mark.unit
def test_a_delivery_is_recorded_before_the_mark_is_cleared(tmp_path: Path, monkeypatch) -> None:
    """M0-18: cleared first, the day had no mark and no delivery, and the next attempt could
    claim it and send it again."""
    db = _db(tmp_path)
    order: list[str] = []
    monkeypatch.setattr(worker, "_run_morning", lambda *_a, **_k: True)
    monkeypatch.setattr(worker, "_mark_delivered", lambda *_a, **_k: order.append("delivered") or True)
    monkeypatch.setattr(worker, "_end_attempt", lambda *_a, **_k: order.append("mark cleared"))
    try:
        assert _begin(db, T0, "worker:aaa") == ("run", 1)
        assert worker._attempt_morning(db, "owner", DAY, 1) is True
        assert order == ["delivered", "mark cleared"]
    finally:
        db.close()
