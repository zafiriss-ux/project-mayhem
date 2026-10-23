"""ADR-0060 / INV-15, INV-17: worker routine claims and override nonces survive a restart.

A restart is a fresh ``run_forever`` (or a fresh scheduler) on the same database
file, with nothing carried over in memory. The claim row in
``worker_routine_executions`` is the only thing that can stop a second morning
routine, and with it a second ``governance_outcomes`` write, on the same day.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
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
    assert claims[0][3] is not None  # the routine delivered, so the day is closed
    assert _rows(db_file, "SELECT attempts, delivered_at IS NOT NULL FROM worker_routine_executions") == [(1, 1)]


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


def test_a_routine_that_crashed_midway_is_reported_and_resumes(data_dir, monkeypatch, caplog):
    """ADR-0067 D8.4 (amends ADR-0060 D1 item 3): a crash before delivery is not a finished day.

    The restarted worker resumes once the retry gap after the crashed attempt has passed (D-113).
    """
    monkeypatch.setattr(worker, "_utc_now", lambda: _MORNING + timedelta(seconds=worker.ROUTINE_RETRY_DELAY_S))
    db = DatabaseManager(db_dir=data_dir)
    assert db.begin_routine_attempt(
        athlete_id="owner", execution_date=_TODAY, routine_type="morning", started_at=_MORNING, max_attempts=3
    ) == ("run", 1)
    db.close()

    with caplog.at_level(logging.WARNING, logger="titan.worker.runner"):
        _start_worker(data_dir, stop_after_routine=True)

    assert _GovernanceWritingCoach.calls == ["owner"]
    incomplete = [r for r in caplog.records if r.getMessage() == "worker_routine_incomplete"]
    assert len(incomplete) == 1
    assert incomplete[0].execution_date == _TODAY
    assert _rows(data_dir / "titan_core.db", "SELECT attempts, delivered_at IS NOT NULL "
                                             "FROM worker_routine_executions") == [(2, 1)]


def test_failed_claim_fails_closed_then_retries(tmp_path, monkeypatch, caplog):
    """D1 step 5: a claim error (not a key conflict) skips the cycle with CRITICAL."""

    class _FlakyDb:
        def __init__(self) -> None:
            self.attempts = 0

        def begin_routine_attempt(self, **_kwargs) -> tuple[str, int]:
            self.attempts += 1
            if self.attempts == 1:
                raise sqlite3.OperationalError("database is locked")
            return "run", 1

    db = _FlakyDb()
    ran: list[str] = []
    monkeypatch.setattr(worker, "_utc_now", lambda: _MORNING)
    monkeypatch.setattr(
        worker, "_run_routine_supervised",
        lambda *a, **k: ran.append(k["execution_date"]) or True,
    )

    with caplog.at_level(logging.CRITICAL, logger="titan.worker.runner"):
        stopped = worker._run_due_routine(db, threading.Event(), tmp_path / "hb", 0.01, 10)

    assert stopped is False
    assert db.attempts == 2
    assert ran == [_TODAY]  # only after the claim succeeded
    assert [r.getMessage() for r in caplog.records] == ["worker_routine_claim_failed"]


def test_failed_claim_never_runs_the_routine_before_stop(tmp_path, monkeypatch):
    class _BrokenDb:
        def begin_routine_attempt(self, **_kwargs) -> tuple[str, int]:
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
    monkeypatch.setattr(worker, "_run_attempt", worker._attempt_morning)  # in-process stand-in coach
    worker._run_with_scheduler(db, threading.Event())
    return registered


def test_multi_athlete_scheduler_uses_the_durable_claim(data_dir, monkeypatch):
    """D1 step 4: the scheduler's per-day gate survives a restart too."""
    monkeypatch.setattr(worker, "_utc_now", lambda: _MORNING)
    db = DatabaseManager(db_dir=data_dir)

    first = _scheduler_callbacks(db, monkeypatch)
    first["round"]()
    first["round"]()  # next 60 s poll, same process
    restarted = _scheduler_callbacks(db, monkeypatch)
    restarted["round"]()  # same day, new process

    assert _GovernanceWritingCoach.calls == ["owner"]
    assert _rows(data_dir / "titan_core.db", "SELECT COUNT(*) FROM governance_outcomes") == [(1,)]
    db.close()


