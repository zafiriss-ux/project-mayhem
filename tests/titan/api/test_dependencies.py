"""Mirrored test for titan/api/dependencies.py — T5-79."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from titan.api.dependencies import require_coach_athlete_access
from titan.api.models import AuthUser


def _request(query_params: dict | None = None, db=None):  # noqa: ANN001, ANN202
    return SimpleNamespace(
        path_params={}, query_params=query_params or {},
        app=SimpleNamespace(state=SimpleNamespace(db=db)),
    )


@pytest.mark.integration
def test_module_imports_without_error() -> None:
    import titan.api.dependencies  # noqa: F401


@pytest.mark.integration
def test_a_coach_without_the_assignment_is_refused() -> None:
    coach = AuthUser(id="c1", username="coach", role="COACH", athlete_id=None)
    db = MagicMock()
    db.get_assigned_athletes.return_value = []
    with pytest.raises(HTTPException) as exc_info:
        require_coach_athlete_access(_request({"athlete_id": "any-athlete-id"}, db), coach)
    assert exc_info.value.status_code == 403


@pytest.mark.integration
def test_a_non_coach_is_left_to_the_routes_own_isolation_check() -> None:
    athlete = AuthUser(id="a1", username="alice", role="ATHLETE", athlete_id="alice")
    assert require_coach_athlete_access(_request({"athlete_id": "alice"}), athlete) is athlete


@pytest.mark.integration
def test_a_coach_with_an_empty_athlete_id_raises_403() -> None:
    coach = AuthUser(id="c1", username="coach", role="COACH", athlete_id=None)
    with pytest.raises(HTTPException) as exc_info:
        require_coach_athlete_access(_request({"athlete_id": ""}, MagicMock()), coach)
    assert exc_info.value.status_code == 403
