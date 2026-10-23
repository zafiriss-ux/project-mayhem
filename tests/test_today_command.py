"""OW-F4 (D-128): the console's /today never writes a second decision for the owner's day.

With today's decision stored, /today sends it again and writes nothing. Without one, the
audit row comes first (INV-22), then the day is claimed and run as the scheduled morning
runs it. Two /today the same day leave one ``governance_outcomes`` row and one audit row.
Synthetic data only.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from titan import main as titan_main
from titan import worker

_NOW = datetime(2026, 10, 23, 8, 0, tzinfo=UTC)
_DAY = "2026-10-23"


def _decision() -> dict:
    return {
        "date": _DAY, "session_planned": "TEMPO", "session_post_governance": "EASY",
        "locks_applied": ["HARD_STOP_ACWR"], "governance_clean": False, "phase": "BUILD",
        "vlg_color": "YELLOW", "apl_priority_vector": {}, "lock_thresholds_active": {},
        "acwr": 1.4, "tsb_value": -10.0, "readiness_score": 55.0, "glycogen_debt": 2.0,
    }


class _Chat:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.sent: list[str] = []

    def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        self.sent.append(text)
        return self.ok


@pytest.fixture
def setup(db_manager_factory, monkeypatch):
    db = db_manager_factory(db_name="test.db")
    chat = _Chat()
    runs: list[int] = []

    def _morning(db_, athlete_id, execution_date, attempt):
        # The scheduled morning's attempt: it records the day's one decision and delivers.
        runs.append(attempt)
        db_.save_governance_decision(_decision())
        return True

    monkeypatch.setattr(worker, "_utc_now", lambda: _NOW)
    monkeypatch.setattr(worker, "_athlete_telegram", lambda db_, athlete_id: chat)
    monkeypatch.setattr(worker, "_attempt_morning", _morning)
    return SimpleNamespace(db=db, chat=chat, runs=runs, lock=threading.Lock())


def _governance_rows(db) -> int:
    return db.conn.execute(
        "SELECT COUNT(*) FROM governance_outcomes WHERE athlete_id = 'owner' AND date = ?", (_DAY,)
    ).fetchone()[0]


def _audit_rows(db) -> list[dict]:
    return db.get_coach_audit_log(coach_id="console:/today")


def _today_command(setup):
    telegram = SimpleNamespace(
        commands={}, register_command=lambda name, cb: telegram.commands.__setitem__(name, cb),
        register_athlete_command=lambda name, cb: None,
    )
    coach = SimpleNamespace(routine_lock=setup.lock, run_morning_routine=lambda: setup.db.save_governance_decision(_decision()))
    titan_main._register_telegram_callbacks(telegram, {"daily_coach": coach, "db": setup.db})
    return telegram.commands["today"]


def test_two_today_commands_leave_one_decision_and_one_audit_row(setup):
    today = _today_command(setup)
    first, second = today(), today()
    assert _governance_rows(setup.db) == 1
    assert len(_audit_rows(setup.db)) == 1
    assert first.startswith("✅") and second.startswith("✅")
    assert setup.runs == [1]
    assert "/today" in setup.chat.sent[-1] and "EASY" in setup.chat.sent[-1]


def test_a_stored_decision_is_sent_again_and_nothing_is_written(setup):
    setup.db.save_governance_decision(_decision())
    assert worker.run_owner_today(setup.db, setup.lock) == "resent"
    assert _governance_rows(setup.db) == 1
    assert _audit_rows(setup.db) == []
    assert setup.runs == []
    assert "Locks: HARD_STOP_ACWR" in setup.chat.sent[0]


def test_without_a_decision_the_audit_row_comes_before_the_claimed_run(setup, monkeypatch):
    seen: list[int] = []
    real = worker._attempt_morning

    def _checking(db_, athlete_id, execution_date, attempt):
        seen.append(len(_audit_rows(db_)))
        return real(db_, athlete_id, execution_date, attempt)

    monkeypatch.setattr(worker, "_attempt_morning", _checking)
    assert worker.run_owner_today(setup.db, setup.lock) == "delivered"
    assert seen == [1]
    assert _audit_rows(setup.db)[0]["action_type"] == "TELEGRAM_TODAY"


def test_an_audit_failure_runs_nothing(setup, monkeypatch):
    def _broken(**_kwargs):
        raise RuntimeError("audit store down")

    monkeypatch.setattr(setup.db, "log_coach_action", _broken)
    assert worker.run_owner_today(setup.db, setup.lock) == "audit_failed"
    assert setup.runs == []
    assert _governance_rows(setup.db) == 0
    assert setup.db.get_routine_resume(athlete_id="owner", execution_date=_DAY, routine_type=worker.ROUTINE_MORNING) == {}


def test_a_running_morning_is_not_started_twice(setup):
    setup.lock.acquire()
    try:
        assert worker.run_owner_today(setup.db, setup.lock) == "busy"
    finally:
        setup.lock.release()
    assert setup.runs == [] and _audit_rows(setup.db) == []


def test_a_failed_send_is_reported(setup):
    setup.db.save_governance_decision(_decision())
    setup.chat.ok = False
    today = _today_command(setup)
    assert today().startswith("❌")
    assert not setup.lock.locked()
