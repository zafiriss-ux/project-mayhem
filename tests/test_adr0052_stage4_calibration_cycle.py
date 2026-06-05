"""
ADR-0052 Stage 4 — OutcomeTracker.run_calibration_cycle() contract tests.

Covers: diversity guard, circuit-breaker guard, accumulating guard,
false-positive loosening, false-negative tightening, hard-stop exclusion,
and full return-structure validation.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from titan.science.outcome_tracker import OutcomeTracker
from titan.science.threshold_adapter import ThresholdAdapter

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

BASE_VALUES = {"ACWR_SOFT_CAP": 1.3, "SLEEP_SCORE_FLOOR": 60.0}
ATHLETE_ID = "test_athlete"


def _make_db(
    is_cold_start: bool = False,
    false_neg_rate: float = 0.05,
) -> MagicMock:
    db = MagicMock()
    db.is_athlete_cold_start.return_value = is_cold_start
    db.get_false_negative_rate.return_value = false_neg_rate
    db.get_athlete_threshold_offsets.return_value = []
    db.save_threshold_offset.return_value = None
    db.get_governance_decisions.return_value = []
    return db


def _make_tracker(db: MagicMock) -> OutcomeTracker:
    return OutcomeTracker(db=db)


def _make_adapter(db: MagicMock) -> ThresholdAdapter:
    adapter = ThresholdAdapter(athlete_id=ATHLETE_ID, db=db)
    adapter.load()
    return adapter


def _calibration_available_summary(
    false_positive_rate: float = 0.10,
    false_negative_rate: float = 0.05,
) -> dict:
    return {
        "status": "CALIBRATION_AVAILABLE",
        "false_positive_rate": false_positive_rate,
        "false_negative_rate": false_negative_rate,
        "n_decisions": 50,
        "n_with_outcome": 40,
        "n_reusable_outcomes": 35,
    }


# ---------------------------------------------------------------------------
# Test 1 — INSUFFICIENT_DIVERSITY when diversity gate fails
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_calibration_cycle_insufficient_diversity():
    db = _make_db()
    tracker = _make_tracker(db)
    adapter = _make_adapter(db)

    with patch.object(tracker, "check_calibration_diversity", return_value=False):
        result = tracker.run_calibration_cycle(ATHLETE_ID, adapter, BASE_VALUES)

    assert result["status"] == "INSUFFICIENT_DIVERSITY"
    assert result["athlete_id"] == ATHLETE_ID
    assert result["adaptations_attempted"] == 0
    assert result["adaptations_applied"] == 0
    assert result["circuit_breaker_active"] is False
    db.save_threshold_offset.assert_not_called()


# ---------------------------------------------------------------------------
# Test 2 — CIRCUIT_BREAKER_ACTIVE when breaker is tripped
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_calibration_cycle_circuit_breaker_active():
    db = _make_db(is_cold_start=False, false_neg_rate=0.99)
    tracker = _make_tracker(db)
    adapter = _make_adapter(db)

    with patch.object(tracker, "check_calibration_diversity", return_value=True):
        result = tracker.run_calibration_cycle(ATHLETE_ID, adapter, BASE_VALUES)

    assert result["status"] == "CIRCUIT_BREAKER_ACTIVE"
    assert result["athlete_id"] == ATHLETE_ID
    assert result["adaptations_attempted"] == 0
    assert result["adaptations_applied"] == 0
    assert result["circuit_breaker_active"] is True
    db.save_threshold_offset.assert_not_called()


# ---------------------------------------------------------------------------
# Test 3 — ACCUMULATING when summary is not ready
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_calibration_cycle_accumulating():
    db = _make_db()
    tracker = _make_tracker(db)
    adapter = _make_adapter(db)

    accumulating_summary = {"status": "ACCUMULATING", "n_decisions": 10}

    with (
        patch.object(tracker, "check_calibration_diversity", return_value=True),
        patch.object(tracker, "get_calibration_summary", return_value=accumulating_summary),
    ):
        result = tracker.run_calibration_cycle(ATHLETE_ID, adapter, BASE_VALUES)

    assert result["status"] == "ACCUMULATING"
    assert result["athlete_id"] == ATHLETE_ID
    assert result["adaptations_attempted"] == 0
    assert result["adaptations_applied"] == 0
    assert result["circuit_breaker_active"] is False
    db.save_threshold_offset.assert_not_called()


# ---------------------------------------------------------------------------
# Test 4 — false-positive > 0.30 → direction +1.0 (loosen)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_calibration_cycle_false_positive_triggers_loosening():
    db = _make_db()
    tracker = _make_tracker(db)
    adapter = _make_adapter(db)

    summary = _calibration_available_summary(false_positive_rate=0.35, false_negative_rate=0.05)

    with (
        patch.object(tracker, "check_calibration_diversity", return_value=True),
        patch.object(tracker, "get_calibration_summary", return_value=summary),
    ):
        result = tracker.run_calibration_cycle(ATHLETE_ID, adapter, BASE_VALUES)

    assert result["status"] == "CALIBRATION_COMPLETE"
    assert result["adaptations_attempted"] == 2  # both soft-gate thresholds
    # save_threshold_offset called with positive delta (loosening)
    assert db.save_threshold_offset.call_count >= 1
    for call in db.save_threshold_offset.call_args_list:
        _, kwargs = call
        assert kwargs["delta_value"] > 0.0


# ---------------------------------------------------------------------------
# Test 5 — false-negative > 0.15 → direction -1.0 (tighten)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_calibration_cycle_false_negative_triggers_tightening():
    db = _make_db()
    tracker = _make_tracker(db)
    adapter = _make_adapter(db)

    summary = _calibration_available_summary(false_positive_rate=0.10, false_negative_rate=0.20)

    with (
        patch.object(tracker, "check_calibration_diversity", return_value=True),
        patch.object(tracker, "get_calibration_summary", return_value=summary),
    ):
        result = tracker.run_calibration_cycle(ATHLETE_ID, adapter, BASE_VALUES)

    assert result["status"] == "CALIBRATION_COMPLETE"
    assert result["adaptations_attempted"] == 2
    assert db.save_threshold_offset.call_count >= 1
    for call in db.save_threshold_offset.call_args_list:
        _, kwargs = call
        assert kwargs["delta_value"] < 0.0


# ---------------------------------------------------------------------------
# Test 6 — hard-stop gates excluded from adaptation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_calibration_cycle_hard_stop_gates_excluded():
    db = _make_db()
    tracker = _make_tracker(db)
    adapter = _make_adapter(db)

    base_values_with_hard_stop = {
        "HARD_STOP_HRV_DELTA": 15.0,
        "ACWR_SOFT_CAP": 1.3,
        "SLEEP_SCORE_FLOOR": 60.0,
    }
    summary = _calibration_available_summary(false_positive_rate=0.35, false_negative_rate=0.05)

    with (
        patch.object(tracker, "check_calibration_diversity", return_value=True),
        patch.object(tracker, "get_calibration_summary", return_value=summary),
    ):
        result = tracker.run_calibration_cycle(ATHLETE_ID, adapter, base_values_with_hard_stop)

    assert result["status"] == "CALIBRATION_COMPLETE"
    # Only 2 soft-gate thresholds attempted; hard-stop excluded
    assert result["adaptations_attempted"] == 2
    called_keys = {
        call.kwargs["threshold_key"] for call in db.save_threshold_offset.call_args_list
    }
    assert "HARD_STOP_HRV_DELTA" not in called_keys


# ---------------------------------------------------------------------------
# Test 7 — CALIBRATION_COMPLETE return structure has all required keys
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_calibration_cycle_complete_return_structure():
    db = _make_db()
    tracker = _make_tracker(db)
    adapter = _make_adapter(db)

    summary = _calibration_available_summary(false_positive_rate=0.35, false_negative_rate=0.05)

    with (
        patch.object(tracker, "check_calibration_diversity", return_value=True),
        patch.object(tracker, "get_calibration_summary", return_value=summary),
    ):
        result = tracker.run_calibration_cycle(ATHLETE_ID, adapter, BASE_VALUES)

    required_keys = {
        "status",
        "athlete_id",
        "adaptations_attempted",
        "adaptations_applied",
        "false_positive_rate",
        "false_negative_rate",
        "circuit_breaker_active",
        "thresholds_evaluated",
        "timestamp",
    }
    assert required_keys.issubset(result.keys())
    assert result["athlete_id"] == ATHLETE_ID
    assert isinstance(result["thresholds_evaluated"], list)
    assert isinstance(result["timestamp"], str)
    assert result["circuit_breaker_active"] is False
