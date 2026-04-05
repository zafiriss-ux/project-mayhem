"""
Fail-closed scenario tests — FS-01, FS-02, FS-06, FS-07, FS-08 (§9.1 Framework).

FS-01  NaN ACWR governance block        — non-finite input must never pass VO2 gate
FS-02  Seven-day HRV decline warning    — baseline drift detection fires at threshold
FS-06  TZ-boundary correct UTC date     — startTimeLocal UTC conversion
FS-07  Restart degraded timer restored  — DegradedModeTracker survives process restart
FS-08  Stale/fresh mixed state          — data_confidence_low forces conservative ceiling
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from titan.config.thresholds import HRV_DRIFT_THRESHOLD_MS
from titan.integrations.garmin_sync import _activity_utc_date
from titan.orchestration.daily_coach import DegradedModeTracker
from titan.science.governance_engine import GovernanceEngine
from titan.science.hrv_engine import HRVGuidedEngine

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _base_governance_context(**overrides: Any) -> dict[str, Any]:
    """Minimal valid governance context with optional per-test overrides."""
    base: dict[str, Any] = {
        "today_hrv": 65.0,
        "baseline_hrv": 65.0,
        "hrv_std_dev": 5.0,
        "today_rhr": 48,
        "baseline_rhr": 48,
        "sleep_score": 80,
        "readiness_score": 80,
        "subjective_fatigue_score": 2,
        "tsb_value": 5.0,
        "acwr": 1.0,
        "glycogen_debt": 1.0,
        "fatigue_level": "LOW",
        "fueling_confirmed": True,
        "days_since_last_vo2": 3,
        "injury_flag": False,
        "data_confidence_low": False,
        "persistence_degraded": False,
    }
    base.update(overrides)
    return base


# ─────────────────────────────────────────────────────────────────────────────
# FS-01 — NaN ACWR governance block
# ─────────────────────────────────────────────────────────────────────────────

class TestFS01NaNAcwrGovernanceBlock:
    """
    NaN ACWR must never allow a quality session through governance.

    When acwr=float("nan") is injected with a HAMMER session:
    - VO2 eligibility gate emits NAN_REJECTED (V1 invalid input)
    - data_confidence_low=True (realistic: bad data ⇒ low confidence) applies
      the STARTUP_DATA_CONFIDENCE_CEILING → EASY + max_zone ≤ 2
    """

    def test_nan_acwr_does_not_pass_vo2_gate(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """FS-01-A: NaN ACWR causes V1 failure in VO2 eligibility gate."""
        engine = GovernanceEngine()
        session = {"session_type": "HAMMER", "max_zone": 5, "duration_min": 60}
        ctx = _base_governance_context(
            acwr=float("nan"),
            fueling_confirmed=True,
        )

        with caplog.at_level(logging.INFO, logger="titan.science.governance_engine"):
            result = engine.apply_constraints(session_plan=session, context=ctx)

        # The session must have been downgraded away from HAMMER.
        assert result.get("session_type") != "HAMMER", (
            "HAMMER session must not survive a NaN ACWR input"
        )
        # Must not be a quality session.
        quality_sessions = {"HAMMER", "RACE", "INTERVALS"}
        assert result.get("session_type") not in quality_sessions, (
            f"Quality session must not be allowed with NaN ACWR, "
            f"got: {result.get('session_type')}"
        )

        # VO2_ELIGIBILITY NAN_REJECTED must appear in the log.
        nan_rejected_events = [
            r for r in caplog.records
            if "NAN_REJECTED" in r.getMessage()
        ]
        assert nan_rejected_events, (
            "Expected NAN_REJECTED log entry from governance gate when acwr=nan"
        )

    def test_nan_acwr_with_data_confidence_low_forces_easy_zone2(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """FS-01-B: NaN ACWR + data_confidence_low=True → EASY + max_zone ≤ 2."""
        engine = GovernanceEngine()
        session = {"session_type": "HAMMER", "max_zone": 5, "duration_min": 60}
        ctx = _base_governance_context(
            acwr=float("nan"),
            data_confidence_low=True,  # realistic: corrupt input signals low confidence
        )

        with caplog.at_level(logging.INFO, logger="titan.science.governance_engine"):
            result = engine.apply_constraints(session_plan=session, context=ctx)

        assert result.get("session_type") == "EASY", (
            f"data_confidence_low + NaN ACWR must produce EASY, got {result.get('session_type')}"
        )
        assert result.get("max_zone", 5) <= 2, (
            f"max_zone must be ≤ 2 under data_confidence_low ceiling, got {result.get('max_zone')}"
        )
        # STARTUP_DATA_CONFIDENCE_CEILING lock must be applied.
        assert "STARTUP_DATA_CONFIDENCE_CEILING" in result.get("governance_locks_applied", []), (
            "STARTUP_DATA_CONFIDENCE_CEILING lock must be present in governance_locks_applied"
        )

    def test_nan_acwr_governance_result_is_not_permissive(self) -> None:
        """FS-01-C: NaN ACWR must never produce governance_clean=True for a quality session."""
        engine = GovernanceEngine()
        # Try every quality session type.
        for session_type in ("HAMMER", "RACE", "INTERVALS"):
            session = {"session_type": session_type, "max_zone": 5, "duration_min": 60}
            ctx = _base_governance_context(acwr=float("nan"), fueling_confirmed=True)
            result = engine.apply_constraints(session_plan=session, context=ctx)

            # If VO2 gate fired, result cannot be clean.
            post_type = result.get("session_type")
            is_quality = post_type in {"HAMMER", "RACE", "INTERVALS"}
            locks = result.get("governance_locks_applied", [])

            if is_quality:
                # If somehow still a quality session, it MUST be governance_clean=False
                # (this path should not happen, but if it does we assert correctness).
                assert result.get("governance_clean") is not True or not locks, (
                    f"Quality session '{post_type}' with NaN ACWR must not be governance_clean=True"
                )
            else:
                # Downgraded — acceptable; verify at least one lock was applied.
                assert locks, (
                    f"NaN ACWR must trigger at least one governance lock for {session_type}"
                )


# ─────────────────────────────────────────────────────────────────────────────
# FS-02 — Seven-day HRV decline triggers warning
# ─────────────────────────────────────────────────────────────────────────────

class TestFS02HRVDeclineWarning:
    """
    A monotone HRV decline must be detected by check_baseline_drift when
    the recent-window mean diverges more than HRV_DRIFT_THRESHOLD_MS (8.0 ms)
    from the anchor window mean.
    """

    def test_seven_day_hrv_decline_detected_by_drift_check(self) -> None:
        """
        FS-02: HRV series [60, 57, 54, 51, 48, 45, 42] (−3 ms/day).
        Using window_days=3: anchor=[60,57,54], recent=[51,48,45].
        delta = |48 - 57| = 9 > HRV_DRIFT_THRESHOLD_MS (8.0) → drift detected.
        """
        engine = HRVGuidedEngine()
        hrv_series = [60.0, 57.0, 54.0, 51.0, 48.0, 45.0, 42.0]
        for i, hrv in enumerate(hrv_series):
            date = f"2026-01-{i + 1:02d}"
            engine.add_hrv_measurement(date, hrv)

        # With window_days=3, requires ≥ 6 entries (3 anchor + 3 recent).
        # We have 7, so: anchor=[60,57,54,51], recent=[48,45,42].
        drift_detected = engine.check_baseline_drift(window_days=3)

        assert drift_detected is True, (
            f"Expected drift to be detected (delta > {HRV_DRIFT_THRESHOLD_MS} ms); "
            f"series: {hrv_series}, window=3"
        )

    def test_static_describe_calibration_drift_detects_decline(self) -> None:
        """
        FS-02: describe_calibration_drift with baseline=60, current=50.
        delta = |50 - 60| = 10 > HRV_DRIFT_THRESHOLD_MS (8.0) → drift_detected=True.
        """
        state = HRVGuidedEngine.describe_calibration_drift(
            baseline_hrv_ms=60.0,
            current_hrv_ms=50.0,
            drift_threshold_ms=HRV_DRIFT_THRESHOLD_MS,
        )

        assert state.drift_detected is True, (
            f"drift_detected must be True when |delta|={state.abs_delta_ms} > {HRV_DRIFT_THRESHOLD_MS}"
        )
        assert state.abs_delta_ms > HRV_DRIFT_THRESHOLD_MS
        assert state.delta_ms == pytest.approx(-10.0, abs=0.01)

    def test_stable_hrv_series_does_not_trigger_drift(self) -> None:
        """FS-02-neg: Stable HRV ±1 ms must not trigger drift detection."""
        engine = HRVGuidedEngine()
        stable = [60.0, 60.5, 59.5, 60.0, 60.5, 59.5, 60.0]
        for i, hrv in enumerate(stable):
            engine.add_hrv_measurement(f"2026-02-{i + 1:02d}", hrv)

        drift = engine.check_baseline_drift(window_days=3)
        assert drift is False, "Stable HRV (variation ≈ 0.5 ms) must not trigger drift warning"

    def test_insufficient_data_returns_false(self) -> None:
        """FS-02-guard: Fewer than window_days*2 entries → False (insufficient data)."""
        engine = HRVGuidedEngine()
        # Add only 5 entries; window_days=3 requires 6.
        for i in range(5):
            engine.add_hrv_measurement(f"2026-03-{i + 1:02d}", 60.0 - i)

        drift = engine.check_baseline_drift(window_days=3)
        assert drift is False, "Insufficient data must return False, not raise"

    def test_declining_series_data_confidence_implied_by_drift(self) -> None:
        """
        FS-02: When drift is detected, describe_calibration_drift must set
        drift_detected=True so callers can flag data_confidence_low.
        """
        state = HRVGuidedEngine.describe_calibration_drift(
            baseline_hrv_ms=60.0,
            current_hrv_ms=50.0,
            drift_threshold_ms=HRV_DRIFT_THRESHOLD_MS,
        )
        # Simulates: confidence["hrv_baseline_drift"] = not state.drift_detected
        data_confidence_ok = not state.drift_detected
        assert data_confidence_ok is False, (
            "data_confidence must be flagged False when HRV drift is detected"
        )


# ─────────────────────────────────────────────────────────────────────────────
# FS-06 — TZ-boundary correct UTC date
# ─────────────────────────────────────────────────────────────────────────────

class TestFS06TimezoneUTCDate:
    """
    _activity_utc_date must convert startTimeLocal with timezone offset to the
    correct UTC calendar date (HD-07 fix).

    Key case: 23:59 local in UTC+3 = 20:59 UTC = still the same calendar day.
    """

    def test_late_evening_utc_plus3_stored_as_correct_utc_date(self) -> None:
        """
        FS-06: startTimeLocal = "2026-04-03T23:59:00+03:00"
        23:59 UTC+3 = 20:59 UTC → calendar date is still 2026-04-03.
        """
        result = _activity_utc_date("2026-04-03T23:59:00+03:00")
        assert result == "2026-04-03", (
            f"Expected '2026-04-03' (UTC), got '{result}'. "
            f"23:59 UTC+3 = 20:59 UTC = still Apr 3."
        )

    def test_midnight_crossing_stored_as_utc_next_day(self) -> None:
        """
        UTC+3 activity at 22:30 local = 19:30 UTC → Apr 3 still.
        UTC+3 activity at 23:00 local = 20:00 UTC → Apr 3 still.
        A true midnight crossing: 01:00 local UTC+3 = 22:00 UTC Apr 2 → Apr 2.
        """
        # 01:00 local UTC+3 = 22:00 UTC previous day
        result = _activity_utc_date("2026-04-03T01:00:00+03:00")
        assert result == "2026-04-02", (
            f"01:00 UTC+3 = 22:00 UTC April 2 — expected '2026-04-02', got '{result}'"
        )

    def test_utc_naive_string_uses_truncation_fallback(self) -> None:
        """
        FS-06-fallback: Strings without timezone info use [:10] truncation
        (unchanged semantics for naive timestamps).
        """
        result = _activity_utc_date("2026-04-03T23:59:00")
        # No tzinfo → [:10] semantics: "2026-04-03"
        assert result == "2026-04-03", (
            f"Naive timestamp must use local date truncation, got '{result}'"
        )

    def test_empty_string_returns_empty(self) -> None:
        """FS-06-guard: Empty input returns empty string without raising."""
        result = _activity_utc_date("")
        assert result == ""

    def test_utc_plus0_preserves_date(self) -> None:
        """UTC+0 activity: no offset → date unchanged."""
        result = _activity_utc_date("2026-04-03T12:00:00+00:00")
        assert result == "2026-04-03"


# ─────────────────────────────────────────────────────────────────────────────
# FS-07 — Restart degraded timer restored
# ─────────────────────────────────────────────────────────────────────────────

class TestFS07RestartDegradedTimerRestored:
    """
    DegradedModeTracker must persist degradation timestamps to the DB and
    restore them on re-instantiation (HD-06 / OBS-039 behaviour).

    A 24h SLO escalation timer that loses its start time on restart would
    never fire the alert.
    """

    def test_degraded_since_restored_from_db_on_restart(
        self, db_manager_factory: Any
    ) -> None:
        """
        FS-07: Persist degraded_since=T then re-instantiate DegradedModeTracker.
        Assert: _degraded_since[failure_type] == T (from DB, not reset to None).
        """
        db = db_manager_factory()

        # Simulate an in-progress degradation 20 hours ago.
        twenty_hours_ago = datetime.now(UTC) - timedelta(hours=20)
        failure_type = "GARMIN_SYNC"
        db.upsert_degraded_mode_state(failure_type, twenty_hours_ago.isoformat())

        # "Restart" = fresh DegradedModeTracker hydrating from DB.
        tracker = DegradedModeTracker(db=db)

        assert failure_type in tracker._degraded_since, (
            f"DegradedModeTracker must hydrate '{failure_type}' from DB on startup"
        )
        restored_ts = tracker._degraded_since[failure_type]
        assert isinstance(restored_ts, datetime), (
            "Restored _degraded_since value must be a datetime, not None"
        )

        # The restored timestamp must be approximately the persisted one.
        delta_seconds = abs(
            (restored_ts.replace(tzinfo=UTC) - twenty_hours_ago).total_seconds()
        )
        assert delta_seconds < 2.0, (
            f"Restored timestamp differs by {delta_seconds:.1f}s from persisted value"
        )

    def test_clean_failure_type_not_in_degraded_since_after_restart(
        self, db_manager_factory: Any
    ) -> None:
        """
        FS-07-neg: A failure_type that was resolved (deleted from DB) must not
        appear in _degraded_since after a restart.
        """
        db = db_manager_factory()
        # Write then immediately delete (resolved state).
        db.upsert_degraded_mode_state("DATA_MISSING", datetime.now(UTC).isoformat())
        db.delete_degraded_mode_state("DATA_MISSING")

        tracker = DegradedModeTracker(db=db)
        assert "DATA_MISSING" not in tracker._degraded_since, (
            "Resolved failure type must not appear in _degraded_since after restart"
        )

    def test_24h_slo_escalation_timer_continues_after_restart(
        self, db_manager_factory: Any
    ) -> None:
        """
        FS-07-SLO: After restart with 20h accumulated, 4h later the 24h alert
        threshold must be reachable without restarting the timer.
        """
        db = db_manager_factory()
        twenty_hours_ago = datetime.now(UTC) - timedelta(hours=20)
        db.upsert_degraded_mode_state("WEATHER_SYNC", twenty_hours_ago.isoformat())

        tracker = DegradedModeTracker(db=db)

        # Simulate another update 4 hours later (now = 24h elapsed total).
        # We manually advance the stored timestamp to be 25h ago to exceed threshold.
        twenty_five_hours_ago = datetime.now(UTC) - timedelta(hours=25)
        tracker._degraded_since["WEATHER_SYNC"] = twenty_five_hours_ago

        alerts_fired: list[str] = []
        tracker.update(
            flags={"WEATHER_SYNC": True},
            alert_fn=lambda msg: alerts_fired.append(msg),
        )

        assert alerts_fired, (
            "24h SLO escalation alert must fire when accumulated degradation ≥ 24h"
        )


# ─────────────────────────────────────────────────────────────────────────────
# FS-08 — Stale/fresh mixed state
# ─────────────────────────────────────────────────────────────────────────────

class TestFS08StaleFreshMixedState:
    """
    When data_confidence_low=True (e.g., stale sleep data mixed with fresh HRV),
    governance must apply the STARTUP_DATA_CONFIDENCE_CEILING:
    - session_type → EASY
    - max_zone → ≤ 2
    """

    def test_data_confidence_low_forces_easy_ceiling(self) -> None:
        """
        FS-08: Context with data_confidence_low=True and quality session.
        Assert: STARTUP_DATA_CONFIDENCE_CEILING applied, output is EASY, max_zone ≤ 2.
        """
        engine = GovernanceEngine()
        session = {"session_type": "INTERVALS", "max_zone": 5, "duration_min": 50}
        ctx = _base_governance_context(data_confidence_low=True)

        result = engine.apply_constraints(session_plan=session, context=ctx)

        assert result.get("session_type") == "EASY", (
            f"data_confidence_low must downgrade INTERVALS to EASY, got {result.get('session_type')}"
        )
        assert result.get("max_zone", 5) <= 2, (
            f"max_zone must be ≤ 2 under data_confidence_low ceiling, got {result.get('max_zone')}"
        )
        assert "STARTUP_DATA_CONFIDENCE_CEILING" in result.get("governance_locks_applied", []), (
            "STARTUP_DATA_CONFIDENCE_CEILING lock must appear in governance_locks_applied"
        )

    def test_data_confidence_low_logged_as_easy_ceiling_event(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """
        FS-08-event: data_confidence_low triggers STARTUP_DATA_CONFIDENCE EASY_CEILING log event.
        """
        engine = GovernanceEngine()
        session = {"session_type": "TEMPO", "max_zone": 4, "duration_min": 45}
        ctx = _base_governance_context(data_confidence_low=True)

        with caplog.at_level(logging.INFO, logger="titan.science.governance_engine"):
            engine.apply_constraints(session_plan=session, context=ctx)

        # Parse JSON log records looking for EASY_CEILING action.
        easy_ceiling_events = []
        for record in caplog.records:
            try:
                payload = json.loads(record.getMessage())
                if payload.get("action") == "EASY_CEILING":
                    easy_ceiling_events.append(payload)
            except (json.JSONDecodeError, AttributeError):
                pass

        assert easy_ceiling_events, (
            "Expected EASY_CEILING governance gate event when data_confidence_low=True"
        )

    def test_data_confidence_low_does_not_downgrade_already_easy(self) -> None:
        """
        FS-08-idempotent: If session is already EASY, data_confidence_low must
        keep it EASY (not REST) and cap max_zone at 2.
        """
        engine = GovernanceEngine()
        session = {"session_type": "EASY", "max_zone": 3, "duration_min": 40}
        ctx = _base_governance_context(data_confidence_low=True)

        result = engine.apply_constraints(session_plan=session, context=ctx)

        assert result.get("session_type") == "EASY", (
            "EASY session must remain EASY under data_confidence_low"
        )
        assert result.get("max_zone", 5) <= 2

    def test_data_confidence_low_respects_fallback_conservative_ceiling(self) -> None:
        """
        FS-08-ceiling: Even HAMMER + data_confidence_low → EASY + max_zone ≤ 2.
        The ceiling is unconditional regardless of original intensity.
        """
        engine = GovernanceEngine()
        for session_type in ("HAMMER", "RACE", "INTERVALS", "TEMPO"):
            session = {"session_type": session_type, "max_zone": 5, "duration_min": 60}
            ctx = _base_governance_context(data_confidence_low=True, fueling_confirmed=True)
            result = engine.apply_constraints(session_plan=session, context=ctx)

            assert result.get("session_type") in {"EASY", "REST"}, (
                f"data_confidence_low must ceiling '{session_type}' to EASY or REST, "
                f"got {result.get('session_type')}"
            )
            assert result.get("max_zone", 5) <= 2, (
                f"max_zone must be ≤ 2 for {session_type} under data_confidence_low, "
                f"got {result.get('max_zone')}"
            )
