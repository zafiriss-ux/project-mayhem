"""
T5-49: Governance conservative defaults.

Verifies that when sleep_score or readiness_score are absent from the governance
context, the 2-of-4 downgrade gate receives a conservative default of 40 (not 100).

ADR-0009 reference: safety gate hardening — missing data must not silently pass gates.
"""

import pytest

from titan.science.governance_engine import GovernanceEngine

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_context(**overrides):
    """Return a minimal governance context that avoids hard-stop gates."""
    base = {
        "hrv_delta": 0.0,
        "rhr_delta": 0.0,
        "tsb": 0.0,
        "subjective_fatigue_score": 0,
        # sleep_score and readiness_score intentionally omitted in some tests
    }
    base.update(overrides)
    return base


def _make_engine():
    return GovernanceEngine()


# ---------------------------------------------------------------------------
# T5-49-A: missing sleep_score defaults to 40 (fires I2_sleep < 60 threshold)
# ---------------------------------------------------------------------------

class TestMissingSleepScoreConservativeDefault:
    """When sleep_score is absent, default must be 40 so I2_sleep fires."""

    @pytest.mark.unit
    @pytest.mark.governance
    def test_missing_sleep_score_fires_i2(self):
        """Absence of sleep_score should yield I2_sleep indicator (40 < 60)."""
        engine = _make_engine()
        ctx = _base_context()
        assert "sleep_score" not in ctx, "Precondition: sleep_score must be absent"

        count, indicators = engine._evaluate_2of4_indicators(ctx)

        assert "I2_sleep" in indicators, (
            f"I2_sleep must fire when sleep_score is absent; indicators={indicators}"
        )

    @pytest.mark.unit
    @pytest.mark.governance
    def test_present_high_sleep_score_does_not_fire_i2(self):
        """A present high sleep_score (>= 60) must NOT fire I2_sleep."""
        engine = _make_engine()
        ctx = _base_context(sleep_score=80)

        count, indicators = engine._evaluate_2of4_indicators(ctx)

        assert "I2_sleep" not in indicators, (
            f"I2_sleep must not fire when sleep_score=80; indicators={indicators}"
        )

    @pytest.mark.unit
    @pytest.mark.governance
    def test_present_low_sleep_score_fires_i2(self):
        """A present low sleep_score (< 60) must fire I2_sleep."""
        engine = _make_engine()
        ctx = _base_context(sleep_score=50)

        count, indicators = engine._evaluate_2of4_indicators(ctx)

        assert "I2_sleep" in indicators, (
            f"I2_sleep must fire when sleep_score=50; indicators={indicators}"
        )


# ---------------------------------------------------------------------------
# T5-49-B: missing readiness_score defaults to 40 (fires I3_readiness < 50)
# ---------------------------------------------------------------------------

class TestMissingReadinessScoreConservativeDefault:
    """When readiness_score is absent, default must be 40 so I3_readiness fires."""

    @pytest.mark.unit
    @pytest.mark.governance
    def test_missing_readiness_score_fires_i3(self):
        """Absence of readiness_score should yield I3_readiness indicator (40 < 50)."""
        engine = _make_engine()
        ctx = _base_context()
        assert "readiness_score" not in ctx, "Precondition: readiness_score must be absent"

        count, indicators = engine._evaluate_2of4_indicators(ctx)

        assert "I3_readiness" in indicators, (
            f"I3_readiness must fire when readiness_score is absent; indicators={indicators}"
        )

    @pytest.mark.unit
    @pytest.mark.governance
    def test_present_high_readiness_score_does_not_fire_i3(self):
        """A present high readiness_score (>= 50) must NOT fire I3_readiness."""
        engine = _make_engine()
        ctx = _base_context(readiness_score=70)

        count, indicators = engine._evaluate_2of4_indicators(ctx)

        assert "I3_readiness" not in indicators, (
            f"I3_readiness must not fire when readiness_score=70; indicators={indicators}"
        )

    @pytest.mark.unit
    @pytest.mark.governance
    def test_present_low_readiness_score_fires_i3(self):
        """A present low readiness_score (< 50) must fire I3_readiness."""
        engine = _make_engine()
        ctx = _base_context(readiness_score=30)

        count, indicators = engine._evaluate_2of4_indicators(ctx)

        assert "I3_readiness" in indicators, (
            f"I3_readiness must fire when readiness_score=30; indicators={indicators}"
        )


# ---------------------------------------------------------------------------
# T5-49-C: both missing — both indicators fire
# ---------------------------------------------------------------------------

class TestBothMissingConservativeDefaults:
    """When both sleep_score and readiness_score are absent, both I2 and I3 fire."""

    @pytest.mark.unit
    @pytest.mark.governance
    def test_both_missing_fires_both_indicators(self):
        engine = _make_engine()
        ctx = _base_context()
        assert "sleep_score" not in ctx
        assert "readiness_score" not in ctx

        count, indicators = engine._evaluate_2of4_indicators(ctx)

        assert "I2_sleep" in indicators, f"I2_sleep must fire; indicators={indicators}"
        assert "I3_readiness" in indicators, f"I3_readiness must fire; indicators={indicators}"
        assert count >= 2, f"count must be >= 2; got {count}"

    @pytest.mark.unit
    @pytest.mark.governance
    def test_both_present_and_healthy_fires_neither(self):
        """Both present with healthy values: neither I2 nor I3 should fire."""
        engine = _make_engine()
        ctx = _base_context(sleep_score=85, readiness_score=75)

        count, indicators = engine._evaluate_2of4_indicators(ctx)

        assert "I2_sleep" not in indicators, f"I2_sleep must not fire; indicators={indicators}"
        assert "I3_readiness" not in indicators, f"I3_readiness must not fire; indicators={indicators}"
