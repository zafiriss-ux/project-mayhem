"""
T5-65: classify_hrv_stress_context — ACWR None must not return TRAINING_EXPLAINED.

ADR-0051 (missing-data policy): when ACWR is None or absent, the HRV drop
classification must return a conservative label that explicitly represents
"classification unavailable due to missing data", not the optimistic pass label.
"""

import pytest

from titan.science.governance_engine import GovernanceEngine

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(**overrides):
    """Minimal context sufficient to reach ACWR evaluation."""
    base = {
        "baseline_hrv": 60.0,
        "today_hrv": 44.0,   # 16 ms drop — past HARD_STOP_HRV_DELTA
        "today_rhr": 55,
        "baseline_rhr": 50,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# T5-65 acceptance criterion
# ---------------------------------------------------------------------------

class TestClassifyHrvDropUnknownAcwr:
    """Verify that missing/None ACWR does not produce TRAINING_EXPLAINED."""

    @pytest.mark.unit
    @pytest.mark.governance
    def test_acwr_key_absent_does_not_return_training_explained(self):
        """Key 'acwr' missing from context → must NOT be TRAINING_EXPLAINED."""
        ctx = _ctx()  # no 'acwr' key
        result = GovernanceEngine.classify_hrv_stress_context(ctx)
        assert result != "TRAINING_EXPLAINED", (
            f"Expected conservative label for absent ACWR, got {result!r}"
        )

    @pytest.mark.unit
    @pytest.mark.governance
    def test_acwr_none_does_not_return_training_explained(self):
        """acwr=None explicitly present → must NOT be TRAINING_EXPLAINED."""
        ctx = _ctx(acwr=None)
        result = GovernanceEngine.classify_hrv_stress_context(ctx)
        assert result != "TRAINING_EXPLAINED", (
            f"Expected conservative label for None ACWR, got {result!r}"
        )

    @pytest.mark.unit
    @pytest.mark.governance
    def test_acwr_absent_returns_unknown_label(self):
        """Key 'acwr' missing → returns UNKNOWN_ACWR."""
        ctx = _ctx()
        result = GovernanceEngine.classify_hrv_stress_context(ctx)
        assert result == "UNKNOWN_ACWR"

    @pytest.mark.unit
    @pytest.mark.governance
    def test_acwr_none_returns_unknown_label(self):
        """acwr=None → returns UNKNOWN_ACWR."""
        ctx = _ctx(acwr=None)
        result = GovernanceEngine.classify_hrv_stress_context(ctx)
        assert result == "UNKNOWN_ACWR"

    @pytest.mark.unit
    @pytest.mark.governance
    def test_acwr_non_numeric_string_returns_unknown_label(self):
        """acwr='bad' (cannot float-cast) → returns UNKNOWN_ACWR."""
        ctx = _ctx(acwr="bad")
        result = GovernanceEngine.classify_hrv_stress_context(ctx)
        assert result == "UNKNOWN_ACWR"

    # ---------------------------------------------------------------------------
    # Regression: valid ACWR values still work correctly
    # ---------------------------------------------------------------------------

    @pytest.mark.unit
    @pytest.mark.governance
    def test_acwr_above_max_returns_training_explained(self):
        """Valid acwr above VO2_ACWR_MAX (1.30) still returns TRAINING_EXPLAINED."""
        ctx = _ctx(acwr=1.5)
        result = GovernanceEngine.classify_hrv_stress_context(ctx)
        assert result == "TRAINING_EXPLAINED"

    @pytest.mark.unit
    @pytest.mark.governance
    def test_acwr_within_safe_zone_and_large_hrv_delta(self):
        """Valid acwr in safe zone + large HRV drop → UNEXPLAINED_MODERATE (not TRAINING_EXPLAINED)."""
        ctx = _ctx(acwr=1.0)
        result = GovernanceEngine.classify_hrv_stress_context(ctx)
        assert result == "UNEXPLAINED_MODERATE"

    @pytest.mark.unit
    @pytest.mark.governance
    def test_acwr_within_safe_zone_normal_hrv(self):
        """Valid acwr + normal HRV delta → TRAINING_EXPLAINED (fallthrough)."""
        ctx = _ctx(acwr=1.0, baseline_hrv=60.0, today_hrv=58.0)
        result = GovernanceEngine.classify_hrv_stress_context(ctx)
        assert result == "TRAINING_EXPLAINED"
