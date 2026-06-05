import pytest

from titan.features.nutrition_optimizer import NutritionOptimizer, NutritionPreferences


class _StubGlycogenModel:
    pass


@pytest.mark.unit
def test_analyze_weight_trend_happy_path_calculates_change_metrics():
    optimizer = NutritionOptimizer(glycogen_model=_StubGlycogenModel())
    optimizer.add_weight_entry("2026-03-01", 70.0)
    optimizer.add_weight_entry("2026-03-02", 70.1)
    optimizer.add_weight_entry("2026-03-03", 70.2)
    optimizer.add_weight_entry("2026-03-04", 70.3)
    optimizer.add_weight_entry("2026-03-05", 70.4)
    optimizer.add_weight_entry("2026-03-06", 70.5)
    optimizer.add_weight_entry("2026-03-07", 70.7)

    trend = optimizer.analyze_weight_trend(days=7)

    assert trend["first_weight"] == 70.0
    assert trend["current_weight"] == 70.7
    assert trend["change_kg"] == 0.7
    assert trend["change_pct"] == 1.0


@pytest.mark.unit
def test_analyze_weight_trend_returns_safe_outcome_when_first_weight_is_zero():
    optimizer = NutritionOptimizer(glycogen_model=_StubGlycogenModel())
    optimizer.add_weight_entry("2026-03-01", 0.0)
    optimizer.add_weight_entry("2026-03-02", 69.5)
    optimizer.add_weight_entry("2026-03-03", 69.4)
    optimizer.add_weight_entry("2026-03-04", 69.3)
    optimizer.add_weight_entry("2026-03-05", 69.2)
    optimizer.add_weight_entry("2026-03-06", 69.1)
    optimizer.add_weight_entry("2026-03-07", 69.0)

    trend = optimizer.analyze_weight_trend(days=7)

    assert trend == {
        "status": "INSUFFICIENT_DATA",
        "change_kg": 0,
        "change_pct": 0,
        "velocity": 0,
        "recommendation": "Need valid baseline weight data",
    }


@pytest.mark.unit
def test_analyze_weight_trend_returns_safe_outcome_when_first_weight_is_negative():
    optimizer = NutritionOptimizer(glycogen_model=_StubGlycogenModel())
    optimizer.add_weight_entry("2026-03-01", -1.0)
    optimizer.add_weight_entry("2026-03-02", 69.5)
    optimizer.add_weight_entry("2026-03-03", 69.4)
    optimizer.add_weight_entry("2026-03-04", 69.3)
    optimizer.add_weight_entry("2026-03-05", 69.2)
    optimizer.add_weight_entry("2026-03-06", 69.1)
    optimizer.add_weight_entry("2026-03-07", 69.0)

    trend = optimizer.analyze_weight_trend(days=7)

    assert trend == {
        "status": "INSUFFICIENT_DATA",
        "change_kg": 0,
        "change_pct": 0,
        "velocity": 0,
        "recommendation": "Need valid baseline weight data",
    }


@pytest.mark.unit
def test_add_weight_entry_happy_path_appends_weight_history():
    optimizer = NutritionOptimizer(glycogen_model=_StubGlycogenModel())

    optimizer.add_weight_entry("2026-03-08", 70.2)

    assert optimizer.weight_history == [("2026-03-08", 70.2)]


@pytest.mark.unit
def test_add_weight_entry_duplicate_date_boundary_keeps_both_entries():
    optimizer = NutritionOptimizer(glycogen_model=_StubGlycogenModel())

    optimizer.add_weight_entry("2026-03-08", 70.2)
    optimizer.add_weight_entry("2026-03-08", 70.0)

    assert optimizer.weight_history == [
        ("2026-03-08", 70.2),
        ("2026-03-08", 70.0),
    ]


@pytest.mark.unit
def test_add_weight_entry_empty_input_boundary_accepts_empty_date():
    optimizer = NutritionOptimizer(glycogen_model=_StubGlycogenModel())

    optimizer.add_weight_entry("", 0.0)

    assert optimizer.weight_history == [("", 0.0)]


