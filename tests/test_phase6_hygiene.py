"""
Phase 6 hygiene — branch-coverage sweep and deliverable validation for the
Operator Console (Web UI / Operator Console).

Coverage targets:
  titan/ui/operator_console.py (99 → 100 %):
    * calibration_review(): sparse-lock skip branch (line 183: continue)

Phase 6 deliverable smoke checks:
  - ADRs 0010–0013 present and well-formed
  - Specs: operator_console_{readiness_dashboard,session_explorer,
            manual_override_workflow,technology_path}.md
  - OperatorConsoleService importable + all six service methods present
  - titan.ui public API exports OperatorConsoleService in __all__
  - test_operator_console_dashboard module importable
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from titan.core.database import DatabaseManager
from titan.ui.operator_console import OperatorConsoleService


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_db(tmp_path: Path) -> DatabaseManager:
    return DatabaseManager(db_name="phase6_hygiene.db", db_dir=tmp_path)


def _save_decision(db: DatabaseManager, date: str, locks: list, completed: bool,
                   phase: str = "BUILD") -> None:
    db.save_governance_decision(
        {
            "date": date,
            "session_planned": "VO2",
            "session_post_governance": "TEMPO" if locks else "VO2",
            "locks_applied": locks,
            "governance_clean": not locks,
            "phase": phase,
            "vlg_color": "YELLOW" if locks else "GREEN",
            "apl_priority_vector": {},
            "lock_thresholds_active": {},
            "acwr": 1.2 if locks else 0.95,
            "tsb_value": -18.0 if locks else -6.0,
            "readiness_score": 58.0 if locks else 78.0,
            "glycogen_debt": 0.15 if locks else 0.05,
            "afi_value": -0.1 if locks else 0.1,
            "outcome_completed": completed,
        }
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1 · operator_console.py — sparse-lock skip branch (line 183)
# ─────────────────────────────────────────────────────────────────────────────

class TestCalibrationReviewSparseLockSkip:
    """Cover the 'continue' on line 183 where a lock has < 3 samples on
    either side — it must be silently skipped, not crash or surface."""

    def test_lock_with_only_one_sample_is_skipped(self, tmp_path):
        """A lock appearing exactly once (n_with_lock=1 < 3) must be absent
        from correlations and therefore absent from candidates lists."""
        db = _make_db(tmp_path)

        # 10 clean decisions — forms the 'without_lock' group
        for day in range(1, 11):
            _save_decision(db, f"2026-04-{day:02d}", locks=[], completed=True)

        # 1 decision with PARASYMPATHETIC_GUARD — n_with_lock=1 < 3 → skip
        _save_decision(db, "2026-04-15", locks=["PARASYMPATHETIC_GUARD"], completed=False)

        service = OperatorConsoleService(db)
        payload = service.calibration_review()

        # Summary must be populated (11 decided rows)
        assert payload["summary"]["samples"] == 11
        # Sparse lock must not surface as any candidate
        for candidate in payload["heuristic_promotion_candidates"]:
            assert "PARASYMPATHETIC_GUARD" not in candidate["trigger_lock"]
        for candidate in payload["moderate_promotion_candidates"]:
            assert "PARASYMPATHETIC_GUARD" not in candidate["trigger_lock"]

    def test_lock_with_two_samples_is_also_skipped(self, tmp_path):
        """n_with_lock=2 < 3 still triggers the skip branch."""
        db = _make_db(tmp_path)

        for day in range(1, 9):
            _save_decision(db, f"2026-05-{day:02d}", locks=[], completed=True)

        # 2 decisions with a rare lock → still below the n >= 3 threshold
        _save_decision(db, "2026-05-09", locks=["CS_CONFIDENCE_LOCK"], completed=False)
        _save_decision(db, "2026-05-10", locks=["CS_CONFIDENCE_LOCK"], completed=False)

        service = OperatorConsoleService(db)
        payload = service.calibration_review()

        assert payload["summary"]["samples"] == 10
        all_candidates = (
            payload["heuristic_promotion_candidates"]
            + payload["moderate_promotion_candidates"]
        )
        for c in all_candidates:
            assert c["trigger_lock"] != "CS_CONFIDENCE_LOCK"

    def test_no_locks_at_all_produces_empty_candidates(self, tmp_path):
        """All decisions governance_clean → locks set is empty → correlations
        loop body never executes; both candidate lists empty."""
        db = _make_db(tmp_path)

        for day in range(1, 8):
            _save_decision(db, f"2026-06-{day:02d}", locks=[], completed=True)

        service = OperatorConsoleService(db)
        payload = service.calibration_review()

        assert payload["summary"]["governance_lock_rate"] == 0.0
        assert payload["heuristic_promotion_candidates"] == []
        assert payload["moderate_promotion_candidates"] == []

    def test_without_lock_group_too_small_is_skipped(self, tmp_path):
        """n_without_lock=2 < 3 → second condition of the OR triggers skip."""
        db = _make_db(tmp_path)

        # 8 decisions all locked → n_without_lock for OVERRIDE_LOCKDOWN = 0 < 3
        for day in range(1, 9):
            _save_decision(db, f"2026-07-{day:02d}", locks=["OVERRIDE_LOCKDOWN"], completed=False)

        # 2 clean decisions → n_without_lock = 2 < 3 for OVERRIDE_LOCKDOWN
        _save_decision(db, "2026-07-09", locks=[], completed=True)
        _save_decision(db, "2026-07-10", locks=[], completed=True)

        service = OperatorConsoleService(db)
        payload = service.calibration_review()

        assert payload["summary"]["samples"] == 10
        # OVERRIDE_LOCKDOWN not in the heuristic/moderate maps, so no candidates
        assert payload["heuristic_promotion_candidates"] == []
        assert payload["moderate_promotion_candidates"] == []


# ─────────────────────────────────────────────────────────────────────────────
# 2 · OperatorConsoleService interface contract
# ─────────────────────────────────────────────────────────────────────────────

class TestOperatorConsoleServiceInterface:
    """Verify the public API surface of OperatorConsoleService."""

    REQUIRED_METHODS = [
        "readiness_load_dashboard",
        "session_explorer",
        "add_manual_annotation",
        "manual_override_workflow",
        "record_manual_override",
        "calibration_review",
    ]

    def test_all_service_methods_present(self, tmp_path):
        db = _make_db(tmp_path)
        service = OperatorConsoleService(db)
        for method_name in self.REQUIRED_METHODS:
            assert hasattr(service, method_name), (
                f"OperatorConsoleService missing method: {method_name}"
            )
            assert callable(getattr(service, method_name))

    def test_service_instantiation_requires_db(self):
        with pytest.raises(TypeError):
            OperatorConsoleService()  # type: ignore[call-arg]

    def test_readiness_dashboard_returns_timeline_and_summary_keys(self, tmp_path):
        payload = OperatorConsoleService(_make_db(tmp_path)).readiness_load_dashboard()
        assert "timeline" in payload
        assert "summary" in payload

    def test_session_explorer_returns_sessions_and_summary_keys(self, tmp_path):
        payload = OperatorConsoleService(_make_db(tmp_path)).session_explorer()
        assert "sessions" in payload
        assert "summary" in payload

    def test_manual_override_workflow_returns_summary_and_overrides_keys(self, tmp_path):
        payload = OperatorConsoleService(_make_db(tmp_path)).manual_override_workflow()
        assert "summary" in payload
        assert "overrides" in payload

    def test_calibration_review_returns_required_keys(self, tmp_path):
        payload = OperatorConsoleService(_make_db(tmp_path)).calibration_review()
        assert "summary" in payload
        assert "heuristic_promotion_candidates" in payload
        assert "moderate_promotion_candidates" in payload


# ─────────────────────────────────────────────────────────────────────────────
# 3 · titan.ui public API
# ─────────────────────────────────────────────────────────────────────────────

class TestTitanUiPublicApi:
    """titan.ui.__init__ must export OperatorConsoleService."""

    def test_operator_console_service_in_all(self):
        import titan.ui as ui_pkg
        assert "OperatorConsoleService" in ui_pkg.__all__

    def test_operator_console_service_importable_from_ui_package(self):
        from titan.ui import OperatorConsoleService as OCS
        assert OCS is OperatorConsoleService


# ─────────────────────────────────────────────────────────────────────────────
# 4 · Phase 6 deliverable smoke checks
# ─────────────────────────────────────────────────────────────────────────────

class TestPhase6DeliverableSmoke:
    """Verify every Phase 6 artefact (ADR, spec, test module) is present."""

    REPO_ROOT = Path(__file__).parent.parent

    # ── ADRs ──────────────────────────────────────────────────────────────────

    @pytest.mark.parametrize("adr_name", [
        "0010-operator-console-readiness-dashboard-mvp.md",
        "0011-operator-console-session-explorer.md",
        "0012-operator-console-manual-override-workflow.md",
        "0013-operator-console-technology-path.md",
    ])
    def test_adr_exists(self, adr_name):
        adr_path = self.REPO_ROOT / "docs" / "adr" / adr_name
        assert adr_path.exists(), f"Missing ADR: docs/adr/{adr_name}"
        assert adr_path.stat().st_size > 0, f"Empty ADR: docs/adr/{adr_name}"

    # ── Specs ─────────────────────────────────────────────────────────────────

    @pytest.mark.parametrize("spec_name", [
        "operator_console_readiness_dashboard.md",
        "operator_console_session_explorer.md",
        "operator_console_manual_override_workflow.md",
        "operator_console_technology_path.md",
    ])
    def test_spec_exists(self, spec_name):
        spec_path = self.REPO_ROOT / "docs" / "specs" / spec_name
        assert spec_path.exists(), f"Missing spec: docs/specs/{spec_name}"
        assert spec_path.stat().st_size > 0, f"Empty spec: docs/specs/{spec_name}"

    # ── Module + test module ──────────────────────────────────────────────────

    def test_operator_console_module_importable(self):
        mod = importlib.import_module("titan.ui.operator_console")
        assert hasattr(mod, "OperatorConsoleService")

    def test_operator_console_dashboard_test_module_importable(self):
        mod = importlib.import_module("tests.test_operator_console_dashboard")
        assert mod is not None

    # ── Roadmap closure ───────────────────────────────────────────────────────

    def test_roadmap_marks_phase6_closed(self):
        roadmap = (self.REPO_ROOT / "docs" / "ROADMAP.MD").read_text()
        assert "Phase 6" in roadmap
        assert "CLOSED" in roadmap

    def test_phase6_adr_0013_status_accepted(self):
        adr_text = (
            self.REPO_ROOT / "docs" / "adr" / "0013-operator-console-technology-path.md"
        ).read_text()
        assert "Accepted" in adr_text or "Implemented" in adr_text
