"""The worker does not take a morning the console is running (D-113, review of #1049).

The console claims the owner's day with the 15-minute retry gap (D-111). The owner-only
worker claimed without the gap, so a console attempt still running was taken again at once
and both could send a briefing. Each test fails without the fix.
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

    def __init__(self, db: DatabaseManager, athlete_id: str = "owner") -> None:
        self.athlete_id = athlete_id

    def run_morning_routine(self) -> bool:
        type(self).calls.append(self.athlete_id)
        return True


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import titan.integrations.telegram_bot as telegram_bot

    monkeypatch.setenv("TITAN_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(worker, "_build_daily_coach", _Coach)
    monkeypatch.setattr(telegram_bot, "TitanTelegramBot", lambda *a, **k: None)
    _Coach.calls = []
    database = DatabaseManager(db_dir=tmp_path)
    yield database
    database.close()


def _stop_on_first_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    slept: list[float] = []

    def _sleep(_stop, seconds, _interval, _heartbeat) -> bool:
        slept.append(seconds)
        return True  # the stop event fired: the loop ends here

    monkeypatch.setattr(worker, "_sleep_with_heartbeat", _sleep)
    return slept


def test_the_worker_does_not_start_a_second_attempt_while_the_console_runs(db, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(worker, "_utc_now", lambda: _SEVEN)
    assert worker._claim_routine(db, "owner", _SEVEN, spaced=True, last_start=False, runner="console") == 1

    monkeypatch.setattr(worker, "_utc_now", lambda: _SEVEN + timedelta(minutes=1))
    slept = _stop_on_first_sleep(monkeypatch)

    assert worker._run_due_routine(db, threading.Event(), tmp_path / "hb", 60, 10) is True
    assert _Coach.calls == []  # no second morning
    assert slept == [60]  # it waits for the console's attempt, one poll at a time


def test_the_worker_stops_for_the_day_once_the_console_delivered(db, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(worker, "_utc_now", lambda: _SEVEN)
    attempt = worker._claim_routine(db, "owner", _SEVEN, spaced=True, last_start=False)
    assert worker._attempt_morning(db, "owner", _DAY, attempt) is True
    assert _Coach.calls == ["owner"]

    monkeypatch.setattr(worker, "_utc_now", lambda: _SEVEN + timedelta(minutes=1))
    slept = _stop_on_first_sleep(monkeypatch)

    assert worker._run_due_routine(db, threading.Event(), tmp_path / "hb", 60, 10) is False
    assert _Coach.calls == ["owner"]
    assert slept == []


def test_the_worker_retries_after_the_gap_when_the_console_did_not_deliver(db, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(worker, "_utc_now", lambda: _SEVEN)
    # The console's attempt ended without delivering, so its "in progress" mark is gone (v34).
    assert worker._claim_routine(db, "owner", _SEVEN, spaced=True, last_start=False, runner="console") == 1
    worker._end_attempt(db, "owner", _DAY)

    later = _SEVEN + timedelta(seconds=worker.ROUTINE_RETRY_DELAY_S + 60)
    monkeypatch.setattr(worker, "_utc_now", lambda: later)
    monkeypatch.setattr(worker, "_run_routine_supervised", lambda *a, **k: _Coach(db).run_morning_routine())

    assert worker._run_due_routine(db, threading.Event(), tmp_path / "hb", 60, 10) is False
    assert _Coach.calls == ["owner"]
