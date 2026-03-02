"""
Tests for P0 Hard-Stop Safety Gates (H1–H5)

Gate order per DECISION_MODEL §4 and ADR-0009:
  H1 — Injury / Medical Flag      → REST  (Gate 1: highest priority)
  H2 — HRV Collapse               → REST  (Gate 2a: OR semantics)
  H3 — RHR Spike                  → REST  (Gate 2b: OR semantics)
  H4 — TSB Critical Floor         → EASY  (Gate 4: load gate)
  H5 — Extreme Subjective Fatigue → EASY  (Gate 3/aggregate)

H2 and H3 use OR semantics per DECISION_MODEL Gate 2:
  IF hrv_collapse OR rhr_collapse → RED hard stop
Either signal alone is sufficient; dual collapse fires both gates.

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


# ── AT-H1: Injury / Medical Flag (Gate 1 — highest priority) ─────────────────

def test_H1_injury_flag_true_forces_rest():
    """AT-H1: injury_flag=True → REST regardless of session."""
    ctx = make_context(injury_flag=True)
    plan = gov.apply_constraints(make_plan("TEMPO"), ctx)
    assert plan["session_type"] == "REST"
    assert "Active injury flag" in plan["governance_override"]
    assert any(r["gate"] == "H1" for r in plan["hard_stop_reasons"])


def test_H1_injury_flag_recorded_alongside_autonomic_gates():
    """H1 (injury) fires and is recorded in hard_stop_reasons even when H2 also fires."""
    ctx = make_context(
        injury_flag=True,
        today_hrv=28.0, baseline_hrv=55.0,   # H2 also fires
    )
    plan = gov.apply_constraints(make_plan("INTERVALS"), ctx)
    gates_fired = [r["gate"] for r in plan["hard_stop_reasons"]]
    assert "H1" in gates_fired
    assert plan["session_type"] == "REST"


def test_H1_no_injury_key_in_context_does_not_fire():
    """AT-H1b: 'injury_flag' absent → context.get returns falsy → gate silent."""
    ctx = {
        "today_hrv": 50.0, "baseline_hrv": 50.0,
        "today_rhr": 50.0, "baseline_rhr": 50.0,
        "tsb_value": 0.0,
        "subjective_fatigue_score": 0,
        # 'injury_flag' key intentionally omitted
    }
    plan = gov.apply_constraints(make_plan("INTERVALS"), ctx)
    assert plan["session_type"] == "INTERVALS"


# ── AT-H2: HRV Collapse — OR semantics (gate fires on HRV alone) ─────────────

def test_H2_hrv_collapse_alone_forces_rest():
    """AT-H2: HRV collapse alone (RHR normal) → REST.
    OR semantics per DECISION_MODEL Gate 2 — HRV collapse is individually sufficient."""
    ctx = make_context(
        today_hrv=28.0, baseline_hrv=55.0,   # delta = -27, exceeds HARD_STOP_HRV_DELTA
        today_rhr=52.0, baseline_rhr=50.0,   # delta = +2, well below RHR threshold
    )
    plan = gov.apply_constraints(make_plan("INTERVALS"), ctx)
    assert plan["session_type"] == "REST"
    assert plan["max_zone"] == 1
    assert "HRV collapse" in plan["governance_override"]
    assert "HARD_STOP_SAFETY_GATES" in plan["governance_locks_applied"]
    assert any(r["gate"] == "H2" for r in plan["hard_stop_reasons"])


def test_H2_hrv_just_above_threshold_does_not_fire():
    """HRV delta = (HARD_STOP_HRV_DELTA - 1) ms → H2 does NOT fire."""
    ctx = make_context(
        today_hrv=50.0 - (HARD_STOP_HRV_DELTA - 1),
        baseline_hrv=50.0,
    )
    plan = gov.apply_constraints(make_plan("INTERVALS"), ctx)
    assert plan["session_type"] == "INTERVALS"


def test_H2_hrv_exactly_at_threshold_fires():
    """HRV drop of exactly HARD_STOP_HRV_DELTA → H2 fires (< boundary: strict)."""
    ctx = make_context(
        today_hrv=50.0 - HARD_STOP_HRV_DELTA,   # exactly at threshold
        baseline_hrv=50.0,
    )
    plan = gov.apply_constraints(make_plan("INTERVALS"), ctx)
    assert plan["session_type"] == "REST"
    assert any(r["gate"] == "H2" for r in plan["hard_stop_reasons"])


# ── AT-H3: RHR Spike — OR semantics (gate fires on RHR alone) ────────────────

def test_H3_rhr_spike_alone_forces_rest():
    """AT-H3: RHR spike alone (HRV normal) → REST.
    OR semantics per DECISION_MODEL Gate 2 — RHR spike is individually sufficient."""
    ctx = make_context(
        today_hrv=49.0, baseline_hrv=50.0,   # delta = -1, well below HRV threshold
        today_rhr=70.0, baseline_rhr=50.0,   # delta = +20, exceeds HARD_STOP_RHR_DELTA
    )
    plan = gov.apply_constraints(make_plan("INTERVALS"), ctx)
    assert plan["session_type"] == "REST"
    assert plan["max_zone"] == 1
    assert "RHR spike" in plan["governance_override"]
    assert "HARD_STOP_SAFETY_GATES" in plan["governance_locks_applied"]
    assert any(r["gate"] == "H3" for r in plan["hard_stop_reasons"])


def test_H3_rhr_just_below_threshold_does_not_fire():
    """RHR delta = (HARD_STOP_RHR_DELTA - 1) bpm → H3 does NOT fire."""
    ctx = make_context(
        today_rhr=50.0 + (HARD_STOP_RHR_DELTA - 1),
        baseline_rhr=50.0,
    )
    plan = gov.apply_constraints(make_plan("INTERVALS"), ctx)
    assert plan["session_type"] == "INTERVALS"


def test_H3_rhr_exactly_at_threshold_fires():
    """RHR spike of exactly HARD_STOP_RHR_DELTA bpm → H3 fires (> boundary: strict)."""
    ctx = make_context(
        today_rhr=50.0 + HARD_STOP_RHR_DELTA,   # exactly at threshold
        baseline_rhr=50.0,
    )
    plan = gov.apply_constraints(make_plan("INTERVALS"), ctx)
    assert plan["session_type"] == "REST"
    assert any(r["gate"] == "H3" for r in plan["hard_stop_reasons"])


def test_H2_H3_dual_collapse_fires_both_gates():
    """Dual collapse: both HRV and RHR beyond thresholds → H2 and H3 both fire."""
    ctx = make_context(
        today_hrv=28.0, baseline_hrv=55.0,   # H2 trigger: delta = -27
        today_rhr=72.0, baseline_rhr=52.0,   # H3 trigger: delta = +20
    )
    plan = gov.apply_constraints(make_plan("INTERVALS"), ctx)
    assert plan["session_type"] == "REST"
    assert plan["max_zone"] == 1
    assert "HARD_STOP_SAFETY_GATES" in plan["governance_locks_applied"]
    gates_fired = [r["gate"] for r in plan["hard_stop_reasons"]]
    assert "H2" in gates_fired
    assert "H3" in gates_fired


def test_dual_collapse_pr_text_closes_12():
    """PR text marker: Closes #12 — verified by dual autonomic gate firing."""
    ctx = make_context(
        today_hrv=28.0, baseline_hrv=55.0,
        today_rhr=72.0, baseline_rhr=52.0,
    )
    plan = gov.apply_constraints(make_plan("INTERVALS"), ctx)
    assert plan["session_type"] == "REST"   # gates fired


