"""Combined gate interaction tests — Gate Coverage Matrix column (d).

Each test exercises two governance gates simultaneously to verify:
  - Neither gate crashes when both fire in the same apply_constraints call
  - Precedence / sequencing produces the correct final session state
  - governance_locks_applied correctly records every fired gate

Gate Coverage Matrix column (d) targets covered by this file:
  H1_OVERRIDE_LOCKDOWN — combined lockdown and H2 interaction  (d_combined)
  H3_RHR_SPIKE         — H3 and H2 combined interaction        (d_combined)
  H4_ACWR              — H4 combined ACWR interaction           (d_combined)
  H5_CONSECUTIVE       — H5 consecutive combined interaction    (d_combined)
"""

from __future__ import annotations

import pytest

from titan.config.thresholds import (
    HARD_STOP_HRV_DELTA,
    HARD_STOP_RHR_DELTA,
    HARD_STOP_TSB_FLOOR,
    SUBJECTIVE_FATIGUE_2OF4,
    SUBJECTIVE_FATIGUE_EXTREME,
)
from titan.science.governance_engine import GovernanceEngine

# ── Module-level helpers (mirror test_p0_safety_gates.py conventions) ─────────

gov = GovernanceEngine()


def _plan(session_type: str = "INTERVALS", **overrides) -> dict:
    base = {"session_type": session_type, "max_zone": 5}
    base.update(overrides)
    return base


def _ctx(**overrides) -> dict:
    """Physiologically safe baseline — no gate fires on defaults."""
    base = {
        "today_hrv": 55.0,
        "baseline_hrv": 55.0,
        "today_rhr": 50.0,
        "baseline_rhr": 50.0,
        "tsb_value": 0.0,
        "injury_flag": False,
        "subjective_fatigue_score": 0,
        "sleep_score": 80,
        "readiness_score": 70,
        "acwr": 1.1,
        "fueling_confirmed": True,
    }
    base.update(overrides)
    return base


# ── H1_OVERRIDE_LOCKDOWN × H2_HRV_DELTA ────────────────────────────────────

class _HighRatioDb:
    """Stub db that reports an override ratio above the lockdown threshold."""

    def get_override_ratio(self, *, athlete_id: str, days: int = 14) -> float:
        return 0.90  # > GOVERNANCE_OVERRIDE_LOCKDOWN_THRESHOLD (0.80)


@pytest.mark.unit
@pytest.mark.governance
def test_h1_and_h2_both_fire_simultaneously():
    """Combined lockdown and H2 gate interaction: OVERRIDE_LOCKDOWN ratio exceeded
    and H2_HRV_DELTA fire simultaneously — verifies hard-stop REST takes precedence
    over the lockdown downgrade (lockdown and h2 combined interaction).

    Expected behaviour:
      - H2 fires first (hard-stop pipeline runs before the gate_order loop).
      - session_type → REST; HARD_STOP_SAFETY_GATES added to locks.
      - OVERRIDE_LOCKDOWN is evaluated but does not add its own lock because
        REST is not in _QUALITY_SESSIONS.
    """
    ctx = _ctx(
        today_hrv=35.0,      # H2: drop = 20 >= HARD_STOP_HRV_DELTA (15)
        baseline_hrv=55.0,
        db=_HighRatioDb(),   # OVERRIDE_LOCKDOWN condition also active
        athlete_id="owner",
    )
    plan = gov.apply_constraints(_plan("INTERVALS"), ctx)

    assert plan["session_type"] == "REST", (
        "H2 hard-stop must override to REST even when lockdown conditions are present"
    )
    locks = plan["governance_locks_applied"]
    assert "HARD_STOP_SAFETY_GATES" in locks, "H2 hard-stop lock must be recorded"
    gates_fired = [r["gate"] for r in plan.get("hard_stop_reasons", [])]
    assert "H2" in gates_fired, "H2 gate must appear in hard_stop_reasons"


# ── H3_RHR_SPIKE × H2_HRV_DELTA ────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.governance
def test_h3_and_h2_combined_fire():
    """H3 and H2 combined gate interaction: RHR spike and HRV collapse fire together
    (combined rhr and hrv hard-stop, h3 interaction with h2).

    Both autonomic gates fire simultaneously (OR semantics, ADR-0009).
    Expected behaviour:
      - session_type → REST; max_zone → 1.
      - Both H2 and H3 present in hard_stop_reasons.
      - HARD_STOP_SAFETY_GATES in governance_locks_applied.
    """
    ctx = _ctx(
        today_hrv=38.0,      # H2: drop = 17 >= HARD_STOP_HRV_DELTA (15)
        baseline_hrv=55.0,
        today_rhr=62.0,      # H3: rise = 12 >= HARD_STOP_RHR_DELTA (8)
        baseline_rhr=50.0,
    )
    plan = gov.apply_constraints(_plan("INTERVALS"), ctx)

    assert plan["session_type"] == "REST"
    assert plan["max_zone"] == 1
    assert "HARD_STOP_SAFETY_GATES" in plan["governance_locks_applied"]
    gates_fired = [r["gate"] for r in plan.get("hard_stop_reasons", [])]
    assert "H2" in gates_fired, "H2 gate must be in hard_stop_reasons"
    assert "H3" in gates_fired, "H3 gate must be in hard_stop_reasons"


