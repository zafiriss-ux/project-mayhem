"""
Hydration calculation tests — weight-based formula.

Guards the hydration fix: 35 ml/kg/day baseline + session-type adjustment,
rounded to nearest 100 ml. Regression guard against the old ~1000 ml bug.
"""

from unittest.mock import MagicMock

import pytest

from titan.features.nutrition_optimizer import NutritionOptimizer


def _make_optimizer() -> NutritionOptimizer:
    db = MagicMock()
    db.get_recent_weight_data.return_value = []
    return NutritionOptimizer(db)


class TestHydrationValues:
    @pytest.mark.unit
    def test_hydration_baseline_75kg_easy(self):
        """75 kg + EASY: 75*35=2625 base + 300 adj = 2925 → rounded to 2900."""
        optimizer = _make_optimizer()
        hydration = optimizer._calculate_hydration(weight_kg=75.0, session_type="EASY")
        assert 2900 <= hydration <= 3000, (
            f"Expected 2900–3000 ml for 75 kg EASY, got {hydration}"
        )

    @pytest.mark.unit
    def test_hydration_baseline_75kg_long_run(self):
        """75 kg + LONG_RUN: 75*35=2625 base + 800 adj = 3425 → rounded to 3400."""
        optimizer = _make_optimizer()
        hydration = optimizer._calculate_hydration(weight_kg=75.0, session_type="LONG_RUN")
        assert 3300 <= hydration <= 3500, (
            f"Expected 3300–3500 ml for 75 kg LONG_RUN, got {hydration}"
        )

    @pytest.mark.unit
    def test_hydration_not_1000ml(self):
        """Regression: any realistic input must produce > 1500 ml (not the old 1000 ml bug)."""
        optimizer = _make_optimizer()
        for session_type in ("EASY", "TEMPO", "INTERVALS", "LONG_RUN", "REST"):
            hydration = optimizer._calculate_hydration(weight_kg=60.0, session_type=session_type)
            assert hydration > 1500, (
                f"hydration_ml={hydration} for 60 kg {session_type} — must be > 1500 ml"
            )
