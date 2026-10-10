"""
SV-03: a RED intensity gate must not turn a planned REST day into EASY.

RED forces EASY so that a hard session is replaced by an easy one. On a REST
day there is nothing to make easier, and overriding it produced "EASY 0 km"
(synthetic-athlete report, SV-03).
"""

import pytest

from titan.config.thresholds import INTENSITY_GOVERNOR_DRIFT_RED
from titan.science.intensity_governor import IntensityGovernor


@pytest.mark.unit
@pytest.mark.parametrize("planned", ["REST", "rest"])
def test_red_gate_leaves_a_rest_day_as_rest(planned: str) -> None:
    result = IntensityGovernor().evaluate(
        {"drift_pct": INTENSITY_GOVERNOR_DRIFT_RED + 1.0, "planned_session": planned}
    )
    assert result.color == "RED"
    assert result.volume_modifier == 0.7  # ADR-0062; a REST day has no volume to scale
    assert result.session_override is None
    assert result.audit["applied_constraints"]["session_override"] is None


@pytest.mark.unit
def test_red_gate_still_forces_easy_on_a_training_day() -> None:
    result = IntensityGovernor().evaluate(
        {"drift_pct": INTENSITY_GOVERNOR_DRIFT_RED + 1.0, "planned_session": "LONG_RUN"}
    )
    assert result.session_override == "EASY"
