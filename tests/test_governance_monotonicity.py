"""
Property-based monotonicity tests for GovernanceEngine (Pass 3).

Invariant: governance decisions must be monotonically non-relaxing as
physiological inputs deteriorate.  Verified with Hypothesis.

6 properties:
  M1 — HRV drop:      larger drop → max_zone never increases
  M2 — RHR rise:      larger rise → max_zone never increases
  M3 — TSB descent:   lower TSB  → max_zone never increases
  M4 — Fatigue score: higher score → max_zone never increases
  M5 — Override ratio: higher ratio → lockdown never lifted
  M6 — ACWR above max: further exceedance → VO2 eligibility never restores
"""

import pytest

pytest.importorskip("hypothesis", reason="Install test deps: pip install -r requirements.txt")

from hypothesis import given, settings
from hypothesis import strategies as st

from titan.science.governance_engine import GovernanceEngine

# ─── Neutral-context helpers ──────────────────────────────────────────────────


class _NeutralDB:
    """DB stub that reports 0 % override ratio — no lockdown."""

    def get_override_ratio(self, **_kwargs: object) -> float:
        return 0.0


class _HighRatioDB:
    """DB stub with a configurable override ratio."""

    def __init__(self, ratio: float) -> None:
        self._ratio = ratio

    def get_override_ratio(self, **_kwargs: object) -> float:
        return self._ratio


class _FullConfidenceTracker:
    """CS tracker stub at full confidence — no CS lock."""

    confidence = 1.0


def _neutral(**overrides: object) -> dict:
    """Return a context dict that fires no governance gates."""
    ctx: dict = {
        "today_hrv": 60.0,
        "baseline_hrv": 60.0,
        "hrv_std_dev": 5.0,
        "today_rhr": 50,
        "baseline_rhr": 50.0,
        "tsb_value": 0.0,
        "subjective_fatigue_score": 0,
        "injury_flag": False,
        "sleep_score": 80,
        "readiness_score": 75.0,
        "acwr": 1.1,
        "glycogen_debt": 2.0,
        "days_since_last_vo2": 3,
        "fueling_confirmed": True,
        "db": _NeutralDB(),
        "cs_tracker": _FullConfidenceTracker(),
        "afi_constraints": {},
        "intensity_gate_result": None,
    }
    ctx.update(overrides)
    return ctx


# ─── Tests ───────────────────────────────────────────────────────────────────


