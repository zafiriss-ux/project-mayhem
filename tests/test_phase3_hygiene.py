"""
Phase 3 hygiene — branch-coverage sweep for governance_contracts,
governance_engine, and adaptive_priority_lock.

These tests close the remaining uncovered defensive branches that are
hard to reach through happy-path or integration tests:

 * governance_contracts.py  (78 → ≥ 80 %): isinstance-guard violations
 * governance_engine.py     (93 %): exception-handler paths + fueling gate
   branches + intensity gate RED/YELLOW + _to_dict_maybe object path
 * adaptive_priority_lock.py (94 %): matrix-miss fallback (lines 237-239)
"""

from __future__ import annotations

import json
import logging

import pytest

from titan.config.thresholds import (
    GOVERNANCE_CS_CONFIDENCE_THRESHOLD,
    GOVERNANCE_OVERRIDE_LOCKDOWN_THRESHOLD,
)
from titan.science.adaptive_priority_lock import AdaptivePriorityLock
from titan.science.governance_contracts import (
    ContractViolation,
    assert_vo2_eligibility_contract,
)
from titan.science.governance_engine import GovernanceEngine
from titan.science.volume_load_gauge import VLGState

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ineligible_base(**overrides) -> dict:
    """Minimal valid *ineligible* vo2_eligibility dict (all required keys)."""
    base = {
        "eligible": False,
        "failed_conditions": ["V1"],
        "original_session": "HAMMER",
        "downgraded_to": "TEMPO",
        "detailed_failed_conditions": [
            {"code": "V1", "metric": "acwr", "operator": "between", "actual": 1.5}
        ],
        "reason": "ACWR out of range",
    }
    base.update(overrides)
    return base


gov = GovernanceEngine()


# ─────────────────────────────────────────────────────────────────────────────
# 1 · governance_contracts — isinstance-guard violation branches
# ─────────────────────────────────────────────────────────────────────────────

class TestContractTypeGuardViolations:
    """Cover every isinstance() raise inside assert_vo2_eligibility_contract."""

    def test_eligible_not_bool_raises(self):
        with pytest.raises(ContractViolation, match="eligible.*bool"):
            assert_vo2_eligibility_contract(_ineligible_base(eligible="yes"))

    def test_failed_conditions_not_list_raises(self):
        with pytest.raises(ContractViolation, match="failed_conditions.*list"):
            assert_vo2_eligibility_contract(_ineligible_base(failed_conditions="V1"))

    def test_original_session_not_str_raises(self):
        with pytest.raises(ContractViolation, match="original_session.*str"):
            assert_vo2_eligibility_contract(_ineligible_base(original_session=123))

    def test_downgraded_to_wrong_type_raises(self):
        """downgraded_to that is neither None nor str triggers line 61."""
        with pytest.raises(ContractViolation, match="downgraded_to.*str or None"):
            assert_vo2_eligibility_contract(_ineligible_base(downgraded_to=42))

    def test_detailed_failed_conditions_not_list_raises(self):
        with pytest.raises(ContractViolation, match="detailed_failed_conditions.*list"):
            assert_vo2_eligibility_contract(
                _ineligible_base(detailed_failed_conditions="bad")
            )

    def test_reason_not_str_raises(self):
        with pytest.raises(ContractViolation, match="reason.*str"):
            assert_vo2_eligibility_contract(_ineligible_base(reason=999))

    def test_ineligible_with_downgraded_to_none_raises(self):
        """eligible=False but downgraded_to=None → structural invariant line 82."""
        r = _ineligible_base(downgraded_to=None)
        with pytest.raises(ContractViolation, match="eligible=False but downgraded_to is None"):
            assert_vo2_eligibility_contract(r)

    def test_detail_entry_not_dict_raises(self):
        """detailed_failed_conditions[i] is a string, not a dict → line 92."""
        r = _ineligible_base(detailed_failed_conditions=["not-a-dict"])
        with pytest.raises(ContractViolation, match="must be dict"):
            assert_vo2_eligibility_contract(r)

    def test_detail_missing_operator_field_raises(self):
        """'operator' is absent from a detail entry → lines 97–98."""
        r = _ineligible_base(
            detailed_failed_conditions=[
                {"code": "V1", "metric": "acwr"}  # 'operator' intentionally absent
            ]
        )
        with pytest.raises(ContractViolation, match="missing required field"):
            assert_vo2_eligibility_contract(r)

    def test_detail_with_unknown_code_raises(self):
        """detail['code'] not in {V1..V5} → line 101."""
        r = _ineligible_base(
            failed_conditions=["V1"],
            detailed_failed_conditions=[
                {"code": "V9", "metric": "acwr", "operator": "between", "actual": 1.5}
            ],
        )
        with pytest.raises(ContractViolation):
            assert_vo2_eligibility_contract(r)

    def test_detail_codes_disagree_with_failed_conditions_raises(self):
        """detail_codes != failed_conditions → line 108."""
        r = _ineligible_base(
            failed_conditions=["V1", "V2"],
            downgraded_to="TEMPO",
            detailed_failed_conditions=[
                {"code": "V1", "metric": "acwr", "operator": "between", "actual": 1.5},
                # Second entry uses V1 again instead of V2 → mismatch
                {"code": "V1", "metric": "readiness_score", "operator": ">=", "actual": 40},
            ],
        )
        with pytest.raises(ContractViolation, match="does not match"):
            assert_vo2_eligibility_contract(r)


