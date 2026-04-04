"""DegradedModeTracker tests (HD-06).

Verifies the contract and behavioral invariants of DegradedModeTracker.
Documents the known limitation (HD-06: state resets on restart) and
verifies the UTC-aware timestamp enforcement.

Framework reference:
  - HD-06: DegradedModeTracker in-memory only — resets on restart; 24h SLO evidence lost
  - HR-01: All datetime in governance path must be UTC-aware
  - Required test: DegradedModeTracker survives simulated restart (documents gap)
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from titan.orchestration.daily_coach import DegradedModeTracker

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_tracker() -> DegradedModeTracker:
    return DegradedModeTracker()


def _noop_alert(msg: str) -> None:
    pass


# ── Basic contract ────────────────────────────────────────────────────────────


def test_tracker_starts_empty():
    """Tracker initialises with no degraded state."""
    tracker = _make_tracker()
    assert tracker.get_degraded_since() == {}


def test_tracker_records_onset_on_first_degraded_flag():
    """First call with is_degraded=True records the onset timestamp."""
    tracker = _make_tracker()
    tracker.update({"garmin": True}, _noop_alert)
    since = tracker.get_degraded_since()
    assert "garmin" in since
    assert since["garmin"] is not None


def test_tracker_clears_on_recovery():
    """Recovery (is_degraded=False) removes the failure type from state."""
    tracker = _make_tracker()
    tracker.update({"garmin": True}, _noop_alert)
    tracker.update({"garmin": False}, _noop_alert)
    assert "garmin" not in tracker.get_degraded_since()


def test_tracker_onset_timestamp_is_stable_across_updates():
    """Onset timestamp must not change while the failure type stays degraded."""
    tracker = _make_tracker()
    tracker.update({"garmin": True}, _noop_alert)
    first_ts = tracker.get_degraded_since()["garmin"]
    tracker.update({"garmin": True}, _noop_alert)  # still degraded
    second_ts = tracker.get_degraded_since()["garmin"]
    assert first_ts == second_ts


def test_tracker_fires_alert_after_threshold():
    """Alert callable fires when failure has been active >= 24 h."""
    tracker = _make_tracker()
    # Manually inject an onset 25 hours ago
    tracker._degraded_since["garmin"] = datetime.now(UTC) - timedelta(hours=25)
    alert_fn = MagicMock()
    tracker.update({"garmin": True}, alert_fn)
    alert_fn.assert_called_once()
    call_msg = alert_fn.call_args[0][0]
    assert "garmin" in call_msg


def test_tracker_does_not_fire_alert_before_threshold():
    """Alert callable must NOT fire when failure has been active < 24 h."""
    tracker = _make_tracker()
    tracker._degraded_since["garmin"] = datetime.now(UTC) - timedelta(hours=20)
    alert_fn = MagicMock()
    tracker.update({"garmin": True}, alert_fn)
    alert_fn.assert_not_called()


def test_tracker_resets_timer_after_alert():
    """After alerting, onset is reset to now to avoid alert storms."""
    tracker = _make_tracker()
    tracker._degraded_since["garmin"] = datetime.now(UTC) - timedelta(hours=25)
    alert_fn = MagicMock()
    tracker.update({"garmin": True}, alert_fn)
    alert_fn.reset_mock()
    # Next update with same failure and elapsed time near-zero → no second alert
    tracker.update({"garmin": True}, alert_fn)
    alert_fn.assert_not_called()


# ── UTC enforcement (HR-01) ───────────────────────────────────────────────────


def test_tracker_stored_timestamps_are_utc_aware():
    """DegradedModeTracker must store UTC-aware datetime objects (HR-01)."""
    tracker = _make_tracker()
    tracker.update({"garmin": True}, _noop_alert)
    for _name, ts in tracker._degraded_since.items():
        assert ts.tzinfo is not None, (
            "DegradedModeTracker must store timezone-aware datetimes (HR-01)"
        )
        # UTC-aware timestamps have UTC offset = 0
        assert ts.utcoffset().total_seconds() == 0


def test_tracker_get_degraded_since_returns_iso_string():
    """get_degraded_since() returns ISO-8601 strings (not raw datetime objects)."""
    tracker = _make_tracker()
    tracker.update({"garmin": True}, _noop_alert)
    result = tracker.get_degraded_since()
    for _name, ts_str in result.items():
        assert isinstance(ts_str, str)
        # Must be parseable as ISO datetime
        dt = datetime.fromisoformat(ts_str)
        assert dt.tzinfo is not None, "Serialised timestamp must be timezone-aware"


# ── HD-06: In-memory restart limitation (documented gap) ─────────────────────


def test_tracker_loses_state_on_restart_simulation():
    """HD-06 KNOWN LIMITATION: DegradedModeTracker resets on process restart.

    This test documents the gap. The fix (persistent storage) is tracked as
    HD-06 in the Technical Debt Register.  When HD-06 is resolved, this test
    must be updated to verify state is restored after re-instantiation.
    """
    tracker = _make_tracker()
    tracker.update({"garmin": True}, _noop_alert)
    assert "garmin" in tracker.get_degraded_since()

    # Simulate restart: new instance has no state
    new_tracker = _make_tracker()
    assert new_tracker.get_degraded_since() == {}, (
        "HD-06 GAP: state is lost on restart. "
        "This test documents the known limitation — update when HD-06 is resolved."
    )


def test_tracker_multiple_failure_types_tracked_independently():
    """Multiple concurrent failure types are each tracked with their own onset."""
    tracker = _make_tracker()
    tracker.update({"garmin": True, "persistence": True}, _noop_alert)
    since = tracker.get_degraded_since()
    assert "garmin" in since
    assert "persistence" in since

    # Recover garmin but keep persistence
    tracker.update({"garmin": False, "persistence": True}, _noop_alert)
    since = tracker.get_degraded_since()
    assert "garmin" not in since
    assert "persistence" in since