class TestGovernanceMonotonicity:
    """Each test verifies one monotonicity invariant of GovernanceEngine."""

    # M1 — HRV drop
    @given(
        drop=st.floats(min_value=0.0, max_value=30.0, allow_nan=False, allow_infinity=False),
        extra=st.floats(min_value=0.0, max_value=20.0, allow_nan=False, allow_infinity=False),
    )
    @pytest.mark.unit
    @pytest.mark.governance
    @settings(max_examples=50)
    def test_m1_hrv_larger_drop_not_less_restrictive(self, drop: float, extra: float) -> None:
        """Larger HRV drop must not produce a less-restrictive max_zone."""
        baseline = 65.0
        gov = GovernanceEngine()

        plan_a: dict = {"session_type": "INTERVALS", "max_zone": 5}
        gov.apply_constraints(plan_a, _neutral(today_hrv=baseline - drop, baseline_hrv=baseline))

        plan_b: dict = {"session_type": "INTERVALS", "max_zone": 5}
        gov.apply_constraints(
            plan_b, _neutral(today_hrv=baseline - drop - extra, baseline_hrv=baseline)
        )

        assert plan_b["max_zone"] <= plan_a["max_zone"], (
            f"drop={drop:.2f}, extra={extra:.2f}: "
            f"max_zone(worse)={plan_b['max_zone']} > max_zone(better)={plan_a['max_zone']}"
        )

    # M2 — RHR rise
    @given(
        rise=st.floats(min_value=0.0, max_value=20.0, allow_nan=False, allow_infinity=False),
        extra=st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    )
    @pytest.mark.unit
    @pytest.mark.governance
    @settings(max_examples=50)
    def test_m2_rhr_larger_rise_not_less_restrictive(self, rise: float, extra: float) -> None:
        """Larger RHR spike must not produce a less-restrictive max_zone."""
        baseline_rhr = 52.0
        gov = GovernanceEngine()

        plan_a: dict = {"session_type": "INTERVALS", "max_zone": 5}
        gov.apply_constraints(
            plan_a, _neutral(today_rhr=baseline_rhr + rise, baseline_rhr=baseline_rhr)
        )

        plan_b: dict = {"session_type": "INTERVALS", "max_zone": 5}
        gov.apply_constraints(
            plan_b, _neutral(today_rhr=baseline_rhr + rise + extra, baseline_rhr=baseline_rhr)
        )

        assert plan_b["max_zone"] <= plan_a["max_zone"], (
            f"rise={rise:.2f}, extra={extra:.2f}: "
            f"max_zone(worse)={plan_b['max_zone']} > max_zone(better)={plan_a['max_zone']}"
        )

    # M3 — TSB descent
    @given(
        tsb=st.floats(min_value=-80.0, max_value=30.0, allow_nan=False, allow_infinity=False),
        extra=st.floats(min_value=0.0, max_value=30.0, allow_nan=False, allow_infinity=False),
    )
    @pytest.mark.unit
    @pytest.mark.governance
    @settings(max_examples=50)
    def test_m3_lower_tsb_not_less_restrictive(self, tsb: float, extra: float) -> None:
        """Lower (more negative) TSB must not produce a less-restrictive max_zone."""
        gov = GovernanceEngine()

        plan_a: dict = {"session_type": "INTERVALS", "max_zone": 5}
        gov.apply_constraints(plan_a, _neutral(tsb_value=tsb))

        plan_b: dict = {"session_type": "INTERVALS", "max_zone": 5}
        gov.apply_constraints(plan_b, _neutral(tsb_value=tsb - extra))

        assert plan_b["max_zone"] <= plan_a["max_zone"], (
            f"tsb={tsb:.2f}, extra={extra:.2f}: "
            f"max_zone(worse)={plan_b['max_zone']} > max_zone(better)={plan_a['max_zone']}"
        )

    # M4 — Fatigue score
    @given(
        score=st.integers(min_value=0, max_value=9),
        extra=st.integers(min_value=0, max_value=2),
    )
    @pytest.mark.unit
    @pytest.mark.governance
    @settings(max_examples=50)
    def test_m4_higher_fatigue_not_less_restrictive(self, score: int, extra: int) -> None:
        """Higher subjective fatigue must not produce a less-restrictive max_zone."""
        score_b = min(score + extra, 10)
        gov = GovernanceEngine()

        plan_a: dict = {"session_type": "INTERVALS", "max_zone": 5}
        gov.apply_constraints(plan_a, _neutral(subjective_fatigue_score=score))

        plan_b: dict = {"session_type": "INTERVALS", "max_zone": 5}
        gov.apply_constraints(plan_b, _neutral(subjective_fatigue_score=score_b))

        assert plan_b["max_zone"] <= plan_a["max_zone"], (
            f"score={score}, extra={extra}: "
            f"max_zone(worse)={plan_b['max_zone']} > max_zone(better)={plan_a['max_zone']}"
        )

    # M5 — Override ratio lockdown
    @given(
        ratio_a=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        extra=st.floats(min_value=0.0, max_value=0.5, allow_nan=False, allow_infinity=False),
    )
    @pytest.mark.unit
    @pytest.mark.governance
    @settings(max_examples=50)
    def test_m5_higher_override_ratio_lockdown_monotonic(
        self, ratio_a: float, extra: float
    ) -> None:
        """If ratio_A triggers lockdown, ratio_B = A+delta must also be locked."""
        ratio_b = min(ratio_a + extra, 1.0)
        gov = GovernanceEngine()

        result_a = gov.check_override_lockdown(db=_HighRatioDB(ratio_a))
        result_b = gov.check_override_lockdown(db=_HighRatioDB(ratio_b))

        if result_a["locked"]:
            assert result_b["locked"], (
                f"Locked at ratio {ratio_a:.3f} but NOT at higher ratio {ratio_b:.3f}"
            )

    # M6 — ACWR above VO2 max: further exceedance cannot restore eligibility
    @given(
        acwr=st.floats(min_value=1.31, max_value=2.5, allow_nan=False, allow_infinity=False),
        extra=st.floats(min_value=0.0, max_value=0.5, allow_nan=False, allow_infinity=False),
    )
    @pytest.mark.unit
    @pytest.mark.governance
    @settings(max_examples=50)
    def test_m6_acwr_above_max_vo2_ineligibility_monotonic(
        self, acwr: float, extra: float
    ) -> None:
        """ACWR above VO2_ACWR_MAX: greater exceedance must not restore VO2 eligibility."""
        gov = GovernanceEngine()

        plan_a: dict = {"session_type": "HAMMER", "max_zone": 5}
        gov.apply_constraints(plan_a, _neutral(acwr=acwr))

        plan_b: dict = {"session_type": "HAMMER", "max_zone": 5}
        gov.apply_constraints(plan_b, _neutral(acwr=acwr + extra))

        eligible_a = plan_a.get("vo2_eligibility", {}).get("eligible", True)
        eligible_b = plan_b.get("vo2_eligibility", {}).get("eligible", True)

        if not eligible_a:
            assert not eligible_b, (
                f"VO2 ineligible at acwr={acwr:.3f} but eligible at acwr={acwr + extra:.3f}"
            )