# ─────────────────────────────────────────────────────────────────────────────
# 2 · governance_engine — exception-handler paths in indicator evaluation
# ─────────────────────────────────────────────────────────────────────────────

class TestGovernanceEngineExceptionPaths:
    """Cover TypeError/ValueError fallback branches in _evaluate_2of4_indicators
    and _check_hard_stops."""

    def test_hrv_conversion_exception_does_not_crash(self):
        """today_hrv/baseline_hrv/hrv_std_dev all present but non-numeric
        → lines 111-112 in _evaluate_2of4_indicators."""
        plan = {"session_type": "EASY", "duration_min": 45}
        ctx = {
            "today_hrv": "bad",
            "baseline_hrv": "bad",
            "hrv_std_dev": "bad",
        }
        result = gov.apply_constraints(plan, ctx)
        assert "session_type" in result  # engine survived

    def test_sleep_score_conversion_exception_does_not_crash(self):
        """sleep_score='nan_str' → lines 120-121 in _evaluate_2of4_indicators."""
        plan = {"session_type": "EASY", "duration_min": 45}
        ctx = {"sleep_score": "not_a_number"}
        result = gov.apply_constraints(plan, ctx)
        assert "session_type" in result

    def test_subjective_fatigue_exception_in_2of4_and_hard_stop(self):
        """subjective_fatigue_score non-castable → TypeError except in _evaluate_2of4
        and int() except in _check_hard_stops (H5 gate): both fall back to 0."""
        plan = {"session_type": "INTERVALS", "duration_min": 60}
        ctx = {"subjective_fatigue_score": "extreme"}
        result = gov.apply_constraints(plan, ctx)
        # Falls back to 0 → no H5 gate fires
        assert result.get("session_type") == "INTERVALS"

    def test_override_lockdown_db_failure_is_fail_safe_and_alerted(self, caplog):
        """Generic DB read failures must lock conservatively and emit structured alert."""

        class _RaisingDB:
            def get_override_ratio(self, days=14):
                raise RuntimeError("db unavailable")

        caplog.set_level(logging.INFO)
        result = gov.check_override_lockdown(_RaisingDB())

        assert result["locked"] is True
        assert result["error_code"] == "DB_READ_ERROR"
        assert result["action"] == "ZONE_2_ONLY"

        events = [
            json.loads(record.getMessage())
            for record in caplog.records
            if 'governance_gate' in record.getMessage()
        ]
        event = next(
            e for e in events
            if e.get("governance_gate") == "OVERRIDE_LOCKDOWN" and e.get("action") == "FAIL_SAFE_LOCK"
        )
        assert event["failure_class"] == "DB_READ_ERROR"
        assert event["error_class"] == "RuntimeError"
        assert event["error_message"] == "db unavailable"
        assert event["component"] == "check_override_lockdown"

    def test_override_lockdown_happy_path_reads_ratio(self):
        class _HealthyDB:
            def get_override_ratio(self, days=14):
                return 0.25

        result = gov.check_override_lockdown(_HealthyDB())
        assert result["locked"] is False
        assert result["ratio"] == 0.25

    def test_override_lockdown_schema_mismatch_classification(self):
        class _SchemaMismatchDB:
            def get_override_ratio(self, days=14):
                raise RuntimeError("no such table: override_log")

        result = gov.check_override_lockdown(_SchemaMismatchDB())
        assert result["locked"] is True
        assert result["error_code"] == "SCHEMA_MISMATCH"

    def test_override_lockdown_computation_error_classification(self):
        class _BadRatioDB:
            def get_override_ratio(self, days=14):
                return "invalid-float"

        result = gov.check_override_lockdown(_BadRatioDB())
        assert result["locked"] is True
        assert result["error_code"] == "COMPUTATION_ERROR"


    def test_override_lockdown_uses_thresholds_constant_boundary(self):
        class _BoundaryDB:
            def get_override_ratio(self, days=14):
                return GOVERNANCE_OVERRIDE_LOCKDOWN_THRESHOLD

        result = gov.check_override_lockdown(_BoundaryDB())
        assert result["locked"] is False

    def test_override_lockdown_locks_above_thresholds_constant(self):
        class _AboveBoundaryDB:
            def get_override_ratio(self, days=14):
                return GOVERNANCE_OVERRIDE_LOCKDOWN_THRESHOLD + 0.01

        result = gov.check_override_lockdown(_AboveBoundaryDB())
        assert result["locked"] is True

    def test_cs_confidence_lock_uses_thresholds_constant_boundary(self):
        class _Tracker:
            confidence = GOVERNANCE_CS_CONFIDENCE_THRESHOLD

        result = gov.check_cs_confidence_lock(_Tracker())
        assert result["locked"] is False

    def test_cs_confidence_lock_triggers_below_thresholds_constant(self):
        class _Tracker:
            confidence = GOVERNANCE_CS_CONFIDENCE_THRESHOLD - 0.01

        result = gov.check_cs_confidence_lock(_Tracker())
        assert result["locked"] is True


