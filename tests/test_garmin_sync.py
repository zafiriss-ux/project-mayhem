import logging

from titan.integrations import garmin_sync
from titan.integrations.garmin_sync import GarminSync


class _FakeClient:
    def __init__(self, payloads):
        self._payloads = list(payloads)
        self.requested_dates = []

    def get_hrv_data(self, day):
        self.requested_dates.append(day)
        item = self._payloads.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_sync_hrv_happy_path_updates_metrics_and_returns_data(monkeypatch):
    events = []
    monkeypatch.setattr(garmin_sync, "_garmin_event", lambda action, **fields: events.append((action, fields)))

    sync = GarminSync(email="u", password="p")
    sync.is_connected = True
    sync.client = _FakeClient(
        [
            {"hrvSummary": {"lastNight5MinHigh": 48.26, "status": "BALANCED"}},
            {"hrvSummary": {"weeklyAvg": 51.0, "status": "LOW"}},
        ]
    )

    result = sync.sync_hrv(days_back=2)

    assert len(result) == 2
    assert result[0]["rmssd"] == 48.3
    assert result[1]["rmssd"] == 51.0
    assert sync.last_hrv_sync_metrics == {"days_back": 2, "synced_days": 2, "skipped_days": 0}
    assert ("hrv_sync_metrics", {"days_back": 2, "synced_days": 2, "skipped_days": 0}) in events


def test_sync_hrv_skipped_day_logs_and_emits_structured_event(monkeypatch, caplog):
    events = []
    monkeypatch.setattr(garmin_sync, "_garmin_event", lambda action, **fields: events.append((action, fields)))

    sync = GarminSync(email="u", password="p")
    sync.is_connected = True
    sync.client = _FakeClient(
        [
            ValueError("bad hrv payload"),
            {"hrvSummary": {"lastNight5MinHigh": 42, "status": "BALANCED"}},
        ]
    )

    with caplog.at_level(logging.WARNING):
        result = sync.sync_hrv(days_back=2)

    assert len(result) == 1
    assert sync.last_hrv_sync_metrics == {"days_back": 2, "synced_days": 1, "skipped_days": 1}

    skipped_event = next(fields for action, fields in events if action == "hrv_day_skipped")
    assert skipped_event["error_class"] == "ValueError"
    assert skipped_event["error_message"] == "bad hrv payload"
    assert skipped_event["date"] in sync.client.requested_dates

    assert "Skipping HRV day" in caplog.text
    assert "ValueError" in caplog.text
    assert "bad hrv payload" in caplog.text
