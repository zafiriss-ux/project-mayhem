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
