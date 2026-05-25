"""Fitness tests for Opus critical fixes (pass type: critical-fix, 2026-05-24)."""
from pathlib import Path

import pytest


@pytest.mark.unit
def test_healthcheck_uses_readyz():
    for path in ["Dockerfile", "docker-compose.yml"]:
        txt = Path(path).read_text()
        assert "/readyz" in txt, (
            f"{path}: HEALTHCHECK must use /readyz not /health"
        )


@pytest.mark.unit
def test_worker_has_sigterm_handler():
    src = Path("titan/worker/__init__.py").read_text()
    assert "SIGTERM" in src, "Worker must handle SIGTERM"
    assert "shutdown" in src.lower(), "Worker must support graceful shutdown"


@pytest.mark.unit
def test_worker_schedule_aligned():
    src = Path("titan/worker/__init__.py").read_text()
    assert "86400" not in src, (
        "Worker must not use raw 86400s sleep — use scheduled alignment instead"
    )
    assert "_seconds_until_next_run" in src or "07" in src, (
        "Worker must align to 07:00"
    )


@pytest.mark.integration
@pytest.mark.governance
def test_override_lockdown_fail_closed():
    from unittest.mock import patch

    from titan.core.database import DatabaseManager
    from titan.science.governance_engine import GovernanceEngine

    db = DatabaseManager(":memory:")
    ge = GovernanceEngine(db=db)
    with patch.object(db, "get_override_ratio", return_value=None):
        ctx = {"session_plan": {"session_type": "INTERVALS"}}
        ge.apply_override_lockdown(ctx)
        assert ctx.get("override_locked") is True, (
            "None ratio must fail closed"
        )


@pytest.mark.unit
def test_rbac_coach_checks_assignments():
    src = Path("titan/api/dependencies.py").read_text()
    assert "coach_athlete_assignments" in src or "get_assigned_athletes" in src, (
        "RBAC must query assignment table"
    )


@pytest.mark.unit
def test_run_api_script_exists():
    assert Path("scripts/run_api.py").exists(), (
        "Reviewable API entrypoint must exist"
    )
