"""
T5-67: sync_sleep / sync_hrv success events must not fire when outer except triggers.

Acceptance criterion: when the outer except block is triggered, no "synced"
success event is emitted by that method — only the error event fires.

Outer exceptions are triggered by patching datetime.now() (called in the loop
body outside the per-day inner try) to raise. Both sync_sleep and sync_hrv
gate their success event and _log_sync inside the outer try block (T5-67 fix),
so they are unreachable when the outer except fires.
"""

from unittest.mock import MagicMock, patch

import pytest

import titan.integrations.garmin_sync as gs_mod
from titan.integrations.garmin_sync import GarminSync


def _make_connected_sync():
    """Return a GarminSync instance that appears connected."""
    sync = GarminSync(email="test@example.com", password="secret")
    sync.is_connected = True
    sync.client = MagicMock()
    return sync


def _capture_events(monkeypatch):
    """Patch _garmin_event and return a list that accumulates event names."""
    emitted: list[str] = []

    def _spy(event_name, **kwargs):
        emitted.append(event_name)

    monkeypatch.setattr(gs_mod, "_garmin_event", _spy)
    return emitted


# ---------------------------------------------------------------------------
# sync_sleep
# ---------------------------------------------------------------------------

class TestSyncSleepSuccessEventGating:

    def test_sleep_synced_not_emitted_on_outer_exception(self, monkeypatch):
        """sleep_synced must not fire when the outer try raises.

        datetime.now() is called in the loop body outside the per-day inner
        try — raising there triggers the outer except path.
        """
        sync = _make_connected_sync()
        emitted = _capture_events(monkeypatch)

        with patch("titan.integrations.garmin_sync.datetime") as mock_dt:
            mock_dt.now.side_effect = RuntimeError("network reset")
            mock_dt.utcnow = MagicMock(return_value=MagicMock(isoformat=lambda: "2026-01-01T00:00:00Z"))
            sync.sync_sleep(days_back=2)

        assert "sleep_synced" not in emitted, (
            f"'sleep_synced' emitted after outer exception; events: {emitted}"
        )

    def test_sleep_synced_emitted_on_success(self, monkeypatch):
        """sleep_synced fires when the sync completes without outer exception."""
        sync = _make_connected_sync()
        sync.client.get_sleep_data = MagicMock(return_value={
            "dailySleepDTO": {
                "sleepTimeSeconds": 25200,
                "deepSleepSeconds": 5400,
                "remSleepSeconds": 7200,
                "sleepScores": {"overall": {"value": 85}},
            }
        })
        emitted = _capture_events(monkeypatch)

        sync.sync_sleep(days_back=1)

        assert "sleep_synced" in emitted, (
            f"'sleep_synced' not emitted on success; events: {emitted}"
        )

    def test_sleep_synced_not_emitted_but_failed_event_is(self, monkeypatch):
        """On outer exception, sync_sleep_failed is emitted, sleep_synced is not."""
        sync = _make_connected_sync()
        emitted = _capture_events(monkeypatch)

        with patch("titan.integrations.garmin_sync.datetime") as mock_dt:
            mock_dt.now.side_effect = RuntimeError("timeout")
            mock_dt.utcnow = MagicMock(return_value=MagicMock(isoformat=lambda: "2026-01-01T00:00:00Z"))
            sync.sync_sleep(days_back=1)

        assert "sleep_synced" not in emitted
        assert "sync_sleep_failed" in emitted, (
            f"'sync_sleep_failed' not emitted; events: {emitted}"
        )


# ---------------------------------------------------------------------------
# sync_hrv
# ---------------------------------------------------------------------------

class TestSyncHrvSuccessEventGating:

    def test_hrv_synced_not_emitted_on_outer_exception(self, monkeypatch):
        """hrv_synced must not fire when the outer try raises.

        datetime.now() is called in the loop body outside the per-day inner
        try — raising there triggers the outer except path.
        """
        sync = _make_connected_sync()
        emitted = _capture_events(monkeypatch)

        with patch("titan.integrations.garmin_sync.datetime") as mock_dt:
            mock_dt.now.side_effect = RuntimeError("connection reset")
            mock_dt.utcnow = MagicMock(return_value=MagicMock(isoformat=lambda: "2026-01-01T00:00:00Z"))
            sync.sync_hrv(days_back=2)

        assert "hrv_synced" not in emitted, (
            f"'hrv_synced' emitted after outer exception; events: {emitted}"
        )

    def test_hrv_synced_emitted_on_success(self, monkeypatch):
        """hrv_synced fires when sync completes cleanly."""
        sync = _make_connected_sync()
        sync.client.get_hrv_data = MagicMock(return_value={
            "hrvSummary": {
                "lastNight5MinHigh": 58.5,
                "status": "BALANCED",
            }
        })
        emitted = _capture_events(monkeypatch)

        sync.sync_hrv(days_back=1)

        assert "hrv_synced" in emitted, (
            f"'hrv_synced' not emitted on success; events: {emitted}"
        )

    def test_hrv_synced_not_emitted_but_failed_event_is(self, monkeypatch):
        """On outer exception, sync_hrv_failed is emitted, hrv_synced is not."""
        sync = _make_connected_sync()
        emitted = _capture_events(monkeypatch)

        with patch("titan.integrations.garmin_sync.datetime") as mock_dt:
            mock_dt.now.side_effect = RuntimeError("timeout")
            mock_dt.utcnow = MagicMock(return_value=MagicMock(isoformat=lambda: "2026-01-01T00:00:00Z"))
            sync.sync_hrv(days_back=1)

        assert "hrv_synced" not in emitted
        assert "sync_hrv_failed" in emitted, (
            f"'sync_hrv_failed' not emitted; events: {emitted}"
        )
