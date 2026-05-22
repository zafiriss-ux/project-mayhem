"""Opus audit 2026-05-22 — B1, B2, B3 regression tests.

B1: override_ratio returns None for cold-start athlete (no governance_outcomes).
B2: RBAC — COACH cannot access unassigned athlete dashboard via route dependency.
B3: get_database_manager raises NotImplementedError for postgres backend.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# B1: Override ratio cold-start returns None
# ─────────────────────────────────────────────────────────────────────────────

class TestOverrideRatioColdStart:
    def test_override_ratio_returns_none_for_cold_start_athlete(self, tmp_path: Path) -> None:
        """Fresh DB with 0 governance_outcomes → get_override_ratio returns None."""
        from titan.core.database import DatabaseManager

        db = DatabaseManager(db_name="test_cold_start.db", db_dir=tmp_path)
        try:
            ratio = db.get_override_ratio("owner", 14)
            assert ratio is None, f"Expected None for cold-start, got {ratio}"
        finally:
            db.close()

    def test_override_ratio_returns_float_when_outcomes_exist(self, tmp_path: Path) -> None:
        """DB with governance_outcomes → get_override_ratio returns a float."""
        from titan.core.database import DatabaseManager

        db = DatabaseManager(db_name="test_with_outcomes.db", db_dir=tmp_path)
        try:
            db.conn.execute(
                "INSERT INTO governance_outcomes "
                "(date, athlete_id, session_planned, session_post_governance, locks_applied_json, "
                "governance_clean, phase, vlg_color, apl_priority_vector_json, "
                "lock_thresholds_active_json, acwr, tsb_value, readiness_score, glycogen_debt) "
                "VALUES ('2026-05-01', 'owner', 'z2', 'z2', '[]', 1, 'base', 'green', '[]', '{}', "
                "0.8, 5.0, 80.0, 0.0)"
            )
            db.conn.commit()
            ratio = db.get_override_ratio("owner", 14)
            assert isinstance(ratio, float), f"Expected float, got {type(ratio)}"
        finally:
            db.close()


# ─────────────────────────────────────────────────────────────────────────────
# B2: RBAC — COACH dashboard route uses proper dependency
# ─────────────────────────────────────────────────────────────────────────────

def _import_dependencies():
    import importlib
    if "titan.api.auth" not in sys.modules:
        auth_stub = MagicMock()
        auth_stub.ACCESS_COOKIE_NAME = "access_token"
        auth_stub.AuthError = Exception
        sys.modules["titan.api.auth"] = auth_stub
    if "titan.api.dependencies" in sys.modules:
        return sys.modules["titan.api.dependencies"]
    return importlib.import_module("titan.api.dependencies")


class TestCoachDashboardRBAC:
    def test_coach_cannot_access_unassigned_athlete_dashboard(self) -> None:
        """require_coach_athlete_access rejects COACH not assigned to requested athlete."""
        from fastapi import HTTPException

        deps = _import_dependencies()
        from titan.api.models import AuthUser

        db = MagicMock()
        db.get_assigned_athletes.return_value = ["other-athlete"]

        req = MagicMock()
        req.path_params = {"athlete_id": "athlete-X"}
        req.query_params = {}
        req.app = SimpleNamespace(state=SimpleNamespace(db=db))

        coach = AuthUser(id="coach-1", username="coach", role="COACH", athlete_id=None)

        with pytest.raises(HTTPException) as exc_info:
            deps.require_coach_athlete_access(req, coach)

        assert exc_info.value.status_code == 403
        assert "athlete-X" in exc_info.value.detail

    def test_coach_can_access_assigned_athlete_dashboard(self) -> None:
        """require_coach_athlete_access passes COACH assigned to the requested athlete."""
        deps = _import_dependencies()
        from titan.api.models import AuthUser

        db = MagicMock()
        db.get_assigned_athletes.return_value = ["athlete-X"]

        req = MagicMock()
        req.path_params = {"athlete_id": "athlete-X"}
        req.query_params = {}
        req.app = SimpleNamespace(state=SimpleNamespace(db=db))

        coach = AuthUser(id="coach-1", username="coach", role="COACH", athlete_id=None)
        result = deps.require_coach_athlete_access(req, coach)
        assert result is coach


# ─────────────────────────────────────────────────────────────────────────────
# B3: postgres backend raises NotImplementedError
# ─────────────────────────────────────────────────────────────────────────────

class TestPostgresBackendDisabled:
    def test_get_database_manager_postgres_raises(self) -> None:
        """TITAN_DB_BACKEND=postgres must raise NotImplementedError (ADR-0044 not complete)."""
        from titan.core.database import get_database_manager

        with pytest.raises(NotImplementedError, match="ADR-0044"):
            get_database_manager(backend="postgres")

    def test_get_database_manager_env_postgres_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """TITAN_DB_BACKEND env var set to postgres must raise NotImplementedError."""
        monkeypatch.setenv("TITAN_DB_BACKEND", "postgres")
        from titan.core.database import get_database_manager

        with pytest.raises(NotImplementedError):
            get_database_manager()
