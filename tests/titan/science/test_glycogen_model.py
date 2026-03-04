import math

from titan.science.glycogen_model import GlycogenDebtAccumulator


def test_empty_state_and_missing_like_inputs_are_safe() -> None:
    accumulator = GlycogenDebtAccumulator()

    assert accumulator.daily_debt == 0.0
    assert accumulator.status == "GOOD"
    assert accumulator.norwegian_protocol(weight_kg=70.0) is None
    assert accumulator.overnight_resynthesis(carb_availability="UNKNOWN") == 0.0
    assert accumulator.electrolyte_guard(dew_point_c=18.0, duration_min=60.0, session_type="EASY") is None


def test_identical_inputs_produce_identical_outputs() -> None:
    kwargs = {
        "date": "2026-03-04",
        "trimp": 95.0,
        "time_above_lt2_min": 18.0,
        "dprime_fraction": 0.4,
        "intra_carb_g": 40.0,
        "weight_kg": 70.0,
    }

    first = GlycogenDebtAccumulator()
    second = GlycogenDebtAccumulator()

    first_update = first.update(**kwargs)
    second_update = second.update(**kwargs)
    first_overnight = first.overnight_resynthesis(sleep_hours=8.0, carb_availability="MODERATE")
    second_overnight = second.overnight_resynthesis(sleep_hours=8.0, carb_availability="MODERATE")

    assert first_update == second_update
    assert first_overnight == second_overnight
    assert first.daily_debt == second.daily_debt
    assert first.debt_history == second.debt_history
    assert first.status == second.status


def test_numeric_outputs_are_finite_for_extreme_inputs() -> None:
    accumulator = GlycogenDebtAccumulator()

    debt = accumulator.update(
        date="2026-03-04",
        trimp=1_000_000.0,
        time_above_lt2_min=1_000_000.0,
        dprime_fraction=999.0,
        intra_carb_g=1_000_000.0,
        weight_kg=0.0,
    )
    recovered = accumulator.overnight_resynthesis(sleep_hours=1_000_000.0, carb_availability="HIGH")
    guard = accumulator.electrolyte_guard(dew_point_c=100.0, duration_min=1_000.0, session_type="RACE")

    assert math.isfinite(debt)
    assert math.isfinite(recovered)
    assert guard is not None
    assert math.isfinite(guard["sodium_mg"])
    assert math.isfinite(guard["fluid_ml_per_hr"])


def test_debt_state_stays_within_existing_bounds() -> None:
    accumulator = GlycogenDebtAccumulator()

    accumulator.update(
        date="2026-03-04",
        trimp=1_000_000.0,
        time_above_lt2_min=1_000_000.0,
        dprime_fraction=1.0,
        intra_carb_g=0.0,
        weight_kg=70.0,
    )
    assert 0.0 <= accumulator.daily_debt <= accumulator.MAX_DEBT

    accumulator.overnight_resynthesis(sleep_hours=1_000_000.0, carb_availability="HIGH")
    assert 0.0 <= accumulator.daily_debt <= accumulator.MAX_DEBT


def test_norwegian_protocol_trigger_threshold_and_bounds() -> None:
    accumulator = GlycogenDebtAccumulator()

    below = accumulator.update(
        date="2026-03-04",
        trimp=200.0,
        time_above_lt2_min=10.0,
        dprime_fraction=1.0,
        intra_carb_g=0.0,
        weight_kg=70.0,
    )
    assert below < 7.0
    assert accumulator.norwegian_protocol(weight_kg=70.0) is None

    at_or_above = accumulator.update(
        date="2026-03-05",
        trimp=200.0,
        time_above_lt2_min=20.0,
        dprime_fraction=1.0,
        intra_carb_g=0.0,
        weight_kg=70.0,
    )
    protocol = accumulator.norwegian_protocol(weight_kg=70.0)

    assert at_or_above >= 7.0
    assert protocol is not None
    assert protocol["triggered"] is True
    assert protocol["status"] == "CRITICAL"
    assert 0.0 <= protocol["debt_score"] <= accumulator.MAX_DEBT


def test_electrolyte_guard_threshold_behavior_is_stable() -> None:
    not_triggered = GlycogenDebtAccumulator.get_electrolyte_guard_status(
        dew_point_c=18.0,
        duration_min=60.0,
        session_type="TEMPO",
    )
    triggered = GlycogenDebtAccumulator.get_electrolyte_guard_status(
        dew_point_c=19.0,
        duration_min=61.0,
        session_type="TEMPO",
    )

    assert not_triggered is None
    assert triggered is not None
    assert triggered["triggered"] is True
    assert triggered["sodium_mg"] > 0
    assert triggered["fluid_ml_per_hr"] > 0
