"""Phase 4 step 9a: the crash rule of the morning routine (ADR-0067 D8.2–D8.4; D-098).

- One row per athlete, UTC day and routine; a delivered day is never sent again.
- A crash before delivery is not a finished day: the same UTC day resumes. If that day's
  decision is already in ``governance_outcomes`` it is sent, not computed again.
- After 3 attempts the day is left, with one CRITICAL log and one message to Zaf.
- This holds for the owner too (amends ADR-0060 D1 item 3).
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest

from titan import worker
from titan.core.database import SCHEMA_VERSION, DatabaseManager

pytestmark = pytest.mark.integration

_MORNING = datetime(2026, 10, 9, 8, 0, tzinfo=UTC)
_TODAY = "2026-10-09"


class _Coach:
    """Stands in for DailyCoach. ``delivers`` decides what the routine returns."""

    calls: list[str] = []
    delivers = True
    writes_decision = True
    stop_after: threading.Event | None = None

    def __init__(self, db: DatabaseManager, athlete_id: str = "owner") -> None:
        self.db = db
        self.athlete_id = athlete_id

    def run_morning_routine(self) -> bool:
        type(self).calls.append(self.athlete_id)
        if type(self).writes_decision:
            self.db.save_governance_decision({
                "athlete_profile_id": self.athlete_id, "date": _TODAY,
                "session_planned": "EASY", "session_post_governance": "EASY",
            })
        if type(self).stop_after is not None:
            type(self).stop_after.set()
        return type(self).delivers


class _Bot:
    """Stands in for TitanTelegramBot: records what would reach Telegram."""

    sent: list[tuple[str, str]] = []
    alerts: list[tuple[str, str, str]] = []
    stop_on_alert: threading.Event | None = None

    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        type(self).sent.append((text, parse_mode))
        return True

    def send_alert(self, title: str, message: str, level: str = "warning") -> bool:
        type(self).alerts.append((title, message, level))
        if type(self).stop_on_alert is not None:
            type(self).stop_on_alert.set()
        return True


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    import titan.integrations.telegram_bot as telegram_bot

    monkeypatch.setenv("TITAN_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TITAN_MULTI_ATHLETE", "")
    monkeypatch.setattr(worker, "_run_backup", lambda db: None)
    monkeypatch.setattr(worker, "_seconds_until_next_run", lambda *a, **k: 0.01)
    monkeypatch.setattr(worker, "ROUTINE_RETRY_DELAY_S", 0.01)
    monkeypatch.setattr(worker, "_utc_now", lambda: _MORNING)
    monkeypatch.setattr(worker, "_build_daily_coach", _Coach)
    monkeypatch.setattr(telegram_bot, "TitanTelegramBot", _Bot)
    _Coach.calls, _Coach.delivers, _Coach.writes_decision, _Coach.stop_after = [], True, True, None
    _Bot.sent, _Bot.alerts, _Bot.stop_on_alert = [], [], None
    return tmp_path


def _rows(data_dir: Path, sql: str) -> list[tuple]:
    conn = sqlite3.connect(data_dir / "titan_core.db")
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def _day(data_dir: Path) -> list[tuple]:
    return _rows(data_dir, "SELECT attempts, delivered_at IS NOT NULL, completed_at IS NOT NULL "
                           "FROM worker_routine_executions")


def _start_worker(data_dir: Path, stop: threading.Event | None = None) -> None:
    """One worker process lifetime on the same file. Without ``stop``, it leaves at the first sleep."""
    if stop is None:
        stop = threading.Event()
        stop.set()
    worker.run_forever(str(data_dir / "titan_core.db"), shutdown_event=stop)


def _attempts_taken(data_dir: Path, n: int, *, decision: bool) -> None:
    """A previous worker took ``n`` attempts and died; with ``decision``, after storing the day's decision."""
    db = DatabaseManager(db_dir=data_dir)
    for _ in range(n):
        db.begin_routine_attempt(athlete_id="owner", execution_date=_TODAY, routine_type="morning",
                                 started_at=_MORNING, max_attempts=3)
    if decision:
        db.save_governance_decision({
            "athlete_profile_id": "owner", "date": _TODAY, "session_planned": "TEMPO",
            "session_post_governance": "EASY", "locks_applied": ["H2_HRV_DROP"],
        })
    db.close()


def test_a_crash_after_the_decision_sends_the_stored_one_and_writes_nothing_twice(data_dir) -> None:
    _attempts_taken(data_dir, 1, decision=True)

    _start_worker(data_dir)

    assert _Coach.calls == []  # not computed again
    assert _rows(data_dir, "SELECT COUNT(*) FROM governance_outcomes") == [(1,)]
    [(text, parse_mode)] = _Bot.sent
    assert "EASY" in text and "H2_HRV_DROP" in text and "TEMPO" not in text
    assert parse_mode == ""  # session and lock names with "_" are sent as plain text
    assert _day(data_dir) == [(2, 1, 1)]

    _start_worker(data_dir)  # the delivered day is never sent again
    assert len(_Bot.sent) == 1


