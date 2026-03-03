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
    assert set(payload.keys()) == {"activities", "weight", "sleep", "hrv"}

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

    caplog.set_level(logging.WARNING)
    sync = GarminSync(email="x", password="y")
    sync.client = _Client()
    sync.is_connected = True

    out = sync.sync_hrv(days_back=2)

    assert len(out) == 1
    assert out[0]["rmssd"] == 46.2
    assert any("Skipping malformed HRV record" in r.getMessage() for r in caplog.records)


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
    assert not any("Skipping malformed HRV record" in r.getMessage() for r in caplog.records)