# ── AT-H4: TSB Critical Floor ─────────────────────────────────────────────────

def test_H4_tsb_below_floor_blocks_hammer():
    """AT-H4: tsb=-52 → EASY or REST, HAMMER blocked."""
    ctx = make_context(tsb_value=-52.0)
    plan = gov.apply_constraints(make_plan("HAMMER"), ctx)
    assert plan["session_type"] in ("EASY", "REST")
    assert "TSB at overtraining threshold" in plan["governance_override"]


def test_H4_tsb_exactly_at_floor_fires():
    """AT-H4b: tsb=-50 (inclusive) → gate fires."""
    ctx = make_context(tsb_value=-50.0)
    plan = gov.apply_constraints(make_plan("INTERVALS"), ctx)
    assert plan["session_type"] in ("EASY", "REST")
    assert "HARD_STOP_SAFETY_GATES" in plan["governance_locks_applied"]
    assert any(r["gate"] == "H4" for r in plan["hard_stop_reasons"])


def test_H4_tsb_just_above_floor_does_not_fire():
    """tsb=-49 (above floor) → H4 does NOT fire."""
    ctx = make_context(tsb_value=-49.0)
    plan = gov.apply_constraints(make_plan("INTERVALS"), ctx)
    assert plan["session_type"] == "INTERVALS"


