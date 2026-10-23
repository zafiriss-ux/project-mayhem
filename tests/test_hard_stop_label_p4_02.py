"""P4-02 (ADR-0069 §6): HARD_STOP_SAFETY_GATES only when an H1-H5 gate really triggers.

When data are only missing, the day keeps the DATA_MISSING_* lock code alone. The session,
the ceiling and the volume do not change; only the label (message and calibration) does. No
lock code is added (ADR-0024). Synthetic data only.
"""

from __future__ import annotations

import pytest

from titan.science.governance_engine import GovernanceEngine


def _context(**changes) -> dict:
    base = {
        "today_hrv": 60.0,
        "baseline_hrv": 60.0,
        "hrv_std_dev": 5.0,
        "today_rhr": 50,
        "baseline_rhr": 50.0,
        "tsb_value": 0.0,
        "subjective_fatigue_score": 2,
        "subjective_fatigue_measured": True,
        "injury_flag": False,
        "sleep_score": 80,
        "readiness_score": 75.0,
        "acwr": 1.1,
        "glycogen_debt": 2.0,
        "days_since_last_vo2": 3,
        "fueling_confirmed": True,
    }
    base.update(changes)
    return base


def _apply(context: dict, session: str = "TEMPO") -> dict:
    return GovernanceEngine().apply_constraints({"session_type": session, "max_zone": 4}, context)


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"baseline_hrv": None}, "DATA_MISSING_CONSERVATIVE_H2"),
        ({"today_rhr": None}, "DATA_MISSING_CONSERVATIVE_H3"),
        ({"tsb_value": None}, "DATA_MISSING_CONSERVATIVE_H4"),
    ],
)
def test_missing_data_alone_is_not_a_hard_stop(changes, code):
    result = _apply(_context(**changes))
    locks = result["governance_locks_applied"]
    assert code in locks
    assert "HARD_STOP_SAFETY_GATES" not in locks
    assert result["session_type"] == "EASY"


@pytest.mark.parametrize(
    "changes",
    [
        {"injury_flag": True},
        {"today_hrv": 30.0},
        {"today_rhr": 70},
        {"tsb_value": -60.0},
        {"subjective_fatigue_score": 9},
    ],
)
def test_a_real_gate_keeps_the_hard_stop_label(changes):
    assert "HARD_STOP_SAFETY_GATES" in _apply(_context(**changes))["governance_locks_applied"]


def test_a_real_gate_with_missing_data_carries_both():
    locks = _apply(_context(injury_flag=True, baseline_hrv=None))["governance_locks_applied"]
    assert "HARD_STOP_SAFETY_GATES" in locks
    assert "DATA_MISSING_CONSERVATIVE_H2" in locks


def test_the_missing_data_reasons_are_still_recorded():
    result = _apply(_context(baseline_hrv=None))
    assert [r["gate"] for r in result["hard_stop_reasons"]] == ["H2_MISSING"]
