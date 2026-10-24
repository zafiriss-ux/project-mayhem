"""INV-21 (AGENTS §8.8, T-PRA-10): the degradation alert chain, end to end.

Garmin failure → ``DegradedModeTracker`` → alert → ``alert_operator`` → Telegram send.

Every link is the real code: ``GarminSync.sync_all`` counts the failed syncs, the real
``DegradedModeTracker`` keeps its timer in a real SQLite database, the real
``TitanEffectBus.make_degraded_hook`` reads ``is_api_degraded`` and the real
``alert_operator`` picks who is told. Only two things are stand-ins: Garmin's answer (an
empty sync, no network) and the Telegram bot (a recorder, no network).

The chain's entry condition is INV-08: a failed sync must count as a failure, or the
chain never starts. The first test checks that link on its own.

Synthetic data only: chats 1 and 1001, athlete id a-0000000a.
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from freezegun import freeze_time

import titan.integrations.telegram_bot as telegram_bot
from titan.config.thresholds import GARMIN_DEGRADATION_FAILURE_THRESHOLD_COUNT
from titan.core.database import DatabaseManager
from titan.integrations.garmin_sync import GarminSync
from titan.orchestration.daily_coach import DegradedModeTracker
from titan.orchestration.effect_bus import TitanEffectBus

_OWNER_CHAT = "1"
_ATHLETE_CHAT = "1001"
_ATHLETE = "a-0000000a"
T0 = "2026-03-02 07:30:00"


class _Bot:
    """Stands in for TitanTelegramBot: records the chat, text and alert level of every send.

    The level is ``None`` for a plain ``send_message``.
    """

    sent: list[tuple[str, str, str | None]] = []

    def __init__(self, *_args, chat_id=None, db=None, athlete_id: str = "owner", **_kwargs) -> None:
        self.athlete_id = athlete_id
        self.db = db
        self.chat = str(chat_id) if chat_id is not None else _OWNER_CHAT

    def _record(self, text: str, level: str | None) -> bool:
        type(self).sent.append((self.chat, text, level))
        return True

    def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        return self._record(text, None)

    def send_alert(self, title: str, message: str, level: str = "warning") -> bool:
        return self._record(f"{title}\n{message}", level)

    def send_structured_alert(self, event_type: str, lock_code: str, message: str) -> bool:
        return self.send_message(f"{event_type}/{lock_code}\n{message}")


@pytest.fixture
def db(tmp_path: Path):
    d = DatabaseManager(db_name="titan_core.db", db_dir=tmp_path)
    yield d
    d.close()


@pytest.fixture(autouse=True)
def _bots(monkeypatch: pytest.MonkeyPatch):
    # alert_operator builds the owner's bot itself for an alert about another athlete.
    monkeypatch.setattr(telegram_bot, "TitanTelegramBot", _Bot)
    _Bot.sent = []


def _empty_sync(days_back: int):
    """Garmin answers, but with no records: a failed sync (ADR-0050 D1 C3)."""
    from titan.orchestration.contracts import GarminSyncResultContract, HRVSyncMetricsContract
    from titan.science.data_trust import evaluate_garmin_trust

    return GarminSyncResultContract(
        activities=[], weight=[], sleep=[], hrv=[],
        hrv_sync_metrics=HRVSyncMetricsContract(days_back=days_back, synced_days=0, skipped_days=0).to_payload(),
        data_trust=evaluate_garmin_trust(data_age_hours=0.0).to_payload(),
    ).to_payload()


def _failing_garmin(monkeypatch: pytest.MonkeyPatch) -> GarminSync:
    """A real GarminSync whose syncs keep failing until it reports the API degraded."""
    garmin = GarminSync(email="e", password="p")
    monkeypatch.setattr(garmin, "_sync_operation", _empty_sync)
    for _ in range(GARMIN_DEGRADATION_FAILURE_THRESHOLD_COUNT):
        garmin.sync_all(days_back=1)
    return garmin


def _morning(tracker: DegradedModeTracker, garmin: GarminSync, telegram: _Bot) -> None:
    """One morning's degraded-mode step, as the effect bus runs it before dispatch."""
    hook = TitanEffectBus.make_degraded_hook(tracker=tracker, garmin=garmin, telegram=telegram)
    hook(SimpleNamespace(decision_trace={}))


def _degraded_events(records) -> list[dict]:
    events = []
    for r in records:
        try:
            payload = json.loads(r.getMessage())
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(payload, dict) and payload.get("action") == "garmin_api_degraded":
            events.append(payload)
    return events


