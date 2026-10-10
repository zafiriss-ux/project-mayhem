import json
import logging
import time
from datetime import datetime

import pytest
from freezegun import freeze_time

from titan.integrations.garmin_sync import (
    GARMIN_PAYLOAD_MALFORMED,
    GARMIN_RATE_LIMIT,
    GARMIN_TIMEOUT,
    GarminSync,
)
from titan.integrations.telegram_bot import TitanTelegramBot


def _json_messages(caplog):
    out = []
    for record in caplog.records:
        try:
            out.append(json.loads(record.getMessage()))
        except json.JSONDecodeError:
            continue
    return out


def test_telegram_logs_slo_alert_without_chat_id(caplog, monkeypatch):
    caplog.set_level(logging.INFO)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    bot = TitanTelegramBot(bot_token="", chat_id="")
    assert bot.send_message("payload") is False

    events = _json_messages(caplog)
    alerts = [e for e in events if e.get("flow") == "telegram" and e.get("action") == "slo_alert"]
    assert alerts
    assert alerts[0]["slo_key"] == "telegram_delivery_missing_chat_id"

    failures = [
        e
        for e in events
        if e.get("flow") == "telegram"
        and e.get("action") == "failure"
        and e.get("subsystem") == "send_message"
    ]
    assert failures
    assert failures[0]["failure_class"] == "SEND_FAIL"


def test_telegram_logs_send_failure_when_delivery_raises(caplog, monkeypatch):
    class _Bot:
        def send_message(self, *_args, **_kwargs):
            raise RuntimeError("downstream error")

    caplog.set_level(logging.INFO)
    monkeypatch.setattr("titan.integrations.telegram_bot.TELEBOT_AVAILABLE", True)
    bot = TitanTelegramBot(bot_token="", chat_id="12345")
    bot.bot = _Bot()

    assert bot.send_message("payload") is False

    events = _json_messages(caplog)
    failures = [
        e
        for e in events
        if e.get("flow") == "telegram"
        and e.get("action") == "failure"
        and e.get("subsystem") == "send_message"
    ]
    assert failures
    assert failures[0]["failure_class"] == "SEND_FAIL"
    assert failures[0]["error_class"] == "RuntimeError"


def test_telegram_logs_poll_failures(caplog, monkeypatch):
    class _Bot:
        def infinity_polling(self, **_kwargs):
            raise RuntimeError("poll exploded")

    caplog.set_level(logging.INFO)
    bot = TitanTelegramBot(bot_token="", chat_id="12345")
    bot.bot = _Bot()

    def _stop_after_retry(timeout):
        bot._stop_event.set()
        return True

    monkeypatch.setattr(bot._stop_event, "wait", _stop_after_retry)
    bot._poll_worker()

    events = _json_messages(caplog)
    failures = [
        e
        for e in events
        if e.get("flow") == "telegram"
        and e.get("action") == "failure"
        and e.get("subsystem") == "poll_worker"
    ]
    assert failures
    assert failures[0]["failure_class"] == "POLL_FAIL"


def test_telegram_scheduler_logs_callback_error_and_drift(caplog, monkeypatch):
    caplog.set_level(logging.INFO)
    bot = TitanTelegramBot(bot_token="", chat_id="12345")
    bot.schedule_task("boom", "10:00", lambda: (_ for _ in ()).throw(ValueError("callback fail")), days=["Monday"])

    class _Now:
        second = 10

        @staticmethod
        def strftime(fmt):
            if fmt == "%H:%M":
                return "10:00"
            if fmt == "%A":
                return "Monday"
            raise AssertionError(f"Unexpected format: {fmt}")

    class _Datetime:
        @staticmethod
        def now(tz=None):
            return _Now()

    times = iter([100.0, 200.0])
    monkeypatch.setattr("titan.integrations.telegram_bot.datetime", _Datetime)

    def _time_now():
        try:
            return next(times)
        except StopIteration:
            return 200.0

    monkeypatch.setattr("titan.integrations.telegram_bot.time.time", _time_now)

    call_count = {"n": 0}

    def _wait(timeout):
        call_count["n"] += 1
        if call_count["n"] >= 2:
            bot._stop_event.set()
            return True
        return False

    monkeypatch.setattr(bot._stop_event, "wait", _wait)
    bot._scheduler_worker()

    events = _json_messages(caplog)
    callback_failures = [
        e
        for e in events
        if e.get("flow") == "telegram"
        and e.get("action") == "failure"
        and e.get("subsystem") == "scheduler_worker"
        and e.get("failure_class") == "CALLBACK_ERROR"
    ]
    assert callback_failures
    assert callback_failures[0]["task_name"] == "boom"

    drift_failures = [
        e
        for e in events
        if e.get("flow") == "telegram"
        and e.get("action") == "failure"
        and e.get("subsystem") == "scheduler_worker"
        and e.get("failure_class") == "SCHEDULER_DRIFT"
    ]
    assert drift_failures
    assert drift_failures[0]["drift_seconds"] > 0


