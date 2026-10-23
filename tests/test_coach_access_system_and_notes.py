"""M0-05 and M0-26 (Project Mayhem, Phase 1; SA:C-1, INV-11, ADR-0054).

- M0-05: the coach id ``system`` used to bypass the assignment table and see every athlete.
  Any API user whose id is ``system`` got that bypass. Access now comes only from
  assignment rows; ``system`` keeps the ``system → owner`` row seeded by the migration.
- M0-26: ``POST /coach/notes`` checked the role only. It now names its athlete and goes
  through the same assignment check and durable audit as ``/coach/overrides`` (INV-22).

Synthetic ids only.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from titan.api.auth import AuthStore, hash_password
from titan.api.main import CSRF_HEADER_NAME, CoachAuditStore, create_app
from titan.core.database import DatabaseManager


@pytest.fixture
def jwt_keys(monkeypatch) -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setenv("TITAN_JWT_PRIVATE_KEY", key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption(),
    ).decode())
    monkeypatch.setenv("TITAN_JWT_PUBLIC_KEY", key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode())


def _add_athlete(db: DatabaseManager, athlete_id: str) -> None:
    db.conn.execute(
        "INSERT OR IGNORE INTO athletes "
        "(athlete_id, display_name, created_at, is_cold_start, cold_start_sessions_count) "
        "VALUES (?, ?, datetime('now'), 1, 0)",
        (athlete_id, athlete_id),
    )
    db.conn.commit()


@pytest.fixture
def api(tmp_path, jwt_keys):  # noqa: ARG001
    database = DatabaseManager(db_dir=tmp_path)
    for athlete in ("a1", "a2"):
        _add_athlete(database, athlete)
    database.assign_athlete_to_coach("coach-1", "a1")
    database.assign_athlete_to_coach("coach-2", "a2")
    store = AuthStore()
    store.upsert_user(user_id="coach-1", username="coach", password_hash=hash_password("coach-pass"),
                      role="COACH", athlete_id=None)
    store.upsert_user(user_id="system", username="sys", password_hash=hash_password("sys-pass"),
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


# ── M0-05: "system" is a coach like any other ─────────────────────────────────

@pytest.mark.governance
def test_system_gets_only_its_assigned_athletes(api) -> None:
    # Before the fix: ["owner", "a1", "a2"], every athlete regardless of assignment.
    assert api.db.get_assigned_athletes("system") == ["owner"]


@pytest.mark.governance
def test_system_sees_a_new_athlete_only_once_assigned(api) -> None:
    _add_athlete(api.db, "a3")
    assert "a3" not in api.db.get_assigned_athletes("system")
    api.db.assign_athlete_to_coach("system", "a3")
    assert "a3" in api.db.get_assigned_athletes("system")


@pytest.mark.integration
@pytest.mark.governance
def test_a_coach_user_named_system_cannot_read_an_unassigned_athlete(api) -> None:
    _login(api, "sys", "sys-pass")
    assert api.client.get("/athletes/a2/dashboard").status_code == 403
    assert api.client.get("/athletes/owner/dashboard").status_code == 200


@pytest.mark.integration
@pytest.mark.governance
def test_a_coach_user_named_system_cannot_override_an_unassigned_athlete(api) -> None:
    csrf = _login(api, "sys", "sys-pass")
    response = api.client.post("/coach/overrides?athlete_id=a2", json={"reason": "x"}, headers=csrf)
    assert response.status_code == 403
    assert api.db.get_coach_audit_log(coach_id="system") == []


# ── M0-26: a coach note names its athlete and is assignment-scoped ────────────

@pytest.mark.integration
@pytest.mark.governance
def test_a_note_for_an_assigned_athlete_is_audited(api) -> None:
    csrf = _login(api, "coach", "coach-pass")
    response = api.client.post("/coach/notes?athlete_id=a1", json={"text": "n"}, headers=csrf)
    assert response.status_code == 200
    rows = api.db.get_coach_audit_log(coach_id="coach-1")
    assert [(row["athlete_id"], row["action_type"]) for row in rows] == [("a1", "ADD_NOTE")]


@pytest.mark.integration
@pytest.mark.governance
def test_a_note_for_an_unassigned_athlete_is_refused_without_audit(api) -> None:
    csrf = _login(api, "coach", "coach-pass")
    response = api.client.post("/coach/notes?athlete_id=a2", json={"text": "n"}, headers=csrf)
    assert response.status_code == 403
    assert api.db.get_coach_audit_log(coach_id="coach-1") == []


@pytest.mark.integration
@pytest.mark.governance
@pytest.mark.parametrize("query", ["", "?athlete_id=", "?athlete_id=%20"])
def test_a_note_without_an_athlete_is_refused(api, query: str) -> None:
    # Before the fix a coach note needed no athlete at all: the role was the only check.
    csrf = _login(api, "coach", "coach-pass")
    response = api.client.post(f"/coach/notes{query}", json={"text": "n"}, headers=csrf)
    assert response.status_code in (403, 422)
    assert api.db.get_coach_audit_log(coach_id="coach-1") == []


@pytest.mark.integration
@pytest.mark.governance
def test_an_athlete_cannot_post_a_coach_note(api) -> None:
    csrf = _login(api, "bob", "bob-pass")
    response = api.client.post("/coach/notes?athlete_id=a2", json={"text": "n"}, headers=csrf)
    assert response.status_code == 403
