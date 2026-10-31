"""T5-50: Tests for Garmin activity_type → session_type mapping in DailyCoach.

The act dict from Garmin sync contains `activity_type` (not `session_type`).
The old code used `act.get('session_type', 'EASY')` which always fell through to
'EASY' because the key is `activity_type`. This test verifies the correct mapping.
"""
from unittest.mock import MagicMock

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


class TestSavedActivityUsesActivityType:
    """The real write path maps ``activity_type`` to the stored ``session_type`` (M0-15).

    These tests used to look for ``DailyCoach._persist_garmin_activities``, which was
    moved to ``garmin_persistence._save_activities`` (D-029), and skipped when it was
    missing, so they never ran. They now call the function the morning and the backfill
    both use, with the real sanity checker, and never skip.
    """

    def _make_act(self, activity_type=None, **kwargs):
        """Return a synthetic act dict shaped like GarminSync's output."""
        base = {
            "date": "2026-03-26",
            "distance_km": 10.0,
            "duration_sec": 3600,
            "avg_hr": 140,
            "max_hr": 165,
            "activity_id": "ACT001",
            "estimated_training_load": 50.0,
            "name": "Morning Run",
        }
        if activity_type is not None:
            base["activity_type"] = activity_type
        base.update(kwargs)
        return base

    def _saved_session_type(self, act):
        from titan.orchestration.garmin_persistence import _save_activities
        from titan.science.data_sanity import DataSanityChecker

        db = MagicMock()
        _save_activities(
            db, [act], "2026-03-26", athlete_id="owner", emit=lambda *a, **k: None,
            sanity=DataSanityChecker(),
        )
        assert db.save_session.call_count == 1, "the synthetic activity was not written"
        kwargs = db.save_session.call_args.kwargs
        assert kwargs["athlete_id"] == "owner"
        return kwargs["session_type"]

    @pytest.mark.parametrize("activity_type,expected_session_type", [
        ("running",           "EASY"),
        ("interval_training", "INTERVALS"),
        ("tempo_run",         "TEMPO"),
        ("long_run",          "LONG_RUN"),
        ("unknown_type",      "EASY"),
    ])
    def test_save_session_uses_mapped_session_type(self, activity_type, expected_session_type):
        assert self._saved_session_type(self._make_act(activity_type)) == expected_session_type

    def test_missing_activity_type_defaults_to_easy(self):
        assert self._saved_session_type(self._make_act()) == "EASY"

    def test_this_file_never_skips(self):
        """A missing function must fail here, never skip quietly again (M0-15)."""
        from pathlib import Path

        assert "pytest" + ".skip(" not in Path(__file__).read_text(encoding="utf-8")
