"""INV-11 (AGENTS §8.4): athlete-scoped routes are assignment-scoped, and a blank id is no bypass.

- Every route whose handler takes ``athlete_id`` depends on ``require_coach_athlete_access``,
  and a role-only ``require_coach`` is never its sole authorization.
- MA-F6: a coach sending an empty (or blank) ``athlete_id`` is refused with 403 before any
  effect, and no audit row is skipped by it; the absent-id permissive path is only for routes
  that take no athlete id.
- The unused, weaker ``require_athlete_access`` (owner and no-datastore bypass) is gone.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from titan.api import dependencies as deps
from titan.api.auth import AuthStore, hash_password
from titan.api.main import CSRF_HEADER_NAME, CoachAuditStore, create_app
from titan.api.models import AuthUser
from titan.core.database import DatabaseManager


def _dependency_calls(dependant) -> set:  # noqa: ANN001
    calls = {dependant.call}
    for sub in dependant.dependencies:
        calls |= _dependency_calls(sub)
    return calls


def _athlete_scoped_routes(app) -> list[APIRoute]:  # noqa: ANN001
    return [
        route for route in app.routes
        if isinstance(route, APIRoute)
        and any(p.name == "athlete_id" for p in route.dependant.path_params + route.dependant.query_params)
    ]


@pytest.fixture
def jwt_keys(monkeypatch) -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setenv("TITAN_JWT_PRIVATE_KEY", key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption(),
    ).decode())
    monkeypatch.setenv("TITAN_JWT_PUBLIC_KEY", key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode())


@pytest.fixture
def app(jwt_keys, tmp_path):  # noqa: ARG001
    database = DatabaseManager(db_dir=tmp_path)
    yield create_app(auth_store=AuthStore(), audit_store=CoachAuditStore(), db=database)
    database.close()


@pytest.mark.unit
def test_there_are_athlete_scoped_routes_to_check(app) -> None:
    paths = {route.path for route in _athlete_scoped_routes(app)}
    assert {"/coach/overrides", "/athletes/{athlete_id}/dashboard"} <= paths


@pytest.mark.unit
def test_every_athlete_scoped_route_uses_the_assignment_scoped_dependency(app) -> None:
    missing = [
        route.path for route in _athlete_scoped_routes(app)
        if deps.require_coach_athlete_access not in _dependency_calls(route.dependant)
    ]
    assert not missing, f"athlete-scoped routes without require_coach_athlete_access: {missing}"


@pytest.mark.unit
def test_no_athlete_scoped_route_relies_on_the_role_only_check_alone(app) -> None:
    role_only = [
        route.path for route in _athlete_scoped_routes(app)
        if deps.require_coach in {d.call for d in route.dependant.dependencies}
        and deps.require_coach_athlete_access not in _dependency_calls(route.dependant)
    ]
    assert not role_only


@pytest.mark.unit
def test_the_weaker_unused_athlete_access_check_is_gone() -> None:
    assert not hasattr(deps, "require_athlete_access")


# ── the dependency on its own ─────────────────────────────────────────────────

def _request(path_params: dict | None = None, query_params: dict | None = None, db=None):  # noqa: ANN001, ANN202
    return SimpleNamespace(
        path_params=path_params or {},
        query_params=query_params or {},
        app=SimpleNamespace(state=SimpleNamespace(db=db)),
    )


_COACH = AuthUser(id="coach-1", username="coach", role="COACH", athlete_id=None)


@pytest.mark.unit
@pytest.mark.parametrize("blank", ["", " ", "\t"])
@pytest.mark.parametrize("where", ["query", "path"])
def test_a_blank_athlete_id_from_a_coach_is_refused(blank: str, where: str) -> None:
    db = MagicMock()
    db.get_assigned_athletes.return_value = ["a1"]
    params = {"athlete_id": blank}
    request = _request(path_params=params) if where == "path" else _request(query_params=params, db=db)
    with pytest.raises(HTTPException) as exc_info:
        deps.require_coach_athlete_access(request, _COACH)
    assert exc_info.value.status_code == 403


@pytest.mark.unit
def test_a_route_without_any_athlete_id_still_lets_the_coach_through() -> None:
    assert deps.require_coach_athlete_access(_request(db=MagicMock()), _COACH) is _COACH


@pytest.mark.unit
def test_an_assigned_athlete_id_in_the_query_passes() -> None:
    db = MagicMock()
    db.get_assigned_athletes.return_value = ["a1"]
    assert deps.require_coach_athlete_access(_request(query_params={"athlete_id": "a1"}, db=db), _COACH) is _COACH


# ── through the app ───────────────────────────────────────────────────────────

@pytest.fixture
def api(tmp_path, jwt_keys):  # noqa: ARG001
    database = DatabaseManager(db_dir=tmp_path)
    database.assign_athlete_to_coach("coach-1", "a1")
    store = AuthStore()
    store.upsert_user(user_id="coach-1", username="coach", password_hash=hash_password("coach-pass"),
                      role="COACH", athlete_id=None)
    store.upsert_user(user_id="ath-2", username="bob", password_hash=hash_password("bob-pass"),
                      role="ATHLETE", athlete_id="a2")
    client = TestClient(create_app(auth_store=store, audit_store=CoachAuditStore(), db=database),
                        base_url="https://testserver")
    yield SimpleNamespace(client=client, db=database)
    database.close()


def _login(api, username: str, password: str) -> dict:  # noqa: ANN001
    assert api.client.post("/auth/login", json={"username": username, "password": password}).status_code == 200
    return {CSRF_HEADER_NAME: api.client.get("/api/csrf-token").json()["csrf_token"]}


@pytest.mark.integration
@pytest.mark.parametrize("query", ["athlete_id=", "athlete_id=%20"])
def test_a_coach_override_with_a_blank_athlete_id_is_refused_before_any_effect(api, query: str) -> None:
    csrf = _login(api, "coach", "coach-pass")
    response = api.client.post(f"/coach/overrides?{query}", json={"reason": "x"}, headers=csrf)
    assert response.status_code == 403
    assert api.db.get_coach_audit_log(coach_id="coach-1") == []


@pytest.mark.integration
def test_a_coach_override_for_an_assigned_athlete_is_audited(api) -> None:
    csrf = _login(api, "coach", "coach-pass")
    response = api.client.post("/coach/overrides?athlete_id=a1", json={"reason": "x"}, headers=csrf)
    assert response.status_code == 200
    rows = api.db.get_coach_audit_log(coach_id="coach-1")
    assert [row["athlete_id"] for row in rows] == ["a1"]


@pytest.mark.integration
def test_an_athlete_cannot_open_another_athletes_dashboard(api) -> None:
    _login(api, "bob", "bob-pass")
    assert api.client.get("/athletes/a1/dashboard").status_code == 403
    assert api.client.get("/athletes/a2/dashboard").status_code == 200