# ─────────────────────────────────────────────────────────────────────────────
# 3 · governance_engine — _to_dict_maybe coverage: dict path + object path
# ─────────────────────────────────────────────────────────────────────────────

class TestToDictMaybe:
    """Cover the two uncovered branches of _to_dict_maybe."""

    def test_intensity_gate_result_as_dict_is_returned_directly(self):
        """intensity_gate_result is already a dict → line 87 (return value)."""
        plan = {"session_type": "EASY", "duration_min": 45}
        gate_dict = {
            "color": "GREEN",
            "max_zone": 5,
            "volume_modifier": 1.0,
            "session_override": None,
            "triggered_signals": [],
            "audit": {},
        }
        result = gov.apply_constraints(plan, {"intensity_gate_result": gate_dict})
        assert result["intensity_gate_result"] == gate_dict  # passthrough

    def test_intensity_gate_result_as_arbitrary_object(self):
        """intensity_gate_result is not dict/None/dataclass → line 92 fallback."""

        class _FakeGate:
            color = "GREEN"
            max_zone = 4
            volume_modifier = 0.9
            session_override = None
            triggered_signals = ["sig"]
            audit = {"note": "test"}

        plan = {"session_type": "EASY", "duration_min": 45}
        result = gov.apply_constraints(plan, {"intensity_gate_result": _FakeGate()})
        assert result["intensity_gate_result"]["color"] == "GREEN"
        assert result["intensity_gate_result"]["max_zone"] == 4

    def test_intensity_gate_red_color_appends_intensity_gate_red_lock(self):
        """color='RED' → lines 444-445: INTENSITY_GATE_RED added to locks."""
        plan = {"session_type": "HAMMER", "duration_min": 45}
        gate = {
            "color": "RED",
            "max_zone": 2,
            "volume_modifier": 0.7,
            "session_override": None,
            "triggered_signals": [],
            "audit": {},
        }
        result = gov.apply_constraints(plan, {"intensity_gate_result": gate})
        assert "INTENSITY_GATE_RED" in result["governance_locks_applied"]

    def test_intensity_gate_yellow_color_appends_intensity_gate_yellow_lock(self):
        """color='YELLOW' → line 447: INTENSITY_GATE_YELLOW added to locks."""
        plan = {"session_type": "EASY", "duration_min": 45}
        gate = {
            "color": "YELLOW",
            "max_zone": 3,
            "volume_modifier": 0.85,
            "session_override": None,
            "triggered_signals": [],
            "audit": {},
        }
        result = gov.apply_constraints(plan, {"intensity_gate_result": gate})
        assert "INTENSITY_GATE_YELLOW" in result["governance_locks_applied"]

    def test_intensity_gate_session_override_is_applied(self):
        """session_override is set → line 443: session_type overwritten."""
        plan = {"session_type": "HAMMER", "duration_min": 45}
        gate = {
            "color": "RED",
            "max_zone": 2,
            "volume_modifier": 0.7,
            "session_override": "EASY",
            "triggered_signals": [],
            "audit": {},
        }
        result = gov.apply_constraints(plan, {"intensity_gate_result": gate})
        assert result["session_type"] == "EASY"


# ─────────────────────────────────────────────────────────────────────────────
# 4 · governance_engine — fueling gate uncovered branches
# ─────────────────────────────────────────────────────────────────────────────

