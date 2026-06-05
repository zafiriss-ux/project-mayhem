from datetime import date, timedelta
from pathlib import Path

import pytest

from titan.core.database import DatabaseManager
from titan.ui.operator_console import OperatorConsoleService


def _make_db(tmp_path: Path) -> DatabaseManager:
    return DatabaseManager(db_name="test_operator_console.db", db_dir=tmp_path)


@pytest.mark.integration
def test_readiness_dashboard_empty_returns_null_summary(tmp_path):
    db = _make_db(tmp_path)
    service = OperatorConsoleService(db)

    payload = service.readiness_load_dashboard()

    assert payload["timeline"] == []
    assert payload["summary"]["samples"] == 0
    assert payload["summary"]["avg_readiness"] is None
    assert payload["summary"]["latest_vlg_color"] is None


@pytest.mark.integration
def test_readiness_dashboard_aggregates_timeline_and_distribution(tmp_path):
    db = _make_db(tmp_path)
    db.save_governance_decision(
        {
            "date": "2026-03-01",
            "session_planned": "VO2",
            "session_post_governance": "TEMPO",
            "locks_applied": ["OVERRIDE_LOCKDOWN"],
            "governance_clean": False,
            "phase": "BUILD",
            "vlg_color": "YELLOW",
            "apl_priority_vector": {},
            "lock_thresholds_active": {},
            "acwr": 1.16,
            "tsb_value": -12.0,
            "readiness_score": 63.0,
            "glycogen_debt": 0.15,
            "afi_value": -0.2,
        }
    )
    db.save_governance_decision(
        {
            "date": "2026-03-02",
            "session_planned": "EASY",
            "session_post_governance": "EASY",
            "locks_applied": [],
            "governance_clean": True,
            "phase": "BUILD",
            "vlg_color": "GREEN",
            "apl_priority_vector": {},
            "lock_thresholds_active": {},
            "acwr": 0.98,
            "tsb_value": -5.0,
            "readiness_score": 78.0,
            "glycogen_debt": 0.05,
            "afi_value": 0.1,
        }
    )

    service = OperatorConsoleService(db)
    payload = service.readiness_load_dashboard(limit=30)

    assert [p["date"] for p in payload["timeline"]] == ["2026-03-01", "2026-03-02"]
    assert payload["summary"]["samples"] == 2
    assert payload["summary"]["avg_readiness"] == pytest.approx(70.5, rel=1e-6)
    assert payload["summary"]["avg_acwr"] == pytest.approx(1.07, rel=1e-6)
    assert payload["summary"]["latest_vlg_color"] == "GREEN"
    assert payload["summary"]["vlg_distribution"] == {"YELLOW": 1, "GREEN": 1}


@pytest.mark.integration
def test_session_explorer_includes_governance_trail_and_annotations(tmp_path):
    db = _make_db(tmp_path)
    db.save_governance_decision(
        {
            "date": "2026-03-03",
            "session_planned": "INTERVALS",
            "session_post_governance": "TEMPO",
            "locks_applied": ["HARD_STOP_TSB_FLOOR"],
            "governance_clean": False,
            "phase": "BUILD",
            "vlg_color": "RED",
            "apl_priority_vector": {},
            "lock_thresholds_active": {},
            "acwr": 1.3,
            "tsb_value": -28.0,
            "readiness_score": 49.0,
            "glycogen_debt": 0.2,
            "afi_value": -0.3,
            "outcome_rpe": 7,
            "outcome_completed": True,
            "outcome_session_type_actual": "TEMPO",
            "outcome_notes": "Cut volume due to fatigue.",
        }
    )

    service = OperatorConsoleService(db)
    payload = service.session_explorer(limit=10)

    assert payload["summary"] == {
        "samples": 1,
        "annotated_sessions": 1,
        "sessions_with_locks": 1,
    }
    session = payload["sessions"][0]
    assert session["date"] == "2026-03-03"
    assert session["manual_annotation"] == "Cut volume due to fatigue."
    assert [step["step"] for step in session["decision_trail"]] == [
        "planned",
        "post_governance",
        "completed",
    ]
    assert session["gate_findings"] == [{"gate": "HARD_STOP_TSB_FLOOR", "status": "TRIGGERED"}]


@pytest.mark.integration
def test_add_manual_annotation_updates_latest_decision_note(tmp_path):
    db = _make_db(tmp_path)
    db.save_governance_decision(
        {
            "date": "2026-03-04",
            "session_planned": "VO2",
            "session_post_governance": "EASY",
            "locks_applied": ["OVERRIDE_LOCKDOWN"],
            "governance_clean": False,
            "phase": "BUILD",
            "vlg_color": "YELLOW",
            "apl_priority_vector": {},
            "lock_thresholds_active": {},
            "acwr": 1.12,
            "tsb_value": -10.0,
            "readiness_score": 58.0,
            "glycogen_debt": 0.11,
            "afi_value": -0.05,
        }
    )

    service = OperatorConsoleService(db)
    assert service.add_manual_annotation("2026-03-04", "Operator overrode due to travel day.") is True

    payload = service.session_explorer(limit=10)
    assert payload["sessions"][0]["manual_annotation"] == "Operator overrode due to travel day."


