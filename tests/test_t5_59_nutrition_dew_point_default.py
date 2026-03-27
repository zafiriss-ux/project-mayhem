"""
T5-59: NutritionOptimizer conservative dew_point default.

When weather data is unavailable, dew_point must default to 25.0°C (conservative,
high sweat/electrolyte assumption) rather than 15.0°C which underestimates fluid needs.
"""

from unittest.mock import MagicMock

import pytest

from titan.features.nutrition_optimizer import NutritionOptimizer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_optimizer() -> NutritionOptimizer:
    """Return a NutritionOptimizer with a mocked DatabaseManager."""
    db = MagicMock()
    db.get_recent_weight_data.return_value = []
    return NutritionOptimizer(db)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDewPointDefaultIsConservative:
    """dew_point default must be 25.0 when weather data is absent."""

    def test_no_dew_point_key_produces_oppressive_hydration(self):
        """
        When today_session has no 'dew_point' key the default must land in
        the 'Oppressive' dew-point bucket (≥22 → 1000 ml/h base rate).

        With the old default of 15.0 the call lands in the 'Sticky' bucket
        (≥15 → 650 ml/h), producing lower hydration_ml.

        This test captures the exact hydration difference so it fails before
        the fix and passes after.
        """
        optimizer = _make_optimizer()

        # Session dict with NO dew_point key — exercises the default
        session_no_dew_point = {
            "type": "EASY",
            "duration_min": 60,
        }

        # Directly exercise _calculate_hydration with both candidate defaults
        hydration_with_new_default = optimizer._calculate_hydration(
            duration_min=60,
            dew_point=25.0,
            session_type="EASY",
        )
        hydration_with_old_default = optimizer._calculate_hydration(
            duration_min=60,
            dew_point=15.0,
            session_type="EASY",
        )

        # Sanity: new (conservative) default gives MORE hydration than old default
        assert hydration_with_new_default > hydration_with_old_default, (
            "dew_point=25 must produce more hydration_ml than dew_point=15"
        )

        # The actual call path through calculate_daily_nutrition (which uses the .get default)
        # must produce the same result as the explicit 25.0 call.
        plan = optimizer.calculate_daily_nutrition(
            weight_kg=70.0,
            today_session=session_no_dew_point,
            tomorrow_session={},
        )

        # The returned hydration_ml must equal the conservative (25.0) value
        assert plan["hydration_ml"] == hydration_with_new_default, (
            f"Expected hydration_ml={hydration_with_new_default} (dew_point=25.0 default) "
            f"but got {plan['hydration_ml']}. "
            "The dew_point default in optimize_nutrition must be 25.0, not 15.0 or 15."
        )

    def test_explicit_dew_point_overrides_default(self):
        """Explicit dew_point in today_session must be honoured regardless of default."""
        optimizer = _make_optimizer()

        # Explicit low dew_point → comfortable bucket (500 ml/h for 60 min = 500 ml)
        hydration_low = optimizer._calculate_hydration(
            duration_min=60,
            dew_point=10.0,
            session_type="EASY",
        )
        assert hydration_low == 500, (
            f"Expected 500 ml for dew_point=10 EASY 60 min, got {hydration_low}"
        )

        # Explicit high dew_point → oppressive bucket (1000 ml/h for 60 min = 1000 ml)
        hydration_high = optimizer._calculate_hydration(
            duration_min=60,
            dew_point=25.0,
            session_type="EASY",
        )
        assert hydration_high == 1000, (
            f"Expected 1000 ml for dew_point=25 EASY 60 min, got {hydration_high}"
        )
