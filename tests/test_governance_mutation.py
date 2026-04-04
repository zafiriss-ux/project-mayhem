"""Governance mutation test suite (T4-18 / ADR-0021).

For each of the 7 governance gates, this file verifies:
  - Boundary-ON:  input at or over threshold → gate fires → correct output.
  - Boundary-OFF: input one unit below threshold → gate does NOT fire.
  - Threshold source: gate logic uses thresholds.py constants (imports verified
    via parametrize — changing the constant changes the boundary automatically).

These tests replace the comment-based "ARCHITECTURE LOCK" with machine-verifiable
protection. Any change to governance gate logic that breaks a boundary case will
fail here before reaching review.
"""

from titan.config.thresholds import (
    HARD_STOP_HRV_DELTA,
    HARD_STOP_RHR_DELTA,
    HARD_STOP_TSB_FLOOR,
    SUBJECTIVE_FATIGUE_EXTREME,
)
from titan.science.governance_engine import (  # noqa: E402
    GovernanceEngine,
)

# ── Shared fixture ────────────────────────────────────────────────────────────

def _base_context(**overrides) -> dict:
    """Return a minimal governance context that does NOT trigger any gate."""
    ctx: dict = {
        "afi_constraints": {"afi_modifier": 0, "readiness_clamp": 100},
        "intensity_gate_result": {"zone": "GREEN"},
        "readiness_score": 75.0,
        "glycogen_debt": 1.0,
        "fatigue_level": "LOW",
        "acwr": 1.0,
        "days_since_last_vo2": 5,
        "fueling_confirmed": True,
        "planned_duration_min": 60,
        "today_hrv": 50.0,
        "baseline_hrv": 40.0,   # delta = +10 (below HARD_STOP_HRV_DELTA=15)
        "hrv_std_dev": 2.0,
        "today_rhr": 52,
        "baseline_rhr": 50.0,   # delta = +2 (below HARD_STOP_RHR_DELTA=8)
        "sleep_score": 75,
        "subjective_fatigue_score": 4,
        "tsb_value": 0.0,       # above HARD_STOP_TSB_FLOOR=-50
        "injury_flag": False,
        "priority_vector": {},
        "lock_thresholds": {},
    }
    ctx.update(overrides)
    return ctx


def _base_session(**overrides) -> dict:
    session: dict = {
        "session_type": "INTERVALS",
        "duration_min": 60,
        "max_zone": 5,
        "volume_pct": 1.0,
    }
    session.update(overrides)
    return session


def _engine() -> GovernanceEngine:
    return GovernanceEngine()


# ── H2: HRV Collapse ─────────────────────────────────────────────────────────

def test_h2_fires_at_threshold():
    """H2 fires when today_hrv drop == HARD_STOP_HRV_DELTA (inclusive)."""
    ctx = _base_context(
        today_hrv=40.0 - HARD_STOP_HRV_DELTA,   # exactly at threshold
        baseline_hrv=40.0,
    )
    result = _engine().apply_constraints(_base_session(), ctx)
    assert result["session_type"] == "REST"
    assert any(r.get("gate") == "H2" for r in result.get("hard_stop_reasons", []))


def test_h2_does_not_fire_below_threshold():
    """H2 must NOT fire when today_hrv drop is 1ms below HARD_STOP_HRV_DELTA."""
    ctx = _base_context(
        today_hrv=40.0 - HARD_STOP_HRV_DELTA + 1.0,
        baseline_hrv=40.0,
    )
    result = _engine().apply_constraints(_base_session(), ctx)
    assert result["session_type"] != "REST"


# ── H3: RHR Spike ────────────────────────────────────────────────────────────

def test_h3_fires_at_threshold():
    """H3 fires when today_rhr rise == HARD_STOP_RHR_DELTA (inclusive)."""
    ctx = _base_context(
        today_rhr=int(50.0 + HARD_STOP_RHR_DELTA),   # exactly at threshold
        baseline_rhr=50.0,
    )
    result = _engine().apply_constraints(_base_session(), ctx)
    assert result["session_type"] == "REST"
    assert any(r.get("gate") == "H3" for r in result.get("hard_stop_reasons", []))


