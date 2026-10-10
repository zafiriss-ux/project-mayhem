import math
from datetime import UTC, date, datetime, timedelta

import pytest

from titan.config import thresholds
from titan.science import tsb_engine
from titan.science.tsb_engine import TSBEngine


def _build_engine_with_history(loads: list[float]) -> TSBEngine:
    """One load per consecutive day, the last one today (the kernel runs up to today)."""
    engine = TSBEngine()
    first = datetime.now(UTC).date() - timedelta(days=len(loads) - 1)
    for index, load in enumerate(loads):
        engine.add_daily_load((first + timedelta(days=index)).isoformat(), load)
    return engine


@pytest.mark.unit
def test_default_ctl_atl_decay_uses_canonical_threshold_constants() -> None:
    engine = _build_engine_with_history([80.0, 100.0, 120.0, 60.0, 90.0])

    assert engine.calculate_ctl() == engine.calculate_ctl(decay=thresholds.CTL_DECAY_DAYS)
    assert engine.calculate_atl() == engine.calculate_atl(decay=thresholds.ATL_DECAY_DAYS)


@pytest.mark.unit
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

@pytest.mark.unit
def test_empty_history_returns_safe_defaults_without_crashing() -> None:
    engine = TSBEngine()

    assert engine.calculate_ctl() is None
    assert engine.calculate_atl() is None
    assert engine.calculate_tsb() == (None, "INSUFFICIENT DATA")
    assert engine.get_tsb_status() == {"tsb_value": None, "status": "INSUFFICIENT DATA"}
    assert engine.get_latest_tsb() == 0.0


@pytest.mark.unit
def test_numeric_outputs_are_always_finite() -> None:
    engine = _build_engine_with_history([100.0, 250.0, 75.0, 410.0, 90.0, 320.0, 180.0])

    ctl = engine.calculate_ctl()
    atl = engine.calculate_atl()
    tsb, _ = engine.calculate_tsb()

    assert ctl is not None and math.isfinite(ctl)
    assert atl is not None and math.isfinite(atl)
    assert tsb is not None and math.isfinite(tsb)


@pytest.mark.unit
def test_ctl_atl_tsb_stay_within_plausible_bounds_for_non_negative_loads() -> None:
    loads = [0.0, 40.0, 65.0, 120.0, 90.0, 150.0, 200.0, 170.0, 80.0, 60.0]
    engine = _build_engine_with_history(loads)

    ctl = engine.calculate_ctl()
    atl = engine.calculate_atl()
    tsb, _ = engine.calculate_tsb()

    assert ctl is not None and 0.0 <= ctl <= max(loads)
    assert atl is not None and 0.0 <= atl <= max(loads)
    assert tsb is not None and -max(loads) <= tsb <= max(loads)


@pytest.mark.unit
def test_identical_input_series_produce_identical_outputs() -> None:
    loads = [35.0, 55.0, 70.0, 45.0, 90.0, 30.0, 75.0, 65.0]
    engine_a = _build_engine_with_history(loads)
    engine_b = _build_engine_with_history(loads)

    assert engine_a.calculate_ctl() == engine_b.calculate_ctl()
    assert engine_a.calculate_atl() == engine_b.calculate_atl()
    assert engine_a.calculate_tsb() == engine_b.calculate_tsb()
    assert engine_a.get_tsb_status() == engine_b.get_tsb_status()


@pytest.mark.unit
def test_very_high_and_very_low_load_sequences_remain_finite_and_stable() -> None:
    high_load_engine = _build_engine_with_history([100.0] * 30 + [5000.0] * 5)
    low_load_engine = _build_engine_with_history([0.0] * 35)

    high_tsb, _ = high_load_engine.calculate_tsb()
    low_tsb, _ = low_load_engine.calculate_tsb()

    assert high_tsb is not None and math.isfinite(high_tsb)
    assert low_tsb is not None and math.isfinite(low_tsb)
    assert high_tsb < 0.0
    assert low_tsb == 0.0


