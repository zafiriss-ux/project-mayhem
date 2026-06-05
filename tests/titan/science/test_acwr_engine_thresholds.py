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