def test_h3_does_not_fire_below_threshold():
    """H3 must NOT fire when today_rhr rise is 1bpm below HARD_STOP_RHR_DELTA."""
    ctx = _base_context(
        today_rhr=int(50.0 + HARD_STOP_RHR_DELTA - 1),
        baseline_rhr=50.0,
    )
    result = _engine().apply_constraints(_base_session(), ctx)
    assert result["session_type"] != "REST"


# ── H4: TSB Floor ────────────────────────────────────────────────────────────

def test_h4_fires_at_threshold():
    """H4 fires when tsb_value == HARD_STOP_TSB_FLOOR (inclusive)."""
    ctx = _base_context(tsb_value=HARD_STOP_TSB_FLOOR)
    session = _base_session(session_type="INTERVALS")
    result = _engine().apply_constraints(session, ctx)
    assert result["session_type"] in {"EASY", "REST"}
    assert any(r.get("gate") == "H4" for r in result.get("hard_stop_reasons", []))


def test_h4_does_not_fire_above_threshold():
    """H4 must NOT fire when tsb_value is 1 unit above HARD_STOP_TSB_FLOOR."""
    ctx = _base_context(tsb_value=HARD_STOP_TSB_FLOOR + 1.0)
    session = _base_session(session_type="INTERVALS")
    result = _engine().apply_constraints(session, ctx)
    assert not any(r.get("gate") == "H4" for r in result.get("hard_stop_reasons", []))


# ── H5: Extreme Subjective Fatigue ────────────────────────────────────────────

def test_h5_fires_at_threshold():
    """H5 fires when subjective_fatigue_score == SUBJECTIVE_FATIGUE_EXTREME."""
    ctx = _base_context(subjective_fatigue_score=SUBJECTIVE_FATIGUE_EXTREME)
    session = _base_session(session_type="INTERVALS")
    result = _engine().apply_constraints(session, ctx)
    assert result["session_type"] in {"EASY", "REST"}
    assert any(r.get("gate") == "H5" for r in result.get("hard_stop_reasons", []))


def test_h5_does_not_fire_below_threshold():
    """H5 must NOT fire when subjective_fatigue_score is 1 below SUBJECTIVE_FATIGUE_EXTREME."""
    ctx = _base_context(subjective_fatigue_score=SUBJECTIVE_FATIGUE_EXTREME - 1)
    result = _engine().apply_constraints(_base_session(), ctx)
    assert "extreme fatigue" not in str(result.get("governance_override", "")).lower()


# ── PERSISTENCE_DEGRADED_CEILING ─────────────────────────────────────────────

def test_persistence_degraded_ceiling_applies():
    """persistence_degraded=True must cap session at EASY and add lock code."""
    ctx = _base_context(persistence_degraded=True)
    session = _base_session(session_type="INTERVALS")
    result = _engine().apply_constraints(session, ctx)
    assert result["session_type"] == "EASY"
    assert "PERSISTENCE_DEGRADED_CEILING" in result.get("governance_locks_applied", [])


def test_persistence_degraded_ceiling_does_not_fire_when_false():
    """persistence_degraded=False must NOT add PERSISTENCE_DEGRADED_CEILING."""
    ctx = _base_context(persistence_degraded=False)
    result = _engine().apply_constraints(_base_session(session_type="INTERVALS"), ctx)
    assert "PERSISTENCE_DEGRADED_CEILING" not in result.get("governance_locks_applied", [])


# ── data_confidence_low ceiling ───────────────────────────────────────────────

def test_data_confidence_low_ceiling_applies():
    """data_confidence_low=True must cap session at EASY and add lock code."""
    ctx = _base_context(data_confidence_low=True)
    session = _base_session(session_type="INTERVALS")
    result = _engine().apply_constraints(session, ctx)
    assert result["session_type"] == "EASY"
    assert "STARTUP_DATA_CONFIDENCE_CEILING" in result.get("governance_locks_applied", [])


# ── NaN Input Tests (INV-01 / HR-02 / HR-04) ────────────────────────────────
# Every governance gate must produce a conservative outcome on NaN input —
# the gate must not silently pass NaN comparisons (float("nan") <= x is False).


