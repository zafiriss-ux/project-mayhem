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
