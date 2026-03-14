from titan.config.thresholds import (
    INTENSITY_GOVERNOR_ACWR_RED,
    INTENSITY_GOVERNOR_ACWR_YELLOW,
    INTENSITY_GOVERNOR_DRIFT_RED,
    INTENSITY_GOVERNOR_DRIFT_YELLOW,
    INTENSITY_GOVERNOR_GLYCOGEN_RED,
    INTENSITY_GOVERNOR_GLYCOGEN_YELLOW,
    INTENSITY_GOVERNOR_READINESS_RED,
    INTENSITY_GOVERNOR_READINESS_YELLOW,
)
from titan.science.intensity_governor import IntensityGovernor


def test_evaluate_uses_threshold_constants_in_audit_payload() -> None:
    governor = IntensityGovernor()

    result = governor.evaluate(
        {
            "drift_pct": 0.0,
            "glycogen_debt": 0.0,
            "acwr": 1.0,
            "readiness_score": 100.0,
        }
    )

    assert result.audit["drift"]["threshold_yellow"] == INTENSITY_GOVERNOR_DRIFT_YELLOW
    assert result.audit["drift"]["threshold_red"] == INTENSITY_GOVERNOR_DRIFT_RED
    assert (
        result.audit["glycogen_debt"]["threshold_yellow"]
        == INTENSITY_GOVERNOR_GLYCOGEN_YELLOW
    )
    assert (
        result.audit["glycogen_debt"]["threshold_red"]
        == INTENSITY_GOVERNOR_GLYCOGEN_RED
    )
    assert result.audit["acwr"]["threshold_yellow"] == INTENSITY_GOVERNOR_ACWR_YELLOW
    assert result.audit["acwr"]["threshold_red"] == INTENSITY_GOVERNOR_ACWR_RED
    assert (
        result.audit["readiness"]["threshold_yellow"]
        == INTENSITY_GOVERNOR_READINESS_YELLOW
    )
    assert result.audit["readiness"]["threshold_red"] == INTENSITY_GOVERNOR_READINESS_RED


def test_evaluate_applies_boundary_behaviour_from_threshold_constants() -> None:
    governor = IntensityGovernor()

    yellow = governor.evaluate(
        {
            "drift_pct": INTENSITY_GOVERNOR_DRIFT_YELLOW,
            "glycogen_debt": INTENSITY_GOVERNOR_GLYCOGEN_YELLOW,
            "acwr": INTENSITY_GOVERNOR_ACWR_YELLOW,
            "readiness_score": INTENSITY_GOVERNOR_READINESS_YELLOW,
        }
    )
    red = governor.evaluate(
        {
            "drift_pct": INTENSITY_GOVERNOR_DRIFT_RED + 0.1,
            "glycogen_debt": INTENSITY_GOVERNOR_GLYCOGEN_RED + 0.1,
            "acwr": INTENSITY_GOVERNOR_ACWR_RED + 0.01,
            "readiness_score": INTENSITY_GOVERNOR_READINESS_RED - 0.1,
        }
    )

    assert yellow.color == "YELLOW"
    assert red.color == "RED"
