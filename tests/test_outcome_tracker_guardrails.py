import json
import logging

from titan.core.database import DatabaseManager
from titan.science.outcome_tracker import OutcomeTracker


def _apl_result() -> dict:
    return {
        "priority_vector": {"HARD_STOP_SAFETY_GATES": 1},
        "lock_thresholds": {"acwr_ceiling": 1.2},
    }


def _seed_decision(tracker: OutcomeTracker, date: str = "2026-03-01") -> None:
    tracker.record_decision(
        session_planned="VO2MAX",
        session_post_governance="EASY",
        locks_applied=["HARD_STOP_SAFETY_GATES"],
        governance_clean=False,
        phase="BUILD",
        vlg_color="YELLOW",
        apl_result=_apl_result(),
        acwr=1.1,
        tsb_value=-20.0,
        readiness_score=66.0,
        glycogen_debt=4.0,
        date=date,
    )


def test_guardrails_happy_path_marks_independent_and_reusable():
    tracker = OutcomeTracker()
    _seed_decision(tracker, date="2026-03-01")

    assert tracker.record_outcome(
        date="2026-03-01",
        completed=True,
        actual_session_type="EASY",
        rpe=6,
        outcome_date="2026-03-03",
    )

    summary = tracker.get_calibration_summary()

    assert summary["n_with_outcome"] == 1
    assert summary["n_reusable_outcomes"] == 1
    assert summary["n_excluded_outcomes"] == 0


def test_guardrails_boundary_marks_non_independent_and_excludes(caplog):
    tracker = OutcomeTracker()
    _seed_decision(tracker, date="2026-03-01")

    caplog.set_level(logging.WARNING, logger="titan.science.outcome_tracker")
    assert tracker.record_outcome(
        date="2026-03-01",
        completed=True,
        actual_session_type="TEMPO",
        rpe=8,
        outcome_date="2026-03-01",
    )

    summary = tracker.get_calibration_summary()
    assert summary["n_with_outcome"] == 1
    assert summary["n_reusable_outcomes"] == 0
    assert summary["n_excluded_outcomes"] == 1

    events = [
        json.loads(record.message)
        for record in caplog.records
        if "outcome_guardrail_activated" in record.message
    ]
    assert len(events) == 1
    assert events[0]["outcome_independence_ok"] is False
    assert events[0]["override_outcome_exclusion"] is True


def test_guardrail_metadata_persistence_roundtrip(tmp_path):
    db = DatabaseManager(db_name="test.db", db_dir=tmp_path)
    tracker = OutcomeTracker(db=db)
    _seed_decision(tracker, date="2026-03-01")

    assert tracker.record_outcome(
        date="2026-03-01",
        completed=True,
        actual_session_type="TEMPO",
        rpe=7,
        outcome_date="2026-03-01",
    )

    reloaded = OutcomeTracker(db=db)
    decisions = reloaded.get_decisions(date="2026-03-01")
    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.decision_was_followed is False
    assert decision.override_outcome_exclusion is True
    assert decision.outcome_independence_ok is False
    assert decision.algorithm_version_snapshot is not None
    assert "outcome_tracker" in decision.algorithm_version_snapshot

    db.close()
