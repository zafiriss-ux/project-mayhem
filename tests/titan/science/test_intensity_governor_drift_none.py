"""
T5-54: drift_pct=None must be treated as unknown (absent from audit),
not as 0.0 (perfect efficiency).

When drift_pct is None, IntensityGovernor must:
  - exclude 'drift' from the audit dict entirely
  - not allow the absent drift signal to mask other RED/YELLOW signals
  - not inject a false GREEN contribution
"""

from titan.science.intensity_governor import IntensityGovernor


def test_drift_pct_none_excluded_from_audit() -> None:
    """drift_pct=None must not appear in audit — unknown ≠ 0.0."""
    governor = IntensityGovernor()
    result = governor.evaluate(
        {
            "drift_pct": None,
            "glycogen_debt": 0.0,
            "acwr": 1.0,
            "readiness_score": 100.0,
        }
    )
    assert "drift" not in result.audit


def test_drift_pct_none_does_not_mask_red_signal() -> None:
    """A RED glycogen signal must still fire when drift is unknown."""
    from titan.config.thresholds import INTENSITY_GOVERNOR_GLYCOGEN_RED

    governor = IntensityGovernor()
    result = governor.evaluate(
        {
            "drift_pct": None,
            "glycogen_debt": INTENSITY_GOVERNOR_GLYCOGEN_RED + 1.0,
            "acwr": 1.0,
            "readiness_score": 100.0,
        }
    )
    assert result.color == "RED"


def test_drift_pct_none_green_result_when_other_signals_green() -> None:
    """All GREEN signals + drift=None should produce a GREEN gate."""
    governor = IntensityGovernor()
    result = governor.evaluate(
        {
            "drift_pct": None,
            "glycogen_debt": 0.0,
            "acwr": 1.0,
            "readiness_score": 100.0,
        }
    )
    assert result.color == "GREEN"


def test_drift_pct_absent_key_excluded_from_audit() -> None:
    """When drift_pct key is entirely absent, drift stays out of audit (unchanged behaviour)."""
    governor = IntensityGovernor()
    result = governor.evaluate(
        {
            "glycogen_debt": 0.0,
            "acwr": 1.0,
            "readiness_score": 100.0,
        }
    )
    assert "drift" not in result.audit
