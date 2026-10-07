"""
B-4 (INV-12) — two-part fail-closed governance guard.

B-4a: GovernanceEngine.apply_constraints() — any exception raised inside the
      gate pipeline is caught and the session is forced to EASY / max_zone=2
      (deny-closed), instead of propagating or returning an unconstrained plan.

B-4b: coaching_pipeline() — any exception raised by _decision_pipeline() is
      caught at the orchestration boundary, alerted via Telegram, and the run
      returns False (no prescription delivered, worker stays alive).

SA:m-1 (INV-13): DegradedModeTracker._hydrate_from_db() — a failed read is
      logged CRITICAL (never silently swallowed), preserves in-memory state,
      marks the tracker degraded, and clears on the next successful read.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest

from titan.orchestration.coaching_pipeline import AthleteCoachingContext, coaching_pipeline
from titan.orchestration.daily_coach import DegradedModeTracker
from titan.science.governance_engine import GovernanceEngine


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


def _build_pipeline_context(*, coach: Any, athlete_id: str = "athlete-1") -> AthleteCoachingContext:
    return AthleteCoachingContext(
        athlete_id=athlete_id,
        coach=coach,
        garmin_data={"status": "ok"},
        soreness=5,
        subjective_fatigue_score=5,
        today_rhr=50,
        today_sleep_score=80,
        today_sleep_hours=7.0,
        baseline_rhr_for_comparison=50.0,
        persistence_degraded=False,
        garmin_data_stale=False,
        latest_hrv=45.0,
        baseline_hrv=42.0,
        hrv_summary={"std_dev": 1.0},
        afi_final=0.0,
        afi_constraints={"afi_modifier": 0, "readiness_clamp": 100},
        tsb_value=0.0,
        tsb_status="BALANCED",
        cs_thermal=None,
        garmin_trust=SimpleNamespace(trust_level=SimpleNamespace(value="HIGH")),
        garmin_report_payload={"source": "garmin"},
        startup_hydration_confidence={"hrv": True, "weight": True, "load": True, "hrr": True, "cs": True},
        startup_confidence_applies=False,
    )


# ─────────────────────────────────────────────────────────────────────────────
# B-4a — apply_constraints() exception fails closed (INV-12)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.governance
def test_apply_constraints_gate_exception_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A gate method raising mid-evaluation must not crash or escape unconstrained —
    apply_constraints must catch it, force EASY/zone-2, and record the lock code."""
    engine = GovernanceEngine()
    session = {"session_type": "HAMMER", "max_zone": 5, "duration_min": 60}
    ctx = _base_governance_context()

    monkeypatch.setattr(
        engine,
        "_check_hard_stops",
        Mock(side_effect=RuntimeError("simulated gate failure")),
    )

    result = engine.apply_constraints(session_plan=session, context=ctx)

    assert result["session_type"] == "EASY"
    assert result["max_zone"] == 2
    assert result["governance_exception_fail_closed"] is True
    assert "GOVERNANCE_EXCEPTION_FAIL_CLOSED" in result["governance_locks_applied"]


@pytest.mark.unit
@pytest.mark.governance
def test_apply_constraints_normal_path_no_fail_closed_marker() -> None:
    """A normal, healthy minimal context must not trigger the fail-closed
    exception path: no GOVERNANCE_EXCEPTION_FAIL_CLOSED lock, and the session
    type is not force-downgraded unless a real gate fired."""
    engine = GovernanceEngine()
    session = {"session_type": "EASY", "max_zone": 3, "duration_min": 45}
    ctx = _base_governance_context()

    result = engine.apply_constraints(session_plan=session, context=ctx)

    assert "governance_exception_fail_closed" not in result
    assert "GOVERNANCE_EXCEPTION_FAIL_CLOSED" not in result["governance_locks_applied"]
    assert result["session_type"] == "EASY"


