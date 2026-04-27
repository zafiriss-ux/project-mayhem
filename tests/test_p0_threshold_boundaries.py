"""
P0 safety threshold boundary tests — VO2_ACWR window and glycogen debt gate.

These tests call the REAL GovernanceEngine.apply_constraints() to verify that
the boundary values defined in titan/config/thresholds.py produce the expected
lock / pass behaviour. No mocks of the governance logic.

Coverage gaps identified in audit 2026-04-26:
  - VO2_ACWR_MIN / VO2_ACWR_MAX  (boundary at ±0.001)
  - VO2_GLYCOGEN_DEBT_MAX         (boundary at ±0.01)
"""
from __future__ import annotations

import pytest

from titan.config.thresholds import (
    VO2_ACWR_MAX,
    VO2_ACWR_MIN,
    VO2_GLYCOGEN_DEBT_MAX,
    VO2_READINESS_MIN,
)
from titan.science.governance_engine import GovernanceEngine


def _vo2_session_plan() -> dict:
    return {"session_type": "HAMMER", "duration_min": 45, "max_zone": 5, "zone": 5}


def _base_context(*, acwr: float, glycogen_debt: float = 0.0, readiness: float = 80.0) -> dict:
    """Minimal context with all VO2 eligibility inputs wired."""
    return {
        "acwr": acwr,
        "readiness_score": readiness,
        "glycogen_debt": glycogen_debt,
        "fatigue_level": "LOW",
        "esi_level": "LOW",
        "days_since_last_vo2": 3,
        "afi_constraints": {"afi_modifier": 0, "readiness_clamp": 100, "parasympathetic_guard": {"triggered": False}},
        "priority_vector": {},
        "lock_thresholds": {},
        "subjective_fatigue_score": 3,
        "hrv_delta": 5.0,
        "today_hrv": 50.0,
        "baseline_hrv": 45.0,
        "hrv_std_dev": 2.0,
        "today_rhr": 50,
        "baseline_rhr": 50,
        "tsb_value": 5.0,
        "sleep_score": 75,
        "planned_duration_min": 45,
        "injury_flag": False,
        "fueling_confirmed": False,
        "data_confidence_low": False,
        "persistence_degraded": False,
        "garmin_data_stale": False,
        "data_trust": {"overall": "HIGH", "reports": []},
    }


def _has_vo2_lock(result: dict) -> bool:
    locks = result.get("governance_locks_applied", [])
    return "VO2_ELIGIBILITY_GATE" in locks


@pytest.mark.parametrize("acwr,should_block", [
    (VO2_ACWR_MIN - 0.001, True),
    (VO2_ACWR_MIN,          False),
    (VO2_ACWR_MIN + 0.001,  False),
    (VO2_ACWR_MAX - 0.001,  False),
    (VO2_ACWR_MAX,          False),
    (VO2_ACWR_MAX + 0.001,  True),
])
def test_vo2_acwr_window_boundary(acwr: float, should_block: bool) -> None:
    """VO2 eligibility gate must block exactly when ACWR is outside [MIN, MAX]."""
    engine = GovernanceEngine()
    plan = _vo2_session_plan()
    ctx = _base_context(acwr=acwr, readiness=VO2_READINESS_MIN + 10.0)
    result = engine.apply_constraints(plan, ctx)
    locked = _has_vo2_lock(result)
    assert locked == should_block, (
        f"ACWR={acwr}: expected block={should_block}, got locked={locked}. "
        f"vo2_eligibility={result.get('vo2_eligibility')}"
    )


@pytest.mark.parametrize("debt,should_block", [
    (VO2_GLYCOGEN_DEBT_MAX - 0.01, False),
    (VO2_GLYCOGEN_DEBT_MAX,        True),
    (VO2_GLYCOGEN_DEBT_MAX + 0.01, True),
])
def test_vo2_glycogen_debt_boundary(debt: float, should_block: bool) -> None:
    """VO2 eligibility gate must block when glycogen_debt >= VO2_GLYCOGEN_DEBT_MAX."""
    engine = GovernanceEngine()
    plan = _vo2_session_plan()
    # Use nominal ACWR so only glycogen decides eligibility
    ctx = _base_context(
        acwr=(VO2_ACWR_MIN + VO2_ACWR_MAX) / 2.0,
        glycogen_debt=debt,
        readiness=VO2_READINESS_MIN + 10.0,
    )
    result = engine.apply_constraints(plan, ctx)
    locked = _has_vo2_lock(result)
    assert locked == should_block, (
        f"glycogen_debt={debt}: expected block={should_block}, got locked={locked}. "
        f"vo2_eligibility={result.get('vo2_eligibility')}"
    )
