import json
import logging
from datetime import datetime

from titan.integrations.garmin_sync import GarminSync
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


def test_garmin_sync_logs_timeout_slo_alert(caplog, monkeypatch):
    caplog.set_level(logging.INFO)
    monkeypatch.setenv("GARMIN_SYNC_TIMEOUT_S", "0")

    sync = GarminSync(email="x", password="y")
    sync.sync_activities = lambda days_back=7: []
    sync.sync_weight = lambda days_back=14: []
    sync.sync_sleep = lambda days_back=7: []
    sync.sync_hrv = lambda days_back=7: []

    payload = sync.sync_all(days_back=1)
    assert set(payload.keys()) == {"activities", "weight", "sleep", "hrv", "hrv_sync_metrics"}
    assert payload["hrv_sync_metrics"] == {"days_back": 0, "synced_days": 0, "skipped_days": 0}

    events = _json_messages(caplog)
    alerts = [e for e in events if e.get("flow") == "garmin_sync" and e.get("action") == "slo_alert"]
    assert alerts
    assert alerts[0]["slo_key"] == "garmin_sync_timeout"


def test_sync_hrv_logs_skipped_malformed_records(caplog):
    class _Client:
        def get_hrv_data(self, day):
            today = datetime.now().strftime("%Y-%m-%d")
            if day == today:
                raise ValueError("bad payload")
            return {"hrvSummary": {"weeklyAvg": 46.2, "status": "BALANCED"}}

    caplog.set_level(logging.INFO)
    sync = GarminSync(email="x", password="y")
    sync.client = _Client()
    sync.is_connected = True

    out = sync.sync_hrv(days_back=2)

    assert len(out) == 1
    assert out[0]["rmssd"] == 46.2
    assert any("Skipping malformed HRV record" in r.getMessage() for r in caplog.records)

    events = _json_messages(caplog)
    skipped = [
        e
        for e in events
        if e.get("flow") == "garmin_sync" and e.get("action") == "hrv_day_skipped"
    ]
    assert len(skipped) == 1
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



def test_sync_hrv_emits_metrics_when_disconnected(caplog):
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
