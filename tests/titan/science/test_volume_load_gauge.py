import math

import pytest

from titan.config.evidence_registry import EVIDENCE_REGISTRY
from titan.config.thresholds import (
    VLG_ACWR_RED_MAX,
    VLG_ACWR_RED_MIN,
    VLG_ACWR_YELLOW_MAX,
    VLG_ACWR_YELLOW_MIN,
    VLG_GLYCOGEN_RED_MIN,
    VLG_GLYCOGEN_YELLOW_MIN,
    VLG_TSB_YELLOW_MIN,
)
from titan.science.volume_load_gauge import VolumeLoadGauge


@pytest.fixture
def gauge() -> VolumeLoadGauge:
    return VolumeLoadGauge()


@pytest.mark.unit
def test_resolve_green_inputs_remain_green(gauge: VolumeLoadGauge) -> None:
    state = gauge.resolve(tsb_value=-10.0, acwr=1.0, glycogen_debt=2.0)

    assert state.color == "GREEN"
    assert state.components == {"tsb": "GREEN", "acwr": "GREEN", "glycogen": "GREEN"}


@pytest.mark.unit
@pytest.mark.parametrize("tsb_value", [math.nan, math.inf, -math.inf])
def test_resolve_non_finite_tsb_is_conservative_not_green(gauge: VolumeLoadGauge, tsb_value: float) -> None:
    state = gauge.resolve(tsb_value=tsb_value, acwr=1.0, glycogen_debt=2.0)

    assert state.color == "RED"
    assert state.score == 2
    assert state.components == {"tsb": "RED", "acwr": "GREEN", "glycogen": "GREEN"}


@pytest.mark.unit
@pytest.mark.parametrize("glycogen_debt", [math.nan, math.inf, -math.inf])
def test_resolve_non_finite_glycogen_is_conservative_not_green(
    gauge: VolumeLoadGauge, glycogen_debt: float
) -> None:
    state = gauge.resolve(tsb_value=-10.0, acwr=1.0, glycogen_debt=glycogen_debt)

    assert state.color == "RED"
    assert state.score == 2
    assert state.components == {"tsb": "GREEN", "acwr": "GREEN", "glycogen": "RED"}


@pytest.mark.unit
def test_vlg_threshold_boundaries_are_read_from_thresholds_constants(gauge: VolumeLoadGauge) -> None:
    assert gauge._tsb_color(VLG_TSB_YELLOW_MIN) == "YELLOW"

    assert gauge._acwr_color(VLG_ACWR_YELLOW_MIN) == "GREEN"
    assert gauge._acwr_color(VLG_ACWR_YELLOW_MIN - 0.01) == "YELLOW"
    assert gauge._acwr_color(VLG_ACWR_RED_MIN) == "YELLOW"
    assert gauge._acwr_color(VLG_ACWR_RED_MIN - 0.01) == "RED"

    assert gauge._acwr_color(VLG_ACWR_YELLOW_MAX) == "GREEN"
    assert gauge._acwr_color(VLG_ACWR_YELLOW_MAX + 0.01) == "YELLOW"
    assert gauge._acwr_color(VLG_ACWR_RED_MAX) == "YELLOW"
    assert gauge._acwr_color(VLG_ACWR_RED_MAX + 0.01) == "RED"

    assert gauge._glycogen_color(VLG_GLYCOGEN_YELLOW_MIN) == "YELLOW"
    assert gauge._glycogen_color(VLG_GLYCOGEN_RED_MIN - 0.01) == "YELLOW"
    assert gauge._glycogen_color(VLG_GLYCOGEN_RED_MIN) == "RED"


@pytest.mark.unit
def test_vlg_threshold_constants_have_evidence_registry_entries() -> None:
    constants = (
        "VLG_TSB_YELLOW_MIN",
        "VLG_ACWR_RED_MIN",
        "VLG_ACWR_YELLOW_MIN",
        "VLG_ACWR_YELLOW_MAX",
        "VLG_ACWR_RED_MAX",
        "VLG_GLYCOGEN_YELLOW_MIN",
        "VLG_GLYCOGEN_RED_MIN",
    )

    for constant in constants:
        assert constant in EVIDENCE_REGISTRY


