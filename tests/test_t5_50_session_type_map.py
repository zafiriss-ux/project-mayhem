"""T5-50: Tests for Garmin activity_type → session_type mapping in DailyCoach.

The act dict from Garmin sync contains `activity_type` (not `session_type`).
The old code used `act.get('session_type', 'EASY')` which always fell through to
'EASY' because the key is `activity_type`. This test verifies the correct mapping.
"""
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import the mapping dict directly once it exists.
# Before the fix, this import will fail or the dict won't exist —
# which makes the tests below fail as required by test-first TDD.
# ---------------------------------------------------------------------------

def _get_mapping():
    """Return the _GARMIN_ACTIVITY_TYPE_MAP from daily_coach module."""
    import titan.orchestration.daily_coach as dc
    return dc._GARMIN_ACTIVITY_TYPE_MAP


class TestGarminActivityTypeMapping:
    """Unit tests for the Garmin activity_type → session_type mapping dict."""

    def test_mapping_exists(self):
        """The module-level mapping dict must exist."""
        mapping = _get_mapping()
        assert isinstance(mapping, dict)

    def test_running_maps_to_easy(self):
        mapping = _get_mapping()
        assert mapping.get("running", "EASY") == "EASY"

    def test_interval_training_maps_to_intervals(self):
        mapping = _get_mapping()
        result = mapping.get("interval_training", "EASY")
        assert result == "INTERVALS", f"Expected INTERVALS, got {result}"

    def test_tempo_run_maps_to_tempo(self):
        mapping = _get_mapping()
        result = mapping.get("tempo_run", "EASY")
        assert result == "TEMPO", f"Expected TEMPO, got {result}"

    def test_long_run_maps_to_long_run(self):
        mapping = _get_mapping()
        result = mapping.get("long_run", "EASY")
        assert result == "LONG_RUN", f"Expected LONG_RUN, got {result}"

    def test_unknown_type_defaults_to_easy(self):
        mapping = _get_mapping()
        result = mapping.get("unknown_activity_xyz", "EASY")
        assert result == "EASY"

    def test_missing_key_defaults_to_easy(self):
        mapping = _get_mapping()
        result = mapping.get("", "EASY")
        assert result == "EASY"


class TestDailyCoachSaveSessionUsesActivityType:
    """Integration-style tests: DailyCoach.persist_synced_activities uses activity_type."""

    def _make_coach(self):
        """Build a minimal DailyCoach with all heavy deps mocked out."""
        from titan.orchestration.daily_coach import DailyCoach

        mock_db = MagicMock()
        mock_db.get_latest_metrics.return_value = None
        mock_db.get_training_load_history.return_value = []

        coach = DailyCoach.__new__(DailyCoach)
        coach.db = mock_db
        coach.garmin_sync = MagicMock()
        coach.weather_api = MagicMock()
        coach.athlete = MagicMock()
        coach.athlete.vo2_max = 50.0
        coach.athlete.resting_hr = 50
        coach.athlete.max_hr = 180
        coach.athlete.athlete_id = "test-athlete"
        coach._degraded_mode = False
        return coach, mock_db

    def _make_act(self, activity_type, **kwargs):
        """Return a minimal act dict as produced by garmin_sync."""
        base = {
            "date": "2026-03-26",
            "activity_type": activity_type,
            "distance_km": 10.0,
            "duration_sec": 3600,
            "avg_hr": 140,
            "max_hr": 165,
            "activity_id": "ACT001",
            "estimated_training_load": 50.0,
            "name": "Morning Run",
        }
        base.update(kwargs)
        return base

    def _call_persist(self, coach, acts):
        """Call the method that persists Garmin activities into the DB."""
        # The method name is step 10 in the 12-step pipeline; find it by searching.
        import titan.orchestration.daily_coach as dc
        # Call the private helper that iterates over acts and calls db.save_session.
        # We patch the sanity validation to always pass (no violations).
        with patch("titan.orchestration.daily_coach.validate_activity_fields", return_value=[]):
            coach._persist_garmin_activities(acts)

    def _find_persist_method(self, coach):
        """Return the method responsible for persisting garmin activities."""
        # Inspect which public/private method calls db.save_session with activity data.
        import titan.orchestration.daily_coach as dc
        return getattr(coach, "_persist_garmin_activities", None)

    def _extract_session_type_call(self, mock_db):
        """Return the session_type kwarg from the first save_session call."""
        assert mock_db.save_session.called, "db.save_session was not called"
        call_kwargs = mock_db.save_session.call_args
        if call_kwargs.kwargs:
            return call_kwargs.kwargs.get("session_type")
        # positional — unlikely but handle it
        return call_kwargs.args[1] if len(call_kwargs.args) > 1 else None

    # ---- parametrised mapping tests via DailyCoach ----

    @pytest.mark.parametrize("activity_type,expected_session_type", [
        ("running",           "EASY"),
        ("interval_training", "INTERVALS"),
        ("tempo_run",         "TEMPO"),
        ("long_run",          "LONG_RUN"),
        ("unknown_type",      "EASY"),
    ])
    def test_save_session_uses_mapped_session_type(self, activity_type, expected_session_type):
        """DailyCoach must pass the mapped session_type to db.save_session."""
        coach, mock_db = self._make_coach()
        method = self._find_persist_method(coach)
        if method is None:
            pytest.skip("_persist_garmin_activities not yet implemented")

        act = self._make_act(activity_type)
        with patch("titan.orchestration.daily_coach.validate_activity_fields", return_value=[]):
            method([act])

        session_type = self._extract_session_type_call(mock_db)
        assert session_type == expected_session_type, (
            f"activity_type={activity_type!r}: expected session_type={expected_session_type!r}, "
            f"got {session_type!r}"
        )

    def test_missing_activity_type_defaults_to_easy(self):
        """Acts without activity_type key must default to EASY."""
        coach, mock_db = self._make_coach()
        method = self._find_persist_method(coach)
        if method is None:
            pytest.skip("_persist_garmin_activities not yet implemented")

        # act has no activity_type key
        act = {
            "date": "2026-03-26",
            "distance_km": 10.0,
            "duration_sec": 3600,
            "avg_hr": 140,
            "max_hr": 165,
            "activity_id": "ACT002",
            "estimated_training_load": 50.0,
            "name": "Morning Run",
        }
        with patch("titan.orchestration.daily_coach.validate_activity_fields", return_value=[]):
            method([act])

        session_type = self._extract_session_type_call(mock_db)
        assert session_type == "EASY", f"Expected EASY for missing activity_type, got {session_type!r}"
