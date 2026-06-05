"""
T5-67: success events must not fire when the outer except block triggers.

Acceptance criterion: when the outer except block is triggered in any of the
four sync methods (sync_sleep, sync_hrv, sync_activities, sync_weight), no
"synced" success event is emitted — only the error/failure event fires.

All four methods use a boolean ``sync_succeeded`` flag (T5-67 fix): the flag
is set True only after all processing completes without raising; success events
are emitted under ``if sync_succeeded:`` outside the try/except block.
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

    @pytest.mark.unit
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

    @pytest.mark.unit
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

    @pytest.mark.unit
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

    @pytest.mark.unit
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

    @pytest.mark.unit
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

    @pytest.mark.unit
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


# ---------------------------------------------------------------------------
# sync_activities
# ---------------------------------------------------------------------------

class TestSyncActivitiesSuccessEventGating:

    @pytest.mark.unit
    def test_activities_synced_not_emitted_on_outer_exception(self, monkeypatch):
        """activities_synced must not fire when the outer try raises.

        Patching get_activities_by_date to raise triggers the outer except
        before sync_succeeded can be set True, so activities_synced is blocked.
        """
        sync = _make_connected_sync()
        sync.client.get_activities_by_date = MagicMock(
            side_effect=RuntimeError("network reset")
        )
        emitted = _capture_events(monkeypatch)

        sync.sync_activities(days_back=3)

        assert "activities_synced" not in emitted, (
            f"'activities_synced' emitted after outer exception; events: {emitted}"
        )

    @pytest.mark.unit
    def test_activities_synced_emitted_on_success(self, monkeypatch):
        """activities_synced fires when the sync completes without outer exception."""
        sync = _make_connected_sync()
        sync.client.get_activities_by_date = MagicMock(return_value=[
            {
                "startTimeLocal": "2026-04-03 07:00:00",
                "activityType": {"typeKey": "running"},
                "duration": 3600,
                "distance": 10000,
                "averageHR": 145,
                "maxHR": 175,
                "calories": 600,
                "elevationGain": 50,
                "activityId": "act-1",
            }
        ])
        emitted = _capture_events(monkeypatch)

        sync.sync_activities(days_back=1)

        assert "activities_synced" in emitted, (
            f"'activities_synced' not emitted on success; events: {emitted}"
        )

    @pytest.mark.unit
    def test_activities_synced_not_emitted_but_failed_event_is(self, monkeypatch):
        """On outer exception, sync_activities_failed is emitted, activities_synced is not."""
        sync = _make_connected_sync()
        sync.client.get_activities_by_date = MagicMock(
            side_effect=ConnectionError("timeout")
        )
        emitted = _capture_events(monkeypatch)

        sync.sync_activities(days_back=1)

        assert "activities_synced" not in emitted
        assert "sync_activities_failed" in emitted, (
            f"'sync_activities_failed' not emitted; events: {emitted}"
        )


# ---------------------------------------------------------------------------
# sync_weight
# ---------------------------------------------------------------------------

class TestSyncWeightSuccessEventGating:

    @pytest.mark.unit
    def test_weight_synced_not_emitted_on_outer_exception(self, monkeypatch):
        """weight_synced must not fire when the outer try raises.

        Patching get_weigh_ins to raise triggers the outer except before
        sync_succeeded is set True, so weight_synced is blocked.
        """
        sync = _make_connected_sync()
        sync.client.get_weigh_ins = MagicMock(
            side_effect=RuntimeError("API unavailable")
        )
        emitted = _capture_events(monkeypatch)

        sync.sync_weight(days_back=7)

        assert "weight_synced" not in emitted, (
            f"'weight_synced' emitted after outer exception; events: {emitted}"
        )

    @pytest.mark.unit
    def test_weight_synced_emitted_on_success(self, monkeypatch):
        """weight_synced fires when the sync completes without outer exception."""
        sync = _make_connected_sync()
        sync.client.get_weigh_ins = MagicMock(return_value={
            "dailyWeightSummaries": [
                {
                    "calendarDate": "2026-04-03",
                    "allDayWeightSummaries": [{"latestWeight": 70000}],
                }
            ]
        })
        emitted = _capture_events(monkeypatch)

        sync.sync_weight(days_back=1)

        assert "weight_synced" in emitted, (
            f"'weight_synced' not emitted on success; events: {emitted}"
        )

    @pytest.mark.unit
    def test_weight_synced_not_emitted_but_failed_event_is(self, monkeypatch):
        """On outer exception, sync_weight_failed is emitted, weight_synced is not."""
        sync = _make_connected_sync()
        sync.client.get_weigh_ins = MagicMock(
            side_effect=OSError("connection refused")
        )
        emitted = _capture_events(monkeypatch)

        sync.sync_weight(days_back=1)

        assert "weight_synced" not in emitted
        assert "sync_weight_failed" in emitted, (
            f"'sync_weight_failed' not emitted; events: {emitted}"
        )
