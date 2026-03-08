import math

import pytest

from titan.config import thresholds
from titan.science import tsb_engine
from titan.science.tsb_engine import TSBEngine


def _build_engine_with_history(loads: list[float]) -> TSBEngine:
    engine = TSBEngine()
    for index, load in enumerate(loads):
        engine.add_daily_load(f"2026-01-{index + 1:02d}", load)
    return engine




def test_default_ctl_atl_decay_uses_canonical_threshold_constants() -> None:
    engine = _build_engine_with_history([80.0, 100.0, 120.0, 60.0, 90.0])

    assert engine.calculate_ctl() == engine.calculate_ctl(decay=thresholds.CTL_DECAY_DAYS)
    assert engine.calculate_atl() == engine.calculate_atl(decay=thresholds.ATL_DECAY_DAYS)


def test_changing_canonical_decay_constants_changes_default_ema_results(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _build_engine_with_history([120.0, 80.0, 160.0, 40.0, 200.0, 20.0])

    baseline_ctl = engine.calculate_ctl()
    baseline_atl = engine.calculate_atl()

    monkeypatch.setattr(tsb_engine, "CTL_DECAY_DAYS", 10)
    monkeypatch.setattr(tsb_engine, "ATL_DECAY_DAYS", 3)

    shifted_ctl = engine.calculate_ctl()
    shifted_atl = engine.calculate_atl()

    assert shifted_ctl is not None and baseline_ctl is not None
    assert shifted_atl is not None and baseline_atl is not None
    assert shifted_ctl != baseline_ctl
    assert shifted_atl != baseline_atl

def test_empty_history_returns_safe_defaults_without_crashing() -> None:
    engine = TSBEngine()

    assert engine.calculate_ctl() is None
    assert engine.calculate_atl() is None
    assert engine.calculate_tsb() == (None, "INSUFFICIENT DATA")
    assert engine.get_tsb_status() == {"tsb_value": None, "status": "INSUFFICIENT DATA"}
    assert engine.get_latest_tsb() == 0.0


def test_numeric_outputs_are_always_finite() -> None:
    engine = _build_engine_with_history([100.0, 250.0, 75.0, 410.0, 90.0, 320.0, 180.0])

    ctl = engine.calculate_ctl()
    atl = engine.calculate_atl()
    tsb, _ = engine.calculate_tsb()

    assert ctl is not None and math.isfinite(ctl)
    assert atl is not None and math.isfinite(atl)
    assert tsb is not None and math.isfinite(tsb)


def test_ctl_atl_tsb_stay_within_plausible_bounds_for_non_negative_loads() -> None:
    loads = [0.0, 40.0, 65.0, 120.0, 90.0, 150.0, 200.0, 170.0, 80.0, 60.0]
    engine = _build_engine_with_history(loads)

    ctl = engine.calculate_ctl()
    atl = engine.calculate_atl()
    tsb, _ = engine.calculate_tsb()

    assert ctl is not None and 0.0 <= ctl <= max(loads)
    assert atl is not None and 0.0 <= atl <= max(loads)
    assert tsb is not None and -max(loads) <= tsb <= max(loads)


def test_identical_input_series_produce_identical_outputs() -> None:
    loads = [35.0, 55.0, 70.0, 45.0, 90.0, 30.0, 75.0, 65.0]
    engine_a = _build_engine_with_history(loads)
    engine_b = _build_engine_with_history(loads)

    assert engine_a.calculate_ctl() == engine_b.calculate_ctl()
    assert engine_a.calculate_atl() == engine_b.calculate_atl()
    assert engine_a.calculate_tsb() == engine_b.calculate_tsb()
    assert engine_a.get_tsb_status() == engine_b.get_tsb_status()


def test_very_high_and_very_low_load_sequences_remain_finite_and_stable() -> None:
    high_load_engine = _build_engine_with_history([100.0] * 30 + [5000.0] * 5)
    low_load_engine = _build_engine_with_history([0.0] * 35)

    high_tsb, _ = high_load_engine.calculate_tsb()
    low_tsb, _ = low_load_engine.calculate_tsb()

    assert high_tsb is not None and math.isfinite(high_tsb)
    assert low_tsb is not None and math.isfinite(low_tsb)
    assert high_tsb < 0.0
    assert low_tsb == 0.0


@pytest.mark.parametrize(
    ("ctl", "atl", "expected_status"),
    [
        (30.0, 4.0, "⚠️ SEVERE DETRAINING"),
        (30.0, 14.0, "⚠️ DETRAINING"),
        (30.0, 20.0, "✅ FRESH"),
        (30.0, 27.0, "🎯 RACE FORM"),
        (10.0, 25.0, "💪 PRODUCTIVE OVERLOAD"),
        (10.0, 45.0, "⚠️ FUNCTIONAL OVERREACH"),
        (10.0, 65.0, "🛑 OVERTRAINED"),
    ],
)
def test_calculate_tsb_status_bands_match_current_threshold_mapping(
    monkeypatch: pytest.MonkeyPatch, ctl: float, atl: float, expected_status: str
) -> None:
    engine = TSBEngine()
    engine.add_daily_load("2026-01-01", 1.0)
    monkeypatch.setattr(engine, "calculate_ctl", lambda decay=None: ctl)
    monkeypatch.setattr(engine, "calculate_atl", lambda decay=None: atl)

    tsb, status = engine.calculate_tsb()

    assert tsb == round(ctl - atl, 1)
    assert status == expected_status


def test_predict_race_day_tsb_returns_none_for_invalid_inputs() -> None:
    engine = TSBEngine()

    assert engine.predict_race_day_tsb(days=1, loads=[]) is None
    assert engine.predict_race_day_tsb(days=3, loads=[10.0, 20.0]) is None


def test_predict_race_day_tsb_uses_current_internal_ctl_atl_state() -> None:
    engine = TSBEngine()
    engine.ctl = 50.0
    engine.atl = 40.0

    predicted = engine.predict_race_day_tsb(days=3, loads=[100.0, 50.0, 0.0, 999.0])

    temp_ctl = 50.0
    temp_atl = 40.0
    for load in [100.0, 50.0, 0.0]:
        temp_atl = (load * (2 / 8)) + (temp_atl * (6 / 8))
        temp_ctl = (load * (2 / 43)) + (temp_ctl * (41 / 43))
    expected = round(temp_ctl - temp_atl, 1)

    assert predicted == expected


def test_predict_race_day_tsb_with_zero_days_returns_current_form_delta() -> None:
    engine = TSBEngine()
    engine.ctl = 37.26
    engine.atl = 42.81

    assert engine.predict_race_day_tsb(days=0, loads=[300.0]) == -5.6