def test_a_crash_before_the_decision_runs_the_routine_again(data_dir) -> None:
    _attempts_taken(data_dir, 1, decision=False)
    stop = threading.Event()
    _Coach.stop_after = stop

    _start_worker(data_dir, stop)

    assert _Coach.calls == ["owner"]
    assert _rows(data_dir, "SELECT COUNT(*) FROM governance_outcomes") == [(1,)]
    assert _day(data_dir) == [(2, 1, 1)]


def test_an_undelivered_day_is_tried_three_times_then_left_with_one_message(data_dir, caplog) -> None:
    _Coach.delivers, _Coach.writes_decision = False, False
    stop = threading.Event()
    _Bot.stop_on_alert = stop

    with caplog.at_level(logging.CRITICAL, logger="titan.worker.runner"):
        _start_worker(data_dir, stop)

    assert _Coach.calls == ["owner"] * 3
    [(title, message, level)] = _Bot.alerts
    assert level == "critical" and "owner" in message and _TODAY in message
    assert [r.getMessage() for r in caplog.records].count("worker_routine_left") == 1
    assert _day(data_dir) == [(3, 0, 1)]

    _start_worker(data_dir)  # restart, same day: no fourth attempt, no second message
    assert len(_Coach.calls) == 3 and len(_Bot.alerts) == 1


def test_a_failed_send_of_the_stored_decision_is_another_attempt(data_dir, monkeypatch) -> None:
    _attempts_taken(data_dir, 2, decision=True)
    monkeypatch.setattr(_Bot, "send_message", lambda self, text, parse_mode="Markdown": False)

    _start_worker(data_dir)

    assert _Coach.calls == []
    assert len(_Bot.alerts) == 1  # the third attempt did not deliver: the day is left
    assert _rows(data_dir, "SELECT COUNT(*) FROM governance_outcomes") == [(1,)]
    assert _day(data_dir) == [(3, 0, 1)]


def test_a_crash_on_the_last_attempt_leaves_the_day_once(data_dir) -> None:
    _attempts_taken(data_dir, 3, decision=False)

    _start_worker(data_dir)
    _start_worker(data_dir)

    assert _Coach.calls == []
    assert len(_Bot.alerts) == 1
    assert _day(data_dir) == [(3, 0, 1)]


def test_the_scheduler_follows_the_same_rule(data_dir) -> None:
    _Coach.delivers, _Coach.writes_decision = False, False
    db = DatabaseManager(db_dir=data_dir)

    for _ in range(5):  # five 60 s polls of the same day
        worker._scheduled_morning(db, "owner")

    assert _Coach.calls == ["owner"] * 3
    assert len(_Bot.alerts) == 1
    db.close()
    assert _day(data_dir) == [(3, 0, 1)]


@pytest.mark.unit
def test_v31_gives_old_rows_one_attempt_and_keeps_their_state(tmp_path) -> None:
    db = DatabaseManager(db_dir=tmp_path)
    db.close()
    raw = sqlite3.connect(tmp_path / "titan_core.db")
    raw.execute("DROP TABLE worker_routine_executions")
    raw.execute("""CREATE TABLE worker_routine_executions (
        athlete_id TEXT NOT NULL, execution_date TEXT NOT NULL, routine_type TEXT NOT NULL,
        started_at TEXT NOT NULL, completed_at TEXT,
        PRIMARY KEY (athlete_id, execution_date, routine_type))""")
    raw.execute("INSERT INTO worker_routine_executions VALUES "
                "('owner', '2026-10-08', 'morning', '2026-10-08T07:00:00+00:00', '2026-10-08T07:01:00+00:00'), "
                "('owner', '2026-10-09', 'morning', '2026-10-09T07:00:00+00:00', NULL)")
    raw.execute("PRAGMA user_version = 30")
    raw.commit()
    raw.close()

    db = DatabaseManager(db_dir=tmp_path)
    try:
        assert db.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 31
        rows = db.conn.execute(
            "SELECT execution_date, attempts, delivered_at, completed_at IS NOT NULL "
            "FROM worker_routine_executions ORDER BY execution_date"
        ).fetchall()
        assert rows == [("2026-10-08", 1, None, 1), ("2026-10-09", 1, None, 0)]
        kwargs = {"athlete_id": "owner", "routine_type": "morning", "started_at": _MORNING, "max_attempts": 3}
        assert db.begin_routine_attempt(execution_date="2026-10-08", **kwargs) == ("closed", 1)
        assert db.begin_routine_attempt(execution_date="2026-10-09", **kwargs) == ("run", 2)
    finally:
        db.close()