@pytest.mark.integration
def test_calibration_review_empty_without_outcomes(tmp_path):
    db = _make_db(tmp_path)
    service = OperatorConsoleService(db)

    payload = service.calibration_review()

    assert payload["summary"]["samples"] == 0
    assert payload["summary"]["governance_lock_rate"] is None
    assert payload["summary"]["lock_rate_by_phase"] == {}
    assert payload["heuristic_promotion_candidates"] == []
    assert payload["moderate_promotion_candidates"] == []
    assert payload["ml_promotion_readiness"]["stage_target"] == "Stage 1+"
    assert payload["ml_promotion_readiness"]["status"] == "REVIEW_REQUIRED"
    assert payload["ml_promotion_readiness"]["engines"][0]["engine"] == "LoadPredictionShadowModel"


@pytest.mark.integration
def test_calibration_review_surfaces_phase_lock_rates_and_candidates(tmp_path):
    db = _make_db(tmp_path)
    for day in range(1, 17):
        is_locked = day <= 8
        db.save_governance_decision(
            {
                "date": f"2026-04-{day:02d}",
                "session_planned": "VO2",
                "session_post_governance": "TEMPO" if is_locked else "VO2",
                "locks_applied": ["VO2_ELIGIBILITY_GATE"] if is_locked else [],
                "governance_clean": not is_locked,
                "phase": "BUILD" if day <= 4 or (9 <= day <= 12) else "PEAK",
                "vlg_color": "YELLOW" if is_locked else "GREEN",
                "apl_priority_vector": {},
                "lock_thresholds_active": {},
                "acwr": 1.2 if is_locked else 0.95,
                "tsb_value": -18.0 if is_locked else -6.0,
                "readiness_score": 58.0 if is_locked else 78.0,
                "glycogen_debt": 0.18 if is_locked else 0.06,
                "afi_value": -0.1 if is_locked else 0.1,
                "outcome_completed": not is_locked,
            }
        )

    service = OperatorConsoleService(db)
    payload = service.calibration_review()

    assert payload["summary"] == {
        "samples": 16,
        "governance_lock_rate": 0.5,
        "lock_rate_by_phase": {"BUILD": 0.5, "PEAK": 0.5},
    }
    assert payload["heuristic_promotion_candidates"] == [
        {
            "parameter": "VO2_READINESS_MIN",
            "trigger_lock": "VO2_ELIGIBILITY_GATE",
            "n_with_lock": 8,
            "n_without_lock": 8,
            "completion_delta_pp": -100.0,
        }
    ]
    assert payload["moderate_promotion_candidates"] == [
        {
            "parameter": "VO2_GLYCOGEN_DEBT_MAX",
            "trigger_lock": "VO2_ELIGIBILITY_GATE",
            "n_with_lock": 8,
            "n_without_lock": 8,
            "completion_delta_pp": -100.0,
            "phase_replication_count": 2,
        }
    ]
    assert payload["ml_promotion_readiness"]["required_controls"] == [
        "ADR updated with evidence_label upgrade HEURISTIC -> MODERATE",
        "deployment docs set TITAN_ML_KILL_SWITCH=0 explicitly",
        "Operator Console calibration review marked promotion-ready",
    ]


@pytest.mark.integration
def test_manual_override_workflow_empty_payload(tmp_path):
    db = _make_db(tmp_path)
    service = OperatorConsoleService(db)

    payload = service.manual_override_workflow(limit=20, days=7)

    assert payload["summary"] == {
        "samples": 0,
        "override_ratio_window_days": 7,
        "override_ratio": 0.0,
        "latest_override_date": None,
    }
    assert payload["overrides"] == []
    assert payload["override_metrics"] == {
        "window_days": 30,
        "samples": 0,
        "override_rate_30d": 0.0,
        "trend": "stable",
        "trust_signal": "STABLE",
        "operator_trust_drift_warning": False,
    }


@pytest.mark.integration
def test_record_manual_override_surfaces_in_workflow_audit_trail(tmp_path):
    db = _make_db(tmp_path)
    service = OperatorConsoleService(db)

    # Seed one governance_outcomes row so get_override_ratio skips cold-start guard.
    db.conn.execute(
        "INSERT INTO governance_outcomes "
        "(date, athlete_id, session_planned, session_post_governance, locks_applied_json, "
        "governance_clean, phase, vlg_color, apl_priority_vector_json, "
        "lock_thresholds_active_json, acwr, tsb_value, readiness_score, glycogen_debt) "
        "VALUES ('2026-01-01', 'owner', 'z2', 'z2', '[]', 1, 'base', 'green', '[]', '{}', "
        "0.8, 5.0, 80.0, 0.0)"
    )
    db.conn.commit()

    # Use relative dates so this test stays valid regardless of when it runs.
    date_1 = (date.today() - timedelta(days=5)).isoformat()
    date_2 = (date.today() - timedelta(days=3)).isoformat()

    assert service.record_manual_override(
        date=date_1,
        prescribed_type="REST",
        actual_type="EASY",
        reason="Travel day schedule shift",
    ) is True
    assert service.record_manual_override(
        date=date_2,
        prescribed_type="TEMPO",
        actual_type="VO2",
        reason="Race simulation",
    ) is True

    payload = service.manual_override_workflow(limit=10, days=14)

    assert payload["summary"] == {
        "samples": 2,
        "override_ratio_window_days": 14,
        "override_ratio": 0.143,
        "latest_override_date": date_2,
    }
    assert payload["override_metrics"]["window_days"] == 30
    assert payload["override_metrics"]["samples"] >= 0
    assert payload["overrides"] == [
        {
            "date": date_1,
            "prescribed_type": "REST",
            "actual_type": "EASY",
            "reason": "Travel day schedule shift",
        },
        {
            "date": date_2,
            "prescribed_type": "TEMPO",
            "actual_type": "VO2",
            "reason": "Race simulation",
        },
    ]
