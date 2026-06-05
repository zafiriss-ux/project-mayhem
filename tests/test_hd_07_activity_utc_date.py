"""
HD-07: Activity date-bucket must use UTC date, not local-time truncation.

Root cause: ``a.get("startTimeLocal", "")[:10]`` takes the first 10 characters
of the local timestamp, discarding any timezone offset.  For an activity that
begins at 01:30 local time in UTC+3, the UTC date is the *previous* calendar
day — the truncation assigns the wrong day-bucket.

Fix: ``_activity_utc_date()`` parses with ``datetime.fromisoformat()``.  When
timezone info is present it converts to UTC before extracting the date.  Naive
strings (no tz suffix) fall back to ``[:10]`` — unchanged semantics.

Test scenarios:
  1. Timezone-aware early-morning: 01:30 UTC+3 → previous UTC date.
  2. Timezone-aware late-evening:  23:59 UTC+3 → same UTC date (regression guard).
  3. Naive string (no tz info):    "2026-04-03 07:00:00" → "2026-04-03" (unchanged).
  4. Space-separated naive:        "2026-04-03 07:00:00" → "2026-04-03".
  5. Empty string:                 "" → "".
  6. Unparseable garbage:          "not-a-date" → "not-a-dat" ([:10] fallback).
  7. Full sync integration:        activity with tz-aware startTimeLocal yields
                                   correct UTC date in returned dict.
"""

from unittest.mock import MagicMock

import pytest

import titan.integrations.garmin_sync as gs_mod
from titan.integrations.garmin_sync import GarminSync, _activity_utc_date

# ---------------------------------------------------------------------------
# Unit tests for _activity_utc_date helper
# ---------------------------------------------------------------------------

class TestActivityUtcDate:

    @pytest.mark.unit
    @pytest.mark.governance
    def test_early_morning_utc_plus3_crosses_to_previous_day(self):
        """01:30 local in UTC+3 = 22:30 UTC previous day → previous UTC date."""
        result = _activity_utc_date("2026-04-04T01:30:00+03:00")
        assert result == "2026-04-03", (
            f"Expected '2026-04-03' (UTC date), got '{result}'"
        )

    @pytest.mark.unit
    @pytest.mark.governance
    def test_late_evening_utc_plus3_stays_same_day(self):
        """23:59 local in UTC+3 = 20:59 UTC same day → same UTC date (no regression)."""
        result = _activity_utc_date("2026-04-03T23:59:00+03:00")
        assert result == "2026-04-03", (
            f"Expected '2026-04-03' (same UTC date), got '{result}'"
        )

    @pytest.mark.unit
    @pytest.mark.governance
    def test_naive_timestamp_no_tz_unchanged(self):
        """Naive ISO string (no tz) falls back to [:10] — no behaviour change."""
        result = _activity_utc_date("2026-04-03T07:00:00")
        assert result == "2026-04-03"

    @pytest.mark.unit
    @pytest.mark.governance
    def test_naive_space_separated_unchanged(self):
        """Space-separated naive timestamp — common Garmin format."""
        result = _activity_utc_date("2026-04-03 07:00:00")
        assert result == "2026-04-03"

    @pytest.mark.unit
    @pytest.mark.governance
    def test_empty_string_returns_empty(self):
        result = _activity_utc_date("")
        assert result == ""

    @pytest.mark.unit
    @pytest.mark.governance
    def test_unparseable_falls_back_to_truncation(self):
        """Unparseable value falls back to [:10] without raising."""
        result = _activity_utc_date("not-a-date-string")
        assert result == "not-a-date"

    @pytest.mark.unit
    @pytest.mark.governance
    def test_utc_minus3_midnight_crossing(self):
        """23:30 local in UTC-3 = 02:30 next day UTC → next UTC date."""
        result = _activity_utc_date("2026-04-03T23:30:00-03:00")
        assert result == "2026-04-04", (
            f"Expected '2026-04-04' (next UTC day), got '{result}'"
        )

    @pytest.mark.unit
    @pytest.mark.governance
    def test_utc_zero_offset_unchanged(self):
        """UTC+0 offset: local date equals UTC date."""
        result = _activity_utc_date("2026-04-03T15:00:00+00:00")
        assert result == "2026-04-03"


# ---------------------------------------------------------------------------
# Integration test: sync_activities uses UTC date in returned records
# ---------------------------------------------------------------------------

class TestSyncActivitiesUtcDate:

    def _make_connected_sync(self):
        sync = GarminSync(email="test@example.com", password="secret")
        sync.is_connected = True
        sync.client = MagicMock()
        return sync

    @pytest.mark.unit
    @pytest.mark.governance
    def test_activity_with_tz_offset_yields_utc_date(self, monkeypatch):
        """sync_activities records use UTC date when startTimeLocal carries tz offset.

        Activity at 01:30 UTC+3 → UTC date is the previous calendar day.
        The returned dict['date'] must reflect the UTC date, not the local date.
        """
        sync = self._make_connected_sync()
        # Patch _garmin_event to suppress structured logging noise
        monkeypatch.setattr(gs_mod, "_garmin_event", lambda *a, **kw: None)
        sync.client.get_activities_by_date = MagicMock(return_value=[
            {
                "startTimeLocal": "2026-04-04T01:30:00+03:00",
                "activityType": {"typeKey": "running"},
                "duration": 3600,
                "distance": 10000,
                "averageHR": 145,
                "maxHR": 175,
                "calories": 600,
                "elevationGain": 50,
                "activityId": "act-tz-1",
            }
        ])

        activities = sync.sync_activities(days_back=1)

        assert len(activities) == 1
        assert activities[0]["date"] == "2026-04-03", (
            f"Expected UTC date '2026-04-03', got '{activities[0]['date']}'"
        )

    @pytest.mark.unit
    @pytest.mark.governance
    def test_activity_naive_timestamp_unchanged(self, monkeypatch):
        """Naive startTimeLocal (no tz) keeps the same date as before the fix."""
        sync = self._make_connected_sync()
        monkeypatch.setattr(gs_mod, "_garmin_event", lambda *a, **kw: None)
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
                "activityId": "act-naive-1",
            }
        ])

        activities = sync.sync_activities(days_back=1)

        assert len(activities) == 1
        assert activities[0]["date"] == "2026-04-03"