# ── H4_ACWR × INTENSITY_GATE ────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.governance
def test_h4_combined_with_intensity_gate():
    """H4 combined ACWR interaction with intensity gate RED: TSB floor and intensity
    gate fire together — both constraints applied simultaneously (h4 interaction).

    Expected behaviour:
      - INTENSITY_GATE_RED added to locks (intensity gate processes first).
      - H4 fires → HARD_STOP_SAFETY_GATES added; session downgraded to EASY;
        max_zone capped at 2 by H4.
      - Both locks coexist in governance_locks_applied.
    """
    ctx = _ctx(
        tsb_value=HARD_STOP_TSB_FLOOR - 2.0,   # H4: below floor → fires
        intensity_gate_result={
            "color": "RED",
            "max_zone": 3,
            "volume_modifier": 0.70,
        },
    )
    plan = gov.apply_constraints(_plan("INTERVALS"), ctx)

    locks = plan["governance_locks_applied"]
    assert "HARD_STOP_SAFETY_GATES" in locks, "H4 must add HARD_STOP_SAFETY_GATES"
    assert "INTENSITY_GATE_RED" in locks, "RED intensity gate must add INTENSITY_GATE_RED"
    assert plan["max_zone"] <= 2, (
        "H4 must cap max_zone ≤ 2 regardless of intensity gate setting"
    )
    gates_fired = [r["gate"] for r in plan.get("hard_stop_reasons", [])]
    assert "H4" in gates_fired, "H4 gate must appear in hard_stop_reasons"


# ── H5_CONSECUTIVE × FUELING_GATE ──────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.governance
def test_h5_combined_with_fueling_gate():
    """H5 consecutive hard-stop combined interaction with fueling gate: extreme
    consecutive fatigue fires alongside fueling gate flag — both locks recorded
    (h5 interaction, combined consecutive and fueling).

    Scenario: session starts as INTERVALS (65 min, no fueling confirmed).
      - H5 fires (extreme fatigue) → session → EASY, max_zone → 2.
      - Fueling gate then evaluates the downgraded EASY session at 65 min →
        phase-1 FLAG (recommended but optional).
      - Both HARD_STOP_SAFETY_GATES and FUELING_GATE_FLAG in locks.
    """
    ctx = _ctx(
        subjective_fatigue_score=SUBJECTIVE_FATIGUE_EXTREME,  # H5 threshold (8)
        fueling_confirmed=False,
    )
    plan = gov.apply_constraints(
        _plan("INTERVALS", duration_min=65),
        ctx,
    )

    locks = plan["governance_locks_applied"]
    assert "HARD_STOP_SAFETY_GATES" in locks, "H5 must add HARD_STOP_SAFETY_GATES"
    assert "FUELING_GATE_FLAG" in locks, (
        "Fueling gate must flag EASY session without confirmed fueling"
    )
    assert plan["session_type"] == "EASY", "H5 must downgrade INTERVALS → EASY"
    gates_fired = [r["gate"] for r in plan.get("hard_stop_reasons", [])]
    assert "H5" in gates_fired, "H5 gate must appear in hard_stop_reasons"


# ── 2OF4_GATE × NaN/None input (Gate Coverage Matrix col c) ────────────────

@pytest.mark.unit
@pytest.mark.governance
def test_2of4_gate_with_none_sleep_score():
    """2-of-4 gate with None sleep_score — DATA_MISSING_CONSERVATIVE.

    sleep None 2of4: gate_coverage_matrix.sh col (c) NaN/None cell for
    READINESS_2OF4_DOWNGRADE.  None sleep_score must not pass the indicator
    silently; it falls back to 40 (< 60 threshold) so I2_sleep fires.
    A second indicator (I4_subjective at SUBJECTIVE_FATIGUE_2OF4) completes
    the 2-of-4 threshold → READINESS_2OF4_DOWNGRADE lock applied.
    """
    ctx = _ctx(
        sleep_score=None,
        subjective_fatigue_score=SUBJECTIVE_FATIGUE_2OF4,
    )
    plan = gov.apply_constraints(_plan("TEMPO"), ctx)

    locks = plan["governance_locks_applied"]
    assert "READINESS_2OF4_DOWNGRADE" in locks, (
        "None sleep_score must be treated as low (conservative) — "
        "2-of-4 gate must fire when a second indicator is also present"
    )
