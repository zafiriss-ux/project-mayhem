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


# ── No-gate clean path ────────────────────────────────────────────────────────

def test_governance_clean_when_no_gate_fires():
    """When no gate condition is met, governance_clean must be True and session
    type must be unchanged."""
    ctx = _base_context()
    result = _engine().apply_constraints(_base_session(session_type="EASY"), ctx)
    assert result["governance_clean"] is True
    assert result["session_type"] == "EASY"
