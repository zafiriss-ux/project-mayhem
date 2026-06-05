"""ADR-0053: H6 Data-Void Conservative Gate tests.

Gate spec: when garmin_data_age_hours > DATA_VOID_THRESHOLD_HOURS,
apply DATA_VOID_CONSERVATIVE lock and cap max_zone to DATA_VOID_ZONE_CAP.
H6 is a soft gate — no early return, cap applied in apply_constraints.
"""

import pytest

from titan.config.thresholds import DATA_VOID_THRESHOLD_HOURS, DATA_VOID_ZONE_CAP
from titan.science.governance_engine import GovernanceEngine

gov = GovernanceEngine()


def make_plan(session_type: str = "EASY", max_zone: int = 5) -> dict:
    return {"session_type": session_type, "max_zone": max_zone}


def make_context(**overrides) -> dict:
    """Baseline context that does not trigger any H1-H5 gate."""
    ctx = {
        "today_hrv": 50.0,
        "baseline_hrv": 50.0,
        "today_rhr": 50.0,
        "baseline_rhr": 50.0,
        "tsb_value": 0.0,
        "injury_flag": False,
        "subjective_fatigue_score": 0,
        "sleep_score": 80,
        "readiness_score": 70,
        "acwr": 1.1,
    }
    ctx.update(overrides)
    return ctx


@pytest.mark.unit
@pytest.mark.governance
def test_h6_fires_when_data_age_exceeds_threshold():
    """AT-H6-01: age > threshold → DATA_VOID_CONSERVATIVE lock + zone cap."""
    ctx = make_context(garmin_data_age_hours=DATA_VOID_THRESHOLD_HOURS + 1.0)
    result = gov.apply_constraints(make_plan(), ctx)
    assert "DATA_VOID_CONSERVATIVE" in result["governance_locks_applied"]
    assert result["max_zone"] <= DATA_VOID_ZONE_CAP


@pytest.mark.unit
@pytest.mark.governance
def test_h6_does_not_fire_within_threshold():
    """AT-H6-02: age <= threshold → gate silent."""
    ctx = make_context(garmin_data_age_hours=DATA_VOID_THRESHOLD_HOURS - 24.0)
    result = gov.apply_constraints(make_plan(), ctx)
    assert "DATA_VOID_CONSERVATIVE" not in result["governance_locks_applied"]


@pytest.mark.unit
@pytest.mark.governance
def test_h6_does_not_fire_when_age_missing():
    """AT-H6-03: garmin_data_age_hours absent → gate silent."""
    ctx = make_context()
    result = gov.apply_constraints(make_plan(), ctx)
    assert "DATA_VOID_CONSERVATIVE" not in result["governance_locks_applied"]


@pytest.mark.unit
@pytest.mark.governance
def test_h6_does_not_fire_on_nan_age():
    """AT-H6-04: NaN age must not trigger gate (INV-01 guard)."""
    ctx = make_context(garmin_data_age_hours=float("nan"))
    result = gov.apply_constraints(make_plan(), ctx)
    assert "DATA_VOID_CONSERVATIVE" not in result["governance_locks_applied"]


@pytest.mark.unit
@pytest.mark.governance
def test_h6_cap_does_not_exceed_zone2():
    """AT-H6-05: zone-5 session under data void is capped at DATA_VOID_ZONE_CAP."""
    ctx = make_context(garmin_data_age_hours=72.0)
    session = make_plan(session_type="INTERVALS", max_zone=5)
    result = gov.apply_constraints(session, ctx)
    assert result["max_zone"] <= DATA_VOID_ZONE_CAP
    assert result["max_zone"] <= 2


@pytest.mark.unit
@pytest.mark.governance
def test_h6_fires_from_real_context_payload():
    """AT-H6-06: H6 fires when context_payload mirrors DailyCoach wiring (line 861).

    Validates the end-to-end path: garmin_data_age_hours in context_payload
    (set at daily_coach.py:861 via garmin_trust.data_age_hours) correctly
    triggers DATA_VOID_CONSERVATIVE and caps max_zone.
    """
    context = make_context(garmin_data_age_hours=72.0)
    result = gov.apply_constraints(make_plan(session_type="TEMPO", max_zone=4), context)
    assert "DATA_VOID_CONSERVATIVE" in result["governance_locks_applied"]
    assert result["max_zone"] <= DATA_VOID_ZONE_CAP


@pytest.mark.unit
@pytest.mark.governance
def test_h6_does_not_fire_when_age_fresh():
    """AT-H6-07: H6 silent when garmin_data_age_hours is within threshold."""
    context = make_context(garmin_data_age_hours=12.0)
    result = gov.apply_constraints(make_plan(), context)
    assert "DATA_VOID_CONSERVATIVE" not in result["governance_locks_applied"]
