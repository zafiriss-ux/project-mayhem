"""Console and owner-only worker (DW-02, DW-04, DW-05, DW-08, DW-10; D-111).

Each test reproduces a finding of the Phase 4 audit and fails without the fix:

- DW-02: the console ran its own morning without claiming the day, so a console and a
  worker on the same database sent the owner two mornings;
- DW-10: the console ran the morning only in the exact 07:00 minute, so a missed minute
  lost the day;
- DW-04: a backup that raised stopped the owner-only worker before the morning;
- DW-05: a hung morning stopped only the heartbeat, and nobody was told on Telegram;
- DW-08: three failed sends of the not-ready notice in three polls lost it for the day.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from titan import worker
from titan.core.database import DatabaseManager

pytestmark = pytest.mark.integration

_DAY = "2026-10-09"
_SEVEN = datetime(2026, 10, 9, 7, 0, tzinfo=UTC)


class _Coach:
    """Stands in for DailyCoach: the routine delivers and is counted."""

    calls: list[str] = []
    delivers = True

    def __init__(self, db: DatabaseManager, athlete_id: str = "owner") -> None:
        self.db = db
        self.athlete_id = athlete_id

    def run_morning_routine(self) -> bool:
        type(self).calls.append(self.athlete_id)
        return type(self).delivers


class _Bot:
    """Stands in for TitanTelegramBot; ``fail`` sends fail first."""

    sent: list[str] = []
    fail = 0

    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        if type(self).fail > 0:
            type(self).fail -= 1
            return False
        type(self).sent.append(text)
        return True

    def send_alert(self, title: str, message: str, level: str = "warning") -> bool:
        type(self).sent.append(f"{title}: {message}")
        return True


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import titan.integrations.telegram_bot as telegram_bot

    monkeypatch.setenv("TITAN_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TITAN_MULTI_ATHLETE", "")
    monkeypatch.setattr(worker, "_build_daily_coach", _Coach)
    monkeypatch.setattr(telegram_bot, "TitanTelegramBot", _Bot)
    _Coach.calls, _Coach.delivers = [], True
    _Bot.sent, _Bot.fail = [], 0
    database = DatabaseManager(db_dir=tmp_path)
    yield database
    database.close()


def _at(monkeypatch: pytest.MonkeyPatch, when: datetime) -> None:
    monkeypatch.setattr(worker, "_utc_now", lambda: when)


def test_the_console_runs_a_morning_it_missed_at_seven(db, monkeypatch) -> None:
    _at(monkeypatch, _SEVEN - timedelta(minutes=1))
    assert worker.run_owner_morning_if_due(db) is False
    assert _Coach.calls == []

    _at(monkeypatch, _SEVEN + timedelta(hours=2, minutes=13))  # the 07:00 minute was missed
    assert worker.run_owner_morning_if_due(db) is True
    assert _Coach.calls == ["owner"]

    assert worker.run_owner_morning_if_due(db) is False  # the next minute: delivered already
    assert _Coach.calls == ["owner"]


def test_the_console_does_not_send_a_morning_the_worker_already_sent(db, monkeypatch) -> None:
    _at(monkeypatch, _SEVEN + timedelta(minutes=1))
    attempt = worker._claim_routine(db, "owner", _SEVEN + timedelta(minutes=1))
    assert attempt == 1
    assert worker._attempt_morning(db, "owner", _DAY, attempt) is True
    assert _Coach.calls == ["owner"]

    _at(monkeypatch, _SEVEN + timedelta(minutes=2))
    assert worker.run_owner_morning_if_due(db) is False
    assert _Coach.calls == ["owner"]


def test_the_console_waits_while_the_workers_attempt_is_not_due_again(db, monkeypatch) -> None:
    """The worker's first attempt did not deliver: the console waits the retry gap, then tries."""
    _Coach.delivers = False
    attempt = worker._claim_routine(db, "owner", _SEVEN)
    worker._attempt_morning(db, "owner", _DAY, attempt)
    assert _Coach.calls == ["owner"]

    _Coach.delivers = True
    _at(monkeypatch, _SEVEN + timedelta(minutes=1))
    assert worker.run_owner_morning_if_due(db) is False
    assert _Coach.calls == ["owner"]

    _at(monkeypatch, _SEVEN + timedelta(seconds=worker.ROUTINE_RETRY_DELAY_S + 60))
    assert worker.run_owner_morning_if_due(db) is True
    assert _Coach.calls == ["owner", "owner"]


def test_a_failing_backup_does_not_stop_the_owners_morning(db, monkeypatch, tmp_path) -> None:
    def _backup_fails(_db) -> None:
        raise NotADirectoryError("backup dir is a file")

    ran: list[bool] = []
    monkeypatch.setattr(worker, "_run_backup", _backup_fails)
    monkeypatch.setattr(worker, "_run_due_routine", lambda *a, **k: ran.append(True) or True)

    worker.run_forever(str(tmp_path / "titan_core.db"), shutdown_event=threading.Event())

    assert ran == [True]


def test_zaf_is_told_once_when_the_morning_hangs(db, monkeypatch, tmp_path) -> None:
    release = threading.Event()
    monkeypatch.setattr(worker, "_attempt_morning", lambda *a, **k: release.wait(5) and False)
    timer = threading.Timer(0.6, release.set)
    timer.start()
    try:
        worker._run_routine_supervised(
            db, tmp_path / "hb", 0.05, 0.2, execution_date=_DAY, attempt=1
        )
    finally:
        timer.cancel()
        release.set()

    hung = [text for text in _Bot.sent if "running for" in text]
    assert len(hung) == 1


def test_the_not_ready_notice_survives_a_short_telegram_outage(db, monkeypatch) -> None:
    db.conn.execute(
        "INSERT INTO athletes (athlete_id, display_name, created_at) VALUES ('a-0000000b', 'b', '2026-10-01')"
    )
    db.conn.commit()
    monkeypatch.setattr(worker, "_utc_now", lambda: _SEVEN)
    _Bot.fail = 10**6  # Telegram is down for the first three polls, one minute apart
    for minute in range(3):
        worker._tell_zaf_not_ready(db, "a-0000000b", "consent: none current", _SEVEN + timedelta(minutes=minute))
    assert _Bot.sent == []
    _Bot.fail = 0  # and back

    later = _SEVEN + timedelta(seconds=worker.ROUTINE_RETRY_DELAY_S + 60)
    worker._tell_zaf_not_ready(db, "a-0000000b", "consent: none current", later)
    worker._tell_zaf_not_ready(db, "a-0000000b", "consent: none current", later + timedelta(minutes=1))

    assert _Bot.sent == ["⏸ a-0000000b is not run today: consent: none current."]


def test_a_task_scheduled_every_minute_fires_at_any_minute(monkeypatch) -> None:
    from titan.integrations import telegram_bot

    bot = telegram_bot.TitanTelegramBot.__new__(telegram_bot.TitanTelegramBot)
    bot._tasks_lock = threading.Lock()
    bot._stop_event = threading.Event()
    bot.scheduled_tasks = []
    fired: list[str] = []
    bot.schedule_task(name="each", time_str=telegram_bot.EVERY_MINUTE, callback=lambda: fired.append("each"))
    bot.schedule_task(name="never", time_str="25:61", callback=lambda: fired.append("never"))
    bot.schedule_task(name="stop", time_str=telegram_bot.EVERY_MINUTE, callback=bot._stop_event.set)

    bot._scheduler_worker()

    assert fired == ["each"]
