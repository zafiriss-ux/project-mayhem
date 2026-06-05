"""
Adversarial scenario tests — BE-01, BE-02, BE-03 (§9.2 Framework).

BE-01  Override Laundering   — operator trust-drift detection + governance lockdown
BE-02  Readiness Gaming      — high readiness / high RPE divergence (detection only)
BE-03  Green Means Go        — consecutive GREEN days do not auto-block governance
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock

import pytest

from titan.config.thresholds import (
    GOVERNANCE_OVERRIDE_LOCKDOWN_THRESHOLD,
    OPERATOR_TRUST_DRIFT_WARNING_RATE_30D,
)
from titan.science.governance_engine import GovernanceEngine
from titan.science.outcome_tracker import OutcomeTracker
from titan.ui.operator_console import OperatorConsoleService

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_decision_row(
    *,
    session_post_governance: str = "INTERVALS",
    outcome_session_type_actual: str | None = None,
) -> dict[str, Any]:
    """Minimal governance_outcomes row for override-metric computation."""
    return {
        "date": "2026-01-01",
        "session_post_governance": session_post_governance,
        "outcome_session_type_actual": outcome_session_type_actual,
    }


def _clean_governance_context(**overrides: Any) -> dict[str, Any]:
    """All-GREEN governance context with no hard-stop triggers."""
    base: dict[str, Any] = {
        "today_hrv": 65.0,
        "baseline_hrv": 65.0,
        "hrv_std_dev": 5.0,
        "today_rhr": 48,
        "baseline_rhr": 48,
        "sleep_score": 80,
        "readiness_score": 80,
        "subjective_fatigue_score": 2,
        "tsb_value": 5.0,
        "acwr": 1.0,
        "glycogen_debt": 1.0,
        "fatigue_level": "LOW",
        "fueling_confirmed": True,
        "days_since_last_vo2": 3,
        "injury_flag": False,
        "data_confidence_low": False,
        "persistence_degraded": False,
    }
    base.update(overrides)
    return base


# ─────────────────────────────────────────────────────────────────────────────
# BE-01 — Override Laundering
# ─────────────────────────────────────────────────────────────────────────────

class TestBE01OverrideLaundering:
    """
    Verify that repeated manual overrides are detected and, at the lockdown
    ceiling, quality sessions are disabled.

    Two separate assertions:
      A. override_rate_30d > OPERATOR_TRUST_DRIFT_WARNING_RATE_30D (0.25)
         → operator_trust_drift_warning = True  (OperatorConsole metric)
      B. get_override_ratio(14d) > GOVERNANCE_OVERRIDE_LOCKDOWN_THRESHOLD (0.80)
         → GovernanceEngine.check_override_lockdown returns locked=True
    """

    @pytest.mark.unit
    @pytest.mark.governance
    def test_override_rate_above_25_pct_emits_trust_drift_warning(self) -> None:
        """
        BE-01-A: 9 overrides in 30 decisions (30%) > 0.25 threshold
        → operator_trust_drift_warning = True.
        """
        # 9 decisions where athlete deviated; 21 followed the prescription.
        rows: list[dict[str, Any]] = []
        for _i in range(9):
            rows.append(_make_decision_row(
                session_post_governance="INTERVALS",
                outcome_session_type_actual="EASY",   # deviation
            ))
        for _i in range(21):
            rows.append(_make_decision_row(
                session_post_governance="INTERVALS",
                outcome_session_type_actual="INTERVALS",  # followed
            ))

        metrics = OperatorConsoleService._compute_override_metrics(rows, window_days=30)

        assert metrics["override_rate_30d"] > OPERATOR_TRUST_DRIFT_WARNING_RATE_30D, (
            f"Expected override_rate_30d > {OPERATOR_TRUST_DRIFT_WARNING_RATE_30D}, "
            f"got {metrics['override_rate_30d']}"
        )
        assert metrics["operator_trust_drift_warning"] is True, (
            "Expected operator_trust_drift_warning=True when rate exceeds 0.25 threshold"
        )
        assert metrics["trust_signal"] == "DRIFT_WARNING"

    @pytest.mark.unit
    @pytest.mark.governance
    def test_override_rate_below_25_pct_no_warning(self) -> None:
        """
        BE-01-A-neg: 6 overrides in 30 decisions (20%) ≤ 0.25 threshold
        → operator_trust_drift_warning = False.
        """
        rows = [
            _make_decision_row(session_post_governance="INTERVALS",
                               outcome_session_type_actual="EASY")
            for _ in range(6)
        ] + [
            _make_decision_row(session_post_governance="INTERVALS",
                               outcome_session_type_actual="INTERVALS")
            for _ in range(24)
        ]

        metrics = OperatorConsoleService._compute_override_metrics(rows, window_days=30)

        assert metrics["operator_trust_drift_warning"] is False
        assert metrics["trust_signal"] == "STABLE"

    @pytest.mark.unit
    @pytest.mark.governance
    def test_override_rate_above_80_pct_disables_quality_sessions(self) -> None:
        """
        BE-01-B: get_override_ratio returning > 0.80
        → check_override_lockdown returns locked=True; quality sessions disabled.
        """
        # Mock DB whose get_override_ratio exceeds the lockdown ceiling.
        mock_db = MagicMock()
        mock_db.get_override_ratio.return_value = 0.86  # 86% override rate

        engine = GovernanceEngine()
        result = engine.check_override_lockdown(mock_db)

        assert result["locked"] is True, (
            "Expected lockdown when ratio > GOVERNANCE_OVERRIDE_LOCKDOWN_THRESHOLD"
        )
        assert result["ratio"] == pytest.approx(0.86)
        assert result["max_zone"] == 2
        # All quality session types must appear in disabled_sessions.
        disabled = set(result["disabled_sessions"])
        for quality in ("INTERVALS", "TEMPO", "RACE", "HAMMER"):
            assert quality in disabled, (
                f"Quality session '{quality}' must be disabled under override lockdown"
            )

    @pytest.mark.unit
    @pytest.mark.governance
    def test_override_rate_exactly_at_lockdown_threshold_not_locked(self) -> None:
        """
        BE-01-B-boundary: ratio == GOVERNANCE_OVERRIDE_LOCKDOWN_THRESHOLD is NOT locked
        (strict > semantics in check_override_lockdown).
        """
        mock_db = MagicMock()
        mock_db.get_override_ratio.return_value = GOVERNANCE_OVERRIDE_LOCKDOWN_THRESHOLD

        engine = GovernanceEngine()
        result = engine.check_override_lockdown(mock_db)

        # Boundary is strict >; at the exact threshold the gate stays open.
        assert result["locked"] is False, (
            "Lockdown should require strictly > threshold, not ≥"
        )


# ─────────────────────────────────────────────────────────────────────────────
# BE-02 — Readiness Gaming
# ─────────────────────────────────────────────────────────────────────────────

class TestBE02ReadinessGaming:
    """
    Verify that injecting perfect readiness followed by a high RPE outcome
    is recorded in OutcomeTracker but does NOT cause an automatic governance block.

    The readiness→outcome divergence is a detection signal only at this phase;
    it does not back-propagate into the governance pipeline as a hard stop.
    """

    @pytest.mark.unit
    @pytest.mark.governance
    def test_readiness_outcome_divergence_recorded_without_block(self) -> None:
        """
        BE-02: Five EXCELLENT readiness days, day 5 RPE=9.
        Governance on day 6 with the same healthy context must remain clean
        (no auto-block from accumulated divergence history).
        """
        tracker = OutcomeTracker()

        # Record 5 decisions — all with excellent readiness.
        apl_empty: dict[str, Any] = {"priority_vector": {}, "lock_thresholds": {}}
        for i in range(5):
            date = f"2026-01-{i + 1:02d}"
            tracker.record_decision(
                session_planned="INTERVALS",
                session_post_governance="INTERVALS",
                locks_applied=[],
                governance_clean=True,
                phase="BUILD",
                vlg_color="GREEN",
                apl_result=apl_empty,
                acwr=1.05,
                tsb_value=6.0,
                readiness_score=95.0,
                glycogen_debt=1.0,
                date=date,
            )

        # Attach a high RPE outcome to the last (day-5) decision.
        ok = tracker.record_outcome(
            date="2026-01-05",
            rpe=9,
            completed=True,
            actual_session_type="INTERVALS",
        )
        assert ok, "record_outcome must return True when the decision date exists"

        # Day 5 decision now has RPE=9 stored.
        decision_day5 = next(
            (d for d in tracker._decisions if d.date == "2026-01-05"), None
        )
        assert decision_day5 is not None
        assert decision_day5.outcome_rpe == 9, (
            "High RPE outcome must be persisted on the decision record"
        )

        # Governance on day 6 with the same healthy context must remain clean.
        engine = GovernanceEngine()
        session = {"session_type": "INTERVALS", "max_zone": 5, "duration_min": 50}
        ctx = _clean_governance_context()
        result = engine.apply_constraints(session_plan=session, context=ctx)

        assert result.get("governance_clean") is True, (
            "Governance must not auto-block based on accumulated outcome RPE history; "
            "readiness-outcome divergence is detection-only at this phase"
        )

    @pytest.mark.unit
    @pytest.mark.governance
    def test_divergence_data_does_not_escalate_to_hard_stop(self) -> None:
        """
        BE-02-guard: Five days of readiness=95 + RPE=9 outcomes must not add
        any hard-stop lock code to the next governance run.
        """
        tracker = OutcomeTracker()
        apl_empty: dict[str, Any] = {"priority_vector": {}, "lock_thresholds": {}}
        for i in range(5):
            tracker.record_decision(
                session_planned="INTERVALS",
                session_post_governance="INTERVALS",
                locks_applied=[],
                governance_clean=True,
                phase="BUILD",
                vlg_color="GREEN",
                apl_result=apl_empty,
                acwr=1.05,
                tsb_value=4.0,
                readiness_score=95.0,
                glycogen_debt=1.0,
                date=f"2026-02-{i + 1:02d}",
            )
            tracker.record_outcome(
                date=f"2026-02-{i + 1:02d}", rpe=9, completed=True
            )

        engine = GovernanceEngine()
        session = {"session_type": "INTERVALS", "max_zone": 5, "duration_min": 50}
        result = engine.apply_constraints(
            session_plan=session, context=_clean_governance_context()
        )

        hard_stop_codes = {"HARD_STOP_SAFETY_GATES", "OVERRIDE_LOCKDOWN",
                           "CS_CONFIDENCE_LOCK", "PARASYMPATHETIC_GUARD"}
        applied = set(result.get("governance_locks_applied", []))
        assert not (applied & hard_stop_codes), (
            f"No hard-stop lock must fire from outcome RPE history; got {applied}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# BE-03 — Green Means Go
# ─────────────────────────────────────────────────────────────────────────────

class TestBE03GreenMeansGo:
    """
    Verify that four consecutive GREEN sessions do not auto-block governance.

    The risk pattern is athletes interpreting GREEN as an unlimited licence to
    push.  Governance must remain advisory on accumulated GREEN streaks (no
    automatic lock) — any escalation requires an explicit threshold breach
    per ADR-0038.
    """

    @pytest.mark.unit
    @pytest.mark.governance
    def test_four_consecutive_green_days_no_auto_block(self) -> None:
        """
        BE-03: Run governance four times with clean healthy context.
        Day 4 must remain governance_clean=True (advisory only).
        """
        engine = GovernanceEngine()
        results: list[dict[str, Any]] = []

        for _ in range(4):
            session = {
                "session_type": "INTERVALS",
                "max_zone": 5,
                "duration_min": 50,
            }
            ctx = _clean_governance_context()
            result = engine.apply_constraints(session_plan=session, context=ctx)
            results.append(result)

        # All four days must be clean.
        for day_idx, r in enumerate(results, start=1):
            assert r.get("governance_clean") is True, (
                f"Day {day_idx}: expected governance_clean=True, "
                f"got locks={r.get('governance_locks_applied')}"
            )

    @pytest.mark.unit
    @pytest.mark.governance
    def test_green_streak_does_not_add_quality_session_streak_lock(self) -> None:
        """
        BE-03: Four clean INTERVALS days must not inject any advisory lock code.
        Per ADR-0038 explicit threshold breach required before lockdown.
        """
        engine = GovernanceEngine()
        applied_across_days: list[list[str]] = []

        for _ in range(4):
            session = {"session_type": "INTERVALS", "max_zone": 5, "duration_min": 50}
            result = engine.apply_constraints(
                session_plan=session, context=_clean_governance_context()
            )
            applied_across_days.append(result.get("governance_locks_applied", []))

        # Day 4 must have zero locks.
        day4_locks = applied_across_days[3]
        assert day4_locks == [], (
            f"Day 4 of GREEN streak must have no governance locks, got: {day4_locks}"
        )

    @pytest.mark.unit
    @pytest.mark.governance
    def test_governance_does_not_auto_block_on_streak_without_explicit_threshold(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """
        BE-03-advisory: Even after 4 consecutive quality sessions governance
        must not apply a lockdown.  Any future streak-based advisory must be
        WARNING-only (logged) — never a hard session_type downgrade.
        """
        engine = GovernanceEngine()

        for _ in range(4):
            session = {"session_type": "INTERVALS", "max_zone": 5, "duration_min": 50}
            with caplog.at_level(logging.DEBUG, logger="titan.science.governance_engine"):
                result = engine.apply_constraints(
                    session_plan=session, context=_clean_governance_context()
                )

        # Final session_type must not have been forcibly downgraded from INTERVALS.
        final_type = result.get("session_type", "INTERVALS")
        assert final_type == "INTERVALS", (
            f"Governance must not downgrade INTERVALS to '{final_type}' "
            f"based on a streak alone (no threshold breached)"
        )
        assert result.get("governance_clean") is True
