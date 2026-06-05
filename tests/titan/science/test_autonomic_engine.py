"""
T5-56: AFI confidence degradation for sparse HRR history.

When hrr_60_today is provided but fewer than 3 HRR data points exist in
hrr_log (sparse history), calculate_afi must:
  - still set hrr_norm = 0.0 (cannot compute reliable z-score)
  - apply a confidence multiplier of 0.7 to last_confidence

When hrr_60_today is None (no measurement at all):
  - hrr_norm = 0.0, confidence = 1.0 (no penalty — data simply absent)

When hrr_log has >= 3 entries and hrr_60_today is provided:
  - hrr_norm computed from z-score, confidence = 1.0
"""

import pytest

from titan.science.autonomic_engine import AutonomicFusionEngine


def _engine_with_hrr_log(n: int) -> AutonomicFusionEngine:
    """Return an engine pre-loaded with n HRR data points."""
    engine = AutonomicFusionEngine()
    for i in range(n):
        engine.add_hrr(f"2026-01-{i + 1:02d}", hrr_60=60, hrr_120=80)
    return engine


class TestAFIConfidenceSparseHRR:
    @pytest.mark.unit
    def test_confidence_1_when_hrr_absent(self) -> None:
        """hrr_60_today=None → confidence=1.0 (no penalty for absent data)."""
        engine = AutonomicFusionEngine()
        engine.calculate_afi(ln_rmssd_deviation=0.0, hrr_60_today=None)
        assert engine.last_confidence == 1.0

    @pytest.mark.unit
    def test_confidence_0_7_when_hrr_sparse_zero_points(self) -> None:
        """hrr_60_today provided, hrr_log empty → confidence=0.7 (sparse)."""
        engine = AutonomicFusionEngine()
        engine.calculate_afi(ln_rmssd_deviation=0.0, hrr_60_today=60)
        assert engine.last_confidence == 0.7

    @pytest.mark.unit
    def test_confidence_0_7_when_hrr_sparse_one_point(self) -> None:
        """hrr_60_today provided, hrr_log has 1 entry → confidence=0.7."""
        engine = _engine_with_hrr_log(1)
        engine.calculate_afi(ln_rmssd_deviation=0.0, hrr_60_today=60)
        assert engine.last_confidence == 0.7

    @pytest.mark.unit
    def test_confidence_0_7_when_hrr_sparse_two_points(self) -> None:
        """hrr_60_today provided, hrr_log has 2 entries → confidence=0.7."""
        engine = _engine_with_hrr_log(2)
        engine.calculate_afi(ln_rmssd_deviation=0.0, hrr_60_today=60)
        assert engine.last_confidence == 0.7

    @pytest.mark.unit
    def test_confidence_1_when_hrr_sufficient(self) -> None:
        """hrr_60_today provided, hrr_log has >= 3 entries → confidence=1.0."""
        engine = _engine_with_hrr_log(3)
        engine.calculate_afi(ln_rmssd_deviation=0.0, hrr_60_today=60)
        assert engine.last_confidence == 1.0

    @pytest.mark.unit
    def test_confidence_1_when_hrr_ample(self) -> None:
        """hrr_60_today provided, hrr_log has 10 entries → confidence=1.0."""
        engine = _engine_with_hrr_log(10)
        engine.calculate_afi(ln_rmssd_deviation=0.0, hrr_60_today=60)
        assert engine.last_confidence == 1.0

    @pytest.mark.unit
    def test_hrr_norm_zero_when_sparse(self) -> None:
        """Sparse history: hrr_norm must remain 0.0 (no z-score computable)."""
        engine = _engine_with_hrr_log(2)
        # With hrr_norm=0.0 and other signals=0.0, AFI should equal 0.0
        afi = engine.calculate_afi(
            ln_rmssd_deviation=0.0,
            hrr_60_today=60,
            sleep_depth_delta=0.0,
            resp_delta=0.0,
        )
        assert afi == 0.0

    @pytest.mark.unit
    def test_afi_value_unchanged_by_confidence_penalty(self) -> None:
        """The AFI float return value must not be altered by the confidence penalty."""
        engine_sparse = _engine_with_hrr_log(2)
        engine_none = AutonomicFusionEngine()

        afi_sparse = engine_sparse.calculate_afi(
            ln_rmssd_deviation=0.5, hrr_60_today=60
        )
        afi_none = engine_none.calculate_afi(
            ln_rmssd_deviation=0.5, hrr_60_today=None
        )
        # Both hrr_norm=0.0, so AFI values must be equal
        assert afi_sparse == afi_none

    @pytest.mark.unit
    def test_last_confidence_reset_each_call(self) -> None:
        """last_confidence reflects the most recent call, not an accumulated state."""
        engine = _engine_with_hrr_log(3)
        # First call: sufficient history → confidence=1.0
        engine.calculate_afi(ln_rmssd_deviation=0.0, hrr_60_today=60)
        assert engine.last_confidence == 1.0
        # Reset log to simulate sparse state
        engine.hrr_log.clear()
        engine.calculate_afi(ln_rmssd_deviation=0.0, hrr_60_today=60)
        assert engine.last_confidence == 0.7
