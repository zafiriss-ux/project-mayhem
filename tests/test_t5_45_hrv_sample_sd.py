"""T5-45: HRV baseline sample SD (N-1) per Plews et al.

Tests that calculate_baseline uses sample standard deviation (ddof=1 / divide by N-1)
rather than population standard deviation (divide by N).

For values [60.0, 70.0, 80.0]:
  mean = 70.0
  sum of squared deviations = (60-70)^2 + (70-70)^2 + (80-70)^2 = 100 + 0 + 100 = 200
  population SD (N)   = sqrt(200/3) ≈ 8.165
  sample SD   (N-1)   = sqrt(200/2) = sqrt(100) = 10.0
"""

import math

import pytest

from titan.science.hrv_engine import HRVGuidedEngine


class TestHRVBaselineSampleSD:
    """Verify that calculate_baseline returns sample SD (N-1), not population SD (N)."""

    def _engine_with_values(self, values: list[float], days: int = 7) -> HRVGuidedEngine:
        """Create an HRVGuidedEngine pre-loaded with the given HRV values."""
        engine = HRVGuidedEngine(baseline_days=days)
        for i, v in enumerate(values):
            engine.add_hrv_measurement(f"2026-01-{i + 1:02d}", v)
        return engine

    def test_sample_sd_three_values(self) -> None:
        """For [60, 70, 80] sample SD == 10.0, population SD ≈ 8.165."""
        engine = self._engine_with_values([60.0, 70.0, 80.0], days=3)
        baseline, std_dev = engine.calculate_baseline(days=3)

        assert baseline == pytest.approx(70.0)
        # Sample SD: sqrt(200 / (3-1)) = sqrt(100) = 10.0
        assert std_dev == pytest.approx(10.0), (
            f"Expected sample SD 10.0 (N-1) but got {std_dev:.4f}. "
            f"If ~8.165, population SD (N) is being used instead."
        )

    def test_sample_sd_two_values(self) -> None:
        """For [60, 80] sample SD == sqrt((400)/1) = 20.0."""
        engine = self._engine_with_values([60.0, 80.0], days=2)
        baseline, std_dev = engine.calculate_baseline(days=2)

        assert baseline == pytest.approx(70.0)
        # mean = 70, deviations^2: 100 + 100 = 200; sample variance = 200/1 = 200; SD = sqrt(200)
        assert std_dev == pytest.approx(math.sqrt(200))

    def test_single_value_returns_zero_sd(self) -> None:
        """Edge case: N=1 must not raise ZeroDivisionError; SD should be 0.0."""
        engine = HRVGuidedEngine(baseline_days=1)
        engine.add_hrv_measurement("2026-01-01", 65.0)
        result = engine.calculate_baseline(days=1)

        assert result is not None
        baseline, std_dev = result
        assert baseline == pytest.approx(65.0)
        assert std_dev == pytest.approx(0.0), (
            f"Single-value SD should be 0.0, got {std_dev}"
        )

    def test_population_sd_not_returned(self) -> None:
        """Explicit anti-regression: population SD value must NOT be returned."""
        engine = self._engine_with_values([60.0, 70.0, 80.0], days=3)
        _, std_dev = engine.calculate_baseline(days=3)

        population_sd = math.sqrt(200 / 3)  # ≈ 8.165
        assert std_dev != pytest.approx(population_sd, abs=1e-6), (
            "calculate_baseline returned population SD (N); expected sample SD (N-1)."
        )
