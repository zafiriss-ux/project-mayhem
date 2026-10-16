"""Phase 4 step 9b: the worker runs every ready athlete (ADR-0067 D7.1, D8.1, D8.5; D-099).

- Every athlete in a fixed order, the owner first, then by registration.
- An athlete who is not ready is not run, nothing is written for them, and Zaf is told
  once per UTC day, also across a restart.
- Each attempt runs in its own child process with a time limit; past it the process is
  killed, the attempt counts and the round moves on to the next athlete.
- A deleted athlete leaves the round; 30 days after /stop the round deletes the athlete.
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import UTC, datetime, timedelta

import pytest

from titan import worker
from titan.core.athlete import CONSENT_TEXT_VERSION
from titan.core.database import DatabaseManager

pytestmark = pytest.mark.integration

_A, _B, _C = "a-0000000a", "a-0000000b", "a-0000000c"
OWNER_CHAT = 1000
_PROFILE = {
    "birth_date": "1988-07-02", "sex": "F", "weight_kg": 58.0, "height_cm": 165,
    "max_hr": 186, "threshold_hr": 166, "training_phase": "BASE", "training_goal": "10K",
    "location_city": "Volos", "location_country": "GR",
}
_MORNING = datetime(2026, 10, 15, 8, 0, tzinfo=UTC)
_TODAY = "2026-10-15"


class _Bot:
    """Stands in for TitanTelegramBot in the parent: records what would reach Zaf."""

    sent: list[str] = []

    def __init__(self, *_args, **kwargs) -> None:
        self.chat_id = kwargs.get("chat_id")

    def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        type(self).sent.append(text)
        return True

    def send_alert(self, title: str, message: str, level: str = "warning") -> bool:
        type(self).sent.append(f"{title}: {message}")
        return True


@pytest.fixture
def db(tmp_path, monkeypatch):
    import titan.integrations.telegram_bot as telegram_bot

    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("TITAN_DATA_DIR", str(data))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", str(OWNER_CHAT))
    from titan.config.settings import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr(telegram_bot, "TitanTelegramBot", _Bot)
    monkeypatch.setattr(worker, "_utc_now", lambda: _MORNING)
    _Bot.sent = []
    manager = DatabaseManager(db_dir=data)
    # Registered in this order: B before A, C last, so the order is not the id order.
    for athlete, created in ((_B, "2026-10-01"), (_A, "2026-10-02"), (_C, "2026-10-03")):
        manager.conn.execute(
            "INSERT INTO athletes (athlete_id, display_name, created_at) VALUES (?, ?, ?)",
            (athlete, athlete, created),
        )
    manager.conn.commit()
    for athlete, chat in ((_A, 2000), (_B, 3000), (_C, 4000)):
        manager.save_athlete_profile(athlete, _PROFILE)
        manager.bind_garmin_account(athlete, f"garmin-{athlete}")
        manager.set_garmin_token_state(athlete, "ok")
        manager.bind_telegram_chat(athlete, chat)
        manager.grant_consent(athlete, CONSENT_TEXT_VERSION, now=_MORNING - timedelta(days=5))
    yield manager
    manager.close()
    get_settings.cache_clear()


def _in_process(monkeypatch) -> list[str]:
    """Run each attempt in-process with a routine that delivers; return the athletes run."""
    ran: list[str] = []
    monkeypatch.setattr(worker, "_run_attempt", worker._attempt_morning)
    monkeypatch.setattr(worker, "_run_morning", lambda _db, athlete_id: ran.append(athlete_id) or True)
    return ran


def _rows_for(db: DatabaseManager, athlete_id: str) -> int:
    return db.conn.execute(
        "SELECT COUNT(*) FROM worker_routine_executions WHERE athlete_id = ?", (athlete_id,)
    ).fetchone()[0]


def test_every_ready_athlete_runs_once_in_order_the_owner_first(db, monkeypatch) -> None:
    ran = _in_process(monkeypatch)

    worker._morning_round(db)
    worker._morning_round(db)  # the next 60 s poll: every day is delivered

    assert db.list_athletes_in_order() == ["owner", _B, _A, _C]
    assert ran == ["owner", _B, _A, _C]
    delivered = db.conn.execute(
        "SELECT athlete_id FROM worker_routine_executions WHERE routine_type = 'morning' "
        "AND delivered_at IS NOT NULL ORDER BY athlete_id"
    ).fetchall()
    assert [r[0] for r in delivered] == sorted(["owner", _A, _B, _C])


def test_before_0700_utc_the_round_does_nothing(db, monkeypatch) -> None:
    ran = _in_process(monkeypatch)
    monkeypatch.setattr(worker, "_utc_now", lambda: _MORNING.replace(hour=6))

    worker._morning_round(db)

    assert ran == []
    assert db.conn.execute("SELECT COUNT(*) FROM worker_routine_executions").fetchone()[0] == 0


@pytest.mark.parametrize(("break_it", "reason"), [
    (lambda db: db.revoke_consent(_A), "consent"),
    (lambda db: db.set_garmin_token_state(_A, "expired"), "garmin: token expired"),
    (lambda db: db.conn.execute("DELETE FROM athlete_profiles WHERE athlete_id = ?", (_A,)), "profile"),
])
def test_an_athlete_not_ready_is_skipped_and_zaf_is_told_once_a_day(db, monkeypatch, break_it, reason) -> None:
    ran = _in_process(monkeypatch)
    break_it(db)
    db.conn.commit()

    worker._morning_round(db)
    worker._morning_round(db)
    restarted = DatabaseManager(db_dir=db.db_path.parent)  # a new worker process, same day
    worker._morning_round(restarted)
    restarted.close()

    assert ran == ["owner", _B, _C]  # the others still run, in order
    assert _rows_for(db, _A) == 0  # nothing written for the athlete (ADR-0067 D4.2, D7.1)
    notices = [text for text in _Bot.sent if _A in text]
    assert len(notices) == 1 and reason in notices[0]

    monkeypatch.setattr(worker, "_utc_now", lambda: _MORNING + timedelta(days=1))
    worker._morning_round(db)
    assert len([text for text in _Bot.sent if _A in text]) == 2  # told again the next UTC day


def test_a_deleted_athlete_leaves_the_round_with_its_notices(db, monkeypatch, tmp_path) -> None:
    from titan.core import athlete_lifecycle

    monkeypatch.setenv(athlete_lifecycle.DELETION_RECORD_ENV, str(tmp_path / "records" / "deletions.jsonl"))
    ran = _in_process(monkeypatch)
    db.revoke_consent(_A)
    worker._morning_round(db)
    assert db.conn.execute(
        "SELECT COUNT(*) FROM worker_routine_executions WHERE routine_type = ?", (f"not_ready:{_A}",)
    ).fetchone()[0] == 1

    athlete_lifecycle.delete_athlete(db, _A, now=_MORNING)
    ran.clear()
    monkeypatch.setattr(worker, "_utc_now", lambda: _MORNING + timedelta(days=1))
    worker._morning_round(db)

    assert _A not in db.list_athletes_in_order()
    assert ran == ["owner", _B, _C]
    assert db.conn.execute(
        "SELECT COUNT(*) FROM worker_routine_executions WHERE routine_type LIKE ?", (f"%{_A}%",)
    ).fetchone()[0] == 0


def test_the_round_deletes_an_athlete_30_days_after_stop(db, monkeypatch, tmp_path) -> None:
    from titan.core import athlete_lifecycle

    monkeypatch.setenv(athlete_lifecycle.DELETION_RECORD_ENV, str(tmp_path / "records" / "deletions.jsonl"))
    _in_process(monkeypatch)
    db.conn.execute(
        "UPDATE consent_log SET revoked_at = ? WHERE athlete_id = ?",
        ((_MORNING - timedelta(days=31)).isoformat(), _A),
    )
    db.conn.commit()

    worker._morning_round(db)

    assert _A not in db.list_athletes_in_order()


def test_one_athlete_failing_does_not_stop_the_round(db, monkeypatch, caplog) -> None:
    ran = _in_process(monkeypatch)

    def _explode(_db, athlete_id):
        if athlete_id == _B:
            raise RuntimeError("readiness store down")

    monkeypatch.setattr(worker, "_readiness_problem", _explode)
    with caplog.at_level(logging.ERROR, logger="titan.worker.scheduler"):
        worker._morning_round(db)

    assert ran == ["owner", _A, _C]
    assert "scheduler_readiness_check_failed" in caplog.text


# ── The child process ─────────────────────────────────────────────────────────


def _remove(db: DatabaseManager, *athletes: str) -> None:
    from titan.core.athlete_lifecycle import _delete_rows

    for athlete in athletes:
        _delete_rows(db, athlete)


def _hang_child(db_path: str, athlete_id: str, execution_date: str, attempt: int) -> None:
    """Child entry that never finishes in time: stands in for a hung routine."""
    time.sleep(60)


def _delivering_child(db_path: str, athlete_id: str, execution_date: str, attempt: int) -> None:
    """Child entry that records the delivery on its own connection, as _child_morning does."""
    from pathlib import Path

    path = Path(db_path)
    child_db = DatabaseManager(db_name=path.name, db_dir=path.parent)
    child_db.mark_routine_delivered(athlete_id=athlete_id, execution_date=execution_date,
                                    routine_type="morning", delivered_at=datetime.now(UTC))
    child_db.close()
    sys.exit(worker._CHILD_DELIVERED)


@pytest.mark.slow
def test_a_hung_child_is_killed_at_the_time_limit_and_the_round_moves_on(db, monkeypatch, caplog) -> None:
    monkeypatch.setattr(worker, "_CHILD_ENTRY", _hang_child)
    monkeypatch.setattr(worker, "_routine_budget_s", lambda: 1.0)
    _remove(db, _A, _C)

    started = time.monotonic()
    with caplog.at_level(logging.CRITICAL, logger="titan.worker.scheduler"):
        worker._morning_round(db)
    elapsed = time.monotonic() - started

    assert elapsed < 20  # two killed children, not two 60 s sleeps
    killed = [r for r in caplog.records if r.getMessage() == "worker_routine_killed"]
    assert [r.athlete_id for r in killed] == ["owner", _B]
    assert db.conn.execute(
        "SELECT athlete_id, attempts, delivered_at FROM worker_routine_executions "
        "WHERE routine_type = 'morning' ORDER BY athlete_id"
    ).fetchall() == [(_B, 1, None), ("owner", 1, None)]


@pytest.mark.slow
def test_a_child_delivers_on_its_own_connection(db, monkeypatch) -> None:
    monkeypatch.setattr(worker, "_CHILD_ENTRY", _delivering_child)
    _remove(db, _A, _B, _C)

    worker._morning_round(db)

    assert db.conn.execute(
        "SELECT attempts, delivered_at IS NOT NULL FROM worker_routine_executions WHERE athlete_id = 'owner'"
    ).fetchall() == [(1, 1)]


def test_the_last_attempt_killed_leaves_the_day(db, monkeypatch) -> None:
    class _Killed:
        exitcode = -9

        def __init__(self, *a, **k) -> None:
            pass

        def start(self) -> None:
            pass

        def join(self, timeout=None) -> None:
            pass

        def is_alive(self) -> bool:
            return False

    class _Context:
        Process = _Killed

    import multiprocessing

    monkeypatch.setattr(multiprocessing, "get_context", lambda _method: _Context)
    for _ in range(2):
        db.begin_routine_attempt(athlete_id="owner", execution_date=_TODAY, routine_type="morning",
                                 started_at=_MORNING, max_attempts=3)

    assert worker._run_attempt(db, "owner", _TODAY, 3) is False

    assert [t for t in _Bot.sent if "not delivered" in t]
    assert db.conn.execute(
        "SELECT completed_at IS NOT NULL FROM worker_routine_executions WHERE athlete_id = 'owner'"
    ).fetchone() == (1,)


@pytest.mark.unit
def test_the_child_entry_exits_with_the_delivery(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(worker, "_attempt_morning", lambda *_a: True)
    with pytest.raises(SystemExit) as delivered:
        worker._child_morning(str(tmp_path / "titan_core.db"), "owner", _TODAY, 1)
    monkeypatch.setattr(worker, "_attempt_morning", lambda *_a: False)
    with pytest.raises(SystemExit) as not_delivered:
        worker._child_morning(str(tmp_path / "titan_core.db"), "owner", _TODAY, 1)

    assert (delivered.value.code, not_delivered.value.code) == (worker._CHILD_DELIVERED, worker._CHILD_NOT_DELIVERED)