@pytest.mark.unit
def test_calculate_daily_nutrition_happy_path_returns_expected_contract_keys():
    optimizer = NutritionOptimizer(glycogen_model=_StubGlycogenModel())
    for day in range(1, 8):
        optimizer.add_weight_entry(f"2026-03-0{day}", 70.0)

    plan = optimizer.calculate_daily_nutrition(
        weight_kg=70.0,
        today_session={"session_type": "TEMPO", "duration_min": 60, "dew_point": 18},
        tomorrow_session={"session_type": "INTERVALS"},
    )

    assert plan["total_calories"] == 2814.0
    assert plan["carbs_g"] == 490.0
    assert plan["carbs_range"] == "416-564g"
    assert plan["protein_g"] == 126.0
    assert plan["fat_g"] == 40
    assert plan["hydration_ml"] == 3000
    assert isinstance(plan["special_notes"], list)
    assert "⚡ High glycogen demand - ensure adequate carbs" in plan["special_notes"]


@pytest.mark.unit
def test_calculate_daily_nutrition_zero_weight_boundary_returns_safe_macro_floor():
    optimizer = NutritionOptimizer(glycogen_model=_StubGlycogenModel())

    plan = optimizer.calculate_daily_nutrition(
        weight_kg=0,
        today_session={"session_type": "REST", "duration_min": 0, "dew_point": 10},
    )

    assert plan["carbs_g"] == 0
    assert plan["protein_g"] == 0
    assert plan["fat_g"] == 127.0
    assert plan["hydration_ml"] == 0


@pytest.mark.unit
def test_calculate_daily_nutrition_extreme_macro_target_boundary_for_race_day():
    optimizer = NutritionOptimizer(glycogen_model=_StubGlycogenModel())

    plan = optimizer.calculate_daily_nutrition(
        weight_kg=120,
        today_session={"session_type": "RACE", "duration_min": 180, "dew_point": 22},
    )

    assert plan["carbs_g"] == 1320.0
    assert plan["carbs_range"] == "1122-1518g"
    assert plan["hydration_ml"] == 4700
    assert plan["fat_g"] == 40


@pytest.mark.unit
def test_calculate_daily_nutrition_hydration_scales_with_session_intensity():
    optimizer = NutritionOptimizer(glycogen_model=_StubGlycogenModel())

    easy = optimizer.calculate_daily_nutrition(
        weight_kg=70,
        today_session={"session_type": "EASY", "duration_min": 30},
    )
    hammer = optimizer.calculate_daily_nutrition(
        weight_kg=70,
        today_session={"session_type": "HAMMER", "duration_min": 30},
    )

    assert easy["hydration_ml"] == 2800
    assert hammer["hydration_ml"] == 3000


@pytest.mark.unit
def test_carb_range_reflects_dietary_style():
    optimizer = NutritionOptimizer(glycogen_model=_StubGlycogenModel())

    low_carb_prefs = NutritionPreferences(dietary_style="low_carb")
    low_carb_plan = optimizer.calculate_daily_nutrition(
        weight_kg=75,
        today_session={"session_type": "EASY", "duration_min": 45},
        prefs=low_carb_prefs,
    )
    # low_carb EASY: carb_g = tdee * 0.35 / 4 ≈ 224g — well below the Burke range of 375-525g
    lc_target = low_carb_plan["carbs_g"]
    lc_min, lc_max = (int(x.rstrip("g")) for x in low_carb_plan["carbs_range"].split("-"))
    assert lc_min == round(lc_target * 0.85)
    assert lc_max == round(lc_target * 1.15)
    assert lc_max < 375  # must not bleed into the old Burke range

    standard_plan = optimizer.calculate_daily_nutrition(
        weight_kg=75,
        today_session={"session_type": "EASY", "duration_min": 45},
    )
    st_target = standard_plan["carbs_g"]
    st_min, st_max = (int(x.rstrip("g")) for x in standard_plan["carbs_range"].split("-"))
    assert st_min == round(st_target * 0.85)
    assert st_max == round(st_target * 1.15)
