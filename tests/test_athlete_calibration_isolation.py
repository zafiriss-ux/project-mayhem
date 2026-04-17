"""
tests/test_athlete_calibration_isolation.py

INV-04 enforcement: per-athlete calibration isolation.
All OutcomeTracker reads are scoped to a single athlete_id;
no cross-athlete query reaches the calibration path.

ADR-0033 Layer 3, Sub-decision L3-B (2026-04-12).
T5-07-L3-B implementation (2026-04-17).
"""

from __future__ import annotations

from titan.science.outcome_tracker import GovernanceDecision, OutcomeTracker


def _apl_result() -> dict:
    return {
        "priority_vector": {"PARASYMPATHETIC_GUARD": 1},
        "lock_thresholds": {"acwr_ceiling": 1.15},
    }


def _make_decision(
    tracker: OutcomeTracker,
    *,
    athlete_profile_id: str = "owner",
    date: str = "2026-04-01",
    session_planned: str = "EASY",
    session_post_governance: str = "EASY",
    locks_applied: list[str] | None = None,
    governance_clean: bool = True,
) -> GovernanceDecision:
    return tracker.record_decision(
        session_planned=session_planned,
        session_post_governance=session_post_governance,
        locks_applied=locks_applied or [],
        governance_clean=governance_clean,
        phase="BASE",
        vlg_color="GREEN",
        apl_result=_apl_result(),
        acwr=0.95,
        tsb_value=-10.0,
        readiness_score=72.0,
        glycogen_debt=2.0,
        athlete_profile_id=athlete_profile_id,
        date=date,
    )


class TestRecordDecisionAthleteIsolation:
    """record_decision() stores athlete_profile_id explicitly."""

    def test_decision_stores_correct_athlete_id(self) -> None:
        tracker = OutcomeTracker()
        _make_decision(tracker, athlete_profile_id="athlete_a")
        decisions = tracker.get_decisions(athlete_id="athlete_a")
        assert len(decisions) == 1
        assert decisions[0].athlete_profile_id == "athlete_a"

    def test_athlete_b_decisions_not_visible_to_athlete_a(self) -> None:
        tracker = OutcomeTracker()
        _make_decision(tracker, athlete_profile_id="athlete_a", date="2026-04-01")
        _make_decision(tracker, athlete_profile_id="athlete_b", date="2026-04-02")
        decisions_a = tracker.get_decisions(athlete_id="athlete_a")
        decisions_b = tracker.get_decisions(athlete_id="athlete_b")
        assert len(decisions_a) == 1
        assert decisions_a[0].date == "2026-04-01"
        assert len(decisions_b) == 1
        assert decisions_b[0].date == "2026-04-02"


class TestRecordOutcomeAthleteIsolation:
    """record_outcome() independence window check is scoped per-athlete."""

    def test_outcome_matches_correct_athlete(self) -> None:
        tracker = OutcomeTracker()
        _make_decision(tracker, athlete_profile_id="athlete_a", date="2026-04-05")
        result = tracker.record_outcome(date="2026-04-05", rpe=6, completed=True, athlete_id="athlete_a")
        assert result is True

    def test_outcome_does_not_match_wrong_athlete(self) -> None:
        """record_outcome() with athlete_b must not find athlete_a's decision."""
        tracker = OutcomeTracker()
        _make_decision(tracker, athlete_profile_id="athlete_a", date="2026-04-05")
        result = tracker.record_outcome(date="2026-04-05", rpe=6, completed=True, athlete_id="athlete_b")
        assert result is False, (
            "record_outcome() must not match decisions across athletes — INV-04 violation"
        )


class TestCalibrationDiversityGateIsolation:
    """check_calibration_diversity() must not pool cross-athlete records."""

    def _seed_athlete(
        self, tracker: OutcomeTracker, athlete_id: str, n: int, types: list[str]
    ) -> None:
        for i in range(n):
            session_type = types[i % len(types)]
            d = _make_decision(
                tracker,
                athlete_profile_id=athlete_id,
                date=f"2025-01-{i + 1:02d}",
                session_post_governance=session_type,
            )
            tracker.record_outcome(
                date=d.date,
                rpe=6,
                completed=True,
                athlete_id=athlete_id,
            )

    def test_athlete_b_not_satisfied_by_athlete_a_records(self) -> None:
        """30 records for athlete_a must not satisfy the gate for athlete_b."""
        tracker = OutcomeTracker()
        self._seed_athlete(tracker, "athlete_a", 30, ["EASY", "TEMPO", "LONG"])
        result_b = tracker.check_calibration_diversity(athlete_id="athlete_b")
        assert result_b is False, (
            "Calibration diversity gate must fail for athlete_b when only "
            "athlete_a has records — cross-athlete pooling is forbidden (INV-04)"
        )

    def test_diversity_gate_passes_when_own_records_sufficient(self) -> None:
        """An athlete with 30 diverse records satisfies the gate for themselves."""
        tracker = OutcomeTracker()
        self._seed_athlete(tracker, "athlete_a", 30, ["EASY", "TEMPO", "LONG"])
        result_a = tracker.check_calibration_diversity(athlete_id="athlete_a")
        assert result_a is True

    def test_diversity_gate_fails_below_minimum_count(self) -> None:
        """Fewer than 30 reusable records must fail the gate."""
        tracker = OutcomeTracker()
        self._seed_athlete(tracker, "athlete_a", 10, ["EASY", "TEMPO", "LONG"])
        assert tracker.check_calibration_diversity(athlete_id="athlete_a") is False

    def test_diversity_gate_fails_on_single_session_type_dominance(self) -> None:
        """If one session type > 60% the gate must fail even with ≥ 30 records."""
        tracker = OutcomeTracker()
        # 28 EASY + 1 TEMPO + 1 LONG = 30 records, EASY = 93% > 60%
        self._seed_athlete(tracker, "athlete_a", 30, ["EASY", "EASY", "EASY", "EASY", "EASY", "EASY", "EASY", "TEMPO", "LONG"])
        assert tracker.check_calibration_diversity(athlete_id="athlete_a") is False


class TestGetCalibrationAnalyticsIsolation:
    """get_calibration_analytics() must return only the requested athlete's records."""

    def test_analytics_for_athlete_a_excludes_athlete_b(self) -> None:
        tracker = OutcomeTracker()
        _make_decision(tracker, athlete_profile_id="athlete_a", date="2026-04-10")
        _make_decision(tracker, athlete_profile_id="athlete_b", date="2026-04-11")

        analytics_a = tracker.get_calibration_analytics(athlete_id="athlete_a")
        decision_ids_a = {r.get("date") for r in analytics_a}
        assert "2026-04-10" in decision_ids_a
        assert "2026-04-11" not in decision_ids_a, (
            "athlete_b's decision appeared in athlete_a's calibration analytics — INV-04 violation"
        )

    def test_analytics_returns_empty_for_unknown_athlete(self) -> None:
        tracker = OutcomeTracker()
        _make_decision(tracker, athlete_profile_id="athlete_a", date="2026-04-10")
        analytics = tracker.get_calibration_analytics(athlete_id="unknown_athlete")
        assert analytics == []