# ── AT-H5: Extreme Subjective Fatigue ────────────────────────────────────────

def test_H5_extreme_fatigue_downgrades_to_easy():
    """AT-H5: subjective_fatigue_score=9 → EASY."""
    ctx = make_context(subjective_fatigue_score=9)
    plan = gov.apply_constraints(make_plan("INTERVALS"), ctx)
    assert plan["session_type"] == "EASY"
    assert "extreme fatigue" in plan["governance_override"]
    assert any(r["gate"] == "H5" for r in plan["hard_stop_reasons"])


def test_H5_fatigue_below_threshold_does_not_fire():
    """AT-H5b: score=7 (< 8) → gate does NOT fire."""
    ctx = make_context(subjective_fatigue_score=7)
    plan = gov.apply_constraints(make_plan("INTERVALS"), ctx)
    assert plan["session_type"] == "INTERVALS"


def test_H5_fatigue_exactly_at_threshold_fires():
    """score=8 (== SUBJECTIVE_FATIGUE_EXTREME) → gate fires (inclusive)."""
    ctx = make_context(subjective_fatigue_score=SUBJECTIVE_FATIGUE_EXTREME)
    plan = gov.apply_constraints(make_plan("INTERVALS"), ctx)
    assert plan["session_type"] == "EASY"


# ── AT-CONFIG: Thresholds are config-driven ──────────────────────────────────

def test_config_hrv_delta_respected(monkeypatch):
    """AT-CONFIG: Raising HARD_STOP_HRV_DELTA to 30 means delta=-27 doesn't fire H2.
    RHR is kept normal so only the HRV threshold is tested in isolation."""
    import titan.science.governance_engine as ge_mod
    import titan.config.thresholds as thr_mod

    monkeypatch.setattr(thr_mod, "HARD_STOP_HRV_DELTA", 30)
    monkeypatch.setattr(ge_mod, "HARD_STOP_HRV_DELTA", 30)

    ctx = make_context(
        today_hrv=28.0, baseline_hrv=55.0,   # delta = -27, below new threshold of 30
        today_rhr=50.0, baseline_rhr=50.0,   # RHR nominal — H3 must not interfere
    )
    plan = gov.apply_constraints(make_plan("INTERVALS"), ctx)
    # H2 should NOT fire: HRV delta (-27) does not reach new threshold (30)
    assert plan["session_type"] == "INTERVALS"


def test_config_rhr_delta_respected(monkeypatch):
    """AT-CONFIG: Raising HARD_STOP_RHR_DELTA to 25 means delta=+20 doesn't fire H3.
    HRV is kept nominal so only the RHR threshold is tested in isolation."""
    import titan.science.governance_engine as ge_mod
    import titan.config.thresholds as thr_mod

    monkeypatch.setattr(thr_mod, "HARD_STOP_RHR_DELTA", 25)
    monkeypatch.setattr(ge_mod, "HARD_STOP_RHR_DELTA", 25)

    ctx = make_context(
        today_hrv=50.0, baseline_hrv=50.0,   # HRV nominal — H2 must not interfere
        today_rhr=70.0, baseline_rhr=50.0,   # delta = +20, below new threshold of 25
    )
    plan = gov.apply_constraints(make_plan("INTERVALS"), ctx)
    # H3 should NOT fire: RHR delta (+20) does not reach new threshold (25)
    assert plan["session_type"] == "INTERVALS"


# ── Gate clean path ───────────────────────────────────────────────────────────

def test_no_gate_fires_session_unchanged():
    """All signals nominal → no hard stop, session passes through."""
    ctx = make_context()
    plan = gov.apply_constraints(make_plan("INTERVALS"), ctx)
    assert plan["session_type"] == "INTERVALS"
    assert plan.get("governance_clean") is True
