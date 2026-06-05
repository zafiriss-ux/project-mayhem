"""Mirrored test for titan/api/dependencies.py — T5-79."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from titan.api.dependencies import require_athlete_access
from titan.api.models import AuthUser


@pytest.mark.integration
def test_module_imports_without_error() -> None:
    import titan.api.dependencies  # noqa: F401


@pytest.mark.integration
def test_require_athlete_access_coach_passes_any_athlete() -> None:
    coach = AuthUser(id="c1", username="coach", role="COACH", athlete_id=None)
    require_athlete_access(coach, "any-athlete-id")


@pytest.mark.integration
def test_require_athlete_access_athlete_own_id_passes() -> None:
    athlete = AuthUser(id="a1", username="alice", role="ATHLETE", athlete_id="alice")
    require_athlete_access(athlete, "alice")


@pytest.mark.integration
def test_require_athlete_access_athlete_other_id_raises_403() -> None:
    athlete = AuthUser(id="a1", username="alice", role="ATHLETE", athlete_id="alice")
    with pytest.raises(HTTPException) as exc_info:
        require_athlete_access(athlete, "bob")
    assert exc_info.value.status_code == 403