def test_garmin_sync_logs_timeout_slo_alert(caplog, monkeypatch):
    caplog.set_level(logging.INFO)
    monkeypatch.setenv("GARMIN_SYNC_TIMEOUT_S", "0")

    sync = GarminSync(email="x", password="y")
    sync._sync_operation = lambda days_back=7: time.sleep(0.05) or {  # WHY: must exceed GARMIN_SYNC_TIMEOUT_S=0 reliably
        "activities": [],
        "weight": [],
        "sleep": [],
        "hrv": [],
        "hrv_sync_metrics": {"days_back": 0, "synced_days": 0, "skipped_days": 0},
        "data_trust": {},
    }

    payload = sync.sync_all(days_back=1)
    assert payload["status"] == "timeout_cancelled"
    assert payload["hrv_sync_metrics"] == {"days_back": 0, "synced_days": 0, "skipped_days": 0}

    events = _json_messages(caplog)
    alerts = [e for e in events if e.get("flow") == "garmin_sync" and e.get("action") == "slo_alert"]
    assert alerts
    assert alerts[0]["slo_key"] == "garmin_sync_timeout"


@freeze_time("2026-04-26")
def test_sync_hrv_logs_skipped_malformed_records(caplog):
    class _Client:
        def get_hrv_data(self, day):
            today = datetime.now().strftime("%Y-%m-%d")
            if day == today:
                raise ValueError("bad payload")
            return {"hrvSummary": {"lastNightAvg": 46.2, "status": "BALANCED"}}

    caplog.set_level(logging.INFO)
    sync = GarminSync(email="x", password="y")
    sync.client = _Client()
    sync.is_connected = True

    out = sync.sync_hrv(days_back=2)

    assert len(out) == 1
    assert out[0]["rmssd"] == 46.2
    assert any("Skipping HRV day" in r.getMessage() for r in caplog.records)

    events = _json_messages(caplog)
    skipped = [
        e
        for e in events
        if e.get("flow") == "garmin_sync"
        and e.get("action") == "GARMIN_PAYLOAD_MALFORMED"
    ]
    assert len(skipped) == 1
    assert "date" in skipped[0]
    assert skipped[0]["error_class"] == "ValueError"
    assert skipped[0]["error_message"] == "bad payload"

    metrics = [
        e
        for e in events
        if e.get("flow") == "garmin_sync" and e.get("action") == "hrv_sync_metrics"
    ]
    assert metrics
    assert metrics[0]["skipped_days"] == 1
    assert metrics[0]["synced_days"] == 1
    assert metrics[0]["days_back"] == 2
    assert sync.last_hrv_sync_metrics == {"days_back": 2, "synced_days": 1, "skipped_days": 1}



def test_sync_hrv_emits_metrics_when_disconnected(caplog, monkeypatch):
    monkeypatch.delenv("GARMIN_EMAIL", raising=False)
    monkeypatch.delenv("GARMIN_PASSWORD", raising=False)
    caplog.set_level(logging.INFO)

    sync = GarminSync(email="", password="")
    out = sync.sync_hrv(days_back=3)

    assert out == []
    assert sync.last_hrv_sync_metrics == {"days_back": 3, "synced_days": 0, "skipped_days": 0}

    events = _json_messages(caplog)
    metrics = [
        e
        for e in events
        if e.get("flow") == "garmin_sync" and e.get("action") == "hrv_sync_metrics"
    ]
    assert metrics
    assert metrics[0] == {
        "flow": "garmin_sync",
        "action": "hrv_sync_metrics",
        "severity": "info",
        "days_back": 3,
        "synced_days": 0,
        "skipped_days": 0,
    }

def test_sync_hrv_ignores_missing_values_without_logging_warning(caplog):
    class _Client:
        def get_hrv_data(self, day):
            return {"hrvSummary": {"status": "UNKNOWN"}}

    caplog.set_level(logging.WARNING)
    sync = GarminSync(email="x", password="y")
    sync.client = _Client()
    sync.is_connected = True

    out = sync.sync_hrv(days_back=2)

    assert out == []
    assert sync.get_sync_summary()["last_hrv_sync_metrics"]["skipped_days"] == 0
    assert not any("Skipping malformed HRV record" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize(
    "method_name,error,expected_failure",
    [
        ("sync_activities", Exception("429 Too Many Requests"), GARMIN_RATE_LIMIT),
        ("sync_weight", TimeoutError("timed out"), GARMIN_TIMEOUT),
        ("sync_sleep", RuntimeError("service unavailable"), "GARMIN_API_UNAVAILABLE"),
    ],
)
def test_sync_methods_emit_structured_failure_events(caplog, method_name, error, expected_failure):
    caplog.set_level(logging.INFO)
    sync = GarminSync(email="x", password="y")
    sync.is_connected = True
    sync.client = type("Client", (), {})()

    if method_name == "sync_activities":
        sync.client.get_activities_by_date = lambda *_: (_ for _ in ()).throw(error)
    elif method_name == "sync_weight":
        sync.client.get_weigh_ins = lambda *_: (_ for _ in ()).throw(error)
    else:
        sync.client.get_sleep_data = lambda *_: (_ for _ in ()).throw(error)

    getattr(sync, method_name)(days_back=1)

    events = _json_messages(caplog)
    failures = [
        e
        for e in events
        if e.get("flow") == "garmin_sync"
        and e.get("action") == expected_failure
        and e.get("subsystem") == method_name
    ]
    assert failures
    assert failures[0]["failure_class"] == expected_failure