@pytest.mark.unit
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


@pytest.mark.unit
def test_predict_race_day_tsb_returns_none_for_invalid_inputs() -> None:
    engine = TSBEngine()

    assert engine.predict_race_day_tsb(days=1, loads=[]) is None
    assert engine.predict_race_day_tsb(days=3, loads=[10.0, 20.0]) is None


@pytest.mark.unit
def test_predict_race_day_tsb_uses_current_internal_ctl_atl_state() -> None:
    engine = TSBEngine()
    engine.ctl = 50.0
    engine.atl = 40.0

    predicted = engine.predict_race_day_tsb(days=3, loads=[100.0, 50.0, 0.0, 999.0])

    temp_ctl = 50.0
    temp_atl = 40.0
    for load in [100.0, 50.0, 0.0]:
        temp_atl += (load - temp_atl) / 7
        temp_ctl += (load - temp_ctl) / 42
    expected = round(temp_ctl - temp_atl, 1)

    assert predicted == expected


@pytest.mark.unit
def test_predict_race_day_tsb_with_zero_days_returns_current_form_delta() -> None:
    engine = TSBEngine()
    engine.ctl = 37.26
    engine.atl = 42.81

    assert engine.predict_race_day_tsb(days=0, loads=[300.0]) == -5.6


# ── SV-08 / D-051: TrainingPeaks form over every calendar day ────────────────


def _kernel(loads: list[tuple[str, float]], end: date) -> tuple[float, float, float]:
    return tsb_engine.compute_ctl_atl_tsb(loads, reference_date=end)


@pytest.mark.unit
def test_one_session_follows_the_trainingpeaks_formula() -> None:
    """CTL += (load - CTL) / 42 and ATL += (load - ATL) / 7, from 0 (TrainingPeaks)."""
    assert _kernel([("2026-03-01", 100.0)], date(2026, 3, 1)) == (2.4, 14.3, -11.9)


@pytest.mark.unit
def test_rest_days_count_as_zero_load() -> None:
    """A gap in the log is a rest day: it lowers CTL and ATL like an explicit 0."""
    end = date(2026, 3, 4)
    sparse = [("2026-03-01", 100.0), ("2026-03-04", 100.0)]
    explicit = [("2026-03-01", 100.0), ("2026-03-02", 0.0), ("2026-03-03", 0.0), ("2026-03-04", 100.0)]
    back_to_back = [("2026-03-03", 100.0), ("2026-03-04", 100.0)]
    assert _kernel(sparse, end) == _kernel(explicit, end)
    assert _kernel(sparse, end) != _kernel(back_to_back, end)


@pytest.mark.unit
def test_days_after_the_last_session_decay_up_to_the_reference_date() -> None:
    loads = [("2026-03-01", 100.0)]
    same_day = _kernel(loads, date(2026, 3, 1))
    week_later = _kernel(loads, date(2026, 3, 8))
    assert week_later[0] < same_day[0] and week_later[1] < same_day[1]
    assert week_later[2] > same_day[2]  # ATL falls faster, so form rises


@pytest.mark.unit
def test_two_sessions_on_one_day_add_up() -> None:
    end = date(2026, 3, 1)
    assert _kernel([("2026-03-01", 60.0), ("2026-03-01", 40.0)], end) == _kernel([("2026-03-01", 100.0)], end)


@pytest.mark.unit
def test_steady_athlete_does_not_jump_overnight() -> None:
    """SV-08: steady_m went from TSB 16.0 to 59.5 in one day. Daily steps stay small."""
    week = [60.0, 0.0, 70.0, 50.0, 0.0, 60.0, 120.0]
    start = date(2026, 1, 1)
    loads = [((start + timedelta(days=i)).isoformat(), week[i % 7]) for i in range(84)]
    tsbs = [_kernel(loads, start + timedelta(days=d))[2] for d in range(42, 84)]
    assert max(abs(b - a) for a, b in zip(tsbs, tsbs[1:], strict=False)) < 20
