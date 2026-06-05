"""
PARASYMPATHETIC_GUARD trigger and pass-through boundary tests.

Validates the Cheung/Plews detection pattern implemented in
AutonomicFusionEngine.check_parasympathetic_guard():
  - HRV > 10% above baseline  AND  HRR z-score < -1.5  → triggered
  - Either condition alone → not triggered
  - Below thresholds → not triggered

Also validates propagation into GovernanceEngine via
afi_constraints["parasympathetic_guard"].
"""
from __future__ import annotations

import pytest

from titan.science.autonomic_engine import AutonomicFusionEngine


def _make_afe_with_hrr_history(hrr_values: list[int]) -> AutonomicFusionEngine:
    """Create an AutonomicFusionEngine pre-loaded with HRR measurements."""
    afe = AutonomicFusionEngine()
    for i, v in enumerate(hrr_values):
        afe.add_hrr(f"2026-04-{i+1:02d}", v)
    return afe


class TestParasympatheticGuardTrigger:

    @pytest.mark.unit
    def test_guard_triggered_when_hrv_elevated_and_hrr_impaired(self):
        """HRV +15% above baseline AND low HRR (z < -1.5) → triggered."""
        # Build history with consistent HRR to establish a baseline
        afe = _make_afe_with_hrr_history([55, 56, 57])
        guard = afe.check_parasympathetic_guard(
            hrv_pct_above_baseline=15.0,  # > 10% threshold
            hrr_60_today=30,              # far below the 55-57 history → z < -1.5
        )
        assert guard["triggered"] is True
        assert guard["readiness_clamp"] == 25
        assert 4 in guard["disabled_zones"]
        assert 5 in guard["disabled_zones"]

    @pytest.mark.unit
    def test_guard_not_triggered_when_hrv_below_threshold(self):
        """HRV only +5% above baseline (below 10% threshold) → not triggered."""
        afe = _make_afe_with_hrr_history([55, 56, 57])
        guard = afe.check_parasympathetic_guard(
            hrv_pct_above_baseline=5.0,   # < 10% threshold
            hrr_60_today=30,              # impaired HRR
        )
        assert guard["triggered"] is False

    @pytest.mark.unit
    def test_guard_not_triggered_when_hrr_is_nominal(self):
        """HRV elevated but HRR is normal → not triggered."""
        afe = _make_afe_with_hrr_history([55, 56, 57])
        guard = afe.check_parasympathetic_guard(
            hrv_pct_above_baseline=20.0,  # > 10% threshold
            hrr_60_today=56,              # within normal HRR range
        )
        assert guard["triggered"] is False

    @pytest.mark.unit
    def test_guard_not_triggered_without_enough_hrr_history(self):
        """With fewer than 3 HRR measurements, impaired HRR cannot be determined."""
        afe = _make_afe_with_hrr_history([55, 56])  # only 2 entries
        guard = afe.check_parasympathetic_guard(
            hrv_pct_above_baseline=20.0,
            hrr_60_today=20,  # very low
        )
        assert guard["triggered"] is False

    @pytest.mark.unit
    def test_guard_not_triggered_when_hrr_none(self):
        """hrr_60_today=None means no HRR measurement today → guard cannot fire."""
        afe = _make_afe_with_hrr_history([55, 56, 57])
        guard = afe.check_parasympathetic_guard(
            hrv_pct_above_baseline=20.0,
            hrr_60_today=None,
        )
        assert guard["triggered"] is False

    @pytest.mark.unit
    def test_guard_triggered_readiness_clamp_is_25(self):
        """When triggered, readiness is clamped to 25 (hard limit)."""
        afe = _make_afe_with_hrr_history([60, 61, 62])
        guard = afe.check_parasympathetic_guard(
            hrv_pct_above_baseline=12.0,
            hrr_60_today=25,
        )
        assert guard["triggered"] is True
        assert guard["readiness_clamp"] == 25

    @pytest.mark.unit
    def test_not_triggered_readiness_clamp_is_100(self):
        """When not triggered, readiness clamp remains at 100."""
        afe = AutonomicFusionEngine()
        guard = afe.check_parasympathetic_guard(hrv_pct_above_baseline=3.0)
        assert guard["triggered"] is False
        assert guard["readiness_clamp"] == 100


class TestGetReadinessConstraintsPropagatesGuard:
    """Verify that get_readiness_constraints() surfaces the guard result."""

    @pytest.mark.unit
    def test_guard_propagated_to_constraints_when_triggered(self):
        afe = _make_afe_with_hrr_history([55, 56, 57])
        constraints = afe.get_readiness_constraints(
            afi_final=0.0,
            hrv_pct_above_baseline=15.0,
            hrr_60_today=25,
        )
        assert constraints["parasympathetic_guard"]["triggered"] is True
        assert constraints["readiness_clamp"] == 25
        assert 5 in constraints["disabled_zones"]

    @pytest.mark.unit
    def test_guard_not_triggered_leaves_constraints_open(self):
        afe = AutonomicFusionEngine()
        constraints = afe.get_readiness_constraints(
            afi_final=0.0,
            hrv_pct_above_baseline=3.0,
        )
        assert constraints["parasympathetic_guard"]["triggered"] is False
        assert constraints["readiness_clamp"] == 100
        assert constraints["disabled_zones"] == []
