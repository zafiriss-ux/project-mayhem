from datetime import date, timedelta

import pytest

from titan.config import thresholds
from titan.science.acwr_engine import ACWREngine


@pytest.mark.unit
def test_calculate_acwr_detraining_risk_branch_between_05_and_08() -> None:
    value, status, recommendation = ACWREngine.calculate_acwr(
        acute_7d=42.0,
        chronic_28d_avg=10.0,
    )

    assert value == 0.6
    assert status == "⚠️ DETRAINING RISK"
    assert recommendation == "Consider volume increase"


@pytest.mark.unit
def test_calculate_acwr_moderate_risk_branch_between_13_and_15() -> None:
    value, status, recommendation = ACWREngine.calculate_acwr(
        acute_7d=98.0,
        chronic_28d_avg=10.0,
    )

    assert value == 1.4
    assert status == "⚠️ MODERATE RISK"
    assert recommendation == "Monitor fatigue"


@pytest.mark.unit
def test_calculate_acwr_uses_threshold_boundaries_from_thresholds_module() -> None:
    chronic = 10.0

    severe_boundary = thresholds.ACWR_SEVERE_DETRAINING_MAX * chronic * 7
    detraining_boundary = thresholds.ACWR_DETRAINING_RISK_MAX * chronic * 7
    maintenance_boundary = thresholds.ACWR_MAINTENANCE_MAX * chronic * 7
    sweet_spot_boundary = thresholds.ACWR_SWEET_SPOT_MAX * chronic * 7
    moderate_boundary = thresholds.ACWR_MODERATE_RISK_MAX * chronic * 7

    assert ACWREngine.calculate_acwr(severe_boundary, chronic)[1] == "⚠️ DETRAINING RISK"
    assert ACWREngine.calculate_acwr(detraining_boundary, chronic)[1] == "➡️ MAINTENANCE"
    assert ACWREngine.calculate_acwr(maintenance_boundary, chronic)[1] == "➡️ MAINTENANCE"
    assert ACWREngine.calculate_acwr(sweet_spot_boundary, chronic)[1] == "✅ SWEET SPOT"
    assert ACWREngine.calculate_acwr(moderate_boundary, chronic)[1] == "⚠️ MODERATE RISK"


@pytest.mark.unit
def test_injury_risk_score_uses_high_risk_threshold_from_thresholds_module() -> None:
    score, label = ACWREngine.injury_risk_score(thresholds.ACWR_HIGH_RISK_MAX)

    assert score == 8
    assert label == "High (2-3x risk)"


# SV-01, D-044: the ACWR the morning routine uses, from stored daily loads.

def _loads(start: date, days: int, load: float = 50.0) -> list[tuple[str, float]]:
    return [((start + timedelta(days=i)).isoformat(), load) for i in range(days)]


def test_from_daily_loads_is_one_for_a_steady_load() -> None:
    today = date(2026, 3, 28)
    assert ACWREngine.from_daily_loads(_loads(today - timedelta(days=42), 42), today) == 1.0


def test_from_daily_loads_leaves_out_today() -> None:
    """The session being decided has not happened; a run already logged today is not acute load."""
    today = date(2026, 3, 28)
    rows = _loads(today - timedelta(days=42), 42) + [(today.isoformat(), 500.0)]
    assert ACWREngine.from_daily_loads(rows, today) == 1.0


def test_from_daily_loads_counts_missing_days_as_rest() -> None:
    today = date(2026, 3, 28)
    rows = _loads(today - timedelta(days=28), 21)  # nothing in the last 7 days
    assert ACWREngine.from_daily_loads(rows, today) == 0.0


def test_from_daily_loads_spike() -> None:
    today = date(2026, 3, 28)
    rows = _loads(today - timedelta(days=28), 21) + _loads(today - timedelta(days=7), 7, 150.0)
    # acute 1050; chronic (21*50 + 7*150) / 28 = 75 a day, 525 a week
    assert ACWREngine.from_daily_loads(rows, today) == 2.0


def test_from_daily_loads_without_a_full_chronic_window_is_none() -> None:
    today = date(2026, 3, 28)
    assert ACWREngine.from_daily_loads(_loads(today - timedelta(days=27), 27), today) is None
    assert ACWREngine.from_daily_loads([], today) is None
