"""Tests for NutritionPreferences personalization layer (ADR-0056)."""
import pytest

from titan.features.nutrition_optimizer import NutritionOptimizer, NutritionPreferences


class _GModel:
    def get_current_glycogen(self):
        return 100.0


def _make_opt():
    return NutritionOptimizer(_GModel())


BASE_SESSION = {"session_type": "EASY", "duration_min": 60}
LONG_RUN_SESSION = {"session_type": "LONG_RUN", "duration_min": 120, "distance_km": 20}
INTERVALS_SESSION = {"session_type": "INTERVALS", "duration_min": 60}


def test_default_prefs_none_unchanged():
    opt = _make_opt()
    result = opt.calculate_daily_nutrition(
        weight_kg=75.0, today_session=BASE_SESSION, prefs=None
    )
    assert "total_calories" in result
    assert "carbs_g" in result
    assert "protein_g" in result
    assert "fat_g" in result
    assert "hydration_ml" in result
    assert result.get("meal_schedule") == []


def test_female_base_calories_reduced():
    opt = _make_opt()
    male_plan = opt.calculate_daily_nutrition(
        weight_kg=75.0,
        today_session=BASE_SESSION,
        prefs=NutritionPreferences(biological_sex='male'),
    )
    female_plan = opt.calculate_daily_nutrition(
        weight_kg=75.0,
        today_session=BASE_SESSION,
        prefs=NutritionPreferences(biological_sex='female'),
    )
    ratio = female_plan["total_calories"] / male_plan["total_calories"]
    assert abs(ratio - 0.87) < 0.01, f"Expected ~0.87, got {ratio:.4f}"


def test_female_luteal_adds_200kcal():
    opt = _make_opt()
    follicular = opt.calculate_daily_nutrition(
        weight_kg=75.0,
        today_session=BASE_SESSION,
        prefs=NutritionPreferences(biological_sex='female', menstrual_phase='follicular'),
    )
    luteal = opt.calculate_daily_nutrition(
        weight_kg=75.0,
        today_session=BASE_SESSION,
        prefs=NutritionPreferences(biological_sex='female', menstrual_phase='luteal'),
    )
    diff = luteal["total_calories"] - follicular["total_calories"]
    assert abs(diff - 200) < 1, f"Expected 200 kcal diff, got {diff}"


def test_low_carb_ignored_on_long_run():
    opt = _make_opt()
    standard = opt.calculate_daily_nutrition(
        weight_kg=75.0,
        today_session=LONG_RUN_SESSION,
        prefs=NutritionPreferences(dietary_style='standard'),
    )
    low_carb = opt.calculate_daily_nutrition(
        weight_kg=75.0,
        today_session=LONG_RUN_SESSION,
        prefs=NutritionPreferences(dietary_style='low_carb'),
    )
    assert abs(low_carb["carbs_g"] - standard["carbs_g"]) < 5, (
        f"low_carb reduced carbs on LONG_RUN: standard={standard['carbs_g']}, low_carb={low_carb['carbs_g']}"
    )
    assert any("Υδατάνθρακες" in n for n in low_carb["special_notes"])


def test_low_carb_applied_on_easy():
    opt = _make_opt()
    plan = opt.calculate_daily_nutrition(
        weight_kg=75.0,
        today_session=BASE_SESSION,
        prefs=NutritionPreferences(dietary_style='low_carb'),
    )
    carb_pct = (plan["carbs_g"] * 4) / plan["total_calories"]
    assert abs(carb_pct - 0.35) < 0.02, f"Expected ~35% carbs, got {carb_pct:.2%}"


def test_fasted_easy_no_preworkout_meal():
    opt = _make_opt()
    plan = opt.calculate_daily_nutrition(
        weight_kg=75.0,
        today_session=BASE_SESSION,
        prefs=NutritionPreferences(fasted_training='easy_only', training_time='morning'),
    )
    labels = [m['label'] for m in plan.get('meal_schedule', [])]
    assert not any('ΠΡΟ-ΠΡΟΠΟΝΗΤΙΚΟ' in lbl for lbl in labels), (
        f"Should have no pre-workout for EASY with easy_only fasted, got: {labels}"
    )


def test_fasted_never_has_preworkout():
    opt = _make_opt()
    plan = opt.calculate_daily_nutrition(
        weight_kg=75.0,
        today_session=BASE_SESSION,
        prefs=NutritionPreferences(fasted_training='never', training_time='morning'),
    )
    labels = [m['label'] for m in plan.get('meal_schedule', [])]
    assert any('ΠΡΟ-ΠΡΟΠΟΝΗΤΙΚΟ' in lbl for lbl in labels), (
        f"Should have pre-workout with fasted=never, got: {labels}"
    )


def test_evening_training_schedule():
    opt = _make_opt()
    plan = opt.calculate_daily_nutrition(
        weight_kg=75.0,
        today_session=BASE_SESSION,
        prefs=NutritionPreferences(training_time='evening', fasted_training='never'),
    )
    schedule = plan.get('meal_schedule', [])
    times = [m['time'] for m in schedule]
    assert '15:30' in times, f"Expected 15:30 pre-workout, got: {times}"
    assert any('19:' in t for t in times), f"Expected post-workout ~19:xx, got: {times}"


def test_nutrition_prefs_db_roundtrip(tmp_path):
    from titan.core.database import DatabaseManager
    db = DatabaseManager(db_dir=tmp_path)
    test_prefs = {
        'training_time': 'evening',
        'fasted_training': 'never',
        'dietary_style': 'mediterranean',
        'meal_frequency': 5,
        'biological_sex': 'female',
        'menstrual_tracking': 'yes',
    }
    db.save_nutrition_preferences("owner", test_prefs)
    result = db.get_nutrition_preferences("owner")
    assert result is not None
    for key, value in test_prefs.items():
        assert result[key] == value, f"Mismatch on {key}: expected {value}, got {result[key]}"


def test_vegetarian_note_in_output():
    opt = _make_opt()
    plan = opt.calculate_daily_nutrition(
        weight_kg=75.0,
        today_session=BASE_SESSION,
        prefs=NutritionPreferences(dietary_style='vegetarian'),
    )
    notes_text = ' '.join(plan.get('special_notes', []))
    assert 'φυτικές πηγές' in notes_text, f"Expected vegetarian note, got: {plan['special_notes']}"
