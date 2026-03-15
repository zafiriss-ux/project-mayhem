"""T5-11 auth layer tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from titan.api.auth import (
    ACCESS_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    AuthStore,
    create_access_token,
    hash_password,
)
from titan.api.main import create_app
from titan.api.models import AuthUser


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
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

    store = AuthStore()
    store.upsert_user(
        user_id="coach-1",
        username="coach",
        password_hash=hash_password("coach-pass"),
        role="COACH",
        athlete_id=None,
    )
    store.upsert_user(
        user_id="athlete-1",
        username="athlete",
        password_hash=hash_password("athlete-pass"),
        role="ATHLETE",
        athlete_id="athlete-1",
    )

    app = create_app(auth_store=store)
    return TestClient(app, base_url="https://testserver")


def test_happy_path_login_and_authenticated_access(client: TestClient) -> None:
    login = client.post("/auth/login", json={"username": "coach", "password": "coach-pass"})
    assert login.status_code == 200

    dashboard = client.get("/athletes/athlete-2/dashboard")
    assert dashboard.status_code == 200
    assert dashboard.json()["athlete_id"] == "athlete-2"


def test_token_expiry_rejects_expired_access_token(client: TestClient) -> None:
    user = AuthUser(id="athlete-1", username="athlete", role="ATHLETE", athlete_id="athlete-1")
    expired_token, _ = create_access_token(user, now=datetime.now(UTC) - timedelta(minutes=20))
    client.cookies.set(ACCESS_COOKIE_NAME, expired_token)

    response = client.get("/athletes/athlete-1/dashboard")
    assert response.status_code == 401


def test_role_violation_blocks_athlete_from_coach_endpoint(client: TestClient) -> None:
    login = client.post("/auth/login", json={"username": "athlete", "password": "athlete-pass"})
    assert login.status_code == 200

    response = client.post("/coach/notes", json={"text": "note"})
    assert response.status_code == 403


def test_isolation_violation_blocks_athlete_cross_access(client: TestClient) -> None:
    login = client.post("/auth/login", json={"username": "athlete", "password": "athlete-pass"})
    assert login.status_code == 200

    response = client.get("/athletes/athlete-2/dashboard")
    assert response.status_code == 403


def test_refresh_token_rotation_invalidates_old_token(client: TestClient) -> None:
    login = client.post("/auth/login", json={"username": "coach", "password": "coach-pass"})
    assert login.status_code == 200
    old_refresh = client.cookies.get(REFRESH_COOKIE_NAME)
    assert old_refresh is not None

    refreshed = client.post("/auth/refresh")
    assert refreshed.status_code == 200

    client.cookies.set(REFRESH_COOKIE_NAME, old_refresh)
    replay = client.post("/auth/refresh")
    assert replay.status_code == 401


def test_health_endpoint_remains_public(client: TestClient) -> None:
    client.cookies.clear()
    response = client.get("/health")
    assert response.status_code == 200


def test_non_health_endpoint_rejects_unauthenticated_access(client: TestClient) -> None:
    client.cookies.clear()
    response = client.get("/athletes/athlete-1/dashboard")
    assert response.status_code == 401
