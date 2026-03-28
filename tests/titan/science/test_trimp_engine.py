"""Tests for TRIMPEngine.calculate_edwards_trimp() — athlete_max_hr correctness.

Covers:
- Zone boundaries are calculated using athlete_max_hr, not session peak HR
- Boundary: session peak HR > athlete_max_hr does not produce zone > 5 or crash
- TRIMP impulse magnitude is consistent with correct zone assignment
- Invalid athlete_max_hr values are rejected gracefully
"""

import pytest

from titan.science.trimp_engine import TRIMPEngine


class TestEdwardsTRIMPZoneBoundaries:
    """Zone classification must use athlete_max_hr as the physiological ceiling."""

    def test_zone1_uses_athlete_max_hr(self):
        # avg_hr=110, athlete_max_hr=190 → 110/190*100 ≈ 57.9% → zone 1 (×1)
        trimp, zone = TRIMPEngine.calculate_edwards_trimp(
            duration_min=60, avg_hr=110, athlete_max_hr=190
        )
        assert zone == 1
        assert trimp == 60.0

    def test_zone2_uses_athlete_max_hr(self):
        # avg_hr=123, athlete_max_hr=190 → 64.7% → zone 2 (×2)
        trimp, zone = TRIMPEngine.calculate_edwards_trimp(
            duration_min=60, avg_hr=123, athlete_max_hr=190
        )
        assert zone == 2
        assert trimp == 120.0

    def test_zone3_uses_athlete_max_hr(self):
        # avg_hr=143, athlete_max_hr=190 → 75.3% → zone 3 (×3)
        trimp, zone = TRIMPEngine.calculate_edwards_trimp(
            duration_min=60, avg_hr=143, athlete_max_hr=190
        )
        assert zone == 3
        assert trimp == 180.0

    def test_zone4_uses_athlete_max_hr(self):
        # avg_hr=160, athlete_max_hr=190 → 84.2% → zone 4 (×4)
        trimp, zone = TRIMPEngine.calculate_edwards_trimp(
            duration_min=60, avg_hr=160, athlete_max_hr=190
        )
        assert zone == 4
        assert trimp == 240.0

    def test_zone5_uses_athlete_max_hr(self):
        # avg_hr=180, athlete_max_hr=190 → 94.7% → zone 5 (×5)
        trimp, zone = TRIMPEngine.calculate_edwards_trimp(
            duration_min=60, avg_hr=180, athlete_max_hr=190
        )
        assert zone == 5
        assert trimp == 300.0

    def test_zone_differs_when_session_peak_below_athlete_max_hr(self):
        """The bug this task fixes: using session_peak_hr instead of
        athlete_max_hr inflates the %HRmax and overestimates the zone.

        Example: avg_hr=130, session_peak_hr=145, athlete_max_hr=190.
          With session_peak as ceiling: 130/145*100 ≈ 89.7% → zone 4
          With athlete_max_hr:          130/190*100 ≈ 68.4% → zone 2

        The correct zone is 2.  The engine must produce zone 2 when
        athlete_max_hr=190 is supplied.
        """
        trimp, zone = TRIMPEngine.calculate_edwards_trimp(
            duration_min=45, avg_hr=130, athlete_max_hr=190
        )
        # 130/190*100 ≈ 68.4% → zone 2
        assert zone == 2
        assert trimp == 90.0  # 45 min × 2


class TestEdwardsTRIMPBoundaryConditions:
    """Edge and boundary conditions for athlete_max_hr."""

    def test_session_peak_above_athlete_max_hr_does_not_crash(self):
        # Session peak can exceed athlete_max_hr in noisy HR data; must not crash.
        # avg_hr=195, athlete_max_hr=190 → 102.6% → zone 5 (×5, capped by >= 90%)
        trimp, zone = TRIMPEngine.calculate_edwards_trimp(
            duration_min=30, avg_hr=195, athlete_max_hr=190
        )
        assert zone == 5
        assert trimp == 150.0

    def test_session_peak_above_athlete_max_hr_does_not_produce_zone_above_5(self):
        # Even extreme outlier avg_hr values must stay within zone 5.
        _, zone = TRIMPEngine.calculate_edwards_trimp(
            duration_min=10, avg_hr=250, athlete_max_hr=190
        )
        assert zone == 5

    def test_athlete_max_hr_zero_returns_none(self):
        trimp, zone = TRIMPEngine.calculate_edwards_trimp(
            duration_min=60, avg_hr=150, athlete_max_hr=0
        )
        assert trimp is None
        assert zone == 0

    def test_athlete_max_hr_below_100_returns_none(self):
        trimp, zone = TRIMPEngine.calculate_edwards_trimp(
            duration_min=60, avg_hr=80, athlete_max_hr=90
        )
        assert trimp is None
        assert zone == 0

    def test_athlete_max_hr_exactly_100_is_valid(self):
        # 100 bpm is the minimum physiologically accepted value.
        trimp, zone = TRIMPEngine.calculate_edwards_trimp(
            duration_min=30, avg_hr=95, athlete_max_hr=100
        )
        assert trimp is not None
        assert zone >= 1

    @pytest.mark.parametrize(
        "avg_hr,athlete_max_hr,expected_zone",
        [
            (59, 100, 1),   # < 60% → zone 1
            (60, 100, 2),   # exactly 60% → zone 2
            (70, 100, 3),   # exactly 70% → zone 3
            (80, 100, 4),   # exactly 80% → zone 4
            (90, 100, 5),   # exactly 90% → zone 5
            (100, 100, 5),  # exactly 100% → zone 5
        ],
    )
    def test_zone_boundary_transitions(self, avg_hr, athlete_max_hr, expected_zone):
        _, zone = TRIMPEngine.calculate_edwards_trimp(
            duration_min=60, avg_hr=avg_hr, athlete_max_hr=athlete_max_hr
        )
        assert zone == expected_zone


class TestEdwardsTRIMPImpulseMagnitude:
    """TRIMP impulse must equal duration_min × zone_multiplier."""

    @pytest.mark.parametrize(
        "duration_min,avg_hr,athlete_max_hr,expected_zone,expected_trimp",
        [
            (30, 110, 190, 1, 30.0),   # zone 1
            (45, 125, 190, 2, 90.0),   # zone 2
            (60, 145, 190, 3, 180.0),  # zone 3
            (20, 162, 190, 4, 80.0),   # zone 4
            (10, 182, 190, 5, 50.0),   # zone 5
        ],
    )
    def test_trimp_equals_duration_times_multiplier(
        self, duration_min, avg_hr, athlete_max_hr, expected_zone, expected_trimp
    ):
        trimp, zone = TRIMPEngine.calculate_edwards_trimp(
            duration_min=duration_min,
            avg_hr=avg_hr,
            athlete_max_hr=athlete_max_hr,
        )
        assert zone == expected_zone
        assert trimp == expected_trimp
