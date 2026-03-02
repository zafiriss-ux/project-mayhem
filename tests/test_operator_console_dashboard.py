from pathlib import Path

from titan.core.database import DatabaseManager
from titan.ui.operator_console import OperatorConsoleService


def _make_db(tmp_path: Path) -> DatabaseManager:
    return DatabaseManager(db_name="test_operator_console.db", db_dir=tmp_path)


def test_readiness_dashboard_empty_returns_null_summary(tmp_path):
    db = _make_db(tmp_path)
    service = OperatorConsoleService(db)

    payload = service.readiness_load_dashboard()

    assert payload["timeline"] == []
    assert payload["summary"]["samples"] == 0
    assert payload["summary"]["avg_readiness"] is None
    assert payload["summary"]["latest_vlg_color"] is None


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
    assert payload["summary"]["avg_readiness"] == 70.5
    assert payload["summary"]["avg_acwr"] == 1.07
    assert payload["summary"]["latest_vlg_color"] == "GREEN"
    assert payload["summary"]["vlg_distribution"] == {"YELLOW": 1, "GREEN": 1}