def test_multi_athlete_scheduler_waits_for_0700_utc(data_dir, monkeypatch):
    monkeypatch.setattr(worker, "_utc_now", lambda: _NIGHT)
    db = DatabaseManager(db_dir=data_dir)

    _scheduler_callbacks(db, monkeypatch)["round"]()

    assert _GovernanceWritingCoach.calls == []
    assert db.get_incomplete_routine_executions(_TODAY) == []
    db.close()


def test_one_row_per_athlete_day_and_routine_counts_the_attempts(tmp_path):
    """ADR-0067 D8.2, D8.4: the row is the claim; each attempt is counted before it runs."""
    db = DatabaseManager(db_dir=tmp_path)
    kwargs = {"athlete_id": "owner", "execution_date": _TODAY, "routine_type": "morning",
              "started_at": _MORNING, "max_attempts": 3}

    assert [db.begin_routine_attempt(**kwargs) for _ in range(4)] == [
        ("run", 1), ("run", 2), ("run", 3), ("exhausted", 3)
    ]
    assert db.begin_routine_attempt(**{**kwargs, "athlete_id": "athlete-2"}) == ("run", 1)
    assert db.get_incomplete_routine_executions(_TODAY) == [("athlete-2", "morning"), ("owner", "morning")]

    db.complete_routine_execution(athlete_id="owner", execution_date=_TODAY, routine_type="morning",
                                  completed_at=_MORNING)
    assert db.begin_routine_attempt(**kwargs) == ("closed", 3)
    db.mark_routine_delivered(athlete_id="athlete-2", execution_date=_TODAY, routine_type="morning",
                              delivered_at=_MORNING)
    assert db.begin_routine_attempt(**{**kwargs, "athlete_id": "athlete-2"}) == ("closed", 1)
    assert db.get_incomplete_routine_executions(_TODAY) == []
    db.close()


# ── ADR-0060 D2 / INV-17: override nonces survive a restart ────────────────────


def test_override_nonce_survives_a_restart_and_is_used_once(tmp_path, monkeypatch):
    """Issued by one bot process, consumed by a fresh one on the same file."""
    from titan.integrations import telegram_bot as tb

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    issuer_db = DatabaseManager(db_dir=tmp_path)
    nonce = tb._create_override_nonce(issuer_db, "dec-7", "owner")
    issuer_db.close()  # the process that sent the button is gone

    restarted = tb.TitanTelegramBot(bot_token="", chat_id=123, db=DatabaseManager(db_dir=tmp_path))
    restarted._prune_expired_override_nonces()  # startup prune keeps unexpired nonces

    assert restarted.process_override_callback(123, f"override:accept:{nonce}") == "✅ Decision accepted."
    replay = tb.TitanTelegramBot(bot_token="", chat_id=123, db=DatabaseManager(db_dir=tmp_path))
    assert "already been used or has expired" in replay.process_override_callback(
        123, f"override:accept:{nonce}"
    )


def test_startup_prunes_only_expired_nonces(tmp_path):
    db = DatabaseManager(db_dir=tmp_path)
    for nonce, offset in (("old", -60), ("fresh", 60)):
        db.issue_override_nonce(
            nonce=nonce, command_type="override", athlete_id="owner", decision_id=f"d-{nonce}",
            issued_at=_MORNING, expires_at=_MORNING.replace(second=0) + timedelta(seconds=offset),
        )

    assert db.prune_expired_override_nonces(_MORNING) == 1
    assert _rows(tmp_path / "titan_core.db", "SELECT nonce FROM telegram_override_nonces") == [("fresh",)]
    db.close()


def test_without_a_stored_nonce_no_override_button_is_sent(tmp_path, monkeypatch, caplog):
    from titan.integrations import telegram_bot as tb

    bot = tb.TitanTelegramBot(bot_token="", chat_id=123, db=None)
    sent: list[str] = []
    bot.bot = object()  # a polling backend is present
    monkeypatch.setattr(tb, "TELEBOT_AVAILABLE", True)
    monkeypatch.setattr(bot, "send_message", lambda text, **_k: sent.append(text) or True)

    with caplog.at_level(logging.CRITICAL):
        assert bot.send_governance_decision(
            text="Hard stop", decision_id="d-1", decision_type="HARD_STOP", athlete_id="owner"
        ) is True

    assert sent == ["Hard stop"]  # plain message, no Accept/Override keyboard
    assert "telegram_override_nonce_unavailable" in [r.getMessage() for r in caplog.records]
