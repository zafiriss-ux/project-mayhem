"""Science engine physiology edge-case regression tests (T4-23)."""

import pytest

from titan.science.governance_engine import GovernanceEngine
from titan.science.readiness_engine import ReadinessEngine
from titan.science.volume_load_gauge import VolumeLoadGauge


def _healthy_context(**overrides) -> dict:
    ctx = {
        "afi_constraints": {"afi_modifier": 0, "readiness_clamp": 100},
        "intensity_gate_result": {"zone": "GREEN"},
        "readiness_score": 80.0,
        "glycogen_debt": 1.0,
        "fatigue_level": "LOW",
        "acwr": 1.0,
        "days_since_last_vo2": 5,
        "fueling_confirmed": True,
        "planned_duration_min": 60,
        "today_hrv": 50.0,
        "baseline_hrv": 40.0,
        "hrv_std_dev": 2.0,
        "today_rhr": 52,
        "baseline_rhr": 50.0,
        "sleep_score": 75,
        "subjective_fatigue_score": 4,
        "tsb_value": 0.0,
        "injury_flag": False,
        "priority_vector": {},
        "lock_thresholds": {},
    }
    ctx.update(overrides)
    return ctx


def _quality_session(**overrides) -> dict:
    session = {
        "session_type": "INTERVALS",
        "duration_min": 60,
        "max_zone": 5,
        "volume_pct": 1.0,
    }
    session.update(overrides)
    return session


@pytest.mark.parametrize(
    ("today_hrv", "baseline_hrv", "expected_rest"),
    [
        pytest.param(0.0, 40.0, True, id="hrv-zero-triggers-hard-stop"),
        pytest.param(30.0, 40.0, False, id="hrv-small-delta-no-hard-stop"),
    ],
)
def test_hrv_edge_cases_preserve_h2_gate_behavior(today_hrv, baseline_hrv, expected_rest):
    result = GovernanceEngine().apply_constraints(
        _quality_session(),
        _healthy_context(today_hrv=today_hrv, baseline_hrv=baseline_hrv),
    )

    h2_triggered = any(reason.get("gate") == "H2" for reason in result.get("hard_stop_reasons", []))
    assert h2_triggered is expected_rest


@pytest.mark.parametrize(
    ("today_rhr", "baseline_rhr", "expect_penalty"),
    [
        pytest.param(200, 50, True, id="rhr-impossible-does-not-produce-healthy-status"),
        pytest.param(52, 50, False, id="rhr-near-baseline-remains-healthy"),
    ],
)
def test_readiness_handles_extreme_rhr_without_invalid_score(today_rhr, baseline_rhr, expect_penalty):
    result = ReadinessEngine.analyze_readiness(
        today_hrv=40.0,
        baseline_hrv=40.0,
        today_rhr=today_rhr,
        baseline_rhr=baseline_rhr,
        sleep_score=80,
        soreness=2,
    )

    assert 0 <= result["score"] <= 100
    if expect_penalty:
        assert result["status"] != "✅ EXCELLENT"
    else:
        assert result["status"] == "✅ EXCELLENT"


@pytest.mark.parametrize(
    ("acwr", "expected_color"),
    [
        pytest.param(None, "GREEN", id="acwr-none-fallback"),
        pytest.param(1.35, "YELLOW", id="acwr-high-warning-band"),
    ],
)
def test_volume_load_gauge_handles_acwr_none_without_crash(acwr, expected_color):
    state = VolumeLoadGauge().resolve(tsb_value=-10.0, acwr=acwr, glycogen_debt=1.0)
    assert state.components["acwr"] == expected_color


def test_governance_remains_clean_for_healthy_input_profile():
    result = GovernanceEngine().apply_constraints(
        _quality_session(session_type="EASY", max_zone=2),
        _healthy_context(),
    )

    assert result["governance_clean"] is True
    assert result.get("hard_stop_reasons", []) == []
    assert result.get("governance_locks_applied", []) == []


def test_governance_approves_quality_session_under_nominal_conditions():
    """Nominal-state coherence oracle (T2-19).

    A fully nominal input profile must not block a high-intensity session
    (INTERVALS + zone=5, which routes through the VO2 eligibility gate).
    Complements the EASY-session test above — a regression in the VO2
    eligibility gate logic would pass the EASY test but fail this one,
    making a silent over-conservative failure visible in CI.
    """
    result = GovernanceEngine().apply_constraints(
        _quality_session(),  # INTERVALS, max_zone=5
        _healthy_context(),  # all metrics nominal; days_since_last_vo2=5 >= threshold
    )

    assert result["governance_clean"] is True, (
        f"Governance blocked a quality session under fully nominal conditions — "
        f"locks: {result.get('governance_locks_applied', [])} | "
        f"hard_stops: {result.get('hard_stop_reasons', [])}"
    )
    assert result.get("hard_stop_reasons", []) == []
    assert result.get("governance_locks_applied", []) == []


@pytest.mark.parametrize(
    ("gate_volume_modifier", "expected"),
    [
        pytest.param(0.0, 0.0, id="zero-stays-zero"),
        pytest.param(None, 0.7, id="missing-falls-back-to-conservative"),
    ],
)
def test_zero_volume_modifier_is_not_replaced(gate_volume_modifier, expected):
    """ADR-0062: the conservative 0.7 replaces a missing modifier only, not a 0.0."""
    gate = {"color": "YELLOW", "max_zone": 2, "session_override": "EASY"}
    if gate_volume_modifier is not None:
        gate["volume_modifier"] = gate_volume_modifier

    result = GovernanceEngine().apply_constraints(
        _quality_session(),
        _healthy_context(intensity_gate_result=gate),
    )

    assert result["volume_modifier"] == pytest.approx(expected)


@pytest.mark.parametrize(
    ("intensity_gate", "tsb_value", "expected_modifier", "expected_cap"),
    [
        pytest.param(None, -60.0, 0.7, 60, id="h4-downgrade-gets-70pct-and-60min"),
        pytest.param({"color": "YELLOW", "volume_modifier": 0.8}, -60.0, 0.7, 60, id="yellow-plus-h4-takes-the-smaller"),
        pytest.param({"color": "YELLOW", "volume_modifier": 0.8}, 0.0, 0.8, None, id="intensity-gate-alone-keeps-its-own"),
        pytest.param(None, 0.0, None, None, id="no-downgrade-no-reduction"),
    ],
)
def test_a_downgrade_without_its_own_modifier_reduces_volume(intensity_gate, tsb_value, expected_modifier, expected_cap):
    """SV-04 / ADR-0065: 2of4, hard stops, VO2 and fueling downgrades get 70% and at most 60'."""
    context = _healthy_context(tsb_value=tsb_value, intensity_gate_result=intensity_gate)
    result = GovernanceEngine().apply_constraints(_quality_session(), context)

    assert result.get("volume_modifier") == (None if expected_modifier is None else pytest.approx(expected_modifier))
    assert result.get("max_duration_min") == expected_cap
