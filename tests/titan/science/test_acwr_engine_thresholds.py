from titan.science.acwr_engine import ACWREngine


def test_calculate_acwr_detraining_risk_branch_between_05_and_08() -> None:
    value, status, recommendation = ACWREngine.calculate_acwr(
        acute_7d=42.0,
        chronic_28d_avg=10.0,
    )

    assert value == 0.6
    assert status == "⚠️ DETRAINING RISK"
    assert recommendation == "Consider volume increase"


def test_calculate_acwr_moderate_risk_branch_between_13_and_15() -> None:
    value, status, recommendation = ACWREngine.calculate_acwr(
        acute_7d=98.0,
        chronic_28d_avg=10.0,
    )

    assert value == 1.4
    assert status == "⚠️ MODERATE RISK"
    assert recommendation == "Monitor fatigue"