@pytest.mark.unit
@pytest.mark.governance
def test_check_override_lockdown_db_read_failure_still_fails_closed() -> None:
    """Regression: db.get_override_ratio raising must still be handled by
    check_override_lockdown's own fail-safe path (locked=True, max_zone=2),
    unaffected by the new apply_constraints-level wrapper."""
    engine = GovernanceEngine()
    db = Mock()
    db.get_override_ratio = Mock(side_effect=RuntimeError("db unavailable"))

    lock = engine.check_override_lockdown(db)

    assert lock["locked"] is True
    assert lock["max_zone"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# B-4b — coaching_pipeline() decision-pipeline exception fails closed (INV-12)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_coaching_pipeline_decision_pipeline_exception_alerts_and_returns_false() -> None:
    """A _decision_pipeline exception must be caught at the orchestration
    boundary: an alert is sent, _effect_runner is never reached, and the
    pipeline returns False (no exception escapes)."""
    send_alert = Mock()
    effect_runner = Mock()
    coach = SimpleNamespace(
        _decision_pipeline=Mock(side_effect=RuntimeError("decision pipeline boom")),
        _effect_runner=effect_runner,
        telegram=SimpleNamespace(send_alert=send_alert),
    )

    result = coaching_pipeline(_build_pipeline_context(coach=coach))

    assert result is False
    send_alert.assert_called_once()
    effect_runner.assert_not_called()


@pytest.mark.unit
def test_coaching_pipeline_normal_path_returns_effect_runner_result() -> None:
    """Regression: when _decision_pipeline succeeds, coaching_pipeline returns
    the _effect_runner result unchanged and never touches the fail-safe alert."""
    decision_result = SimpleNamespace(session_plan={"session_type": "EASY"})
    send_alert = Mock()
    coach = SimpleNamespace(
        _decision_pipeline=Mock(return_value=decision_result),
        _effect_runner=Mock(return_value=True),
        telegram=SimpleNamespace(send_alert=send_alert),
    )

    result = coaching_pipeline(_build_pipeline_context(coach=coach))

    assert result is True
    coach._effect_runner.assert_called_once_with(decision_result)
    send_alert.assert_not_called()


# ── SA:m-1 / INV-13 — DegradedModeTracker hydration ─────────────────────────

_HEALTHY_FLAGS = {
    "persistence_degraded": False,
    "data_confidence_low": False,
    "garmin_data_stale": False,
    "garmin_api_degraded": False,
}


def test_tracker_hydration_read_failure_logs_critical_and_marks_degraded(caplog) -> None:
    db = Mock()
    db.get_all_degraded_mode_states.side_effect = RuntimeError("database is locked")

    with caplog.at_level(logging.CRITICAL, logger="titan.orchestration.daily_coach"):
        tracker = DegradedModeTracker(db=db)

    assert tracker.hydration_failed is True
    assert DegradedModeTracker.HYDRATION_FAILURE in tracker.get_degraded_since()
    assert any(
        r.levelno == logging.CRITICAL and "degraded_mode_hydration_failed" in r.getMessage()
        for r in caplog.records
    )


def test_tracker_hydration_failure_preserves_in_memory_state() -> None:
    db = Mock()
    db.get_all_degraded_mode_states.return_value = []
    tracker = DegradedModeTracker(db=db)
    tracker.update({**_HEALTHY_FLAGS, "garmin_data_stale": True}, alert_fn=Mock())
    stale_since = tracker.get_degraded_since()["garmin_data_stale"]

    db.get_all_degraded_mode_states.side_effect = RuntimeError("disk I/O error")
    assert tracker._hydrate_from_db() is False

    assert tracker.get_degraded_since()["garmin_data_stale"] == stale_since
    assert tracker.hydration_failed is True


def test_tracker_hydration_clears_on_next_successful_read() -> None:
    db = Mock()
    db.get_all_degraded_mode_states.side_effect = RuntimeError("database is locked")
    tracker = DegradedModeTracker(db=db)
    assert tracker.hydration_failed is True

    persisted = datetime(2026, 10, 1, 7, 0, tzinfo=UTC)
    db.get_all_degraded_mode_states.side_effect = None
    db.get_all_degraded_mode_states.return_value = [("garmin_api_degraded", persisted.isoformat())]
    tracker.update({**_HEALTHY_FLAGS, "garmin_api_degraded": True}, alert_fn=Mock())

    assert tracker.hydration_failed is False
    degraded = tracker.get_degraded_since()
    assert DegradedModeTracker.HYDRATION_FAILURE not in degraded
    assert "garmin_api_degraded" in degraded


def test_tracker_hydration_marker_is_never_persisted() -> None:
    db = Mock()
    db.get_all_degraded_mode_states.side_effect = RuntimeError("database is locked")
    tracker = DegradedModeTracker(db=db)

    tracker.update(_HEALTHY_FLAGS, alert_fn=Mock())

    written = [c.args[0] for c in db.upsert_degraded_mode_state.call_args_list]
    deleted = [c.args[0] for c in db.delete_degraded_mode_state.call_args_list]
    assert DegradedModeTracker.HYDRATION_FAILURE not in written + deleted
