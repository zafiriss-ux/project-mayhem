"""P4-09 (F-01): slo_alert events reach the owner instead of only the log.

Every structured event is built by ``structured_event_payload``; an ``slo_alert`` also goes to
the registered listeners. The worker counts each one and, after a morning attempt, sends the
owner one message naming the alerts it raised. Alerts about Telegram itself are not sent over
Telegram. Synthetic data only.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

import titan.integrations.telegram_bot as telegram_bot
import titan.worker as worker
from titan.core import structured_events
from titan.core.database import DatabaseManager
from titan.core.structured_events import add_slo_alert_listener, structured_event_payload

DAY = "2026-03-02"
T0 = dt.datetime(2026, 3, 2, 7, 0, tzinfo=dt.UTC)


@pytest.fixture
def listeners(monkeypatch):  # noqa: ANN201
    monkeypatch.setattr(structured_events, "_slo_alert_listeners", [])
    return structured_events._slo_alert_listeners


@pytest.mark.unit
def test_only_slo_alerts_reach_the_listeners_and_a_failing_one_breaks_nothing(listeners) -> None:
    seen: list[dict] = []

    def broken(_payload: dict) -> None:
        raise RuntimeError("listener down")

    add_slo_alert_listener(broken)
    add_slo_alert_listener(seen.append)
    add_slo_alert_listener(seen.append)  # twice is once

    structured_event_payload("garmin_sync", "sync_complete", elapsed_s=1)
    payload = structured_event_payload("garmin_sync", "slo_alert", slo_key="garmin_sync_timeout")

    assert payload["slo_key"] == "garmin_sync_timeout"
    assert [p["slo_key"] for p in seen] == ["garmin_sync_timeout"]


class _Bot:
    sent: list[tuple[str, str, str]] = []

    def __init__(self, *_a, **_k) -> None:
        pass

    def send_alert(self, title: str, message: str, level: str = "warning") -> bool:
        _Bot.sent.append((title, message, level))
        return True


@pytest.mark.integration
def test_the_owner_is_told_once_per_attempt_which_slo_alerts_it_raised(
    tmp_path: Path, monkeypatch, listeners,
) -> None:
    db = DatabaseManager(db_name="titan_core.db", db_dir=tmp_path)
    _Bot.sent = []
    counted: list[dict] = []
    monkeypatch.setattr(telegram_bot, "TitanTelegramBot", _Bot)
    monkeypatch.setattr(worker, "_mark_delivered", lambda *_a, **_k: True)
    from titan.observability import metrics

    real_metrics = metrics.get_metrics()
    monkeypatch.setattr(
        real_metrics, "counter", lambda name, value=1, labels=None: counted.append({"name": name, **(labels or {})}),
    )

    def morning(*_a, **_k) -> bool:
        for key in ("garmin_sync_timeout", "nutrition_plan_missing", "garmin_sync_timeout", "telegram_delivery_failed"):
            structured_event_payload("test", "slo_alert", slo_key=key)
        return True

    monkeypatch.setattr(worker, "_run_morning", morning)
    try:
        structured_event_payload("test", "slo_alert", slo_key="before_the_attempt")
        db.begin_routine_attempt(
            athlete_id="owner", execution_date=DAY, routine_type="morning", started_at=T0, max_attempts=3,
        )
        assert worker._attempt_morning(db, "owner", DAY, 1) is True

        [(title, message, level)] = _Bot.sent
        assert title == "SLO alerts" and level == "warning"
        assert "garmin_sync_timeout (2×)" in message and "nutrition_plan_missing" in message
        assert "telegram_delivery_failed" not in message  # not told over the channel that failed
        assert "before_the_attempt" not in message  # only the attempt's own alerts
        assert sorted(c["slo_key"] for c in counted if c["name"] == "slo_alert") == [
            "garmin_sync_timeout", "garmin_sync_timeout", "nutrition_plan_missing", "telegram_delivery_failed",
        ]
    finally:
        db.close()


@pytest.mark.integration
def test_an_attempt_with_no_slo_alert_sends_no_alert(tmp_path: Path, monkeypatch, listeners) -> None:
    db = DatabaseManager(db_name="titan_core.db", db_dir=tmp_path)
    _Bot.sent = []
    monkeypatch.setattr(telegram_bot, "TitanTelegramBot", _Bot)
    monkeypatch.setattr(worker, "_mark_delivered", lambda *_a, **_k: True)
    monkeypatch.setattr(worker, "_run_morning", lambda *_a, **_k: True)
    try:
        db.begin_routine_attempt(
            athlete_id="owner", execution_date=DAY, routine_type="morning", started_at=T0, max_attempts=3,
        )
        assert worker._attempt_morning(db, "owner", DAY, 1) is True
        assert _Bot.sent == []
    finally:
        db.close()
