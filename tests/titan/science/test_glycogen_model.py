import math

from titan.science.glycogen_model import GlycogenDebtAccumulator, GlycogenEngine, GlycogenModel


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


def test_estimate_glycogen_depletion_covers_intensity_bands() -> None:
    high = GlycogenModel.estimate_glycogen_depletion(duration_min=60.0, intensity_pct_vo2max=90.0)
    moderate_high = GlycogenModel.estimate_glycogen_depletion(duration_min=60.0, intensity_pct_vo2max=80.0)
    moderate = GlycogenModel.estimate_glycogen_depletion(duration_min=60.0, intensity_pct_vo2max=70.0)
    easy = GlycogenModel.estimate_glycogen_depletion(duration_min=60.0, intensity_pct_vo2max=60.0)

    assert high["intensity_classification"] == "HIGH (intervals/race)"
    assert high["depletion_rate"] == 2.5
    assert moderate_high["intensity_classification"] == "MODERATE-HIGH (tempo)"
    assert moderate_high["depletion_rate"] == 1.8
    assert moderate["intensity_classification"] == "MODERATE (steady)"
    assert moderate["depletion_rate"] == 1.2
    assert easy["intensity_classification"] == "EASY (fat burning)"
    assert easy["depletion_rate"] == 0.8


def test_daily_carb_recommendation_handles_named_and_default_loads() -> None:
    very_high = GlycogenModel.daily_carb_recommendation(weight_kg=70.0, training_load="VERY_HIGH")
    defaulted = GlycogenModel.daily_carb_recommendation(weight_kg=70.0, training_load="UNKNOWN")

    assert very_high["carbs_g_per_kg_low"] == 8
    assert very_high["carbs_g_per_kg_high"] == 12
    assert very_high["total_carbs_range"] == "560-840g"
    assert very_high["context"] == "Heavy blocks"
    assert defaulted["carbs_g_per_kg_low"] == 5
    assert defaulted["carbs_g_per_kg_high"] == 7
    assert defaulted["total_carbs_range"] == "350-490g"
    assert defaulted["context"] == "Moderate"


def test_glycogen_flag_paths_for_low_carb_quality_and_ok() -> None:
    low_carb = GlycogenEngine.glycogen_flag(low_carb_day=True, back_to_back_quality=False, weight=70.0)
    quality = GlycogenEngine.glycogen_flag(low_carb_day=False, back_to_back_quality=True, weight=70.0)
    ok = GlycogenEngine.glycogen_flag(low_carb_day=False, back_to_back_quality=False, weight=70.0)

    assert low_carb == (False, None, ["LOW_GLYCOGEN: Hammer forbidden today"])
    assert quality == (True, 490, ["BACK-TO-BACK QUALITY: Carbs ≥ 490g required"])
    assert ok == (True, None, ["GLYCOGEN OK: Normal fueling rules"])


def test_status_reports_moderate_band() -> None:
    accumulator = GlycogenDebtAccumulator()
    accumulator.daily_debt = 5.0

    assert accumulator.status == "MODERATE"