@pytest.mark.integration
def test_failed_syncs_count_as_failures_and_raise_a_critical_event(monkeypatch, caplog) -> None:
    """INV-08, the chain's entry: failed syncs reach the threshold and say so at CRITICAL."""
    with caplog.at_level(logging.ERROR):
        garmin = _failing_garmin(monkeypatch)
    assert garmin.is_api_degraded is True
    events = _degraded_events(caplog.records)
    assert events, "garmin_api_degraded was not emitted when the failure threshold was crossed"
    assert events[-1]["severity"] == "critical"


@pytest.mark.integration
def test_garmin_down_for_24_hours_tells_the_owner_once(monkeypatch, db) -> None:
    garmin = _failing_garmin(monkeypatch)
    owner_bot = _Bot()
    with freeze_time(T0) as clock:
        tracker = DegradedModeTracker(db=db)
        _morning(tracker, garmin, owner_bot)
        assert _Bot.sent == [], "the first degraded morning only opens the timer"
        assert "garmin_api_degraded" in dict(db.get_all_degraded_mode_states(athlete_id="owner"))

        clock.tick(timedelta(hours=23))
        _morning(tracker, garmin, owner_bot)
        assert _Bot.sent == [], "no alert before 24 hours"

        clock.tick(timedelta(hours=1))
        _morning(tracker, garmin, owner_bot)
        assert len(_Bot.sent) == 1, "one alert at 24 hours"

        # The alert restarts the timer: the next morning sends nothing new (no alert storm).
        clock.tick(timedelta(hours=1))
        _morning(tracker, garmin, owner_bot)
    assert len(_Bot.sent) == 1
    chat, text, level = _Bot.sent[0]
    assert chat == _OWNER_CHAT
    assert "TITAN degraded mode" in text and "garmin_api_degraded" in text
    # Today's level (D-143): the event is CRITICAL, the Telegram alert goes out as a warning.
    assert level == "warning"


@pytest.mark.integration
def test_the_timer_survives_a_worker_restart(monkeypatch, db) -> None:
    """The 24 hours count across restarts: a new tracker reads the timer from the database."""
    garmin = _failing_garmin(monkeypatch)
    with freeze_time(T0) as clock:
        _morning(DegradedModeTracker(db=db), garmin, _Bot())
        clock.tick(timedelta(hours=24))
        _morning(DegradedModeTracker(db=db), garmin, _Bot())
    assert len(_Bot.sent) == 1
    assert "garmin_api_degraded" in _Bot.sent[0][1]


@pytest.mark.integration
def test_garmin_back_before_24_hours_sends_nothing(monkeypatch, db) -> None:
    garmin = _failing_garmin(monkeypatch)
    with freeze_time(T0) as clock:
        tracker = DegradedModeTracker(db=db)
        _morning(tracker, garmin, _Bot())
        garmin._consecutive_failures = 0  # a sync with records resets the streak (garmin_sync.py)
        clock.tick(timedelta(hours=12))
        _morning(tracker, garmin, _Bot())
        clock.tick(timedelta(hours=12))
        _morning(tracker, garmin, _Bot())
    assert _Bot.sent == []
    assert "garmin_api_degraded" not in dict(db.get_all_degraded_mode_states(athlete_id="owner"))


@pytest.mark.integration
def test_an_athletes_alert_reaches_the_athlete_and_the_owner(monkeypatch, db) -> None:
    """D-107: the athlete gets a short note, the owner gets the operator alert with the id."""
    garmin = _failing_garmin(monkeypatch)
    athlete_bot = _Bot(chat_id=_ATHLETE_CHAT, athlete_id=_ATHLETE)
    with freeze_time(T0) as clock:
        tracker = DegradedModeTracker(db=db, athlete_id=_ATHLETE)
        _morning(tracker, garmin, athlete_bot)
        clock.tick(timedelta(hours=24))
        _morning(tracker, garmin, athlete_bot)
    to_athlete = [t for c, t, _level in _Bot.sent if c == _ATHLETE_CHAT]
    to_owner = [t for c, t, _level in _Bot.sent if c == _OWNER_CHAT]
    assert len(to_athlete) == 1 and len(to_owner) == 1
    assert "reduced mode" in to_athlete[0]
    assert "garmin_api_degraded" not in to_athlete[0] and "Check credentials" not in to_athlete[0]
    assert _ATHLETE in to_owner[0] and "garmin_api_degraded" in to_owner[0]
    assert "(warning)" in to_owner[0]
    # The owner's own timers are untouched by the athlete's (ISO-2).
    assert dict(db.get_all_degraded_mode_states(athlete_id="owner")) == {}