def test_h2_nan_hrv_does_not_fire_silently():
    """H2: NaN today_hrv must NOT silently pass (gate rejected, not triggered)."""
    ctx = _base_context(today_hrv=float("nan"), baseline_hrv=50.0)
    result = _engine().apply_constraints(_base_session(), ctx)
    # NaN HRV → gate rejected via isfinite check → h2 does not fire
    # (conservative ceiling applied upstream via data_confidence_low)
    # Key invariant: H2 must NOT fire with session_type=REST due to NaN alone
    # (NaN is not a confirmed HRV collapse — it is missing data)
    assert result is not None  # pipeline must not raise
    # NaN should not produce REST via H2 gate (would be silent false positive)
    hard_stop_gates = [r.get("gate") for r in result.get("hard_stop_reasons", [])]
    assert "H2" not in hard_stop_gates, "H2 must not fire on NaN HRV (INV-01)"


def test_h3_nan_rhr_does_not_fire_silently():
    """H3: NaN today_rhr must NOT silently pass (gate rejected, not triggered)."""
    ctx = _base_context(today_rhr=float("nan"), baseline_rhr=50.0)
    result = _engine().apply_constraints(_base_session(), ctx)
    assert result is not None
    hard_stop_gates = [r.get("gate") for r in result.get("hard_stop_reasons", [])]
    assert "H3" not in hard_stop_gates, "H3 must not fire on NaN RHR (INV-01)"


def test_h4_nan_tsb_does_not_fire_silently():
    """H4: NaN tsb_value must NOT silently bypass the floor gate."""
    # If NaN tsb silently returned False for <= HARD_STOP_TSB_FLOOR, the gate
    # would be bypassed. The fix converts non-finite to None → gate skipped.
    ctx = _base_context(tsb_value=float("nan"))
    session = _base_session(session_type="INTERVALS")
    result = _engine().apply_constraints(session, ctx)
    assert result is not None
    # NaN TSB → tsb_value becomes None → H4 does not fire (missing data, not confirmed floor)
    hard_stop_gates = [r.get("gate") for r in result.get("hard_stop_reasons", [])]
    assert "H4" not in hard_stop_gates, "H4 must not fire on NaN TSB (INV-01)"


def test_vo2_nan_acwr_blocks_vo2_session():
    """VO2 eligibility gate: NaN ACWR must mark V1 invalid and block VO2.

    HAMMER and INTERVALS@zone5 are the VO2-session types that trigger the gate.
    """
    ctx = _base_context(acwr=float("nan"))
    # INTERVALS with zone 5 triggers the VO2 eligibility check
    session = _base_session(session_type="INTERVALS", max_zone=5)
    session["zone"] = 5
    result = _engine().apply_constraints(session, ctx)
    assert result is not None
    # NaN ACWR → acwr_invalid = True → V1 fails → session downgraded (not INTERVALS@5)
    applied_locks = result.get("governance_locks_applied", [])
    assert "VO2_ELIGIBILITY_GATE" in applied_locks, (
        f"VO2_ELIGIBILITY_GATE must be locked when ACWR is NaN (INV-01); "
        f"applied_locks={applied_locks}"
    )


def test_vo2_nan_readiness_blocks_vo2_session():
    """VO2 eligibility gate: NaN readiness must mark V2 invalid and block VO2."""
    ctx = _base_context(readiness_score=float("nan"))
    session = _base_session(session_type="INTERVALS", max_zone=5)
    session["zone"] = 5
    result = _engine().apply_constraints(session, ctx)
    assert result is not None
    applied_locks = result.get("governance_locks_applied", [])
    assert "VO2_ELIGIBILITY_GATE" in applied_locks, (
        f"VO2_ELIGIBILITY_GATE must be locked when readiness is NaN (INV-01); "
        f"applied_locks={applied_locks}"
    )


def test_vo2_nan_glycogen_debt_blocks_vo2_session():
    """VO2 eligibility gate: NaN glycogen_debt must mark V3 invalid and block VO2."""
    ctx = _base_context(glycogen_debt=float("nan"))
    session = _base_session(session_type="INTERVALS", max_zone=5)
    session["zone"] = 5
    result = _engine().apply_constraints(session, ctx)
    assert result is not None
    applied_locks = result.get("governance_locks_applied", [])
    assert "VO2_ELIGIBILITY_GATE" in applied_locks, (
        f"VO2_ELIGIBILITY_GATE must be locked when glycogen_debt is NaN (INV-01); "
        f"applied_locks={applied_locks}"
    )


