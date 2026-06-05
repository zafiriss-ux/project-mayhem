"""
T5-59: NutritionOptimizer hydration baseline is weight-based, not dew-point-based.

The hydration calculation uses 35 ml/kg/day baseline + session-type adjustment,
producing physiologically correct values for endurance runners (>2500 ml for 75 kg).
The old dew-point-only formula produced 1000 ml for a 60-min session, which was
insufficient as a daily hydration target.
"""

from unittest.mock import MagicMock

import pytest

from titan.features.nutrition_optimizer import NutritionOptimizer


def _make_optimizer() -> NutritionOptimizer:
    """Return a NutritionOptimizer with a mocked DatabaseManager."""
    db = MagicMock()
    db.get_recent_weight_data.return_value = []
    return NutritionOptimizer(db)


class TestHydrationIsWeightBased:
    """Hydration must use weight-based formula, not the old dew-point-only formula."""

    @pytest.mark.unit
    def test_hydration_scales_with_weight(self):
        """Heavier athlete gets more hydration."""
        optimizer = _make_optimizer()
        light = optimizer._calculate_hydration(weight_kg=60.0, session_type="EASY")
        heavy = optimizer._calculate_hydration(weight_kg=90.0, session_type="EASY")
        assert heavy > light, "Heavier athlete must have higher daily hydration target"

    @pytest.mark.unit
    def test_hydration_scales_with_session_intensity(self):
        """Long run adds more hydration than easy run for same weight."""
        optimizer = _make_optimizer()
        easy = optimizer._calculate_hydration(weight_kg=75.0, session_type="EASY")
        long_run = optimizer._calculate_hydration(weight_kg=75.0, session_type="LONG_RUN")
        assert long_run > easy, "LONG_RUN must require more hydration than EASY"

    @pytest.mark.unit
    def test_hydration_not_old_1000ml_bug(self):
        """Regression guard: daily hydration must be well above 1000 ml for a 75 kg athlete."""
        optimizer = _make_optimizer()
        hydration = optimizer._calculate_hydration(weight_kg=75.0, session_type="EASY")
        assert hydration > 1500, (
            f"hydration_ml={hydration} — must be > 1500 ml for a 75 kg athlete; "
            "the old dew-point formula produced ~1000 ml which is not a daily target"
        )

    @pytest.mark.unit
    def test_calculate_daily_nutrition_returns_weight_based_hydration(self):
        """calculate_daily_nutrition must forward weight_kg to the hydration calculation."""
        optimizer = _make_optimizer()
        plan = optimizer.calculate_daily_nutrition(
            weight_kg=75.0,
            today_session={"session_type": "EASY", "duration_min": 60},
            tomorrow_session={},
        )
        expected = optimizer._calculate_hydration(weight_kg=75.0, session_type="EASY")
        assert plan["hydration_ml"] == expected
