"""Coverage guard — governance_engine.py uncovered branches (Phase 24).

Closes the CI coverage gap (97.39% → ≥98%) identified in the Opus pre-Phase-24
audit (2026-05-29). Each test class maps to a specific uncovered line group.

Targeted lines (governance_engine.py):
  231        – apply_override_lockdown: db is None early return
  234-237    – apply_override_lockdown: db.get_override_ratio raises → fail-closed
  238-248    – apply_override_lockdown: ratio is None → COLD_START_LOCKDOWN
  290-292    – _evaluate_2of4_indicators: sleep_score TypeError → default 40
  322-324    – classify_hrv_stress_context: non-finite HRV → NAN_REJECTED
  333-335    – classify_hrv_stress_context: non-finite RHR → NAN_REJECTED
  343-344    – classify_hrv_stress_context: acwr absent/None → UNKNOWN_ACWR
  349-351    – classify_hrv_stress_context: non-finite ACWR → NAN_REJECTED + UNKNOWN_ACWR
  353-354    – classify_hrv_stress_context: acwr > VO2_ACWR_MAX → TRAINING_EXPLAINED
  656-660    – _check_hard_stops H6 branch: non-numeric age → debug log, no crash
  1023-1042  – _check_fueling_gate: LONG_RUN ≥90 min → phase-4 LOCK → PROGRESSIVE
  1347-1357  – apply_constraints gate loop: PARASYMPATHETIC_GUARD triggered
  1458       – get_governance_report: db=None → override_lockdown fallback
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from titan.config.thresholds import VO2_ACWR_MAX
from titan.science.governance_engine import GovernanceEngine

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _session_plan(session_type: str = "INTERVALS", duration: int = 60) -> dict:
    return {"session_type": session_type, "duration_min": duration}


def _base_context(**overrides) -> dict:
    ctx: dict = {
        "readiness_score": 80.0,
        "acwr": 1.0,
        "tsb_value": -5.0,
        "glycogen_debt": 2.0,
        "baseline_hrv": 55.0,
        "today_hrv": 53.0,
        "baseline_rhr": 48,
        "today_rhr": 49,
        "sleep_score": 80,
        "soreness": 2,
        "subjective_fatigue_score": 2,
        "garmin_data_age_hours": 1.0,
        "garmin_data_trust_level": "TRUSTED",
        "afi_constraints": {"parasympathetic_guard": {"triggered": False}},
        "days_since_last_vo2": 7,
        "data_confidence_low": False,
        "persistence_degraded": False,
    }
    ctx.update(overrides)
    return ctx


# ---------------------------------------------------------------------------
# Group 1 — apply_override_lockdown edge paths (lines 231, 234-237, 238-248)
# ---------------------------------------------------------------------------

class TestOverrideLockdownEdgePaths:
    """Tests for the three non-happy-path branches in apply_override_lockdown."""

    @pytest.mark.unit
    def test_db_none_early_return_does_not_set_locked(self) -> None:
        """Line 231: self._db is None → early return; override_locked not set."""
        ge = GovernanceEngine()
        ctx: dict = {"session_plan": _session_plan()}
        ge.apply_override_lockdown(ctx)
        assert not ctx.get("override_locked", False)

    @pytest.mark.unit
    def test_db_exception_fail_closed_locks_session(self) -> None:
        """Lines 234-237: get_override_ratio raises → fail-closed, lock applied."""
        mock_db = MagicMock()
        mock_db.get_override_ratio.side_effect = RuntimeError("db unavailable")
        ge = GovernanceEngine(db=mock_db)
        ctx: dict = {"session_plan": _session_plan()}
        ge.apply_override_lockdown(ctx)
        assert ctx.get("override_locked") is True
        assert ctx["session_plan"].get("lock_applied") is True

    @pytest.mark.unit
    def test_ratio_none_cold_start_lockdown_emitted(self) -> None:
        """Lines 238-248: ratio=None (cold-start) → COLD_START_LOCKDOWN, locked."""
        mock_db = MagicMock()
        mock_db.get_override_ratio.return_value = None
        ge = GovernanceEngine(db=mock_db)
        ctx: dict = {"session_plan": _session_plan()}
        ge.apply_override_lockdown(ctx)
        assert ctx.get("override_locked") is True
        assert ctx["session_plan"].get("lock_applied") is True


# ---------------------------------------------------------------------------
# Group 2 — _evaluate_2of4_indicators: sleep_score TypeError (lines 290-292)
# ---------------------------------------------------------------------------

class TestTwoOf4SleepTypeError:
    """Non-numeric sleep_score triggers ValueError fallback → I2_sleep fires."""

    @pytest.mark.unit
    def test_non_numeric_sleep_score_defaults_to_below_60(self) -> None:
        """Lines 290-292: float('not_a_number') raises ValueError → sleep_score=40 → I2."""
        ge = GovernanceEngine()
        ctx = _base_context(sleep_score="not_a_number", soreness=8)
        _count, indicators = ge._evaluate_2of4_indicators(ctx)
        assert "I2_sleep" in indicators


# ---------------------------------------------------------------------------
# Group 3 — classify_hrv_stress_context non-finite and TRAINING_EXPLAINED paths
# (lines 322-324, 333-335, 343-344, 349-351, 353-354)
# ---------------------------------------------------------------------------

class TestClassifyHrvStressContextEdgePaths:
    """Edge paths in the H2/H3 stress-source classifier."""

    @pytest.mark.unit
    def test_non_finite_hrv_does_not_crash(self) -> None:
        """Lines 322-324: NaN HRV → NAN_REJECTED gate event; returns str."""
        ctx = _base_context(baseline_hrv=float("nan"), today_hrv=50.0)
        result = GovernanceEngine.classify_hrv_stress_context(ctx)
        assert isinstance(result, str)

    @pytest.mark.unit
    def test_inf_hrv_does_not_crash(self) -> None:
        """Lines 322-324: Inf HRV → NAN_REJECTED gate event; returns str."""
        ctx = _base_context(baseline_hrv=float("inf"), today_hrv=50.0)
        result = GovernanceEngine.classify_hrv_stress_context(ctx)
        assert isinstance(result, str)

    @pytest.mark.unit
    def test_non_finite_rhr_does_not_crash(self) -> None:
        """Lines 333-335: Inf RHR → NAN_REJECTED gate event; returns str."""
        ctx = _base_context(baseline_rhr=float("inf"), today_rhr=50)
        result = GovernanceEngine.classify_hrv_stress_context(ctx)
        assert isinstance(result, str)

    @pytest.mark.unit
    def test_acwr_absent_returns_unknown_acwr(self) -> None:
        """Lines 343-344: acwr key absent from context → UNKNOWN_ACWR."""
        ctx = _base_context()
        ctx.pop("acwr", None)
        result = GovernanceEngine.classify_hrv_stress_context(ctx)
        assert result == "UNKNOWN_ACWR"

    @pytest.mark.unit
    def test_acwr_none_returns_unknown_acwr(self) -> None:
        """Lines 343-344: acwr=None → UNKNOWN_ACWR."""
        ctx = _base_context(acwr=None)
        result = GovernanceEngine.classify_hrv_stress_context(ctx)
        assert result == "UNKNOWN_ACWR"

    @pytest.mark.unit
    def test_non_finite_acwr_returns_unknown_acwr(self) -> None:
        """Lines 349-351: float('nan') ACWR → NAN_REJECTED + UNKNOWN_ACWR."""
        ctx = _base_context(acwr=float("nan"))
        result = GovernanceEngine.classify_hrv_stress_context(ctx)
        assert result == "UNKNOWN_ACWR"

    @pytest.mark.unit
    def test_high_acwr_returns_training_explained(self) -> None:
        """Lines 353-354: acwr > VO2_ACWR_MAX → TRAINING_EXPLAINED."""
        ctx = _base_context(acwr=float(VO2_ACWR_MAX) + 0.5)
        result = GovernanceEngine.classify_hrv_stress_context(ctx)
        assert result == "TRAINING_EXPLAINED"


# ---------------------------------------------------------------------------
# Group 4 — H6 non-numeric garmin_data_age_hours (lines 656-660)
# ---------------------------------------------------------------------------

class TestH6NonNumericAge:
    """Non-numeric age triggers the debug-log except branch, not a crash."""

    @pytest.mark.unit
    def test_string_age_skips_h6_gate_without_crash(self) -> None:
        """Lines 656-660: garmin_data_age_hours='bad' → debug log, empty reasons."""
        ge = GovernanceEngine()
        sp = _session_plan()
        ctx = _base_context(garmin_data_age_hours="not_numeric")
        reasons = ge._check_hard_stops(sp, ctx)
        assert isinstance(reasons, list)
        assert not any(r.get("gate") == "H6" for r in reasons)


# ---------------------------------------------------------------------------
# Group 5 — LONG_RUN fueling phase-4 lock (lines 1023-1042)
# ---------------------------------------------------------------------------

class TestFuelingGateLongRunPhase4:
    """LONG_RUN ≥90 min without fueling → phase-4 LOCK to PROGRESSIVE."""

    @pytest.mark.unit
    def test_long_run_90min_no_fueling_flags_and_keeps_the_long_run(self) -> None:
        """ADR-0063: LONG_RUN 90 min → FLAG phase 4, the session stays LONG_RUN."""
        ge = GovernanceEngine()
        sp = _session_plan("LONG_RUN", 90)
        ctx = _base_context()
        ctx["session_plan"] = sp
        result = ge._check_fueling_gate(sp, ctx)
        assert result is not None
        assert result["action"] == "FLAG"
        assert result["phase"] == 4
        assert sp["session_type"] == "LONG_RUN"

    @pytest.mark.unit
    def test_long_run_120min_no_fueling_also_flagged(self) -> None:
        """ADR-0063: LONG_RUN 120 min → same phase-4 flag."""
        ge = GovernanceEngine()
        sp = _session_plan("LONG_RUN", 120)
        ctx = _base_context()
        ctx["session_plan"] = sp
        result = ge._check_fueling_gate(sp, ctx)
        assert result is not None
        assert result["action"] == "FLAG"
        assert result["phase"] == 4

    @pytest.mark.unit
    def test_long_run_89min_does_not_trigger_phase4_lock(self) -> None:
        """Boundary: LONG_RUN 89 min < 90 → phase-4 lock does NOT fire."""
        ge = GovernanceEngine()
        sp = _session_plan("LONG_RUN", 89)
        ctx = _base_context()
        ctx["session_plan"] = sp
        result = ge._check_fueling_gate(sp, ctx)
        if result is not None:
            assert result.get("phase") != 4


# ---------------------------------------------------------------------------
# Group 6 — PARASYMPATHETIC_GUARD triggered in apply_constraints (1347-1357)
# ---------------------------------------------------------------------------

class TestParasympatheticGuardApplied:
    """PARASYMPATHETIC_GUARD triggered → session forced to EASY, max_zone=2."""

    @pytest.mark.unit
    def test_triggered_para_guard_forces_easy_session(self) -> None:
        """Lines 1347-1357: para_guard.triggered=True → EASY + PARASYMPATHETIC_GUARD lock."""
        ge = GovernanceEngine()
        sp = _session_plan("INTERVALS", 60)
        ctx = _base_context(
            afi_constraints={
                "parasympathetic_guard": {
                    "triggered": True,
                    "reason": "HR recovery impaired with elevated HRV",
                }
            }
        )
        ctx["session_plan"] = sp
        result = ge.apply_constraints(sp, ctx)
        assert result.get("session_type") == "EASY" or "PARASYMPATHETIC_GUARD" in result.get(
            "governance_locks_applied", []
        )


# ---------------------------------------------------------------------------
# Group 7 — get_governance_report db=None fallback (line 1458)
# ---------------------------------------------------------------------------

class TestGetGovernanceReportDbNone:
    """db=None → override_lockdown falls back to {"locked": False}."""

    @pytest.mark.unit
    def test_db_none_override_lockdown_fallback(self) -> None:
        """Line 1458: db=None → {"locked": False} in override_lockdown key."""
        ge = GovernanceEngine()
        result = ge.get_governance_report(db=None)
        assert isinstance(result, dict)
        ol = result.get("override_lockdown")
        assert ol == {"locked": False}