# ── NaN boundary tests: H5, FUELING_GATE, INTENSITY_GATE (T5-72b / ADR-0009) ─

def test_h5_nan_fatigue_does_not_fire_silently():
    """H5: NaN subjective_fatigue_score must NOT silently trigger the gate (INV-01)."""
    ctx = _base_context(subjective_fatigue_score=float("nan"))
    result = _engine().apply_constraints(_base_session(), ctx)
    assert result is not None
    hard_stop_gates = [r.get("gate") for r in result.get("hard_stop_reasons", [])]
    assert "H5" not in hard_stop_gates, "H5 must not fire on NaN fatigue score (INV-01)"


def test_fueling_gate_nan_duration_does_not_lock():
    """FUELING_GATE: NaN duration_min must be rejected without applying a lock (INV-01)."""
    ctx = _base_context(fueling_confirmed=False)
    session = _base_session(session_type="TEMPO", duration_min=float("nan"))
    result = _engine().apply_constraints(session, ctx)
    assert result is not None
    applied_locks = result.get("governance_locks_applied", [])
    assert "FUELING_GATE_LOCK" not in applied_locks, (
        f"FUELING_GATE_LOCK must not fire on NaN duration (INV-01); "
        f"applied_locks={applied_locks}"
    )


def test_intensity_gate_nan_volume_modifier_defaults_to_one():
    """INTENSITY_GATE: NaN volume_modifier must be rejected and default to 1.0 (INV-01)."""
    ctx = _base_context(
        intensity_gate_result={"color": "GREEN", "max_zone": 5, "volume_modifier": float("nan")}
    )
    result = _engine().apply_constraints(_base_session(), ctx)
    assert result is not None
    assert result.get("volume_modifier") == 1.0, (
        f"volume_modifier must default to 1.0 on NaN input (INV-01); "
        f"got {result.get('volume_modifier')}"
    )


# ── VO2 eligibility ESI EXTREME boundary (T5-14 / ADR-0034) ────────────────

def test_vo2_esi_extreme_boundary_on_blocks_vo2_session():
    """Boundary-ON: esi_level=EXTREME must fail V4 and downgrade VO2 work."""
    ctx = _base_context(
        esi_level="EXTREME",
        acwr=1.0,
        readiness_score=75.0,
        glycogen_debt=1.0,
        fatigue_level="LOW",
        days_since_last_vo2=5,
    )
    session = _base_session(session_type="HAMMER", max_zone=5)

    result = _engine().apply_constraints(session, ctx)

    assert result["session_type"] == "TEMPO"
    assert "VO2_ELIGIBILITY_GATE" in result.get("governance_locks_applied", [])
    vo2 = result.get("vo2_eligibility", {})
    assert vo2.get("eligible") is False
    assert "V4" in vo2.get("failed_conditions", [])


def test_vo2_esi_extreme_boundary_off_does_not_block_vo2_session():
    """Boundary-OFF: non-EXTREME ESI must not trigger VO2 V4 failure by itself."""
    ctx = _base_context(
        esi_level="HIGH",
        acwr=1.0,
        readiness_score=75.0,
        glycogen_debt=1.0,
        fatigue_level="LOW",
        days_since_last_vo2=5,
    )
    session = _base_session(session_type="HAMMER", max_zone=5)

    result = _engine().apply_constraints(session, ctx)

    assert result["session_type"] == "HAMMER"
    assert "VO2_ELIGIBILITY_GATE" not in result.get("governance_locks_applied", [])
    vo2 = result.get("vo2_eligibility", {})
    assert vo2.get("eligible") is True


# ── No-gate clean path ────────────────────────────────────────────────────────

def test_governance_clean_when_no_gate_fires():
    """When no gate condition is met, governance_clean must be True and session
    type must be unchanged."""
    ctx = _base_context()
    result = _engine().apply_constraints(_base_session(session_type="EASY"), ctx)
    assert result["governance_clean"] is True
    assert result["session_type"] == "EASY"
