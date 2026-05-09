"""C2/C3 audit middleware contract tests — Opus audit 2026-05-09."""

from __future__ import annotations

import os

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from titan.api.auth import AuthError, AuthStore, hash_password, validate_jwt_keys_at_startup
from titan.api.main import CSRF_HEADER_NAME, CoachAuditStore, create_app


def _make_rsa_keypair() -> tuple[str, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


def _csrf_headers(client: TestClient) -> dict[str, str]:
    r = client.get("/api/csrf-token")
    return {CSRF_HEADER_NAME: r.json()["csrf_token"]}


@pytest.fixture
def coach_client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, CoachAuditStore]:
    private_pem, public_pem = _make_rsa_keypair()
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
    audit_store = CoachAuditStore()
    app = create_app(auth_store=auth_store, audit_store=audit_store)
    return TestClient(app, base_url="https://testserver"), audit_store


def _login_coach(client: TestClient) -> None:
    r = client.post("/auth/login", json={"username": "coach", "password": "coach-pass"})
    assert r.status_code == 200


def test_authenticated_post_creates_audit_row(
    coach_client: tuple[TestClient, CoachAuditStore],
) -> None:
    client, audit_store = coach_client
    _login_coach(client)
    csrf = _csrf_headers(client)

    r = client.post("/coach/overrides?athlete_id=athlete-99", json={"reason": "test"}, headers=csrf)
    assert r.status_code == 200

    assert len(audit_store.rows) >= 1
    assert any(row.coach_id == "coach-1" for row in audit_store.rows)


def test_unauthenticated_request_no_audit_row(
    coach_client: tuple[TestClient, CoachAuditStore],
) -> None:
    client, audit_store = coach_client

    # No login — unauthenticated GET hits a coach-protected route
    r = client.get("/athletes/athlete-99/dashboard")
    assert r.status_code == 401

    assert audit_store.rows == []


def test_jwt_startup_validation_raises_without_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TITAN_JWT_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("TITAN_JWT_PUBLIC_KEY", raising=False)

    with pytest.raises(AuthError):
        validate_jwt_keys_at_startup()