class TestFuelingGateUncoveredBranches:
    """Cover the two fueling gate branches that weren't reached by existing tests."""

    def test_tempo_90min_without_fueling_locks_to_easy(self):
        """TEMPO ≥ 90 min, fueling_confirmed=False → LOCK phase 2 (lines 375-385)."""
        plan = {"session_type": "TEMPO", "duration_min": 90}
        result = gov.apply_constraints(plan, {"fueling_confirmed": False})
        assert result.get("fueling_gate", {}).get("action") == "LOCK"
        assert result.get("fueling_gate", {}).get("locked_to") == "EASY"
        assert result["session_type"] == "EASY"
        assert "FUELING_GATE_LOCK" in result["governance_locks_applied"]

    def test_intervals_90min_without_fueling_locks_to_easy(self):
        """INTERVALS ≥ 90 min, fueling_confirmed=False → LOCK phase 2."""
        plan = {"session_type": "INTERVALS", "duration_min": 95}
        result = gov.apply_constraints(plan, {"fueling_confirmed": False})
        assert result.get("fueling_gate", {}).get("action") == "LOCK"
        assert result["session_type"] == "EASY"

    def test_easy_75min_without_fueling_flags_session_unchanged(self):
        """EASY 60-89 min, fueling_confirmed=False → FLAG phase 1 (lines 411-418)."""
        plan = {"session_type": "EASY", "duration_min": 75}
        result = gov.apply_constraints(plan, {"fueling_confirmed": False})
        fg = result.get("fueling_gate", {})
        assert fg.get("action") == "FLAG"
        assert fg.get("phase") == 1
        assert fg.get("session_unchanged") is True
        assert result["session_type"] == "EASY"  # session NOT changed

    def test_progressive_65min_without_fueling_flags_session_unchanged(self):
        """PROGRESSIVE 60-89 min, fueling_confirmed=False → FLAG phase 1."""
        plan = {"session_type": "PROGRESSIVE", "duration_min": 65}
        result = gov.apply_constraints(plan, {"fueling_confirmed": False})
        fg = result.get("fueling_gate", {})
        assert fg.get("action") == "FLAG"
        assert fg.get("phase") == 1


# ─────────────────────────────────────────────────────────────────────────────
# 5 · adaptive_priority_lock — matrix-miss fallback (lines 237-239)
# ─────────────────────────────────────────────────────────────────────────────

class TestAPLMatrixFallback:
    """When the phase×load_band key is absent from _PHASE_LOAD_MATRIX,
    the fallback branch (lines 237-239) must produce a valid result."""

    def test_unknown_phase_load_combination_uses_fallback(self, monkeypatch):
        """Patch _PHASE_LOAD_MATRIX to be empty → key lookup always misses."""
        import titan.science.adaptive_priority_lock as apl_mod
        monkeypatch.setattr(apl_mod, "_PHASE_LOAD_MATRIX", {})

        apl = AdaptivePriorityLock()
        vlg = VLGState(color="GREEN", score=0, components={}, rationale=[])
        result = apl.resolve(
            vlg_state=vlg,
            afi_constraints={},
            phase="BASE",
            cs_confidence=0.8,
        )

        pv = result["priority_vector"]
        assert pv["PARASYMPATHETIC_GUARD"] == 1
        assert pv.get("OVERRIDE_LOCKDOWN") == 2
        assert pv.get("CS_CONFIDENCE_LOCK") == 3
        assert "Fallback default" in result["apl_rationale"].get("OVERRIDE_LOCKDOWN", "")

    def test_unknown_phase_string_normalises_to_base(self):
        """An unrecognised phase string is normalised to BASE (warning logged)."""
        apl = AdaptivePriorityLock()
        vlg = VLGState(color="GREEN", score=0, components={}, rationale=[])
        result = apl.resolve(
            vlg_state=vlg,
            afi_constraints={},
            phase="INVALID_PHASE",
            cs_confidence=0.9,
        )
        # BASE phase results should use a valid matrix row → priority_vector intact
        pv = result["priority_vector"]
        assert pv["PARASYMPATHETIC_GUARD"] == 1
        assert len(pv) == 3

    def test_cs_confidence_below_050_tightens_threshold(self):
        """cs_confidence < 0.50 must raise cs_min_confidence to ≥ 0.85."""
        apl = AdaptivePriorityLock()
        vlg = VLGState(color="GREEN", score=0, components={}, rationale=[])
        result = apl.resolve(
            vlg_state=vlg,
            afi_constraints={},
            phase="BASE",
            cs_confidence=0.30,
        )
        assert result["lock_thresholds"]["cs_min_confidence"] >= 0.85
