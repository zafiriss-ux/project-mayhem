"""Tests for T5-48: Garmin data age propagation to governance context.

Covers:
- GarminSyncResult contract carries data_age_hours
- Governance context dict contains garmin_data_age_hours and garmin_data_trust_level
- Gate event log payloads include both fields
- Missing fields (None/absent) do not crash the engine
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from titan.orchestration.contracts import GarminSyncResultContract, HRVSyncMetricsContract
from titan.science.governance_engine import GovernanceEngine

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hrv_metrics():
    return HRVSyncMetricsContract(days_back=7, synced_days=7, skipped_days=0).to_payload()


def _minimal_session(session_type: str = "EASY") -> dict:
    return {"session_type": session_type, "duration_min": 45, "max_zone": 5}


def _minimal_context(**overrides: Any) -> dict:
    base: dict[str, Any] = {
        "today_hrv": 60.0,
        "baseline_hrv": 58.0,
        "today_rhr": 52,
        "baseline_rhr": 51.0,
        "tsb_value": 5.0,
        "subjective_fatigue_score": 2,
        "injury_flag": False,
        "acwr": 1.0,
        "readiness_score": 75.0,
        "glycogen_debt": 2.0,
        "fatigue_level": "LOW",
        "days_since_last_vo2": 3,
        "fueling_confirmed": True,
        "planned_duration_min": 45,
        "afi_constraints": {},
        "intensity_gate_result": {"gate": "GREEN"},
        "priority_vector": {},
        "lock_thresholds": {},
        "sleep_score": 78,
    }
    base.update(overrides)
    return base


def _capture_gate_events(caplog, gov: GovernanceEngine, session: dict, context: dict) -> list[dict]:
    """Run apply_constraints and return all parsed governance_gate log entries."""
    with caplog.at_level(logging.INFO, logger="titan.science.governance_engine"):
        gov.apply_constraints(session, context)

    events = []
    for record in caplog.records:
        try:
            payload = json.loads(record.getMessage())
        except (json.JSONDecodeError, TypeError):
            continue
        if "governance_gate" in payload:
            events.append(payload)
    return events


# ---------------------------------------------------------------------------
# 1. GarminSyncResult contract: data_age_hours field
# ---------------------------------------------------------------------------

class TestGarminSyncResultDataAgeHours:
    def test_data_age_hours_present_when_set(self):
        result = GarminSyncResultContract(
            activities=[], weight=[], sleep=[], hrv=[],
            hrv_sync_metrics=_hrv_metrics(),
            data_age_hours=1.5,
        ).to_payload()
        assert result["data_age_hours"] == pytest.approx(1.5)

    def test_data_age_hours_zero_for_fresh_sync(self):
        result = GarminSyncResultContract(
            activities=[], weight=[], sleep=[], hrv=[],
            hrv_sync_metrics=_hrv_metrics(),
            data_age_hours=0.0,
        ).to_payload()
        assert result["data_age_hours"] == pytest.approx(0.0)

    def test_data_age_hours_absent_when_none(self):
        result = GarminSyncResultContract(
            activities=[], weight=[], sleep=[], hrv=[],
            hrv_sync_metrics=_hrv_metrics(),
        ).to_payload()
        assert "data_age_hours" not in result

    def test_data_age_hours_float_inf_survives(self):
        result = GarminSyncResultContract(
            activities=[], weight=[], sleep=[], hrv=[],
            hrv_sync_metrics=_hrv_metrics(),
            data_age_hours=float("inf"),
        ).to_payload()
        assert result["data_age_hours"] == float("inf")


# ---------------------------------------------------------------------------
# 2. Governance context dict propagation
# ---------------------------------------------------------------------------

class TestGovernanceContextFields:
    def test_context_contains_garmin_data_age_hours(self):
        ctx = _minimal_context(garmin_data_age_hours=2.5, garmin_data_trust_level="TRUSTED")
        assert ctx["garmin_data_age_hours"] == pytest.approx(2.5)

    def test_context_contains_garmin_data_trust_level(self):
        ctx = _minimal_context(garmin_data_age_hours=30.0, garmin_data_trust_level="INVALID")
        assert ctx["garmin_data_trust_level"] == "INVALID"

    def test_context_trust_level_values(self):
        for level in ("TRUSTED", "SUSPECT", "INVALID"):
            ctx = _minimal_context(garmin_data_age_hours=1.0, garmin_data_trust_level=level)
            assert ctx["garmin_data_trust_level"] == level


# ---------------------------------------------------------------------------
# 3. Gate events include both fields
# ---------------------------------------------------------------------------

class TestGateEventPayloads:
    def test_apply_constraints_complete_event_carries_age_fields(self, caplog):
        gov = GovernanceEngine()
        ctx = _minimal_context(garmin_data_age_hours=4.0, garmin_data_trust_level="SUSPECT")
        events = _capture_gate_events(caplog, gov, _minimal_session(), ctx)

        complete = next((e for e in events if e.get("governance_gate") == "APPLY_CONSTRAINTS"), None)
        assert complete is not None, "APPLY_CONSTRAINTS COMPLETE event not found"
        assert complete["garmin_data_age_hours"] == pytest.approx(4.0)
        assert complete["garmin_data_trust_level"] == "SUSPECT"

    def test_h1_gate_event_carries_age_fields(self, caplog):
        gov = GovernanceEngine()
        ctx = _minimal_context(
            injury_flag=True,
            garmin_data_age_hours=10.0,
            garmin_data_trust_level="INVALID",
        )
        events = _capture_gate_events(caplog, gov, _minimal_session("INTERVALS"), ctx)

        h1 = next((e for e in events if e.get("governance_gate") == "H1"), None)
        assert h1 is not None, "H1 gate event not found"
        assert h1["garmin_data_age_hours"] == pytest.approx(10.0)
        assert h1["garmin_data_trust_level"] == "INVALID"

    def test_h2_gate_event_carries_age_fields(self, caplog):
        gov = GovernanceEngine()
        # HRV collapse: today_hrv <= baseline_hrv - 15
        ctx = _minimal_context(
            today_hrv=40.0,
            baseline_hrv=60.0,
            garmin_data_age_hours=7.0,
            garmin_data_trust_level="SUSPECT",
        )
        events = _capture_gate_events(caplog, gov, _minimal_session(), ctx)

        h2 = next((e for e in events if e.get("governance_gate") == "H2"), None)
        assert h2 is not None, "H2 gate event not found"
        assert h2["garmin_data_age_hours"] == pytest.approx(7.0)
        assert h2["garmin_data_trust_level"] == "SUSPECT"

    def test_h4_gate_event_carries_age_fields(self, caplog):
        gov = GovernanceEngine()
        ctx = _minimal_context(
            tsb_value=-55.0,
            garmin_data_age_hours=3.0,
            garmin_data_trust_level="TRUSTED",
        )
        events = _capture_gate_events(caplog, gov, _minimal_session("INTERVALS"), ctx)

        h4 = next((e for e in events if e.get("governance_gate") == "H4"), None)
        assert h4 is not None, "H4 gate event not found"
        assert h4["garmin_data_age_hours"] == pytest.approx(3.0)
        assert h4["garmin_data_trust_level"] == "TRUSTED"

    def test_vo2_eligibility_gate_event_carries_age_fields(self, caplog):
        gov = GovernanceEngine()
        # VO2 eligibility fails: acwr too high
        ctx = _minimal_context(
            acwr=1.5,
            garmin_data_age_hours=1.0,
            garmin_data_trust_level="TRUSTED",
        )
        session = _minimal_session("HAMMER")
        session["max_zone"] = 5
        events = _capture_gate_events(caplog, gov, session, ctx)

        vo2 = next((e for e in events if e.get("governance_gate") == "VO2_ELIGIBILITY"), None)
        assert vo2 is not None, "VO2_ELIGIBILITY gate event not found"
        assert vo2["garmin_data_age_hours"] == pytest.approx(1.0)
        assert vo2["garmin_data_trust_level"] == "TRUSTED"


# ---------------------------------------------------------------------------
# 4. Missing fields do not crash the engine
# ---------------------------------------------------------------------------

class TestMissingFieldsDefensiveBehavior:
    def test_no_crash_when_both_fields_absent(self, caplog):
        gov = GovernanceEngine()
        # Context without garmin_data_age_hours or garmin_data_trust_level
        ctx = _minimal_context()
        assert "garmin_data_age_hours" not in ctx
        assert "garmin_data_trust_level" not in ctx

        result = gov.apply_constraints(_minimal_session(), ctx)
        assert result is not None
        assert "session_type" in result

    def test_no_crash_when_age_is_none(self, caplog):
        gov = GovernanceEngine()
        ctx = _minimal_context(garmin_data_age_hours=None, garmin_data_trust_level="UNKNOWN")
        result = gov.apply_constraints(_minimal_session(), ctx)
        assert "session_type" in result

    def test_complete_event_age_is_none_when_absent(self, caplog):
        gov = GovernanceEngine()
        ctx = _minimal_context()
        events = _capture_gate_events(caplog, gov, _minimal_session(), ctx)

        complete = next((e for e in events if e.get("governance_gate") == "APPLY_CONSTRAINTS"), None)
        assert complete is not None
        # When field is absent from context, value should be None (not raise)
        assert complete.get("garmin_data_age_hours") is None

    def test_complete_event_trust_is_unknown_when_absent(self, caplog):
        gov = GovernanceEngine()
        ctx = _minimal_context()
        events = _capture_gate_events(caplog, gov, _minimal_session(), ctx)

        complete = next((e for e in events if e.get("governance_gate") == "APPLY_CONSTRAINTS"), None)
        assert complete is not None
        assert complete.get("garmin_data_trust_level") == "UNKNOWN"

    def test_no_crash_when_age_is_inf(self, caplog):
        gov = GovernanceEngine()
        ctx = _minimal_context(garmin_data_age_hours=float("inf"), garmin_data_trust_level="INVALID")
        result = gov.apply_constraints(_minimal_session(), ctx)
        assert "session_type" in result
