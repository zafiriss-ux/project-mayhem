import math

from titan.science.tsb_engine import TSBEngine


def _build_engine_with_history(loads: list[float]) -> TSBEngine:
    engine = TSBEngine()
    for index, load in enumerate(loads):
        engine.add_daily_load(f"2026-01-{index + 1:02d}", load)
    return engine


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
