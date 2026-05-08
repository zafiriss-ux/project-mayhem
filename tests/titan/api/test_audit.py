"""T5-13 audit middleware tests."""

from __future__ import annotations

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from titan.api.auth import AuthStore, hash_password
from titan.api.main import CSRF_HEADER_NAME, AuditActionType, CoachAuditStore, create_app


def _csrf_headers(client: TestClient) -> dict[str, str]:
    r = client.get("/api/csrf-token")
    return {CSRF_HEADER_NAME: r.json()["csrf_token"]}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, CoachAuditStore]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    monkeypatch.setenv("TITAN_JWT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("TITAN_JWT_PUBLIC_KEY", public_pem)

    auth_store = AuthStore()
    auth_store.upsert_user(
        user_id="coach-1",
        username="coach",
        password_hash=hash_password("coach-pass"),
        role="COACH",
        athlete_id=None,
    )
    auth_store.upsert_user(
        user_id="athlete-1",
        username="athlete",
        password_hash=hash_password("athlete-pass"),
        role="ATHLETE",
        athlete_id="athlete-1",
    )

    audit_store = CoachAuditStore()
    app = create_app(auth_store=auth_store, audit_store=audit_store)
    return TestClient(app, base_url="https://testserver"), audit_store


def _login_coach(client: TestClient) -> None:
    response = client.post("/auth/login", json={"username": "coach", "password": "coach-pass"})
    assert response.status_code == 200


def test_audit_middleware_writes_rows_for_all_required_action_types(client: tuple[TestClient, CoachAuditStore]) -> None:
    test_client, audit_store = client
    _login_coach(test_client)

    csrf = _csrf_headers(test_client)
    responses = [
        test_client.get("/athletes/athlete-2/dashboard?include=hrv"),
        test_client.post("/coach/overrides?athlete_id=athlete-2", json={"reason": "coach"}, headers=csrf),
        test_client.get("/coach/export?athlete_id=athlete-2&format=json"),
        test_client.delete("/coach/athlete-data?athlete_id=athlete-2", headers=csrf),
    ]
    assert all(response.status_code == 200 for response in responses)

    actions = [row.action_type for row in audit_store.rows]
    assert actions == [
        AuditActionType.VIEW_DATA.value,
        AuditActionType.SUBMIT_OVERRIDE.value,
        AuditActionType.EXPORT_DATA.value,
        AuditActionType.DELETE_DATA.value,
    ]


def test_audit_records_coach_and_athlete_identity(client: tuple[TestClient, CoachAuditStore]) -> None:
    test_client, audit_store = client
    _login_coach(test_client)

    response = test_client.get("/athletes/athlete-xyz/dashboard")
    assert response.status_code == 200

    row = audit_store.rows[-1]
    assert row.coach_id == "coach-1"
    assert row.athlete_id == "athlete-xyz"


def test_audit_path_is_non_bypassable_for_covered_health_data_endpoints(
    client: tuple[TestClient, CoachAuditStore],
) -> None:
    test_client, audit_store = client
    _login_coach(test_client)

    covered = [
        ("GET", "/athletes/athlete-2/dashboard", None),
        ("POST", "/coach/overrides?athlete_id=athlete-2", {"reason": "r"}),
        ("GET", "/coach/export?athlete_id=athlete-2", None),
        ("DELETE", "/coach/athlete-data?athlete_id=athlete-2", None),
    ]

    csrf = _csrf_headers(test_client)
    for method, url, payload in covered:
        before = len(audit_store.rows)
        if method == "GET":
            response = test_client.get(url)
        elif method == "POST":
            response = test_client.post(url, json=payload, headers=csrf)
        else:
            response = test_client.delete(url, headers=csrf)
        assert response.status_code == 200
        assert len(audit_store.rows) == before + 1


def test_audit_does_not_log_non_coach_requests(client: tuple[TestClient, CoachAuditStore]) -> None:
    test_client, audit_store = client
    response = test_client.post("/auth/login", json={"username": "athlete", "password": "athlete-pass"})
    assert response.status_code == 200

    denied = test_client.get("/athletes/athlete-2/dashboard")
    assert denied.status_code == 403
    assert audit_store.rows == []