# ── XA-T04 (#1169): an ACWR that is unknown or not a number reads as GREEN ──────

_XA_T04 = "XA-T04 (#1169): VolumeLoadGauge.resolve turns an unknown or non-numeric ACWR into 1.0 or lets NaN through"


@pytest.mark.unit
@pytest.mark.parametrize("acwr", [math.inf, -math.inf])
def test_1169_control_an_infinite_acwr_is_red(gauge: VolumeLoadGauge, acwr: float) -> None:
    state = gauge.resolve(tsb_value=-10.0, acwr=acwr, glycogen_debt=2.0)

    assert state.components["acwr"] == "RED"
    assert state.color == "RED"


@pytest.mark.unit
@pytest.mark.xfail(strict=True, raises=AssertionError, reason=_XA_T04)
@pytest.mark.parametrize("acwr", [math.nan, "bad"], ids=["nan", "not a number"])
def test_1169_an_acwr_that_is_not_a_number_is_not_green(gauge: VolumeLoadGauge, acwr: object) -> None:
    state = gauge.resolve(tsb_value=-10.0, acwr=acwr, glycogen_debt=2.0)  # type: ignore[arg-type]

    assert state.components["acwr"] != "GREEN"  # as a non-finite TSB or glycogen debt
    assert state.color != "GREEN"


@pytest.mark.unit
@pytest.mark.xfail(strict=True, raises=AssertionError, reason=_XA_T04)
def test_1169_an_unknown_acwr_is_not_reported_as_in_range(gauge: VolumeLoadGauge) -> None:
    """The morning passes acwr=None when the load history is too short (_acwr_from_history).

    Which colour an unknown ACWR takes is the owner's decision; here only that it is
    not reported as a measured, in-range GREEN.
    """
    state = gauge.resolve(tsb_value=-10.0, acwr=None, glycogen_debt=2.0)  # type: ignore[arg-type]

    assert state.components["acwr"] != "GREEN"
    assert "All load components within green operating range" not in state.rationale


def _morning_load_step(acwr: object, tsb_value: object):
    """DailyCoach step 9a (``_step_load_priority``) with the real VLG and priority lock."""
    from types import SimpleNamespace

    from titan.orchestration.daily_coach import DailyCoach
    from titan.science.adaptive_priority_lock import AdaptivePriorityLock, _vlg_to_load_band

    coach = DailyCoach.__new__(DailyCoach)
    coach.vlg = VolumeLoadGauge()
    coach.glycogen = SimpleNamespace(daily_debt=2.0)
    coach.apl = AdaptivePriorityLock()
    coach.cs_tracker = SimpleNamespace(confidence=0.9)
    coach.athlete_profile = None
    _tsb, vlg_state, _phase, _apl = coach._step_load_priority(
        acwr=acwr, tsb_value=tsb_value, afi_constraints={}, today_session={"session_type": "TEMPO"},  # type: ignore[arg-type]
    )
    return vlg_state, _vlg_to_load_band(vlg_state)


@pytest.mark.unit
def test_1169_control_the_morning_load_step_with_measured_inputs_is_optimal() -> None:
    vlg_state, band = _morning_load_step(acwr=1.0, tsb_value=-10.0)

    assert vlg_state.color == "GREEN" and band == "OPTIMAL"


@pytest.mark.unit
@pytest.mark.xfail(strict=True, raises=AssertionError, reason=_XA_T04)
def test_1169_the_morning_load_step_with_unknown_acwr_and_tsb_is_not_optimal() -> None:
    """An unknown TSB becomes 0.0 (``_safe_float``) and an unknown ACWR 1.0, so the
    priority lock sees the OPTIMAL load band."""
    vlg_state, band = _morning_load_step(acwr=None, tsb_value=None)

    assert vlg_state.color != "GREEN"
    assert band != "OPTIMAL"
