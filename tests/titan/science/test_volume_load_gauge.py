import math

import pytest

from titan.science.volume_load_gauge import VolumeLoadGauge


@pytest.fixture
def gauge() -> VolumeLoadGauge:
    return VolumeLoadGauge()


def test_resolve_green_inputs_remain_green(gauge: VolumeLoadGauge) -> None:
    state = gauge.resolve(tsb_value=-10.0, acwr=1.0, glycogen_debt=2.0)

    assert state.color == "GREEN"
    assert state.components == {"tsb": "GREEN", "acwr": "GREEN", "glycogen": "GREEN"}


@pytest.mark.parametrize("tsb_value", [math.nan, math.inf, -math.inf])
def test_resolve_non_finite_tsb_is_conservative_not_green(gauge: VolumeLoadGauge, tsb_value: float) -> None:
    state = gauge.resolve(tsb_value=tsb_value, acwr=1.0, glycogen_debt=2.0)

    assert state.color == "RED"
    assert state.score == 2
    assert state.components == {"tsb": "RED", "acwr": "GREEN", "glycogen": "GREEN"}


@pytest.mark.parametrize("glycogen_debt", [math.nan, math.inf, -math.inf])
def test_resolve_non_finite_glycogen_is_conservative_not_green(
    gauge: VolumeLoadGauge, glycogen_debt: float
) -> None:
    state = gauge.resolve(tsb_value=-10.0, acwr=1.0, glycogen_debt=glycogen_debt)

    assert state.color == "RED"
    assert state.score == 2
    assert state.components == {"tsb": "GREEN", "acwr": "GREEN", "glycogen": "RED"}
