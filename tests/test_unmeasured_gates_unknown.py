"""OW-F3 (ADR-0069 §3): a gate whose input was not measured is UNKNOWN, not CLEAR.

No source sends an injury flag yet (``/injury`` comes with schema v34), so H1 cannot pass:
it is UNKNOWN. The same holds for H2-H5 when their input is missing, and for H5 when the
fatigue is the D-043 default 3 and not the athlete's entry. Only the wording changes: no
decision moves. Synthetic data only.
"""

from __future__ import annotations

import pytest

from tests.test_daily_coach_characterization import (  # noqa: F401  (world is a fixture)
    _run_scenario,
    normal_day,
    world,
)
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
        "injury_flag": False,
        "sleep_score": 80,
        "readiness_score": 75.0,
        "acwr": 1.1,
        "glycogen_debt": 2.0,
        "days_since_last_vo2": 3,
        "fueling_confirmed": True,
    }
    base.update(changes)
    return {k: v for k, v in base.items() if v is not ...}


def _findings(context: dict) -> tuple[dict, dict]:
    result = GovernanceEngine().apply_constraints({"session_type": "EASY", "max_zone": 2}, context)
    rationale = result["decision_rationale"]
    return {f["gate"]: f["status"] for f in rationale["gate_findings"]}, rationale


@pytest.mark.parametrize(
    ("flag", "status"), [(..., "UNKNOWN"), (None, "UNKNOWN"), (False, "CLEAR"), (True, "TRIGGERED")]
)
def test_h1_is_unknown_without_an_injury_source(flag, status):
    statuses, _ = _findings(_context(injury_flag=flag))
    assert statuses["H1"] == status


@pytest.mark.parametrize(
    ("changes", "gate"),
    [
        ({"today_hrv": None}, "H2"),
        ({"baseline_hrv": None}, "H2"),
        ({"today_rhr": None}, "H3"),
        ({"tsb_value": None}, "H4"),
        ({"subjective_fatigue_score": ...}, "H5"),
        ({"subjective_fatigue_measured": False}, "H5"),
    ],
)
def test_a_gate_without_its_input_is_unknown(changes, gate):
    statuses, _ = _findings(_context(**changes))
    assert statuses[gate] == "UNKNOWN"


def test_a_measured_fatigue_stays_clear_or_triggered():
    assert _findings(_context(subjective_fatigue_measured=True))[0]["H5"] == "CLEAR"
    assert _findings(_context(subjective_fatigue_score=9, subjective_fatigue_measured=True))[0]["H5"] == "TRIGGERED"


def test_no_lock_names_the_gates_that_were_not_measured():
    _, rationale = _findings(_context(injury_flag=None, subjective_fatigue_measured=False))
    assert rationale["primary_reason"] == (
        "No governance lock triggered: training proceeds as planned. Not measured: H1, H5."
    )


def test_all_measured_keeps_the_old_wording():
    _, rationale = _findings(_context(subjective_fatigue_measured=True))
    assert rationale["primary_reason"] == "No governance lock triggered: training proceeds as planned."


def test_the_morning_sends_h1_and_the_default_fatigue_as_not_measured(world, monkeypatch):
    seen: list[dict] = []
    original = GovernanceEngine._build_decision_rationale

    def spy(self, context, session_plan, applied_locks):
        rationale = original(self, context, session_plan, applied_locks)
        seen.append({f.gate: f.status for f in rationale.gate_findings})
        return rationale

    monkeypatch.setattr(GovernanceEngine, "_build_decision_rationale", spy)
    _run_scenario(world, [normal_day(0)])
    assert seen, "the morning built no rationale"
    assert seen[-1]["H1"] == "UNKNOWN"
    assert seen[-1]["H5"] == "UNKNOWN"


def test_the_athletes_fatigue_entry_counts_as_measured(world, monkeypatch):
    seen: list[dict] = []
    original = GovernanceEngine._build_decision_rationale

    def spy(self, context, session_plan, applied_locks):
        rationale = original(self, context, session_plan, applied_locks)
        seen.append({f.gate: f.status for f in rationale.gate_findings})
        return rationale

    monkeypatch.setattr(GovernanceEngine, "_build_decision_rationale", spy)
    _run_scenario(world, [normal_day(0)], soreness=4)
    assert seen and seen[-1]["H5"] == "CLEAR"
