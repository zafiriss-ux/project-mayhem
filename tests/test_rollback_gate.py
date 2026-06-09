"""
Tests for CalibrationRollbackGate — P27-04 completion-rate rollback gate.

Covers:
  - degraded completion triggers would_revert=True and apply(advisory=False) deletes
  - improved/stable completion => would_revert=False, no deletion
  - manual offset with degraded completion => never reverted (source guard)
  - insufficient sample size => would_revert=False with reason
  - advisory=True default => recommends but does not delete
  - hard-stop key => not present as an offset; gate skips cleanly
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from titan.config.thresholds import (
    CALIBRATION_MIN_OUTCOME_COUNT,
    HARD_STOP_THRESHOLD_KEYS,
    ROLLBACK_DEGRADATION_THRESHOLD_PP,
)
from titan.science.rollback_gate import MODULE_VERSION, CalibrationRollbackGate

_ANCHOR = "2026-05-01T08:00:00+00:00"  # well within 30d on both sides for test purposes
_ATHLETE = "owner"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db(
    offsets: list[dict] | None = None,
    pre_rate: float | None = 0.9,
    post_rate: float | None = 0.9,
    pre_count: int = CALIBRATION_MIN_OUTCOME_COUNT,
    post_count: int = CALIBRATION_MIN_OUTCOME_COUNT,
) -> MagicMock:
    db = MagicMock()
    db.get_athlete_threshold_offsets.return_value = offsets or []
    db.get_completion_rate.side_effect = [
        (pre_rate, pre_count),
        (post_rate, post_count),
    ]
    db.delete_threshold_offset.return_value = 1
    return db


def _calibration_offset(key: str = "ACWR_SWEET_SPOT_MAX") -> dict:
    return {
        "threshold_key": key,
        "delta_value": 0.05,
        "source": "calibration",
        "updated_at": _ANCHOR,
    }


def _manual_offset(key: str = "ACWR_SWEET_SPOT_MAX") -> dict:
    return {
        "threshold_key": key,
        "delta_value": 0.05,
        "source": "manual",
        "updated_at": _ANCHOR,
    }


# ---------------------------------------------------------------------------
# Test 1 — degraded completion triggers revert
# ---------------------------------------------------------------------------

class TestDegradedCompletion:
    @pytest.mark.unit
    def test_would_revert_true_when_degraded(self):
        """pre 0.9, post 0.6 on calibration offset => would_revert=True."""
        db = _make_db(
            offsets=[_calibration_offset()],
            pre_rate=0.9,
            post_rate=0.6,
        )
        gate = CalibrationRollbackGate(db=db)
        recs = gate.evaluate(_ATHLETE)
        assert len(recs) == 1
        rec = recs[0]
        assert rec["would_revert"] is True
        assert rec["degradation_pp"] == pytest.approx(30.0)

    @pytest.mark.unit
    def test_apply_advisory_false_deletes_offset(self):
        """apply(advisory=False) calls delete_threshold_offset for would_revert rows."""
        db = _make_db(
            offsets=[_calibration_offset()],
            pre_rate=0.9,
            post_rate=0.6,
        )
        gate = CalibrationRollbackGate(db=db)
        recs = gate.apply(_ATHLETE, advisory=False)
        assert len(recs) == 1
        assert recs[0]["would_revert"] is True
        db.delete_threshold_offset.assert_called_once_with(_ATHLETE, "ACWR_SWEET_SPOT_MAX")

    @pytest.mark.unit
    def test_exactly_at_threshold_reverts(self):
        """degradation >= ROLLBACK_DEGRADATION_THRESHOLD_PP at boundary — should revert."""
        # 0.9 - 0.79 = 0.11 → 11pp, clearly above the 10pp threshold without float edge.
        db = _make_db(
            offsets=[_calibration_offset()],
            pre_rate=0.9,
            post_rate=0.79,
        )
        gate = CalibrationRollbackGate(db=db)
        recs = gate.evaluate(_ATHLETE)
        assert recs[0]["would_revert"] is True


# ---------------------------------------------------------------------------
# Test 2 — improved/stable completion => would_revert=False, row untouched
# ---------------------------------------------------------------------------

class TestStableCompletion:
    @pytest.mark.unit
    def test_stable_completion_no_revert(self):
        """Same rate before and after => no revert."""
        db = _make_db(
            offsets=[_calibration_offset()],
            pre_rate=0.8,
            post_rate=0.8,
        )
        gate = CalibrationRollbackGate(db=db)
        recs = gate.apply(_ATHLETE, advisory=False)
        assert recs[0]["would_revert"] is False
        db.delete_threshold_offset.assert_not_called()

    @pytest.mark.unit
    def test_improved_completion_no_revert(self):
        """Higher completion after calibration => no revert."""
        db = _make_db(
            offsets=[_calibration_offset()],
            pre_rate=0.7,
            post_rate=0.9,
        )
        gate = CalibrationRollbackGate(db=db)
        recs = gate.evaluate(_ATHLETE)
        assert recs[0]["would_revert"] is False
        assert (recs[0]["degradation_pp"] or 0.0) < 0  # negative = improvement

    @pytest.mark.unit
    def test_small_drop_below_threshold_no_revert(self):
        """Drop < ROLLBACK_DEGRADATION_THRESHOLD_PP pp => no revert."""
        small_drop = (ROLLBACK_DEGRADATION_THRESHOLD_PP - 1) / 100.0
        db = _make_db(
            offsets=[_calibration_offset()],
            pre_rate=0.9,
            post_rate=0.9 - small_drop,
        )
        gate = CalibrationRollbackGate(db=db)
        recs = gate.evaluate(_ATHLETE)
        assert recs[0]["would_revert"] is False


# ---------------------------------------------------------------------------
# Test 3 — manual offset is never reverted (source guard)
# ---------------------------------------------------------------------------

class TestManualOffsetSafetyGuard:
    @pytest.mark.unit
    def test_manual_offset_not_in_recommendations(self):
        """Manual offsets are filtered from evaluate() — source guard."""
        db = _make_db(
            offsets=[_manual_offset()],
            pre_rate=0.9,
            post_rate=0.6,
        )
        gate = CalibrationRollbackGate(db=db)
        recs = gate.evaluate(_ATHLETE)
        assert recs == []

    @pytest.mark.unit
    def test_manual_offset_apply_never_deletes(self):
        """apply(advisory=False) does not delete a manual offset even with degradation."""
        db = _make_db(
            offsets=[_manual_offset()],
            pre_rate=0.9,
            post_rate=0.6,
        )
        gate = CalibrationRollbackGate(db=db)
        gate.apply(_ATHLETE, advisory=False)
        db.delete_threshold_offset.assert_not_called()

    @pytest.mark.unit
    def test_mixed_offsets_only_calibration_evaluated(self):
        """With both manual and calibration offsets, only calibration is evaluated."""
        db = MagicMock()
        db.get_athlete_threshold_offsets.return_value = [
            _manual_offset("ACWR_SWEET_SPOT_MAX"),
            _calibration_offset("VO2_ACWR_MAX"),
        ]
        # Only one get_completion_rate pair needed (for the calibration offset)
        db.get_completion_rate.side_effect = [
            (0.9, CALIBRATION_MIN_OUTCOME_COUNT),
            (0.6, CALIBRATION_MIN_OUTCOME_COUNT),
        ]
        db.delete_threshold_offset.return_value = 1
        gate = CalibrationRollbackGate(db=db)
        recs = gate.evaluate(_ATHLETE)
        assert len(recs) == 1
        assert recs[0]["threshold_key"] == "VO2_ACWR_MAX"


# ---------------------------------------------------------------------------
# Test 4 — insufficient sample size => would_revert=False with reason
# ---------------------------------------------------------------------------

class TestInsufficientSampleSize:
    @pytest.mark.unit
    def test_insufficient_pre_window_no_revert(self):
        """Pre window has < CALIBRATION_MIN_OUTCOME_COUNT samples => no revert."""
        db = _make_db(
            offsets=[_calibration_offset()],
            pre_rate=0.9,
            post_rate=0.6,
            pre_count=CALIBRATION_MIN_OUTCOME_COUNT - 1,
            post_count=CALIBRATION_MIN_OUTCOME_COUNT,
        )
        gate = CalibrationRollbackGate(db=db)
        recs = gate.evaluate(_ATHLETE)
        assert recs[0]["would_revert"] is False
        assert recs[0]["reason"] == "insufficient_data"

    @pytest.mark.unit
    def test_insufficient_post_window_no_revert(self):
        """Post window has < CALIBRATION_MIN_OUTCOME_COUNT samples => no revert."""
        db = _make_db(
            offsets=[_calibration_offset()],
            pre_rate=0.9,
            post_rate=0.6,
            pre_count=CALIBRATION_MIN_OUTCOME_COUNT,
            post_count=CALIBRATION_MIN_OUTCOME_COUNT - 1,
        )
        gate = CalibrationRollbackGate(db=db)
        recs = gate.evaluate(_ATHLETE)
        assert recs[0]["would_revert"] is False
        assert recs[0]["reason"] == "insufficient_data"

    @pytest.mark.unit
    def test_both_windows_insufficient_no_revert(self):
        """Both windows too small => no revert, reason=insufficient_data."""
        db = _make_db(
            offsets=[_calibration_offset()],
            pre_rate=0.9,
            post_rate=0.6,
            pre_count=0,
            post_count=0,
        )
        gate = CalibrationRollbackGate(db=db)
        recs = gate.evaluate(_ATHLETE)
        assert recs[0]["would_revert"] is False
        assert recs[0]["reason"] == "insufficient_data"

    @pytest.mark.unit
    def test_degradation_pp_none_when_insufficient(self):
        """degradation_pp is None when data is insufficient."""
        db = _make_db(
            offsets=[_calibration_offset()],
            pre_rate=0.9,
            post_rate=0.6,
            pre_count=2,
            post_count=2,
        )
        gate = CalibrationRollbackGate(db=db)
        recs = gate.evaluate(_ATHLETE)
        assert recs[0]["degradation_pp"] is None


# ---------------------------------------------------------------------------
# Test 5 — advisory=True default does not delete
# ---------------------------------------------------------------------------

class TestAdvisoryDefault:
    @pytest.mark.unit
    def test_advisory_true_returns_recommendations_without_deleting(self):
        """advisory=True (default): returns recs but never calls delete."""
        db = _make_db(
            offsets=[_calibration_offset()],
            pre_rate=0.9,
            post_rate=0.6,
        )
        gate = CalibrationRollbackGate(db=db)
        recs = gate.apply(_ATHLETE)  # default advisory=True
        assert len(recs) == 1
        assert recs[0]["would_revert"] is True
        db.delete_threshold_offset.assert_not_called()

    @pytest.mark.unit
    def test_advisory_true_explicit_no_delete(self):
        """advisory=True explicit: recommendations returned, no deletion."""
        db = _make_db(
            offsets=[_calibration_offset()],
            pre_rate=0.9,
            post_rate=0.4,
        )
        gate = CalibrationRollbackGate(db=db)
        recs = gate.apply(_ATHLETE, advisory=True)
        assert any(r["would_revert"] for r in recs)
        db.delete_threshold_offset.assert_not_called()


# ---------------------------------------------------------------------------
# Test 6 — hard-stop key cannot be an offset; gate skips cleanly
# ---------------------------------------------------------------------------

class TestHardStopKeyNotAdapted:
    @pytest.mark.unit
    def test_empty_offsets_returns_empty_recommendations(self):
        """No offsets at all => empty recommendation list; gate completes cleanly."""
        db = _make_db(offsets=[])
        gate = CalibrationRollbackGate(db=db)
        recs = gate.evaluate(_ATHLETE)
        assert recs == []

    @pytest.mark.unit
    def test_hard_stop_key_filtered_from_evaluation(self):
        """A calibration row with a hard-stop key is skipped defensively."""
        hard_key = next(iter(HARD_STOP_THRESHOLD_KEYS))
        db = MagicMock()
        db.get_athlete_threshold_offsets.return_value = [
            {
                "threshold_key": hard_key,
                "delta_value": 0.05,
                "source": "calibration",
                "updated_at": _ANCHOR,
            }
        ]
        gate = CalibrationRollbackGate(db=db)
        recs = gate.evaluate(_ATHLETE)
        assert recs == []
        db.get_completion_rate.assert_not_called()

    @pytest.mark.unit
    def test_apply_on_no_offsets_returns_empty(self):
        """apply() with no offsets does not raise and returns empty list."""
        db = _make_db(offsets=[])
        gate = CalibrationRollbackGate(db=db)
        recs = gate.apply(_ATHLETE, advisory=False)
        assert recs == []
        db.delete_threshold_offset.assert_not_called()


# ---------------------------------------------------------------------------
# Test 7 — module-level sanity
# ---------------------------------------------------------------------------

class TestModuleVersion:
    @pytest.mark.unit
    def test_module_version_present(self):
        assert MODULE_VERSION == "1.0.0"
