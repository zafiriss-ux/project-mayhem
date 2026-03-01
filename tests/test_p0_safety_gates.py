"""
Tests for Issue #12 — P0 Hard-Stop Safety Gates (H1–H4)

Acceptance scenarios per .github/issues/001-p0-safety-gates.md.

Run with:
    pytest tests/test_p0_safety_gates.py -v
"""

import pytest
from titan.science.governance_engine import GovernanceEngine
from titan.config.thresholds import (
    HARD_STOP_HRV_DELTA,
    HARD_STOP_RHR_DELTA,
    HARD_STOP_TSB_FLOOR,
    SUBJECTIVE_FATIGUE_EXTREME,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def make_plan(session_type: str = "INTERVALS") -> dict:
    return {"session_type": session_type, "max_zone": 5}


def make_context(**overrides) -> dict:
    """Baseline context that does NOT trigger any hard stop."""
    ctx = {
        "today_hrv":               50.0,
        "baseline_hrv":            50.0,
        "today_rhr":               50.0,
        "baseline_rhr":            50.0,
        "tsb_value":               0.0,
        "injury_flag":             False,
        "subjective_fatigue_score": 0,
    }
    ctx.update(overrides)
    return ctx


gov = GovernanceEngine()


# ── AT-H1: HRV + RHR dual collapse ───────────────────────────────────────────

def test_H1_dual_collapse_forces_rest():
    """AT-H1: Both HRV and RHR beyond thresholds → REST, max_zone=1."""
    ctx = make_context(
        today_hrv=28.0, baseline_hrv=55.0,   # delta = -27
        today_rhr=72.0, baseline_rhr=52.0,   # delta = +20
    )
    plan = gov.apply_constraints(make_plan("INTERVALS"), ctx)
    assert plan["session_type"] == "REST"
    assert plan["max_zone"] == 1
    assert "HRV/RHR dual collapse" in plan["governance_override"]
    assert "HARD_STOP_SAFETY_GATES" in plan["governance_locks_applied"]
    assert any(r["gate"] == "H1" for r in plan["hard_stop_reasons"])


def test_H1_dual_collapse_pr_text_closes_12():
    """PR text marker: Closes #12 — verified by H1 gate firing."""
    ctx = make_context(
        today_hrv=28.0, baseline_hrv=55.0,
        today_rhr=72.0, baseline_rhr=52.0,
    )
    plan = gov.apply_constraints(make_plan("INTERVALS"), ctx)
    assert plan["session_type"] == "REST"   # gate fired


def test_H1_only_hrv_drops_does_not_fire():
    """AT-H1b: Only HRV drops (RHR normal) → H1 does NOT fire."""
    ctx = make_context(
        today_hrv=28.0, baseline_hrv=55.0,   # delta = -27
        today_rhr=54.0, baseline_rhr=52.0,   # delta = +2 (below threshold)
    )
    plan = gov.apply_constraints(make_plan("INTERVALS"), ctx)
    assert plan["session_type"] == "INTERVALS"   # H1 did not fire


def test_H1_only_rhr_spikes_does_not_fire():
    """H1 requires BOTH thresholds; only RHR spike → gate silent."""
    ctx = make_context(
        today_hrv=49.0, baseline_hrv=50.0,   # delta = -1 (fine)
        today_rhr=70.0, baseline_rhr=50.0,   # delta = +20
    )
    plan = gov.apply_constraints(make_plan("INTERVALS"), ctx)
    assert plan["session_type"] == "INTERVALS"


# ── AT-H2: TSB floor ──────────────────────────────────────────────────────────

def test_H2_tsb_below_floor_blocks_hammer():
    """AT-H2: tsb=-52 → EASY or REST, HAMMER blocked."""
    ctx = make_context(tsb_value=-52.0)
    plan = gov.apply_constraints(make_plan("HAMMER"), ctx)
    assert plan["session_type"] in ("EASY", "REST")
    assert "TSB at overtraining threshold" in plan["governance_override"]


def test_H2_tsb_exactly_at_floor_fires():
    """AT-H2b: tsb=-50 (inclusive) → gate fires."""
    ctx = make_context(tsb_value=-50.0)
    plan = gov.apply_constraints(make_plan("INTERVALS"), ctx)
    assert plan["session_type"] in ("EASY", "REST")
    assert "HARD_STOP_SAFETY_GATES" in plan["governance_locks_applied"]
    assert any(r["gate"] == "H2" for r in plan["hard_stop_reasons"])


def test_H2_tsb_just_above_floor_does_not_fire():
    """tsb=-49 (above floor) → H2 does NOT fire."""
    ctx = make_context(tsb_value=-49.0)
    plan = gov.apply_constraints(make_plan("INTERVALS"), ctx)
    assert plan["session_type"] == "INTERVALS"


# ── AT-H3: Injury flag ────────────────────────────────────────────────────────

def test_H3_injury_flag_true_forces_rest():
    """AT-H3: injury_flag=True → REST regardless of session."""
    ctx = make_context(injury_flag=True)
    plan = gov.apply_constraints(make_plan("TEMPO"), ctx)
    assert plan["session_type"] == "REST"
    assert "Active injury flag" in plan["governance_override"]


def test_H3_no_injury_key_in_context_does_not_fire():
    """AT-H3b: 'injury_flag' absent → context.get returns falsy → gate silent."""
    ctx = {
        "today_hrv": 50.0, "baseline_hrv": 50.0,
        "today_rhr": 50.0, "baseline_rhr": 50.0,
        "tsb_value": 0.0,
        "subjective_fatigue_score": 0,
        # 'injury_flag' key intentionally omitted
    }
    plan = gov.apply_constraints(make_plan("INTERVALS"), ctx)
    assert plan["session_type"] == "INTERVALS"


# ── AT-H4: Extreme subjective fatigue ────────────────────────────────────────

def test_H4_extreme_fatigue_downgrades_to_easy():
    """AT-H4: subjective_fatigue_score=9 → EASY."""
    ctx = make_context(subjective_fatigue_score=9)
    plan = gov.apply_constraints(make_plan("INTERVALS"), ctx)
    assert plan["session_type"] == "EASY"
    assert "extreme fatigue" in plan["governance_override"]


def test_H4_fatigue_below_threshold_does_not_fire():
    """AT-H4b: score=7 (< 8) → gate does NOT fire."""
    ctx = make_context(subjective_fatigue_score=7)
    plan = gov.apply_constraints(make_plan("INTERVALS"), ctx)
    assert plan["session_type"] == "INTERVALS"


def test_H4_fatigue_exactly_at_threshold_fires():
    """score=8 (== SUBJECTIVE_FATIGUE_EXTREME) → gate fires (inclusive)."""
    ctx = make_context(subjective_fatigue_score=SUBJECTIVE_FATIGUE_EXTREME)
    plan = gov.apply_constraints(make_plan("INTERVALS"), ctx)
    assert plan["session_type"] == "EASY"


# ── AT-CONFIG: Thresholds are config-driven ──────────────────────────────────

def test_config_thresholds_respected(monkeypatch):
    """AT-CONFIG: Raising HARD_STOP_HRV_DELTA to 20 means delta=-18 doesn't fire H1."""
    import titan.science.governance_engine as ge_mod
    import titan.config.thresholds as thr_mod

    monkeypatch.setattr(thr_mod, "HARD_STOP_HRV_DELTA", 20)
    monkeypatch.setattr(ge_mod, "HARD_STOP_HRV_DELTA", 20)

    ctx = make_context(
        today_hrv=40.0, baseline_hrv=58.0,   # delta = -18 < 20 → below new threshold
        today_rhr=70.0, baseline_rhr=50.0,   # RHR would be above threshold
    )
    plan = gov.apply_constraints(make_plan("INTERVALS"), ctx)
    # H1 should NOT fire: HRV delta (-18) does not reach new threshold (20)
    assert plan["session_type"] == "INTERVALS"


# ── Gate clean path ───────────────────────────────────────────────────────────

def test_no_gate_fires_session_unchanged():
    """All signals nominal → no hard stop, session passes through."""
    ctx = make_context()
    plan = gov.apply_constraints(make_plan("INTERVALS"), ctx)
    assert plan["session_type"] == "INTERVALS"
    assert plan.get("governance_clean") is True
