from titan.features.nutrition_optimizer import NutritionOptimizer


class _StubGlycogenModel:
    pass


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
